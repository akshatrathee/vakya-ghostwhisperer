package com.vakya.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import java.io.File
import java.io.FileOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Foreground service that captures audio via [AudioRecord] at 16kHz mono
 * PCM_16BIT and writes a WAV file to the app cache directory.
 *
 * Start/stop via [ACTION_START] / [ACTION_STOP] intents from [MainActivity].
 * When recording stops the service fires [ACTION_WAV_READY] broadcast with
 * the WAV path, then calls [VakyaBridge.transcribe] on a background coroutine.
 */
class AudioRecordService : Service() {

    companion object {
        const val ACTION_START     = "com.vakya.app.ACTION_START_RECORDING"
        const val ACTION_STOP      = "com.vakya.app.ACTION_STOP_RECORDING"
        const val ACTION_WAV_READY = "com.vakya.app.ACTION_WAV_READY"
        const val EXTRA_WAV_PATH   = "wav_path"
        const val EXTRA_RESULT     = "result_json"

        private const val TAG              = "AudioRecordService"
        private const val CHANNEL_ID       = "vakya_recording"
        private const val NOTIFICATION_ID  = 1
        private const val SAMPLE_RATE      = 16_000
        private const val CHANNEL_CONFIG   = AudioFormat.CHANNEL_IN_MONO
        private const val AUDIO_FORMAT     = AudioFormat.ENCODING_PCM_16BIT
    }

    private var recorder: AudioRecord? = null
    private var recordingJob: Job? = null
    private val serviceScope = CoroutineScope(Dispatchers.IO)
    private var isRecording = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> startRecording()
            ACTION_STOP  -> stopRecording()
        }
        return START_NOT_STICKY
    }

    // ------------------------------------------------------------------
    // Recording
    // ------------------------------------------------------------------

    private fun startRecording() {
        if (isRecording) return

        startForeground(NOTIFICATION_ID, buildNotification("Recording…"))
        isRecording = true

        val minBuf = AudioRecord.getMinBufferSize(SAMPLE_RATE, CHANNEL_CONFIG, AUDIO_FORMAT)
        val bufSize = maxOf(minBuf, SAMPLE_RATE * 2)   // at least 1 second

        recorder = AudioRecord(
            MediaRecorder.AudioSource.MIC,
            SAMPLE_RATE,
            CHANNEL_CONFIG,
            AUDIO_FORMAT,
            bufSize,
        )

        val pcmChunks = mutableListOf<ByteArray>()
        recorder!!.startRecording()

        recordingJob = serviceScope.launch {
            val buf = ByteArray(bufSize)
            while (isRecording) {
                val read = recorder!!.read(buf, 0, bufSize)
                if (read > 0) {
                    pcmChunks.add(buf.copyOf(read))
                }
            }
            recorder!!.stop()
            recorder!!.release()
            recorder = null

            val wavFile = writeWav(pcmChunks)
            Log.i(TAG, "WAV written: ${wavFile.absolutePath}")
            onWavReady(wavFile.absolutePath)
        }
    }

    private fun stopRecording() {
        isRecording = false
        // recordingJob completes naturally once isRecording = false
    }

    // ------------------------------------------------------------------
    // WAV muxing
    // ------------------------------------------------------------------

    private fun writeWav(chunks: List<ByteArray>): File {
        val pcmSize = chunks.sumOf { it.size }
        val outFile = File(cacheDir, "vakya_${System.currentTimeMillis()}.wav")

        FileOutputStream(outFile).use { fos ->
            fos.write(wavHeader(pcmSize))
            for (chunk in chunks) fos.write(chunk)
        }
        return outFile
    }

    /** Standard 44-byte PCM WAV header. */
    private fun wavHeader(pcmBytes: Int): ByteArray {
        val totalDataLen   = pcmBytes + 36
        val byteRate       = SAMPLE_RATE * 1 * 2   // sampleRate * channels * bitsPerSample/8
        val buf = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN)
        buf.put("RIFF".toByteArray())
        buf.putInt(totalDataLen)
        buf.put("WAVE".toByteArray())
        buf.put("fmt ".toByteArray())
        buf.putInt(16)                 // chunk size
        buf.putShort(1)                // PCM format
        buf.putShort(1)                // mono
        buf.putInt(SAMPLE_RATE)
        buf.putInt(byteRate)
        buf.putShort(2)                // block align
        buf.putShort(16)               // bits per sample
        buf.put("data".toByteArray())
        buf.putInt(pcmBytes)
        return buf.array()
    }

    // ------------------------------------------------------------------
    // Handoff to PipelineBridge
    // ------------------------------------------------------------------

    private fun onWavReady(wavPath: String) {
        updateNotification("Transcribing…")
        serviceScope.launch {
            val result = VakyaBridge.transcribe(wavPath, deleteAfter = true)
            Log.i(TAG, "Transcription done in ${result.duration_s}s")

            val broadcastIntent = Intent(ACTION_WAV_READY).apply {
                putExtra(EXTRA_WAV_PATH, wavPath)
                putExtra(EXTRA_RESULT, result.text)
            }
            sendBroadcast(broadcastIntent)
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
        }
    }

    // ------------------------------------------------------------------
    // Notification
    // ------------------------------------------------------------------

    private fun createNotificationChannel() {
        val nm = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Vakya Recording",
            NotificationManager.IMPORTANCE_LOW,
        )
        nm.createNotificationChannel(channel)
    }

    private fun buildNotification(text: String): Notification =
        NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Vakya")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setOngoing(true)
            .build()

    private fun updateNotification(text: String) {
        val nm = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        nm.notify(NOTIFICATION_ID, buildNotification(text))
    }

    override fun onDestroy() {
        isRecording = false
        recorder?.release()
        recorder = null
        super.onDestroy()
    }
}
