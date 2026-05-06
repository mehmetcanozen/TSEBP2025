package com.anonymous.mobiletest.suppression

import android.content.Context
import android.content.res.AssetManager
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream

class BundleRuntimeStore(private val context: Context) : AutoCloseable {
  companion object {
    private const val ASSET_BUNDLE_ROOT = "suppression-model-bundle"
  }

  private val baseDir = File(context.filesDir, "semantic-noise-suppression")
  private val bundleRoot = File(baseDir, "bundles")

  @Volatile
  private var runtime: SuppressionRuntime? = null
  @Volatile
  private var bundleDir: File? = null
  @Volatile
  private var manifest: ModelBundleManifest? = null

  fun prepare(options: PrepareOptions): RuntimeInfo {
    baseDir.mkdirs()
    bundleRoot.mkdirs()

    val resolvedBundle = installBundledBundleIfPresent(options.reinstallBundled)

    require(resolvedBundle != null && resolvedBundle.exists()) {
      "No bundled on-device suppression model is available in the Android app assets."
    }

    val loadedManifest = parseManifest(File(resolvedBundle, "manifest.json"))

    if (runtime != null && manifest?.version != loadedManifest.version) {
      runtime?.close()
      runtime = null
    }

    val selectedModel = chooseModelFile(resolvedBundle, loadedManifest)
    val activeRuntime = runtime ?: createSuppressionRuntime(loadedManifest, selectedModel).also {
      runtime = it
    }

    bundleDir = resolvedBundle
    manifest = loadedManifest
    return withAudioRuntimeInfo(activeRuntime.runtimeInfo(resolvedBundle.absolutePath))
  }

  fun runtimeInfo(): RuntimeInfo {
    val activeRuntime = runtime
    val loadedManifest = manifest
    return if (activeRuntime != null && loadedManifest != null && bundleDir != null) {
      withAudioRuntimeInfo(activeRuntime.runtimeInfo(bundleDir!!.absolutePath))
    } else {
      RuntimeInfo(
        provider = "cpu",
        warmed = false,
        modelId = null,
        modelFamily = null,
        displayName = null,
        runtimeKind = null,
        modelVersion = null,
        modelPath = null,
        bundlePath = null,
        sampleRate = 32_000,
        categoryCount = 0,
        availableProviders = listOf("cpu"),
        audioEngine = "auto",
        nativeOboeAvailable = NativeOboeAudioEngine.isAvailable(),
      )
    }
  }

  fun categories(): List<CategoryProfile> = manifest?.categories ?: emptyList()

  fun suppressionRuntime(): SuppressionRuntime {
    return runtime ?: throw IllegalStateException("Suppression model is not prepared")
  }

  override fun close() {
    runtime?.close()
    runtime = null
  }

  private fun withAudioRuntimeInfo(info: RuntimeInfo): RuntimeInfo =
    info.copy(
      audioEngine = "auto",
      nativeOboeAvailable = NativeOboeAudioEngine.isAvailable(),
    )

  private fun installBundledBundleIfPresent(reinstallBundled: Boolean): File? {
    val assetManifestPath = "$ASSET_BUNDLE_ROOT/manifest.json"
    val assetManager = context.assets
    val bundledManifestJson = try {
      assetManager.open(assetManifestPath).bufferedReader(Charsets.UTF_8).use { it.readText() }
    } catch (_: Exception) {
      return null
    }

    val bundledManifest = parseManifest(JSONObject(bundledManifestJson))
    val outputDir = File(bundleRoot, bundledManifest.version)
    val manifestFile = File(outputDir, "manifest.json")
    val manifestMatches = manifestFile.exists() &&
      manifestFile.readText(Charsets.UTF_8) == bundledManifestJson
    val artifactsPresent = bundledManifest.artifacts.all { artifact ->
      File(outputDir, artifact.filename).exists()
    }

    if (outputDir.exists() && !reinstallBundled && manifestMatches && artifactsPresent) {
      return outputDir
    }

    if (outputDir.exists()) {
      outputDir.deleteRecursively()
    }
    copyAssetDirectory(assetManager, ASSET_BUNDLE_ROOT, outputDir)
    return outputDir
  }

