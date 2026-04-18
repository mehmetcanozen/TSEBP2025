package com.anonymous.mobiletest.suppression

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import java.io.File
import java.nio.FloatBuffer
import java.nio.LongBuffer
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt
import org.pytorch.executorch.EValue
import org.pytorch.executorch.Module
import org.pytorch.executorch.Tensor

fun createSuppressionRuntime(
  manifest: ModelBundleManifest,
  modelFile: File,
): SuppressionRuntime {
  return when (manifest.runtimeKind) {
    "onnx_category_separator" -> AudioSepOnnxRuntime(manifest, modelFile)
    "executorch_streaming_target_extractor" -> WaveformerExecuTorchRuntime(manifest, modelFile)
    else -> throw IllegalArgumentException("Unsupported runtime kind: ${manifest.runtimeKind}")
  }
}

private class AudioSepOnnxRuntime(
  private val manifest: ModelBundleManifest,
  private val modelFile: File,
) : SuppressionRuntime {
  private val environment = OrtEnvironment.getEnvironment()
  private val sessionOptions = OrtSession.SessionOptions()
  private val session: OrtSession
  private val lock = Any()
  private val categoryOrder = manifest.categories.map { it.id }
  private val segmentSamples =
    max(1, (manifest.sampleRate * (manifest.segmentSeconds ?: 5.0)).toInt())
  private val overlapSamples =
    ((manifest.sampleRate * (manifest.overlapSeconds ?: 1.0)).roundToInt()).coerceAtLeast(0)

  init {
    sessionOptions.setOptimizationLevel(OrtSession.SessionOptions.OptLevel.ALL_OPT)
    sessionOptions.setIntraOpNumThreads(2)
    session = environment.createSession(modelFile.absolutePath, sessionOptions)
    warmup()
  }

  override fun runtimeInfo(bundlePath: String): RuntimeInfo {
    return RuntimeInfo(
      provider = "cpu",
      warmed = true,
      modelId = manifest.modelId,
      modelFamily = manifest.modelFamily,
      displayName = manifest.displayName,
      runtimeKind = manifest.runtimeKind,
      modelVersion = manifest.version,
      modelPath = modelFile.absolutePath,
      bundlePath = bundlePath,
      sampleRate = manifest.sampleRate,
      categoryCount = manifest.categories.size,
      availableProviders = listOf("cpu"),
    )
  }

  override fun categories(): List<CategoryProfile> = manifest.categories

  override fun createLiveProcessor(
    category: CategoryProfile,
    nativeSampleRate: Int,
    config: LiveConfig,
  ): LiveSuppressionProcessor {
    return AudioSepLiveProcessor(
      runtime = this,
      category = category,
      nativeSampleRate = nativeSampleRate,
      config = config,
    )
  }

  override fun close() {
    session.close()
  }

  private fun warmup() {
    runWindow(FloatArray(segmentSamples), 0)
  }

  private fun separateCategory(audio: FloatArray, categoryId: String): FloatArray {
    val categoryIndex = categoryOrder.indexOf(categoryId)
    require(categoryIndex >= 0) { "Unknown model category: $categoryId" }

    if (audio.size <= segmentSamples) {
      return runWindow(audio, categoryIndex)
    }

    val step = max(1, segmentSamples - overlapSamples)
    val separated = FloatArray(audio.size)
    val weights = FloatArray(audio.size)
    var start = 0

    while (true) {
      val end = min(start + segmentSamples, audio.size)
      val chunk = audio.copyOfRange(start, end)
      val window = buildOverlapWindow(
        length = chunk.size,
        overlapSamples = min(overlapSamples, chunk.size),
        fadeIn = start > 0,
        fadeOut = end < audio.size,
      )
      val chunkOutput = runWindow(chunk, categoryIndex)
      for (index in chunkOutput.indices) {
        separated[start + index] += chunkOutput[index] * window[index]
        weights[start + index] += window[index]
      }
      if (end >= audio.size) {
        break
      }
      start += step
    }

    for (index in separated.indices) {
      if (weights[index] > 1.0e-8f) {
        separated[index] /= weights[index]
      }
    }
    return separated
  }

  private fun runWindow(chunk: FloatArray, categoryIndex: Int): FloatArray {
    val validLength = min(chunk.size, segmentSamples)
    val padded = FloatArray(segmentSamples)
    for (index in 0 until validLength) {
      padded[index] = chunk[index]
    }

    val mixture = OnnxTensor.createTensor(
      environment,
      FloatBuffer.wrap(padded),
      longArrayOf(1, 1, segmentSamples.toLong()),
    )
    val category = OnnxTensor.createTensor(
      environment,
      LongBuffer.wrap(longArrayOf(categoryIndex.toLong())),
      longArrayOf(1),
    )

    var separated = FloatArray(validLength)
    mixture.use { mixTensor ->
      category.use { categoryTensor ->
        synchronized(lock) {
          session.run(
            mapOf(
              "mixture" to mixTensor,
              "category_idx" to categoryTensor,
            )
          ).use { result ->
            @Suppress("UNCHECKED_CAST")
            val output = (result[0].value as Array<Array<FloatArray>>)[0][0]
            separated = output.copyOf(validLength)
          }
        }
      }
    }
    return separated
  }

  private class AudioSepLiveProcessor(
    private val runtime: AudioSepOnnxRuntime,
    private val category: CategoryProfile,
    private val nativeSampleRate: Int,
    private val config: LiveConfig,
  ) : LiveSuppressionProcessor {
    private val contextSamples =
      max(1, (nativeSampleRate * (runtime.manifest.segmentSeconds ?: 5.0)).toInt())
    private val preferredHopSamples =
      max(1, nativeSampleRate * runtime.manifest.preferredLiveHopMs.orDefault(config.hopMs) / 1000)
    private val rollingInput = RollingWindow(contextSamples + nativeSampleRate * 2)
    private val masker = WienerMasker()

    override fun preferredHopSamples(): Int = preferredHopSamples

    override fun processChunk(chunk: FloatArray): FloatArray {
      if (chunk.isEmpty()) {
        return FloatArray(0)
      }

      rollingInput.append(chunk, chunk.size)
      val context = rollingInput.latestPadded(contextSamples)
      val peakValue = max(peak(context).toFloat(), 1f)
      val normalized = FloatArray(context.size) { index ->
        (context[index] / peakValue).coerceIn(-1f, 1f)
      }
      val resampled = linearResample(normalized, nativeSampleRate, runtime.manifest.sampleRate)
      val unwantedResampled = runtime.separateCategory(resampled, category.id)
      var unwanted = linearResample(unwantedResampled, runtime.manifest.sampleRate, nativeSampleRate)
      if (unwanted.size != context.size) {
        unwanted = unwanted.copyOf(context.size)
      }

      val separationRatio = (rms(unwanted) / max(rms(context), 1.0e-8)).toFloat()
      if (separationRatio in 1.0e-6f..0.18f) {
        val scale = min(0.18f / separationRatio, 1.15f)
        for (index in unwanted.indices) {
          unwanted[index] *= scale
        }
      }

      val effectiveAggressiveness =
        max(config.aggressiveness, category.defaultAggressiveness)
      val nFft = if (category.transient) 1024 else 2048
      val ddAlpha = if (category.transient) 0.92f else 0.98f
      val clean = masker.apply(
        mix = context,
        unwanted = unwanted,
        sampleRate = nativeSampleRate,
        nFft = nFft,
        options = MaskingOptions(
          aggressiveness = effectiveAggressiveness,
          ddAlpha = ddAlpha,
          maskFloor = 0.07f,
          maxSuppressionRatio = 0.82f,
          speechDominanceThreshold = 2.5f,
        )
      )
      val keep = min(chunk.size, clean.size)
      return clean.copyOfRange(clean.size - keep, clean.size)
    }

    override fun close() = Unit
  }
}

