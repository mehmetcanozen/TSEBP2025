package com.anonymous.mobiletest.suppression

import java.util.concurrent.atomic.AtomicInteger
import kotlin.math.min

class FloatRingBuffer(requestedCapacity: Int) {
  private val capacity = nextPowerOfTwo(maxOf(1024, requestedCapacity))
  private val mask = capacity - 1
  private val buffer = FloatArray(capacity)
  private val readIndex = AtomicInteger(0)
  private val writeIndex = AtomicInteger(0)

  fun write(source: FloatArray, count: Int = source.size): Int =
    write(source, 0, count)

  fun write(source: FloatArray, offset: Int, count: Int): Int {
    if (offset < 0 || offset >= source.size || count <= 0) {
      return 0
    }
    val safeCount = min(count, source.size - offset)
    val read = readIndex.get()
    val write = writeIndex.get()
    val writable = capacity - (write - read) - 1
    val toWrite = min(safeCount, writable)
    for (i in 0 until toWrite) {
      buffer[(write + i) and mask] = source[offset + i]
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

  fun dropOldest(count: Int): Int {
    if (count <= 0) {
      return 0
    }
    val read = readIndex.get()
    val write = writeIndex.get()
    val available = write - read
    val dropped = min(count, available)
    if (dropped > 0) {
      readIndex.lazySet(read + dropped)
    }
    return dropped
  }

  private fun nextPowerOfTwo(value: Int): Int {
    var n = 1
    while (n < value) {
      n = n shl 1
    }
    return n
  }
}

class FloatBlockQueue(initialCapacity: Int) {
  private var buffer = FloatArray(nextPowerOfTwo(maxOf(1024, initialCapacity)))
  private var start = 0
  var size = 0
    private set

  fun append(source: FloatArray, count: Int = source.size) {
    val safeCount = min(count, source.size)
    if (safeCount <= 0) {
      return
    }
    ensureCapacity(size + safeCount)
    if (start + size + safeCount > buffer.size) {
      compact()
    }
    System.arraycopy(source, 0, buffer, start + size, safeCount)
    size += safeCount
  }

  fun popInto(destination: FloatArray, count: Int = destination.size): Boolean {
    val safeCount = min(count, destination.size)
    if (safeCount <= 0 || size < safeCount) {
      return false
    }
    System.arraycopy(buffer, start, destination, 0, safeCount)
    start += safeCount
    size -= safeCount
    if (start > buffer.size / 2) {
      compact()
    }
    return true
  }

  private fun ensureCapacity(required: Int) {
    if (required <= buffer.size) {
      return
    }
    val next = FloatArray(nextPowerOfTwo(required))
    System.arraycopy(buffer, start, next, 0, size)
    buffer = next
    start = 0
  }

  private fun compact() {
    if (size > 0 && start > 0) {
      System.arraycopy(buffer, start, buffer, 0, size)
    }
    start = 0
  }

  private fun nextPowerOfTwo(value: Int): Int {
    var n = 1
    while (n < value) {
      n = n shl 1
    }
    return n
  }
}