  private fun copyAssetDirectory(assetManager: AssetManager, assetPath: String, outputDir: File) {
    val children = assetManager.list(assetPath).orEmpty()
    if (children.isEmpty()) {
      val outputFile = outputDir
      outputFile.parentFile?.mkdirs()
      assetManager.open(assetPath).use { input ->
        FileOutputStream(outputFile).use { output -> input.copyTo(output) }
      }
      return
    }

    outputDir.mkdirs()

    for (child in children) {
      val childAssetPath = "$assetPath/$child"
      val target = File(outputDir, child)
      val grandChildren = assetManager.list(childAssetPath).orEmpty()
      if (grandChildren.isEmpty()) {
        target.parentFile?.mkdirs()
        assetManager.open(childAssetPath).use { input ->
          FileOutputStream(target).use { output -> input.copyTo(output) }
        }
      } else {
        copyAssetDirectory(assetManager, childAssetPath, target)
      }
    }
  }

  private fun parseManifest(file: File): ModelBundleManifest {
    return parseManifest(JSONObject(file.readText(Charsets.UTF_8)))
  }

  private fun parseManifest(json: JSONObject): ModelBundleManifest {
    val categoriesJson = json.optJSONArray("categories") ?: JSONArray()
    val artifactsJson = json.optJSONArray("artifacts") ?: JSONArray()
    val stateTensorsJson = json.optJSONObject("state_tensors") ?: JSONObject()

    val categories = buildList {
      for (index in 0 until categoriesJson.length()) {
        val item = categoriesJson.getJSONObject(index)
        add(
          CategoryProfile(
            id = item.getString("id"),
            label = item.optString("label", item.getString("id")),
            defaultAggressiveness = item.optDouble("default_aggressiveness", 1.4).toFloat(),
            transient = item.optBoolean("transient", false),
          )
        )
      }
    }

    val artifacts = buildList {
      for (index in 0 until artifactsJson.length()) {
        val item = artifactsJson.getJSONObject(index)
        add(
          ModelArtifact(
            filename = item.getString("filename"),
            format = item.optString("format", "binary"),
            provider = item.optString("provider", "cpu"),
            role = item.optString("role", "metadata"),
          )
        )
      }
    }

    val stateTensors = buildMap {
      val keys = stateTensorsJson.keys()
      while (keys.hasNext()) {
        val key = keys.next()
        val values = stateTensorsJson.optJSONArray(key) ?: JSONArray()
        val shape = buildList {
          for (index in 0 until values.length()) {
            add(values.getInt(index))
          }
        }
        put(key, shape)
      }
    }

    return ModelBundleManifest(
      version = json.getString("version"),
      modelId = json.optString("model_id", "unknown"),
      modelFamily = json.optString("model_family", "unknown"),
      displayName = json.optString("display_name", json.optString("model_id", "Suppression Model")),
      suppressionStrategy = json.optString("suppression_strategy", "masked_unwanted_track"),
      runtimeKind = json.optString("runtime_kind", "onnx_category_separator"),
      sampleRate = json.optInt("sample_rate", 32_000),
      segmentSeconds =
        if (json.has("segment_seconds")) json.optDouble("segment_seconds") else null,
      overlapSeconds =
        if (json.has("overlap_seconds")) json.optDouble("overlap_seconds") else null,
      chunkSamples =
        if (json.has("chunk_samples")) json.optInt("chunk_samples") else null,
      preferredLiveHopMs =
        if (json.has("preferred_live_hop_ms")) json.optInt("preferred_live_hop_ms") else null,
      mixChannels = json.optInt("mix_channels", 1),
      stateTensors = stateTensors,
      categories = categories,
      artifacts = artifacts,
    )
  }

  private fun chooseModelFile(bundleDirectory: File, bundleManifest: ModelBundleManifest): File {
    val preferred = when (bundleManifest.runtimeKind) {
      "executorch_streaming_target_extractor", "executorch_category_separator" ->
        bundleManifest.artifacts
          .filter { it.format == "executorch" || it.filename.endsWith(".pte") }
          .map { it.filename }
      else ->
        listOf("model_fixed.ort") +
          bundleManifest.artifacts.filter { it.provider == "cpu" }.map { it.filename } +
          bundleManifest.artifacts.map { it.filename }
    }

    for (filename in preferred.distinct()) {
      val candidate = File(bundleDirectory, filename)
      if (!candidate.exists()) {
        continue
      }
      val isLoadable = when (bundleManifest.runtimeKind) {
        "executorch_streaming_target_extractor", "executorch_category_separator" ->
          filename.endsWith(".pte")
        else -> filename.endsWith(".onnx") || filename.endsWith(".ort")
      }
      if (isLoadable) {
        return candidate
      }
    }

    throw IllegalStateException("No loadable runtime artifact was found in ${bundleDirectory.absolutePath}")
  }

}
