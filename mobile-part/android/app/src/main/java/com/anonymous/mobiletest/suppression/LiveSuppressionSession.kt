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

import kotlin.math.max

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

  private val capturedFrames = AtomicLong(0)
  private val renderedFrames = AtomicLong(0)
  private val providerName = runtime.runtimeInfo("").provider

  private val nativeSampleRate =
    audioManager.getProperty(AudioManager.PROPERTY_OUTPUT_SAMPLE_RATE)?.toIntOrNull() ?: 48_000
  private val nativeFramesPerBuffer =
    audioManager.getProperty(AudioManager.PROPERTY_OUTPUT_FRAMES_PER_BUFFER)?.toIntOrNull() ?: 256
  private val lookaheadMs = config.lookaheadMs.coerceIn(100, 1000)
  private val captureRing = FloatRingBuffer(nativeSampleRate * 15)
  private val renderRing = FloatRingBuffer(nativeSampleRate * 8)

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
  private var lastMeterAt = 0L

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
    val captureBytes = max(
      AudioRecord.getMinBufferSize(
        nativeSampleRate,
        AudioFormat.CHANNEL_IN_MONO,
        AudioFormat.ENCODING_PCM_16BIT
      ),
      blockFrames * 4
    )
    val renderBytes = max(
      AudioTrack.getMinBufferSize(
        nativeSampleRate,
        AudioFormat.CHANNEL_OUT_MONO,
        AudioFormat.ENCODING_PCM_16BIT
      ),
      blockFrames * 4
    )

    val recordBuilder = AudioRecord.Builder()
      .setAudioSource(MediaRecorder.AudioSource.VOICE_RECOGNITION)
      .setAudioFormat(
        AudioFormat.Builder()
          .setSampleRate(nativeSampleRate)
          .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
          .setChannelMask(AudioFormat.CHANNEL_IN_MONO)
          .build()
      )
      .setBufferSizeInBytes(captureBytes)

    val trackBuilder = AudioTrack.Builder()
      .setAudioAttributes(
        AudioAttributes.Builder()
          .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
          .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
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
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
      trackBuilder.setPerformanceMode(AudioTrack.PERFORMANCE_MODE_LOW_LATENCY)
    }

    Log.d(TAG, "Initializing AudioRecord with sampleRate=$nativeSampleRate, source=VOICE_RECOGNITION")
    record = recordBuilder.build()
    Log.d(TAG, "Initializing AudioTrack with sampleRate=$nativeSampleRate, usage=VOICE_COMMUNICATION")
    track = trackBuilder.build()

    if (record?.state != AudioRecord.STATE_INITIALIZED) {
        Log.e(TAG, "AudioRecord could not be initialized. State: ${record?.state}")
        throw IllegalStateException("AudioRecord could not be initialized")
    }
    if (track?.state != AudioTrack.STATE_INITIALIZED) {
        Log.e(TAG, "AudioTrack could not be initialized. State: ${track?.state}")
        throw IllegalStateException("AudioTrack could not be initialized")
    }

    audioManager.mode = AudioManager.MODE_IN_COMMUNICATION
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

    captureThread?.join(5000)
    processThread?.join(60000) // Give AI plenty of time to drain queue (up to 60s for slow devices)
    renderThread?.join(5000)


    record?.stop()
    record?.release()
    track?.pause()
    track?.flush()
    track?.release()
    liveProcessor?.close()
    wavWriter?.close()
    liveProcessor = null
    wavWriter = null


    record = null
    track = null
    audioManager.mode = AudioManager.MODE_NORMAL
    emitStatus("stopped", "Live suppression stopped", null, 0.0)
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
        val cleanChunk = processor.processChunk(inputChunk)
        val inferenceMs = (System.nanoTime() - started) / 1_000_000.0
        lastOutputChunk = cleanChunk

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

  private fun renderLoop(blockFrames: Int) {
    Process.setThreadPriority(Process.THREAD_PRIORITY_AUDIO)
    val audioTrack = track ?: return
    val prebufferFrames = nativeSampleRate * lookaheadMs / 1000
    val zeros = ShortArray(blockFrames)
    val block = FloatArray(blockFrames)
    val pcm = ShortArray(blockFrames)

    while (running.get()) {
      if (renderRing.availableToRead() < prebufferFrames) {
        audioTrack.write(zeros, 0, zeros.size, AudioTrack.WRITE_BLOCKING)
        renderedFrames.addAndGet(zeros.size.toLong())
        continue
      }

      val read = renderRing.read(block, block.size)
      if (read < block.size) {
        xruns.incrementAndGet()
        for (index in read until block.size) {
          block[index] = 0f
        }
      }
      for (index in block.indices) {
        val sample = block[index].coerceIn(-1f, 1f)
        pcm[index] = (sample * 32767f).toInt().toShort()
      }
      audioTrack.write(pcm, 0, pcm.size, AudioTrack.WRITE_BLOCKING)
      renderedFrames.addAndGet(pcm.size.toLong())
    }
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
    onStatus(
      StatusSnapshot(
        sessionId = sessionId,
        state = state,
        provider = providerName,
        inferenceMs = inferenceMs,
        queueDepthMs = queueDepthMs,
        xruns = xruns.get(),
        hopMs = activeHopMs,
        lookaheadMs = lookaheadMs,
        sampleRate = nativeSampleRate,
        message = message,
      )
    )
  }
}
