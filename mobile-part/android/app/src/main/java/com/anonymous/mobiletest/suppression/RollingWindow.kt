package com.anonymous.mobiletest.suppression

class RollingWindow(private val capacity: Int) {
  private val samples = FloatArray(capacity)
  private var writeIndex = 0
  private var filled = 0

  fun append(source: FloatArray, count: Int) {
    for (i in 0 until count) {
      samples[writeIndex] = source[i]
      writeIndex = (writeIndex + 1) % capacity
      if (filled < capacity) {
        filled += 1
      }
    }
  }

  fun latestPadded(targetLength: Int): FloatArray {
    val output = FloatArray(targetLength)
    val copyCount = minOf(targetLength, filled)
    val start = if (filled < capacity) {
      filled - copyCount
    } else {
      ((writeIndex - copyCount) + capacity) % capacity
    }

    for (i in 0 until copyCount) {
      val valueIndex = if (filled < capacity) {
        start + i
      } else {
        (start + i) % capacity
      }
      output[targetLength - copyCount + i] = samples[valueIndex]
    }

    return output
  }
}
