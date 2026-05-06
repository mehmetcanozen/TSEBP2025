package com.anonymous.mobiletest.suppression

import java.io.File
import java.io.RandomAccessFile
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * A simple utility to write 16-bit Mono WAV files from Float PCM buffers.
 */
class WavWriter(private val file: File, private val sampleRate: Int) : AutoCloseable {
    private val raf = RandomAccessFile(file, "rw")
    private var totalPcmBytes = 0L
    private var maxAmplitude = 0f
    private var nonZeroSamples = 0L
    private var pcmBytes = ByteArray(8192)
    private val headerBytes = ByteArray(44)
    private val headerBuffer = ByteBuffer.wrap(headerBytes).order(ByteOrder.LITTLE_ENDIAN)


    init {
        file.parentFile?.mkdirs()
        raf.setLength(0)
        writeHeader(0) // Write initial dummy header; close patches the final size.
    }

    fun write(buffer: FloatArray, length: Int) = synchronized(this) {
        if (!raf.channel.isOpen) return
        val safeLength = kotlin.math.min(length, buffer.size)
        if (safeLength <= 0) return

        val requiredBytes = safeLength * 2
        if (pcmBytes.size < requiredBytes) {
            pcmBytes = ByteArray(requiredBytes)
        }
        val pcm = ByteBuffer.wrap(pcmBytes, 0, requiredBytes).order(ByteOrder.LITTLE_ENDIAN)
        for (i in 0 until safeLength) {
          val valFloat = buffer[i]
          val safeFloat = if (valFloat.isNaN() || valFloat.isInfinite()) 0f else valFloat
          val absValue = if (safeFloat < 0) -safeFloat else safeFloat
          if (absValue > maxAmplitude) maxAmplitude = absValue
          if (absValue > 1.0e-5f) nonZeroSamples += 1
          
          val sample = safeFloat.coerceIn(-1f, 1f)
          pcm.putShort((sample * 32767.0f).toInt().toShort())
        }

        raf.write(pcmBytes, 0, requiredBytes)
        totalPcmBytes += safeLength * 2L
    }

    override fun close() = synchronized(this) {
        if (raf.channel.isOpen) {
            raf.seek(0)
            writeHeader(totalPcmBytes)
            raf.close()
            android.util.Log.d(
                "WavWriter",
                "Closed WAV file. Total bytes: $totalPcmBytes, rate: $sampleRate, maxAmp: $maxAmplitude, nonZeroSamples: $nonZeroSamples, path: ${file.absolutePath}"
            )
        }
    }



    private fun writeHeader(pcmBytes: Long) {
        headerBuffer.clear()
        
        // RIFF header
        headerBuffer.put("RIFF".toByteArray())
        headerBuffer.putInt((36 + pcmBytes).toInt())
        headerBuffer.put("WAVE".toByteArray())
        
        // FMT chunk
        headerBuffer.put("fmt ".toByteArray())
        headerBuffer.putInt(16) // Subchunk1Size (16 for PCM)
        headerBuffer.putShort(1.toShort()) // AudioFormat (1 for PCM)
        headerBuffer.putShort(1.toShort()) // NumChannels (1 for Mono)
        headerBuffer.putInt(sampleRate)
        headerBuffer.putInt(sampleRate * 2) // ByteRate (SampleRate * NumChannels * BitsPerSample/8)
        headerBuffer.putShort(2.toShort()) // BlockAlign (NumChannels * BitsPerSample/8)
        headerBuffer.putShort(16.toShort()) // BitsPerSample
        
        // DATA chunk
        headerBuffer.put("data".toByteArray())
        headerBuffer.putInt(pcmBytes.toInt())
        
        raf.seek(0)
        raf.write(headerBytes)
    }
}
