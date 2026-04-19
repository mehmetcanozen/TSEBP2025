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


    init {
        writeHeader(0) // Write initial dummy header
    }

    fun write(buffer: FloatArray, length: Int) = synchronized(this) {
        if (!raf.channel.isOpen) return
        val pcm = ByteBuffer.allocate(length * 2).order(ByteOrder.LITTLE_ENDIAN)
        for (i in 0 until length) {
          val valFloat = buffer[i]
          val absValue = if (valFloat < 0) -valFloat else valFloat
          if (absValue > maxAmplitude) maxAmplitude = absValue
          
          val sample = valFloat.coerceIn(-1f, 1f)
          pcm.putShort((sample * 32767.0f).toInt().toShort())
        }

        raf.write(pcm.array())
        totalPcmBytes += length * 2
    }

    override fun close() = synchronized(this) {
        if (raf.channel.isOpen) {
            raf.seek(0)
            writeHeader(totalPcmBytes)
            raf.close()
            android.util.Log.d("WavWriter", "Closed WAV file. Total bytes: $totalPcmBytes, rate: $sampleRate, maxAmp: $maxAmplitude")
        }
    }



    private fun writeHeader(pcmBytes: Long) {
        val header = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN)
        
        // RIFF header
        header.put("RIFF".toByteArray())
        header.putInt((36 + pcmBytes).toInt())
        header.put("WAVE".toByteArray())
        
        // FMT chunk
        header.put("fmt ".toByteArray())
        header.putInt(16) // Subchunk1Size (16 for PCM)
        header.putShort(1.toShort()) // AudioFormat (1 for PCM)
        header.putShort(1.toShort()) // NumChannels (1 for Mono)
        header.putInt(sampleRate)
        header.putInt(sampleRate * 2) // ByteRate (SampleRate * NumChannels * BitsPerSample/8)
        header.putShort(2.toShort()) // BlockAlign (NumChannels * BitsPerSample/8)
        header.putShort(16.toShort()) // BitsPerSample
        
        // DATA chunk
        header.put("data".toByteArray())
        header.putInt(pcmBytes.toInt())
        
        raf.seek(0)
        raf.write(header.array())
    }
}
