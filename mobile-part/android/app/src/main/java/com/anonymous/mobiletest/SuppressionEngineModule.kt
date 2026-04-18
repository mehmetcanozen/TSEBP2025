package com.anonymous.mobiletest

import com.anonymous.mobiletest.suppression.*
import com.facebook.react.bridge.Arguments
import com.facebook.react.bridge.LifecycleEventListener
import com.facebook.react.bridge.Promise
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.bridge.ReactMethod
import com.facebook.react.bridge.ReadableMap
import com.facebook.react.bridge.WritableArray
import com.facebook.react.bridge.WritableMap
import com.facebook.react.modules.core.DeviceEventManagerModule
import java.util.concurrent.Executors

class SuppressionEngineModule(
  reactContext: ReactApplicationContext,
) : ReactContextBaseJavaModule(reactContext), LifecycleEventListener {
  private val executor = Executors.newSingleThreadExecutor()
  private val runtimeStore = BundleRuntimeStore(reactContext)
  @Volatile
  private var liveSession: LiveSuppressionSession? = null

  init {
    reactContext.addLifecycleEventListener(this)
  }

  override fun getName(): String = "SuppressionEngine"

  @ReactMethod
  fun prepare(options: ReadableMap?, promise: Promise) {
    executor.execute {
      try {
        val prepared = runtimeStore.prepare(
          PrepareOptions(
            bundleDownloadUrl = options?.getStringOrNull("bundleDownloadUrl"),
            accessToken = options?.getStringOrNull("accessToken"),
            expectedVersion = options?.getStringOrNull("expectedVersion"),
            expectedChecksum = options?.getStringOrNull("expectedChecksum"),
            forceRefresh = options?.getBooleanOrDefault("forceRefresh", false) ?: false,
          )
        )
        promise.resolve(prepared.toWritableMap())
      } catch (error: Throwable) {
        promise.reject("prepare_failed", error.message, error)
      }
    }
  }

  @ReactMethod
  fun startLive(config: ReadableMap, promise: Promise) {
    executor.execute {
      try {
        val runtime = runtimeStore.suppressionRuntime()
        val categoryId = requireNotNull(config.getString("categoryId")) {
          "categoryId is required"
        }
        val category = runtimeStore.categories().find { it.id == categoryId }
          ?: throw IllegalArgumentException("Unknown category: $categoryId")

        liveSession?.close()
        liveSession = LiveSuppressionSession(
          context = reactApplicationContext,
          runtime = runtime,
          category = category,
          config = LiveConfig(
            categoryId = categoryId,
            aggressiveness = config.getDoubleOrDefault("aggressiveness", category.defaultAggressiveness.toDouble()).toFloat(),
            hopMs = config.getIntOrDefault("hopMs", 500),
            lookaheadMs = config.getIntOrDefault("lookaheadMs", 250),
          ),
          onStatus = { snapshot -> emitEvent("SuppressionEngineStatus", snapshot.toWritableMap()) },
          onMeter = { snapshot -> emitEvent("SuppressionEngineMeter", snapshot.toWritableMap()) },
        )
        val sessionId = liveSession?.start() ?: throw IllegalStateException("Failed to start live session")
        val payload = Arguments.createMap()
        payload.putString("sessionId", sessionId)
        promise.resolve(payload)
      } catch (error: Throwable) {
        promise.reject("start_live_failed", error.message, error)
      }
    }
  }

  @ReactMethod
  fun stopLive(promise: Promise) {
    executor.execute {
      try {
        liveSession?.close()
        liveSession = null
        promise.resolve(null)
      } catch (error: Throwable) {
        promise.reject("stop_live_failed", error.message, error)
      }
    }
  }

  @ReactMethod
  fun getRuntimeInfo(promise: Promise) {
    executor.execute {
      promise.resolve(runtimeStore.runtimeInfo().toWritableMap())
    }
  }

  @ReactMethod
  fun getCategories(promise: Promise) {
    executor.execute {
      try {
        val array = Arguments.createArray()
        for (category in runtimeStore.categories()) {
          array.pushMap(category.toWritableMap())
        }
        promise.resolve(array)
      } catch (error: Throwable) {
        promise.reject("get_categories_failed", error.message, error)
      }
    }
  }

  @ReactMethod
  fun addListener(eventName: String) {
    // Required by React Native's NativeEventEmitter contract.
  }

  @ReactMethod
  fun removeListeners(count: Double) {
    // Required by React Native's NativeEventEmitter contract.
  }

  override fun onHostResume() = Unit

  override fun onHostPause() {
    liveSession?.close()
    liveSession = null
  }

  override fun onHostDestroy() {
    liveSession?.close()
    liveSession = null
    runtimeStore.close()
    executor.shutdownNow()
  }

  private fun emitEvent(name: String, payload: WritableMap) {
    reactApplicationContext
      .getJSModule(DeviceEventManagerModule.RCTDeviceEventEmitter::class.java)
      .emit(name, payload)
  }
}