private class WaveformerExecuTorchRuntime(
  private val manifest: ModelBundleManifest,
  private val modelFile: File,
) : SuppressionRuntime {
  private val module = Module.load(modelFile.absolutePath)
  private val categoryOrder = manifest.categories.map { it.id }
  private val chunkSamples =
    manifest.chunkSamples ?: error("Waveformer manifest is missing chunkSamples")
  private val mixChannels = max(1, manifest.mixChannels)
  private val encShape =
    manifest.stateTensors["enc_buf"] ?: error("Waveformer manifest is missing enc_buf shape")
  private val decShape =
    manifest.stateTensors["dec_buf"] ?: error("Waveformer manifest is missing dec_buf shape")
  private val outShape =
    manifest.stateTensors["out_buf"] ?: error("Waveformer manifest is missing out_buf shape")

  override fun runtimeInfo(bundlePath: String): RuntimeInfo {
    return RuntimeInfo(
      provider = "executorch",
      warmed = true,
      modelId = manifest.modelId,
      modelFamily = manifest.modelFamily,
      displayName = manifest.displayName,
      runtimeKind = manifest.runtimeKind,
      modelVersion = manifest.version,
      modelPath = modelFile.absolutePath,
      bundlePath = bundlePath,
      sampleRate = manifest.sampleRate,
      categoryCount = manifest.categories.size,
      availableProviders = listOf("executorch"),
    )
  }

  override fun categories(): List<CategoryProfile> = manifest.categories

  override fun createLiveProcessor(
    category: CategoryProfile,
    nativeSampleRate: Int,
    config: LiveConfig,
  ): LiveSuppressionProcessor {
    return WaveformerLiveProcessor(
      runtime = this,
      category = category,
      nativeSampleRate = nativeSampleRate,
      config = config,
    )
  }

  override fun close() {
    module.destroy()
  }

  private fun categoryIndex(categoryId: String): Int {
    val index = categoryOrder.indexOf(categoryId)
    require(index >= 0) { "Unknown model category: $categoryId" }
    return index
  }

  private fun runCategoryChunk(
    chunk: FloatArray,
    categoryId: String,
    state: WaveformerState,
  ): FloatArray {
    val preparedChunk = when {
      chunk.size == chunkSamples -> chunk
      chunk.size < chunkSamples -> FloatArray(chunkSamples).also { padded ->
        chunk.copyInto(padded, endIndex = chunk.size)
      }
      else -> chunk.copyOf(chunkSamples)
    }

    val stereo = FloatArray(mixChannels * chunkSamples)
    for (channel in 0 until mixChannels) {
      val offset = channel * chunkSamples
      preparedChunk.copyInto(stereo, destinationOffset = offset)
    }

    val labelVector = FloatArray(categoryOrder.size)
    labelVector[categoryIndex(categoryId)] = 1f

    val outputs = module.forward(
      EValue.from(Tensor.fromBlob(stereo, longArrayOf(1, mixChannels.toLong(), chunkSamples.toLong()))),
      EValue.from(Tensor.fromBlob(labelVector, longArrayOf(1, categoryOrder.size.toLong()))),
      EValue.from(Tensor.fromBlob(state.encBuf, encShape.toLongArray())),
      EValue.from(Tensor.fromBlob(state.decBuf, decShape.toLongArray())),
      EValue.from(Tensor.fromBlob(state.outBuf, outShape.toLongArray())),
    )

    val target = outputs[0].toTensor().dataAsFloatArray
    state.encBuf = outputs[1].toTensor().dataAsFloatArray
    state.decBuf = outputs[2].toTensor().dataAsFloatArray
    state.outBuf = outputs[3].toTensor().dataAsFloatArray

    val monoTarget = FloatArray(chunk.size)
    for (index in monoTarget.indices) {
      var sum = 0f
      for (channel in 0 until mixChannels) {
        sum += target[channel * chunkSamples + index]
      }
      monoTarget[index] = sum / mixChannels.toFloat()
    }
    return monoTarget
  }

  private class WaveformerLiveProcessor(
    private val runtime: WaveformerExecuTorchRuntime,
    private val category: CategoryProfile,
    private val nativeSampleRate: Int,
    private val config: LiveConfig,
  ) : LiveSuppressionProcessor {
    private val preferredHopSamples =
      max(
        1,
        (nativeSampleRate.toDouble() * runtime.chunkSamples.toDouble() / runtime.manifest.sampleRate.toDouble())
          .roundToInt()
      )
    private val state = WaveformerState(
      encBuf = FloatArray(runtime.encShape.product()),
      decBuf = FloatArray(runtime.decShape.product()),
      outBuf = FloatArray(runtime.outShape.product()),
    )

    override fun preferredHopSamples(): Int = preferredHopSamples

    override fun processChunk(chunk: FloatArray): FloatArray {
      if (chunk.isEmpty()) {
        return FloatArray(0)
      }

      val clipped = FloatArray(chunk.size) { index -> chunk[index].coerceIn(-1f, 1f) }
      var resampled = linearResample(clipped, nativeSampleRate, runtime.manifest.sampleRate)
      if (resampled.size != runtime.chunkSamples) {
        resampled = when {
          resampled.size < runtime.chunkSamples -> FloatArray(runtime.chunkSamples).also { padded ->
            resampled.copyInto(padded, endIndex = resampled.size)
          }
          else -> resampled.copyOf(runtime.chunkSamples)
        }
      }

      val target = runtime.runCategoryChunk(resampled, category.id, state)
      val scale = max(config.aggressiveness, category.defaultAggressiveness).coerceIn(0.5f, 2.0f)
      val cleanResampled = FloatArray(target.size) { index ->
        (resampled[index] - scale * target[index]).coerceIn(-1f, 1f)
      }
      val clean = linearResample(cleanResampled, runtime.manifest.sampleRate, nativeSampleRate)
      return if (clean.size == chunk.size) {
        clean
      } else {
        clean.copyOf(chunk.size)
      }
    }

    override fun close() = Unit
  }

  private data class WaveformerState(
    var encBuf: FloatArray,
    var decBuf: FloatArray,
    var outBuf: FloatArray,
  )
}

private fun Int?.orDefault(defaultValue: Int): Int = this ?: defaultValue

private fun List<Int>.product(): Int =
  fold(1) { total, value -> total * max(1, value) }

private fun List<Int>.toLongArray(): LongArray =
  LongArray(size) { index -> this[index].toLong() }
