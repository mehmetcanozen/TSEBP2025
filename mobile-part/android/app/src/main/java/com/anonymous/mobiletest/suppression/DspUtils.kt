package com.anonymous.mobiletest.suppression

import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.floor
import kotlin.math.max
import kotlin.math.min
import kotlin.math.PI
import kotlin.math.pow
import kotlin.math.sin
import kotlin.math.sqrt

data class Complex32(var real: Float, var imag: Float) {
  fun magnitude(): Float = sqrt(real * real + imag * imag)
  fun times(scale: Float): Complex32 = Complex32(real * scale, imag * scale)
}

data class MaskingOptions(
  val aggressiveness: Float,
  val ddAlpha: Float,
  val maskFloor: Float,
  val maxSuppressionRatio: Float,
  val speechDominanceThreshold: Float,
)

fun linearResample(audio: FloatArray, sourceRate: Int, targetRate: Int): FloatArray {
  if (audio.isEmpty() || sourceRate == targetRate) {
    return audio.copyOf()
  }

  val scale = targetRate.toDouble() / sourceRate.toDouble()
  val targetLength = max(1, kotlin.math.round(audio.size * scale).toInt())
  val output = FloatArray(targetLength)

  for (index in output.indices) {
    val position = index / scale
    val left = floor(position).toInt().coerceIn(0, audio.lastIndex)
    val right = min(left + 1, audio.lastIndex)
    val frac = (position - left).toFloat()
    output[index] = audio[left] + (audio[right] - audio[left]) * frac
  }
  return output
}

fun sincResampleToLength(audio: FloatArray, targetLength: Int, radius: Int = 8): FloatArray {
  if (targetLength <= 0) {
    return FloatArray(0)
  }
  if (audio.isEmpty()) {
    return FloatArray(targetLength)
  }
  if (audio.size == targetLength) {
    return audio.copyOf()
  }

  val safeRadius = max(2, radius)
  val output = FloatArray(targetLength)
  val scale = audio.size.toDouble() / targetLength.toDouble()
  val cutoff = min(1.0, targetLength.toDouble() / audio.size.toDouble())

  for (index in output.indices) {
    val sourcePosition = (index.toDouble() + 0.5) * scale - 0.5
    val center = floor(sourcePosition).toInt()
    var weighted = 0.0
    var weightSum = 0.0

    for (tap in (center - safeRadius + 1)..(center + safeRadius)) {
      val distance = sourcePosition - tap.toDouble()
      val windowDistance = abs(distance) / safeRadius.toDouble()
      if (windowDistance >= 1.0) {
        continue
      }

      val sincArg = distance * cutoff
      val sinc = if (abs(sincArg) < 1.0e-8) {
        1.0
      } else {
        sin(PI * sincArg) / (PI * sincArg)
      }
      val window = 0.5 + 0.5 * cos(PI * windowDistance)
      val weight = cutoff * sinc * window
      val sourceIndex = tap.coerceIn(0, audio.lastIndex)
      weighted += audio[sourceIndex].toDouble() * weight
      weightSum += weight
    }

    output[index] = if (abs(weightSum) > 1.0e-8) {
      (weighted / weightSum).toFloat()
    } else {
      0f
    }
  }

  return output
}

fun buildOverlapWindow(length: Int, overlapSamples: Int, fadeIn: Boolean, fadeOut: Boolean): FloatArray {
  val output = FloatArray(length) { 1f }
  val overlap = min(length, overlapSamples)
  if (overlap <= 0) {
    return output
  }

  for (index in 0 until overlap) {
    val ramp = index.toFloat() / overlap.toFloat()
    if (fadeIn) {
      output[index] = ramp
    }
    if (fadeOut) {
      val target = length - overlap + index
      output[target] = min(output[target], 1f - ramp)
    }
  }
  return output
}

fun rms(signal: FloatArray): Double {
  if (signal.isEmpty()) {
    return 0.0
  }
  var energy = 0.0
  for (sample in signal) {
    energy += sample.toDouble().pow(2.0)
  }
  return sqrt(energy / signal.size.toDouble())
}

fun peak(signal: FloatArray): Double {
  var value = 0.0
  for (sample in signal) {
    value = max(value, abs(sample.toDouble()))
  }
  return value
}

fun percentile95(values: List<Double>): Double {
  if (values.isEmpty()) {
    return 0.0
  }
  val sorted = values.sorted()
  val index = ((sorted.size - 1) * 0.95).toInt().coerceIn(0, sorted.lastIndex)
  return sorted[index]
}
