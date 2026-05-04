package com.vakya.app

import android.util.Log
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import com.google.gson.Gson
import com.google.gson.JsonObject

/**
 * Singleton wrapper around the Chaquopy PipelineBridge Python object.
 *
 * All public methods are safe to call from any thread; Chaquopy handles
 * the GIL internally.
 */
object VakyaBridge {

    private const val TAG = "VakyaBridge"

    @Volatile private var bridge: PyObject? = null
    private val gson = Gson()

    /** Called once from [VakyaApplication.onCreate]. */
    fun init(configDir: String, modelsDir: String, enhancedCleanup: Boolean = false) {
        val py = Python.getInstance()
        val module = py.getModule("vakya.platform.android.main")
        bridge = module.callAttr("init", configDir, modelsDir, enhancedCleanup)
        Log.i(TAG, "PipelineBridge initialised")
    }

    /** Transcribe a WAV file written by [AudioRecordService]. */
    fun transcribe(wavPath: String, deleteAfter: Boolean = true): TranscribeResult {
        val raw = requireBridge().callAttr("transcribe", wavPath, deleteAfter).toString()
        Log.d(TAG, "transcribe raw: $raw")
        return gson.fromJson(raw, TranscribeResult::class.java)
    }

    /** Synthesise TTS and return path to output WAV. */
    fun synthesise(text: String, voiceId: String? = null): SynthesiseResult {
        val raw = requireBridge().callAttr("synthesise", text, voiceId).toString()
        return gson.fromJson(raw, SynthesiseResult::class.java)
    }

    /** Toggle Phi-3 Mini enhanced cleanup. */
    fun setEnhancedCleanup(enabled: Boolean) {
        requireBridge().callAttr("set_enhanced_cleanup", enabled)
    }

    /** Pre-load models after first-run model download. */
    fun warmUp() {
        requireBridge().callAttr("warm_up")
    }

    private fun requireBridge(): PyObject =
        bridge ?: error("VakyaBridge not initialised — call init() first")

    // ------------------------------------------------------------------
    // Result data classes (Gson-deserialised from JSON strings)
    // ------------------------------------------------------------------

    data class TranscribeResult(
        val text: String = "",
        val language: String = "en",
        val duration_s: Double = 0.0,
        val engine: String = "",
        val error: String? = null,
    )

    data class SynthesiseResult(
        val wav_path: String? = null,
        val duration_s: Double = 0.0,
        val error: String? = null,
    )
}
