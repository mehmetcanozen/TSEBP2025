package com.anonymous.mobiletest.suppression

import org.jtransforms.fft.FloatFFT_1D
import kotlin.math.PI
import kotlin.math.max
import kotlin.math.min

class WienerMasker {
  private val plans = mutableMapOf<Int, FftPlan>()
  private var prevCleanPower: FloatArray? = null
  private var prevNoisePower: FloatArray? = null

  fun apply(
    mix: FloatArray,
    unwanted: FloatArray,
    sampleRate: Int,
    nFft: Int,
    options: MaskingOptions,
  ): FloatArray {
    val minLength = min(mix.size, unwanted.size)
    if (minLength <= 0) {
      return FloatArray(0)
    }

    val mixSlice = mix.copyOf(minLength)
    val unwantedSlice = unwanted.copyOf(minLength)
    val plan = planFor(nFft)
    val mixFrames = stft(mixSlice, plan)
    val unwantedFrames = stft(unwantedSlice, plan)
    if (mixFrames.isEmpty() || unwantedFrames.isEmpty()) {
      return FloatArray(minLength)
    }

    val freqBins = mixFrames.first().size
    if (prevCleanPower?.size != freqBins) {
      prevCleanPower = FloatArray(freqBins)
      prevNoisePower = FloatArray(freqBins) { 1.0e-10f }
    }

    val previousClean = prevCleanPower ?: FloatArray(freqBins)
    val previousNoise = prevNoisePower ?: FloatArray(freqBins) { 1.0e-10f }
    val perceptualFloor = buildPerceptualFloor(freqBins, sampleRate, 0.01f, 0.05f)
    val cleanFrames = ArrayList<Array<Complex32>>(mixFrames.size)
    val eps = 1.0e-10f

    for (frameIndex in mixFrames.indices) {
      val mixFrame = mixFrames[frameIndex]
      val unwantedFrame = unwantedFrames[frameIndex]
      val cleanFrame = Array(freqBins) { Complex32(0f, 0f) }

      for (bin in 0 until freqBins) {
        val mixValue = mixFrame[bin]
        val unwantedValue = unwantedFrame[bin]
        val magMix = mixValue.magnitude()
        val limitedUnwanted = min(
          unwantedValue.magnitude(),
          options.maxSuppressionRatio * (magMix + eps)
        )
        val mixPower = magMix * magMix
        val noisePower = limitedUnwanted * limitedUnwanted + eps
        val gamma = mixPower / noisePower
        val gammaMinusOne = max(gamma - 1f, 0f)
        val snrPrior = previousClean[bin] / max(previousNoise[bin], eps)
        var xi = options.ddAlpha * snrPrior + (1f - options.ddAlpha) * gammaMinusOne
        xi = max(xi, 0f)
        var gain = xi / (options.aggressiveness + xi + eps)

        val floor = max(perceptualFloor[bin], options.maskFloor)
        val dominance = mixPower / max(noisePower, eps)
        if (dominance >= options.speechDominanceThreshold) {
          val preserveBias = (
            (dominance - options.speechDominanceThreshold) /
              max(options.speechDominanceThreshold, eps)
            ).coerceIn(0f, 1f)
          gain = max(gain, (floor + 0.18f * preserveBias).coerceIn(floor, 1f))
        }

        gain = gain.coerceIn(floor, 1f)
        previousClean[bin] = gain * gain * mixPower
        previousNoise[bin] = noisePower
        cleanFrame[bin] = mixValue.times(gain)
      }

      cleanFrame[0].imag = 0f
      if (freqBins > 1) {
        cleanFrame[freqBins - 1].imag = 0f
      }
      cleanFrames.add(cleanFrame)
    }

    prevCleanPower = previousClean
    prevNoisePower = previousNoise
    return istft(cleanFrames, plan, minLength)
  }

  private fun planFor(nFft: Int): FftPlan {
    return plans.getOrPut(nFft) {
      val window = FloatArray(nFft) { index ->
        (0.5 - 0.5 * kotlin.math.cos((2.0 * PI * index.toDouble() / nFft.toDouble()))).toFloat()
      }
      FftPlan(
        nFft = nFft,
        hopSize = nFft / 2,
        window = window,
        fft = FloatFFT_1D(nFft.toLong()),
      )
    }
  }

