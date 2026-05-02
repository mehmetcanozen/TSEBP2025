package com.anonymous.mobiletest.suppression

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaRecorder
import android.os.Build
import android.os.Process
import android.util.Log
import java.io.File
import java.util.UUID
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicLong

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

class LiveSuppressionSession(
  context: Context,
  private val runtime: SuppressionRuntime,
  private val category: CategoryProfile,
  private val config: LiveConfig,
  private val recordFile: File? = null,
  private val onStatus: (StatusSnapshot) -> Unit,
  private val onMeter: (MeterSnapshot) -> Unit,
) : AutoCloseable {

  companion object {
    private const val TAG = "LiveSuppressionSession"
  }

  private val sessionId = UUID.randomUUID().toString()
  private val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
  private val running = AtomicBoolean(false)
  private val isClosing = AtomicBoolean(false)
  private val xruns = AtomicInteger(0)
  private val limiterHits = AtomicInteger(0)
  private val failOpenCount = AtomicInteger(0)
  private val boundaryRepairHits = AtomicInteger(0)

  private val capturedFrames = AtomicLong(0)
  private val renderedFrames = AtomicLong(0)
  private val runtimeSnapshot = runtime.runtimeInfo("")
  private val providerName = runtimeSnapshot.provider

  private val nativeSampleRate =
    audioManager.getProperty(AudioManager.PROPERTY_OUTPUT_SAMPLE_RATE)?.toIntOrNull() ?: 48_000
  private val nativeFramesPerBuffer =
    audioManager.getProperty(AudioManager.PROPERTY_OUTPUT_FRAMES_PER_BUFFER)?.toIntOrNull() ?: 256
  private val lookaheadMs = config.lookaheadMs.coerceIn(200, 1200)
  private val captureSource =
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
      MediaRecorder.AudioSource.UNPROCESSED
    } else {
      MediaRecorder.AudioSource.MIC
    }
  private val captureRing = FloatRingBuffer(nativeSampleRate * 15)
  private val renderRing = FloatRingBuffer(nativeSampleRate * 8)
  private val startupBlendMs =
    if (runtimeSnapshot.runtimeKind?.contains("streaming_target_extractor") == true) 220 else 900
  private val startupBlendFrames = (nativeSampleRate * startupBlendMs / 1000).toLong()
  private val processBoundaryFadeFrames = max(16, nativeSampleRate * 3 / 1000)
  private val renderBoundaryFadeFrames = max(16, nativeSampleRate * 5 / 1000)

  private var liveProcessor: LiveSuppressionProcessor? = null
  private var wavWriter: WavWriter? = null
  private var activeHopSamples = max(1, nativeSampleRate * config.hopMs / 1000)

  private var activeHopMs = config.hopMs.coerceIn(50, 1000)
  private var record: AudioRecord? = null
  private var track: AudioTrack? = null
  private var captureThread: Thread? = null
  private var processThread: Thread? = null
  private var renderThread: Thread? = null
  private var lastInputChunk = FloatArray(0)
  private var lastOutputChunk = FloatArray(0)
  @Volatile private var lastRawOutputPeak = 0.0
  @Volatile private var lastFinalOutputPeak = 0.0
  private var lastMeterAt = 0L
  private var hasProcessedOutput = false
  private var lastProcessedSample = 0f
  private var processedOutputFrames = 0L

  fun getSessionId(): String = sessionId

  fun start(): String {

    if (!running.compareAndSet(false, true)) {
      return sessionId
    }

    liveProcessor = runtime.createLiveProcessor(category, nativeSampleRate, config)
    wavWriter = recordFile?.let { WavWriter(it, nativeSampleRate) }
    activeHopSamples = liveProcessor?.preferredHopSamples()?.coerceAtLeast(1)

      ?: max(1, nativeSampleRate * config.hopMs / 1000)
    activeHopMs = max(1, (activeHopSamples * 1000.0 / nativeSampleRate.toDouble()).toInt())

    val blockFrames = max(nativeFramesPerBuffer, 256)
    val stableBufferBytes = max(blockFrames * 8, nativeSampleRate / 2) * 2
    val captureBytes = max(
      AudioRecord.getMinBufferSize(
        nativeSampleRate,
        AudioFormat.CHANNEL_IN_MONO,
        AudioFormat.ENCODING_PCM_16BIT
      ),
      stableBufferBytes
    )
    val renderBytes = max(
      AudioTrack.getMinBufferSize(
        nativeSampleRate,
        AudioFormat.CHANNEL_OUT_MONO,
        AudioFormat.ENCODING_PCM_16BIT
      ),
      stableBufferBytes
    )

    fun buildAudioRecord(source: Int): AudioRecord =
      AudioRecord.Builder()
        .setAudioSource(source)
        .setAudioFormat(
          AudioFormat.Builder()
            .setSampleRate(nativeSampleRate)
            .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
            .setChannelMask(AudioFormat.CHANNEL_IN_MONO)
            .build()
        )
        .setBufferSizeInBytes(captureBytes)
        .build()

    val trackBuilder = AudioTrack.Builder()
      .setAudioAttributes(
        AudioAttributes.Builder()
          .setUsage(AudioAttributes.USAGE_MEDIA)
          .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
          .build()
      )
      .setAudioFormat(
        AudioFormat.Builder()
          .setSampleRate(nativeSampleRate)
          .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
          .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
          .build()
      )
      .setTransferMode(AudioTrack.MODE_STREAM)
      .setBufferSizeInBytes(renderBytes)

    var actualCaptureSource = captureSource
    Log.d(TAG, "Initializing AudioRecord with sampleRate=$nativeSampleRate, source=$captureSource, bufferBytes=$captureBytes")
    record = try {
      buildAudioRecord(captureSource)
    } catch (error: Throwable) {
      if (captureSource == MediaRecorder.AudioSource.MIC) {
        throw error
      }
      Log.w(TAG, "AudioRecord source=$captureSource failed; falling back to MIC", error)
      actualCaptureSource = MediaRecorder.AudioSource.MIC
      buildAudioRecord(actualCaptureSource)
    }
    if (record?.state != AudioRecord.STATE_INITIALIZED && captureSource != MediaRecorder.AudioSource.MIC) {
      Log.w(TAG, "AudioRecord source=$captureSource was not initialized; falling back to MIC")
      record?.release()
      actualCaptureSource = MediaRecorder.AudioSource.MIC
      record = buildAudioRecord(actualCaptureSource)
    }
    Log.d(TAG, "Initializing AudioTrack with sampleRate=$nativeSampleRate, usage=MEDIA, bufferBytes=$renderBytes, lookaheadMs=$lookaheadMs")
    track = trackBuilder.build()

    if (record?.state != AudioRecord.STATE_INITIALIZED) {
        Log.e(TAG, "AudioRecord could not be initialized. State: ${record?.state}, source=$actualCaptureSource")
        throw IllegalStateException("AudioRecord could not be initialized")
    }
    if (track?.state != AudioTrack.STATE_INITIALIZED) {
        Log.e(TAG, "AudioTrack could not be initialized. State: ${track?.state}")
        throw IllegalStateException("AudioTrack could not be initialized")
    }

    audioManager.mode = AudioManager.MODE_NORMAL
    emitStatus("warming", "Opening live audio streams", null, 0.0)

    record?.startRecording()
    track?.play()
    prewarmOutput()

    captureThread = Thread({ captureLoop(blockFrames) }, "sns-capture")
    processThread = Thread({ processLoop(blockFrames) }, "sns-process")
    renderThread = Thread({ renderLoop(blockFrames) }, "sns-render")

    captureThread?.start()
    processThread?.start()
    renderThread?.start()

    emitStatus("running", "Live suppression active", null, 0.0)
    return sessionId
  }

  fun requestStop() {
    running.set(false)
  }

  fun stop() {
    if (!isClosing.compareAndSet(false, true)) {
      return
    }
    running.set(false)

    try {
      captureThread?.join(5000)
      processThread?.join()
      renderThread?.join(5000)
    } catch (error: InterruptedException) {
      Thread.currentThread().interrupt()
      Log.w(TAG, "Interrupted while stopping live session", error)
    } finally {
      try {
        if (record?.recordingState == AudioRecord.RECORDSTATE_RECORDING) {
          record?.stop()
        }
      } catch (error: Throwable) {
        Log.w(TAG, "AudioRecord stop failed during cleanup", error)
      }

      try {
        record?.release()
      } catch (error: Throwable) {
        Log.w(TAG, "AudioRecord release failed during cleanup", error)
      }

      try {
        track?.pause()
        track?.flush()
      } catch (error: Throwable) {
        Log.w(TAG, "AudioTrack pause/flush failed during cleanup", error)
      }

      try {
        track?.release()
      } catch (error: Throwable) {
        Log.w(TAG, "AudioTrack release failed during cleanup", error)
      }

      try {
        liveProcessor?.close()
      } catch (error: Throwable) {
        Log.w(TAG, "Live processor close failed during cleanup", error)
      }

      try {
        wavWriter?.close()
      } catch (error: Throwable) {
        Log.e(TAG, "WAV writer close failed during cleanup", error)
      }

      liveProcessor = null
      wavWriter = null
      record = null
      track = null
      audioManager.mode = AudioManager.MODE_NORMAL
      emitStatus("stopped", "Live suppression stopped", null, 0.0)
    }
  }

  override fun close() {
    stop()
  }

  private fun captureLoop(blockFrames: Int) {
    Process.setThreadPriority(Process.THREAD_PRIORITY_AUDIO)
    val recorder = record ?: return
    val pcm = ShortArray(blockFrames)
    val mono = FloatArray(blockFrames)

    while (running.get()) {
      val read = recorder.read(pcm, 0, pcm.size, AudioRecord.READ_BLOCKING)
      if (read <= 0) {
        continue
      }
      for (index in 0 until read) {
        mono[index] = (pcm[index] / 32768.0f).coerceIn(-1f, 1f)
      }
      val chunk = mono.copyOf(read)
      lastInputChunk = chunk
      val written = captureRing.write(chunk, read)
      if (written < read) {
        xruns.incrementAndGet()
      }
      capturedFrames.addAndGet(read.toLong())
    }
  }

  private fun processLoop(blockFrames: Int) {
    Process.setThreadPriority(Process.THREAD_PRIORITY_AUDIO)
    val processor = liveProcessor ?: return
    val scratch = FloatArray(max(blockFrames * 2, activeHopSamples))
    val pending = ArrayList<Float>(activeHopSamples * 4)

    while (running.get() || captureRing.availableToRead() > 0 || pending.size >= activeHopSamples) {

      val read = captureRing.read(scratch, scratch.size)
      if (read > 0) {
        for (index in 0 until read) {
          pending.add(scratch[index])
        }
      }

      if (read <= 0 && !running.get()) {
        if (pending.size < activeHopSamples) break
      }

      while (pending.size >= activeHopSamples) {
        val inputChunk = FloatArray(activeHopSamples)


        for (index in 0 until activeHopSamples) {
          inputChunk[index] = pending[index]
        }
        pending.subList(0, activeHopSamples).clear()
        lastInputChunk = inputChunk


        val started = System.nanoTime()
        val rawChunk = processor.processChunk(inputChunk)
        lastRawOutputPeak = finitePeak(rawChunk)
        val cleanChunk = stabilizeOutputChunk(inputChunk, rawChunk)
        val inferenceMs = (System.nanoTime() - started) / 1_000_000.0
        lastOutputChunk = cleanChunk
        lastFinalOutputPeak = finitePeak(cleanChunk)

        val written = renderRing.write(cleanChunk, cleanChunk.size)
        wavWriter?.write(cleanChunk, cleanChunk.size)
        if (written < cleanChunk.size) {

          xruns.incrementAndGet()
        }

        val queueDepthMs =
          renderRing.availableToRead().toDouble() / nativeSampleRate.toDouble() * 1000.0
        val currentState = if (running.get()) "running" else "stopping"
        val currentMsg = if (running.get()) "Live suppression active" else "Finishing recording..."
        emitStatus(currentState, currentMsg, inferenceMs, queueDepthMs)
      }

      maybeEmitMeter()
      if (read <= 0) {
        Thread.sleep(5)
      }
    }
  }

  private fun stabilizeOutputChunk(inputChunk: FloatArray, rawChunk: FloatArray): FloatArray {
    if (inputChunk.isEmpty() || rawChunk.isEmpty()) {
      return FloatArray(0)
    }

    val output = when {
      rawChunk.size == inputChunk.size -> rawChunk.copyOf()
      rawChunk.size > inputChunk.size -> rawChunk.copyOf(inputChunk.size)
      else -> rawChunk.copyOf(inputChunk.size)
    }

    for (index in output.indices) {
      val sample = output[index]
      output[index] = if (sample.isNaN() || sample.isInfinite()) 0f else sample
    }

    val inStartupBlend = processedOutputFrames < startupBlendFrames
    if (inStartupBlend) {
      applyStartupBlend(inputChunk, output)
    }

    val inputPeak = peak(inputChunk).toFloat()
    var outputPeak = peak(output).toFloat()
    if (outputPeak < 1.0e-4f && inputPeak > 1.0e-3f) {
      failOpenCount.incrementAndGet()
      for (index in output.indices) {
        output[index] = if (index < inputChunk.size) inputChunk[index] else 0f
      }
      outputPeak = peak(output).toFloat()
    }

    val peakCeiling = if (inputPeak > 1.0e-3f) {
      min(0.98f, max(0.08f, inputPeak * 2.5f + 0.02f))
    } else {
      0.08f
    }
    if (outputPeak > peakCeiling) {
      limiterHits.incrementAndGet()
      val gain = peakCeiling / outputPeak
      for (index in output.indices) {
        output[index] *= gain
      }
    }

    if (hasProcessedOutput && !inStartupBlend) {
      val repaired = applyStartCorrection(
        samples = output,
        validLength = output.size,
        previousSample = lastProcessedSample,
        maxFrames = processBoundaryFadeFrames,
        threshold = 0.18f,
        maxCorrection = 0.12f,
      )
      if (repaired) {
        boundaryRepairHits.incrementAndGet()
      }
    }

    for (index in output.indices) {
      output[index] = output[index].coerceIn(-0.98f, 0.98f)
    }

    lastProcessedSample = output.last()
    hasProcessedOutput = true
    processedOutputFrames += output.size.toLong()
    return output
  }

  private fun renderLoop(blockFrames: Int) {
    Process.setThreadPriority(Process.THREAD_PRIORITY_AUDIO)
    val audioTrack = track ?: return
    val prebufferFrames = nativeSampleRate * lookaheadMs / 1000
    val block = FloatArray(blockFrames)
    val pcm = ShortArray(blockFrames)
    var startedPlayback = false
    var lastSample = 0f
    var needsBoundaryRepair = false

    while (running.get() || renderRing.availableToRead() > 0) {
      val available = renderRing.availableToRead()
      if (!startedPlayback) {
        if (available < prebufferFrames && running.get()) {
          Thread.sleep(5)
          continue
        }
        startedPlayback = true
      }

      if (available < blockFrames) {
        if (running.get()) {
          xruns.incrementAndGet()
          fillFallbackBlock(block, lastSample)
          writeRenderBlock(audioTrack, block, pcm)
          lastSample = block[block.size - 1]
          needsBoundaryRepair = true
          continue
        }
        if (available <= 0) {
          break
        }
      }

      val read = renderRing.read(block, block.size)
      if (read <= 0) {
        Thread.sleep(5)
        continue
      }

      if (read < block.size) {
        xruns.incrementAndGet()
        val missing = block.size - read
        for (index in read until block.size) {
          val fade = 1f - ((index - read + 1).toFloat() / (missing + 1).toFloat())
          block[index] = lastSample * fade
        }
        needsBoundaryRepair = true
      } else if (needsBoundaryRepair) {
        val repaired = applyStartCorrection(
          samples = block,
          validLength = block.size,
          previousSample = lastSample,
          maxFrames = renderBoundaryFadeFrames,
          threshold = 0.08f,
          maxCorrection = 0.35f,
        )
        if (repaired) {
          boundaryRepairHits.incrementAndGet()
        }
        needsBoundaryRepair = false
      }
      writeRenderBlock(audioTrack, block, pcm)
      lastSample = block[block.size - 1]
    }
  }

  private fun fillFallbackBlock(block: FloatArray, previousSample: Float) {
    for (index in block.indices) {
      val fade = 1f - ((index + 1).toFloat() / block.size.toFloat())
      block[index] = (previousSample * fade).coerceIn(-0.98f, 0.98f)
    }
  }

  private fun writeRenderBlock(audioTrack: AudioTrack, block: FloatArray, pcm: ShortArray) {
    for (index in block.indices) {
      val sample = block[index].coerceIn(-0.98f, 0.98f)
      pcm[index] = (sample * 32767f).toInt().toShort()
    }
    val written = audioTrack.write(pcm, 0, pcm.size, AudioTrack.WRITE_BLOCKING)
    if (written > 0) {
      renderedFrames.addAndGet(written.toLong())
    }
    if (written < pcm.size) {
      xruns.incrementAndGet()
    }
  }

  private fun applyStartupBlend(inputChunk: FloatArray, output: FloatArray) {
    if (startupBlendFrames <= 0L) {
      return
    }

    for (index in output.indices) {
      val absoluteFrame = processedOutputFrames + index.toLong()
      if (absoluteFrame >= startupBlendFrames) {
        break
      }
      val dry = if (index < inputChunk.size) inputChunk[index] else 0f
      val wet = output[index]
      val wetMix = (absoluteFrame.toFloat() / startupBlendFrames.toFloat()).coerceIn(0f, 1f)
      output[index] = dry * (1f - wetMix) + wet * wetMix
    }
  }

  private fun applyStartCorrection(
    samples: FloatArray,
    validLength: Int,
    previousSample: Float,
    maxFrames: Int,
    threshold: Float,
    maxCorrection: Float,
  ): Boolean {
    if (validLength <= 0 || maxFrames <= 0) {
      return false
    }
    val correction = (previousSample - samples[0]).coerceIn(-maxCorrection, maxCorrection)
    if (abs(correction) <= threshold) {
      return false
    }
    val frames = min(validLength, maxFrames)
    for (index in 0 until frames) {
      val fade = 1f - (index.toFloat() / frames.toFloat())
      samples[index] = (samples[index] + correction * fade).coerceIn(-0.98f, 0.98f)
    }
    return true
  }

  private fun finitePeak(samples: FloatArray): Double {
    var value = 0.0
    for (sample in samples) {
      if (sample.isNaN() || sample.isInfinite()) {
        continue
      }
      value = max(value, abs(sample.toDouble()))
    }
    return value
  }

  private fun prewarmOutput() {
    val silenceFrames = nativeSampleRate * lookaheadMs / 1000
    val silence = ShortArray(max(silenceFrames, nativeFramesPerBuffer))
    track?.write(silence, 0, silence.size, AudioTrack.WRITE_BLOCKING)
  }

  private fun maybeEmitMeter() {
    val now = System.currentTimeMillis()
    if (now - lastMeterAt < 125) {
      return
    }
    lastMeterAt = now
    onMeter(
      MeterSnapshot(
        sessionId = sessionId,
        rmsIn = rms(lastInputChunk),
        rmsOut = rms(lastOutputChunk),
        peakIn = peak(lastInputChunk),
        peakOut = peak(lastOutputChunk),
        rawOutPeak = lastRawOutputPeak,
        finalOutPeak = lastFinalOutputPeak,
        capturedFrames = capturedFrames.get(),
        renderedFrames = renderedFrames.get(),
        timestampMs = now,
      )
    )
  }

  private fun emitStatus(
    state: String,
    message: String,
    inferenceMs: Double?,
    queueDepthMs: Double,
  ) {
    val nativeUnderruns =
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
        track?.underrunCount ?: 0
      } else {
        0
      }
    val processorDiagnostics = liveProcessor?.diagnostics() ?: ProcessorDiagnostics()
    onStatus(
      StatusSnapshot(
        sessionId = sessionId,
        state = state,
        provider = providerName,
        inferenceMs = inferenceMs,
        queueDepthMs = queueDepthMs,
        xruns = xruns.get() + nativeUnderruns,
        audioTrackUnderruns = nativeUnderruns,
        limiterHits = limiterHits.get(),
        failOpenCount = failOpenCount.get(),
        boundaryRepairHits = boundaryRepairHits.get(),
        startupBlendMs = startupBlendMs,
        waveformerPostFilter = processorDiagnostics.waveformerPostFilter,
        wienerBypassed = processorDiagnostics.wienerBypassed,
        hopMs = activeHopMs,
        lookaheadMs = lookaheadMs,
        sampleRate = nativeSampleRate,
        message = message,
      )
    )
  }
}
