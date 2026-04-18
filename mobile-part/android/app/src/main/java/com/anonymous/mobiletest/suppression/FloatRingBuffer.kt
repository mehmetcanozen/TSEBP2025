package com.anonymous.mobiletest.suppression

import java.util.concurrent.atomic.AtomicInteger
import kotlin.math.min

class FloatRingBuffer(requestedCapacity: Int) {
  private val capacity = nextPowerOfTwo(maxOf(1024, requestedCapacity))
  private val mask = capacity - 1
  private val buffer = FloatArray(capacity)
  private val readIndex = AtomicInteger(0)
  private val writeIndex = AtomicInteger(0)

  fun write(source: FloatArray, count: Int = source.size): Int {
    val safeCount = min(count, source.size)
    val read = readIndex.get()
    val write = writeIndex.get()
    val writable = capacity - (write - read) - 1
    val toWrite = min(safeCount, writable)
    for (i in 0 until toWrite) {
      buffer[(write + i) and mask] = source[i]
    }
    if (toWrite > 0) {
      writeIndex.lazySet(write + toWrite)
    }
    return toWrite
  }

  fun read(destination: FloatArray, count: Int = destination.size): Int {
    val safeCount = min(count, destination.size)
    val read = readIndex.get()
    val write = writeIndex.get()
    val available = write - read
    val toRead = min(safeCount, available)
    for (i in 0 until toRead) {
      destination[i] = buffer[(read + i) and mask]
    }
    if (toRead > 0) {
      readIndex.lazySet(read + toRead)
    }
    return toRead
  }

  fun availableToRead(): Int = writeIndex.get() - readIndex.get()

  private fun nextPowerOfTwo(value: Int): Int {
    var n = 1
    while (n < value) {
      n = n shl 1
    }
    return n
  }
}
