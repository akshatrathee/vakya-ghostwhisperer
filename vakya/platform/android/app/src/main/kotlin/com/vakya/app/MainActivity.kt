package com.vakya.app

import android.Manifest
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.google.android.material.bottomsheet.BottomSheetDialog
import com.google.android.material.button.MaterialButton
import com.google.android.material.switchmaterial.SwitchMaterial
import com.vakya.app.databinding.ActivityMainBinding

/**
 * Main activity — bottom sheet recording control.
 *
 * UI states:
 *   IDLE       — FAB shows mic icon, transcript area shows last result
 *   RECORDING  — FAB shows stop icon, status "Recording…"
 *   PROCESSING — FAB disabled, status "Transcribing…"
 */
class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private var isRecording = false

    private val resultReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            val text = intent.getStringExtra(AudioRecordService.EXTRA_RESULT) ?: ""
            onTranscriptReady(text)
        }
    }

    // Mic permission launcher
    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { grants ->
        val micGranted = grants[Manifest.permission.RECORD_AUDIO] == true
        if (micGranted) toggleRecording()
        else Toast.makeText(this, "Microphone permission required", Toast.LENGTH_LONG).show()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.fabRecord.setOnClickListener {
            if (isRecording) stopRecording() else checkPermissionAndRecord()
        }

        binding.btnSettings.setOnClickListener { showSettingsSheet() }

        registerReceiver(
            resultReceiver,
            IntentFilter(AudioRecordService.ACTION_WAV_READY),
            RECEIVER_NOT_EXPORTED,
        )
    }

    override fun onDestroy() {
        super.onDestroy()
        unregisterReceiver(resultReceiver)
    }

    // ------------------------------------------------------------------
    // Recording control
    // ------------------------------------------------------------------

    private fun checkPermissionAndRecord() {
        val needed = mutableListOf(Manifest.permission.RECORD_AUDIO)
        if (Build.VERSION.SDK_INT >= 33) needed += Manifest.permission.POST_NOTIFICATIONS

        val missing = needed.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isEmpty()) toggleRecording() else permissionLauncher.launch(missing.toTypedArray())
    }

    private fun toggleRecording() {
        if (isRecording) stopRecording() else startRecording()
    }

    private fun startRecording() {
        isRecording = true
        binding.fabRecord.setImageResource(android.R.drawable.ic_media_pause)
        binding.tvStatus.text = "Recording…"
        binding.tvTranscript.text = ""

        startForegroundService(Intent(this, AudioRecordService::class.java).apply {
            action = AudioRecordService.ACTION_START
        })
    }

    private fun stopRecording() {
        isRecording = false
        binding.fabRecord.isEnabled = false
        binding.tvStatus.text = "Transcribing…"

        startService(Intent(this, AudioRecordService::class.java).apply {
            action = AudioRecordService.ACTION_STOP
        })
    }

    // ------------------------------------------------------------------
    // Result
    // ------------------------------------------------------------------

    private fun onTranscriptReady(text: String) {
        binding.fabRecord.isEnabled = true
        binding.fabRecord.setImageResource(android.R.drawable.ic_btn_speak_now)
        binding.tvStatus.text = "Tap mic to record"
        binding.tvTranscript.text = text

        // Copy to clipboard
        val clip = android.content.ClipData.newPlainText("Vakya transcript", text)
        val cm = getSystemService(CLIPBOARD_SERVICE) as android.content.ClipboardManager
        cm.setPrimaryClip(clip)
        Toast.makeText(this, "Copied to clipboard", Toast.LENGTH_SHORT).show()
    }

    // ------------------------------------------------------------------
    // Settings bottom sheet
    // ------------------------------------------------------------------

    private fun showSettingsSheet() {
        val sheet = BottomSheetDialog(this)
        val view = LayoutInflater.from(this).inflate(R.layout.sheet_settings, null)
        sheet.setContentView(view)

        val switchEnhanced = view.findViewById<SwitchMaterial>(R.id.switch_enhanced_cleanup)
        switchEnhanced.setOnCheckedChangeListener { _, checked ->
            VakyaBridge.setEnhancedCleanup(checked)
            val label = if (checked) "Phi-3 Mini (uses ~2.3 GB RAM)" else "Rule-based (fast)"
            view.findViewById<TextView>(R.id.tv_cleanup_label).text = label
        }

        sheet.show()
    }
}
