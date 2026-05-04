# PLATFORMS.md — Per-Platform Implementation Notes

## Platform 1: Windows (Build First)

### Shell: PyQt6
- Framework: PyQt6 (LGPL) — mature, full Win32 access, no Electron overhead
- Entry point: `platform/windows/shell.py`
- Target: Windows 10/11, x86-64

### Hotkey / Overlay (Wispr-mode)
- Global hotkey registration: `keyboard` library (MIT) + Win32 `RegisterHotKey`
- Default hotkey: `Ctrl+Shift+Space` (configurable)
- Overlay window:
  - Frameless `QDialog`, `Qt.WindowStaysOnTopHint`
  - Positioned bottom-right (configurable)
  - Shows: waveform animation during recording, spinner during pipeline, transcript preview
  - Paste to active window: `pywin32` `SendInput` simulating Ctrl+V after clipboard write
- Overlay must not steal focus from the active application

### Audio Capture (Windows)
- Library: `sounddevice` (PortAudio backend, MIT)
- Sample rate: 16kHz, mono, int16
- Buffer size: 100ms chunks
- Device selection: user-configurable in settings; default = system default mic

### Diarization on Windows
- **Use WhisperX** as the unified STT+diarization layer (see ADR-005)
- WhisperX installs via pip and handles pyannote inside a virtualenv
- Do NOT attempt to install pyannote-audio standalone on Windows

### Distribution
- Packaging: PyInstaller → single-folder bundle
- First-run downloader runs as a separate step before main app launches
- Installer: NSIS or Inno Setup wrapper around PyInstaller bundle
- Models stored: `%APPDATA%\Vakya\models\`
- Data stored: `%APPDATA%\Vakya\data\`

### Windows-Specific Constraints
- `sounddevice` requires Microsoft C++ Redistributable — bundle in installer
- llama-cpp-python Windows wheel: use pre-built wheel from llama-cpp-python releases,
  not source build (source build requires MSVC, impractical for users)
- pyannote model gating: HF token stored in `%APPDATA%\Vakya\config\hf_token.txt`
  User enters token once during onboarding. Never transmitted anywhere.
  ⚠️ Stored as plain text in Phase 2. Phase 3 should migrate to Windows Credential Manager
  (`keyring` library, MIT) for secure encrypted storage.

---

## Platform 2: Android (Build Second)

### Shell Strategy
Two options evaluated — **Option B recommended:**

**Option A: Buildozer (Python for Android)**
- Pure Python shell. Same codebase.
- Kivy UI.
- Problem: llama-cpp-python ARM build is complex. CosyVoice2 has no Buildozer recipe.
- Risk: High. Build toolchain fragile.

**Option B: Kotlin shell + Python subprocess (Chaquopy)**
- Kotlin handles: UI, audio capture (AudioRecord API), foreground service
- Chaquopy embeds CPython 3.11 in the APK
- Python core pipeline called via Chaquopy bridge
- Models stored in app external storage (`/sdcard/Android/data/com.vakya.app/`)
- Risk: Medium. Chaquopy is production-grade (used in commercial apps).
- **Recommended: Option B**

### Audio Capture (Android)
- `AudioRecord` API in Kotlin foreground service
- 16kHz, mono, PCM_16BIT
- Foreground service required for background recording (notification shown)
- WAV written to app sandboxed cache dir (`context.cacheDir`) → passed to Python pipeline.
  This is permitted under the hard constraint — app cache is not accessible to other apps
  or the user's file browser. The WAV is deleted immediately after STT completes.

### STT on Android
- Primary: Moonshine v2 Base (~58MB) — via Python bridge
- Fallback: whisper.cpp JNI bindings (ggml-org/whisper.cpp has Android example)
- Model files stored in app external storage

### LLM on Android
- Phi-3 Mini Q4 on Android (4GB+ RAM phone): viable but tight
- Decision: **Rule-based cleanup default on Android.** Phi-3 Mini available as
  optional "Enhanced cleanup" toggle — user accepts it will use ~2.3GB RAM.
- This avoids killing the phone for users who just want quick transcription.

### TTS on Android
- Kokoro ONNX (Android ONNX Runtime) — primary
- No CosyVoice2 on Android Phase 1 (too heavy for default path)
- Voice cloning: deferred to Phase 2 on Android

### Distribution
- Google Play Store + direct APK download
- Min API level: 26 (Android 8.0) — required for foreground service audio
- Target API: 35 (Android 15)

---

## Platform 3: iOS (Build Third)

### Shell: Swift + BeeWare (Briefcase)
- Swift handles: UI (SwiftUI), audio (AVFoundation), App Store compliance
- BeeWare Briefcase embeds CPython for **orchestration only** — pipeline coordination,
  file I/O, vocab store reads, session logging, and output formatting.
- **All neural inference on iOS goes through CoreML — not Python.** This is the split:

```
iOS Architecture:
  Swift UI layer
      ↓
  Python (BeeWare) — orchestrator
      ↓ calls CoreML wrappers via ctypes/cffi
  CoreML models — actual inference
      whisper.cpp CoreML backend (STT)
      Phi-3 Mini via coremltools conversion (LLM)
      Kokoro ONNX → CoreML (TTS)
```

- The Python `STTEngine`, `LLMEngine`, `TTSEngine` abstract interfaces are satisfied
  by iOS-specific implementations that call CoreML internally.
- This means the pipeline orchestrator (`core/pipeline.py`) runs unchanged on iOS —
  only the engine implementations differ.
- Alternative considered: pure Swift with CoreML models — rejected because
  rewriting the entire pipeline orchestration in Swift duplicates all business logic.
  The Python orchestrator layer is lightweight enough to embed via BeeWare.

### iOS Hard Constraints (App Store)
- **Background processing:** iOS kills background apps. Audio recording must use
  `AVAudioSession` category `.record` with background mode entitlement.
  Only active recording is permitted in background — not inference.
  Therefore: inference runs after user stops recording and app is foregrounded.
- **CoreML requirement for on-device models:** All neural inference must go
  through CoreML for App Store approval and performance.
  - whisper.cpp has a working CoreML backend (`make coreml` target)
  - Moonshine v2: CoreML export evaluation REQUIRED before iOS build starts
  - Phi-3 Mini: Use Core ML conversion via `coremltools` — community conversions exist
  - CosyVoice2: Likely no CoreML export. Use Kokoro ONNX → CoreML instead.
- **Storage:** Models in `Application Support` directory (~2GB limit before
  app must use `NSFileProtectionComplete` entitlement)

### Audio Capture (iOS)
- `AVAudioEngine` with tap on input node
- 16kHz, mono, PCM Float32 → convert to Int16 for Whisper
- `AVAudioSession` `.record` category set before capture starts

### Distribution
- App Store submission: requires Apple Developer account ($99/yr)
- TestFlight for beta distribution
- Alternative: Direct IPA for enterprise/sideload (avoids App Store constraints)

---

## Raspberry Pi 5

Not a formal build target but a supported configuration.
Runs the Windows/Linux Python pipeline directly. No platform shell needed.
User interface: headless CLI or simple Tkinter window.

```bash
# RPi entry point
python -m vakya.cli --mode farm_log --output stdout
```

RAM profile: See MODELS.md — RPi fallback chain (whisper.cpp base.en + Piper).
