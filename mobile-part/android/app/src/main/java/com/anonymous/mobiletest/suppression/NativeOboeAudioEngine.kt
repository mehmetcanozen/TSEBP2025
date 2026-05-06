package com.anonymous.mobiletest.suppression

import android.util.Log
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.math.max

data class NativeOboeStats(
  val actualSampleRate: Int,
  val framesPerBurst: Int,
  val inputChannelCount: Int,
  val outputChannelCount: Int,
  val callbackUnderruns: Long,
  val inputOverflows: Long,
  val renderUnderruns: Long,
  val renderOverflows: Long,
  val capturedFrames: Long,
  val renderedFrames: Long,
  val renderQueueFrames: Int,
)

class NativeOboeAudioEngine(
  requestedSampleRate: Int,
  requestedFramesPerBurst: Int,
  captureCapacityFrames: Int,
  renderCapacityFrames: Int,
) : AutoCloseable {
  companion object {
    private const val TAG = "NativeOboeAudioEngine"
    private val libraryLoaded: Boolean = try {
      System.loadLibrary("suppressionaudio")
      true
    } catch (error: Throwable) {
      Log.w(TAG, "Native Oboe library is unavailable", error)
      false
    }

    fun isAvailable(): Boolean = libraryLoaded
  }

  private val closed = AtomicBoolean(false)
  private val handle: Long

  init {
    require(libraryLoaded) { "Native Oboe library is unavailable" }
    handle = nativeCreate(
      requestedSampleRate = requestedSampleRate,
      requestedFramesPerBurst = max(64, requestedFramesPerBurst),
      captureCapacityFrames = max(requestedSampleRate, captureCapacityFrames),
      renderCapacityFrames = max(requestedSampleRate, renderCapacityFrames),
    )
    require(handle != 0L) { "Native Oboe engine allocation failed" }
  }

  fun start() {
    checkOpen()
    if (!nativeStart(handle)) {
      val error = nativeLastError(handle).ifBlank { "Oboe stream start failed" }
      throw IllegalStateException(error)
    }
  }

  fun stop() {
    if (!closed.get()) {
      nativeStop(handle)
    }
  }

  fun readCapture(destination: FloatArray, maxFrames: Int = destination.size): Int {
    checkOpen()
    return nativeReadCapture(handle, destination, maxFrames)
  }

  fun writeRender(source: FloatArray, frames: Int = source.size): Int {
    checkOpen()
    return nativeWriteRender(handle, source, frames)
  }

  fun availableCapture(): Int {
    checkOpen()
    return nativeAvailableCapture(handle)
  }

  fun availableRender(): Int {
    checkOpen()
    return nativeAvailableRender(handle)
  }

  fun dropOldestRender(frames: Int): Int {
    checkOpen()
    return nativeDropOldestRender(handle, frames)
  }

  fun stats(): NativeOboeStats {
    checkOpen()
    val values = nativeStats(handle)
    return NativeOboeStats(
      actualSampleRate = values.getOrElse(0) { 0L }.toInt(),
      framesPerBurst = values.getOrElse(1) { 0L }.toInt(),
      inputChannelCount = values.getOrElse(2) { 0L }.toInt(),
      outputChannelCount = values.getOrElse(3) { 0L }.toInt(),
      callbackUnderruns = values.getOrElse(4) { 0L },
      inputOverflows = values.getOrElse(5) { 0L },
      renderUnderruns = values.getOrElse(6) { 0L },
      renderOverflows = values.getOrElse(7) { 0L },
      capturedFrames = values.getOrElse(8) { 0L },
      renderedFrames = values.getOrElse(9) { 0L },
      renderQueueFrames = values.getOrElse(10) { 0L }.toInt(),
    )
  }

  override fun close() {
    if (closed.compareAndSet(false, true)) {
      nativeStop(handle)
      nativeRelease(handle)
    }
  }

  private fun checkOpen() {
    check(!closed.get()) { "Native Oboe engine is closed" }
  }

  private external fun nativeCreate(
    requestedSampleRate: Int,
    requestedFramesPerBurst: Int,
    captureCapacityFrames: Int,
    renderCapacityFrames: Int,
  ): Long

  private external fun nativeStart(handle: Long): Boolean

  private external fun nativeStop(handle: Long)

  private external fun nativeRelease(handle: Long)

  private external fun nativeReadCapture(handle: Long, destination: FloatArray, maxFrames: Int): Int

  private external fun nativeWriteRender(handle: Long, source: FloatArray, frames: Int): Int

  private external fun nativeAvailableCapture(handle: Long): Int

  private external fun nativeAvailableRender(handle: Long): Int

  private external fun nativeDropOldestRender(handle: Long, frames: Int): Int

  private external fun nativeStats(handle: Long): LongArray

  private external fun nativeLastError(handle: Long): String
}
