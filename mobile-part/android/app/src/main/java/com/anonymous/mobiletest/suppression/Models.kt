package com.anonymous.mobiletest.suppression

data class CategoryProfile(
  val id: String,
  val label: String,
  val defaultAggressiveness: Float,
  val transient: Boolean,
)

data class ModelArtifact(
  val filename: String,
  val format: String,
  val provider: String,
  val role: String,
)

data class ModelBundleManifest(
  val version: String,
  val modelId: String,
  val modelFamily: String,
  val displayName: String,
  val suppressionStrategy: String,
  val runtimeKind: String,
  val sampleRate: Int,
  val segmentSeconds: Double?,
  val overlapSeconds: Double?,
  val chunkSamples: Int?,
  val preferredLiveHopMs: Int?,
  val mixChannels: Int,
  val stateTensors: Map<String, List<Int>>,
  val categories: List<CategoryProfile>,
  val artifacts: List<ModelArtifact>,
)

data class PrepareOptions(
  val bundleDownloadUrl: String?,
  val accessToken: String?,
  val expectedVersion: String?,
  val expectedChecksum: String?,
  val forceRefresh: Boolean,
)

data class LiveConfig(
  val categoryId: String,
  val aggressiveness: Float,
  val hopMs: Int,
  val lookaheadMs: Int,
  val waveformerPostFilter: String = "off",
)

data class ProcessorDiagnostics(
  val waveformerPostFilter: String? = null,
  val wienerBypassed: Boolean = false,
)

data class RuntimeInfo(
  val provider: String,
  val warmed: Boolean,
  val modelId: String?,
  val modelFamily: String?,
  val displayName: String?,
  val runtimeKind: String?,
  val modelVersion: String?,
  val modelPath: String?,
  val bundlePath: String?,
  val sampleRate: Int,
  val categoryCount: Int,
  val availableProviders: List<String>,
)

data class StatusSnapshot(
  val sessionId: String?,
  val state: String,
  val provider: String,
  val inferenceMs: Double?,
  val queueDepthMs: Double?,
  val xruns: Int,
  val audioTrackUnderruns: Int,
  val limiterHits: Int,
  val failOpenCount: Int,
  val boundaryRepairHits: Int,
  val startupBlendMs: Int,
  val waveformerPostFilter: String?,
  val wienerBypassed: Boolean,
  val hopMs: Int,
  val lookaheadMs: Int,
  val sampleRate: Int,
  val message: String?,
)

data class MeterSnapshot(
  val sessionId: String?,
  val rmsIn: Double,
  val rmsOut: Double,
  val peakIn: Double,
  val peakOut: Double,
  val rawOutPeak: Double,
  val finalOutPeak: Double,
  val capturedFrames: Long,
  val renderedFrames: Long,
  val timestampMs: Long,
)

interface LiveSuppressionProcessor : AutoCloseable {
  fun preferredHopSamples(): Int

  fun processChunk(chunk: FloatArray): FloatArray

  fun diagnostics(): ProcessorDiagnostics = ProcessorDiagnostics()
}

interface SuppressionRuntime : AutoCloseable {
  fun runtimeInfo(bundlePath: String): RuntimeInfo

  fun categories(): List<CategoryProfile>

  fun createLiveProcessor(
    category: CategoryProfile,
    nativeSampleRate: Int,
    config: LiveConfig,
  ): LiveSuppressionProcessor
}