  private fun stft(signal: FloatArray, plan: FftPlan): List<Array<Complex32>> {
    val starts = frameStarts(signal.size, plan.nFft, plan.hopSize)
    val frames = ArrayList<Array<Complex32>>(starts.size)
    val freqBins = plan.nFft / 2 + 1

    for (start in starts) {
      val frame = FloatArray(plan.nFft * 2)
      val available = min(signal.size - start, plan.nFft).coerceAtLeast(0)
      for (index in 0 until available) {
        frame[index * 2] = signal[start + index] * plan.window[index]
      }
      plan.fft.complexForward(frame)

      val spectrum = Array(freqBins) { Complex32(0f, 0f) }
      for (bin in 0 until freqBins) {
        spectrum[bin] = Complex32(frame[bin * 2], frame[bin * 2 + 1])
      }
      frames.add(spectrum)
    }
    return frames
  }

  private fun istft(frames: List<Array<Complex32>>, plan: FftPlan, outputLength: Int): FloatArray {
    if (frames.isEmpty()) {
      return FloatArray(outputLength)
    }

    val totalLength = plan.hopSize * (frames.size - 1) + plan.nFft
    val output = FloatArray(totalLength)
    val norm = FloatArray(totalLength)
    val freqBins = plan.nFft / 2 + 1

    for ((frameIndex, frame) in frames.withIndex()) {
      val fullSpectrum = FloatArray(plan.nFft * 2)
      for (bin in 0 until freqBins) {
        fullSpectrum[bin * 2] = frame[bin].real
        fullSpectrum[bin * 2 + 1] = frame[bin].imag
      }
      for (bin in 1 until freqBins - 1) {
        val mirror = plan.nFft - bin
        fullSpectrum[mirror * 2] = frame[bin].real
        fullSpectrum[mirror * 2 + 1] = -frame[bin].imag
      }
      fullSpectrum[1] = 0f
      if (freqBins > 1) {
        fullSpectrum[(freqBins - 1) * 2 + 1] = 0f
      }

      plan.fft.complexInverse(fullSpectrum, true)

      val start = frameIndex * plan.hopSize
      for (sampleIndex in 0 until plan.nFft) {
        val weighted = fullSpectrum[sampleIndex * 2] * plan.window[sampleIndex]
        output[start + sampleIndex] += weighted
        norm[start + sampleIndex] += plan.window[sampleIndex] * plan.window[sampleIndex]
      }
    }

    for (index in output.indices) {
      if (norm[index] > 1.0e-8f) {
        output[index] /= norm[index]
      }
    }

    return if (output.size == outputLength) {
      output
    } else {
      output.copyOf(outputLength)
    }
  }

  private fun frameStarts(signalLength: Int, nFft: Int, hopSize: Int): List<Int> {
    if (signalLength == 0 || signalLength <= nFft) {
      return listOf(0)
    }

    val starts = ArrayList<Int>()
    var start = 0
    while (true) {
      starts.add(start)
      if (start + nFft >= signalLength) {
        break
      }
      start += max(hopSize, 1)
    }
    return starts
  }

  private fun buildPerceptualFloor(
    freqBins: Int,
    sampleRate: Int,
    floorMin: Float,
    floorMax: Float,
  ): FloatArray {
    val floor = FloatArray(freqBins) { floorMin }
    val nyquist = sampleRate.toFloat() / 2f
    val low = 200f
    val peak = 2500f
    val high = 10_000f

    for (index in floor.indices) {
      val frequency = index.toFloat() / max(freqBins - 1, 1).toFloat() * nyquist
      floor[index] = when {
        frequency < low || frequency > high -> floorMin
        frequency <= peak -> {
          val t = (frequency - low) / (peak - low)
          floorMin + t * (floorMax - floorMin)
        }
        else -> {
          val t = (frequency - peak) / (high - peak)
          floorMax - t * (floorMax - floorMin)
        }
      }
    }
    return floor
  }

  private data class FftPlan(
    val nFft: Int,
    val hopSize: Int,
    val window: FloatArray,
    val fft: FloatFFT_1D,
  )
}