private fun ReadableMap.getStringOrNull(key: String): String? {
  return if (hasKey(key) && !isNull(key)) getString(key) else null
}

private fun ReadableMap.getBooleanOrDefault(key: String, defaultValue: Boolean): Boolean? {
  return if (hasKey(key) && !isNull(key)) getBoolean(key) else defaultValue
}

private fun ReadableMap.getIntOrDefault(key: String, defaultValue: Int): Int {
  return if (hasKey(key) && !isNull(key)) getDouble(key).toInt() else defaultValue
}

private fun ReadableMap.getDoubleOrDefault(key: String, defaultValue: Double): Double {
  return if (hasKey(key) && !isNull(key)) getDouble(key) else defaultValue
}

private fun RuntimeInfo.toWritableMap(): WritableMap {
  return Arguments.createMap().apply {
    putString("provider", provider)
    putBoolean("warmed", warmed)
    putString("modelId", modelId)
    putString("modelFamily", modelFamily)
    putString("displayName", displayName)
    putString("runtimeKind", runtimeKind)
    putString("modelVersion", modelVersion)
    putString("modelPath", modelPath)
    putString("bundlePath", bundlePath)
    putInt("sampleRate", sampleRate)
    putInt("categoryCount", categoryCount)
    putArray("availableProviders", availableProviders.toWritableArray())
  }
}

private fun CategoryProfile.toWritableMap(): WritableMap {
  return Arguments.createMap().apply {
    putString("id", id)
    putString("label", label)
    putDouble("defaultAggressiveness", defaultAggressiveness.toDouble())
    putBoolean("transient", transient)
  }
}

private fun StatusSnapshot.toWritableMap(): WritableMap {
  return Arguments.createMap().apply {
    putString("sessionId", sessionId)
    putString("state", state)
    putString("provider", provider)
    if (inferenceMs != null) putDouble("inferenceMs", inferenceMs) else putNull("inferenceMs")
    if (queueDepthMs != null) putDouble("queueDepthMs", queueDepthMs) else putNull("queueDepthMs")
    putInt("xruns", xruns)
    putInt("hopMs", hopMs)
    putInt("lookaheadMs", lookaheadMs)
    putInt("sampleRate", sampleRate)
    putString("message", message)
  }
}

private fun MeterSnapshot.toWritableMap(): WritableMap {
  return Arguments.createMap().apply {
    putString("sessionId", sessionId)
    putDouble("rmsIn", rmsIn)
    putDouble("rmsOut", rmsOut)
    putDouble("peakIn", peakIn)
    putDouble("peakOut", peakOut)
    putDouble("capturedFrames", capturedFrames.toDouble())
    putDouble("renderedFrames", renderedFrames.toDouble())
    putDouble("timestampMs", timestampMs.toDouble())
  }
}

private fun List<String>.toWritableArray(): WritableArray {
  return Arguments.createArray().also { array ->
    for (value in this) {
      array.pushString(value)
    }
  }
}
