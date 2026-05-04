# PROGRESS.md — Vakya Build Log

**Read this file at the start of every new Claude session before writing any code.**  
Maintained alongside the codebase. Update after every sprint.

---

## Sprint Status

| Sprint | Goal | Status | Tests |
|--------|------|--------|-------|
| 1 | Core pipeline CLI (VAD→STT→LLM→Output) | ✅ Complete | 14/14 |
| 2 | STT upgrade + diarization + voice profiles | ✅ Complete | 45/45 (+3 skip) |
| 3 | TTS + voice cloning + on-demand synthesis | ✅ Complete | 66/66 (+3 skip) |
| 4 | Windows PyQt6 UI (traditional + hotkey) | ✅ Complete | 86/86 (+3 skip) |
| 5 | Onboarding + model downloader UI | ✅ Complete | 104/104 (+3 skip) |
| 6 | Android port (Kotlin + Chaquopy) | ✅ Complete | 133/133 (+3 skip) |
| 7 | iOS port (Swift + CoreML) | ✅ Complete | 176/176 (+3 skip) |

---

## Files Built (Sprint 1–3)

```
vakya/
├── CLAUDE.md                          ← updated v3.0
├── PROGRESS.md                        ← this file
├── cli.py                             ← transcription + TTS + benchmark CLI
├── __init__.py / __main__.py
├── config/
│   ├── default.yaml
│   └── hardware_profiles.yaml
├── core/
│   ├── audio_capture.py               ← abstract interface + FileAudioCapture stub
│   ├── pipeline.py                    ← run() + synthesise() orchestrators
│   ├── vad.py                         ← Silero VAD + energy fallback
│   ├── stt/
│   │   ├── base.py                    ← STTEngine interface, STTResult, STTSegment
│   │   ├── whisper_cpp.py             ← bundled model (Sprint 1 default)
│   │   ├── faster_whisper.py          ← primary desktop (Sprint 2)
│   │   ├── moonshine.py               ← mobile primary
│   │   └── qwen3_asr.py               ← Hindi priority
│   ├── llm/
│   │   ├── base.py                    ← LLMEngine interface, CleanupMode, system prompts
│   │   ├── chunker.py                 ← 2800-token chunks, 200-token overlap, reassembly
│   │   ├── phi3_mini.py               ← Phi-3 Mini + RuleBasedEngine fallback
│   │   └── wiki_ingest.py             ← Phase 3 placeholder
│   ├── diarizer/
│   │   ├── base.py                    ← Diarizer interface, DiarSegment
│   │   ├── whisperx.py                ← Windows primary (STT+diarize combined)
│   │   └── pyannote.py                ← Linux/macOS primary
│   ├── tts/
│   │   ├── base.py                    ← TTSEngine interface
│   │   ├── engine_factory.py          ← hw-tier engine selector + ADR-004 gate
│   │   ├── cosyvoice2.py              ← primary desktop + zero-shot cloning
│   │   ├── kokoro.py                  ← ONNX fallback (minimum spec)
│   │   ├── piper.py                   ← RPi fallback
│   │   └── omnivoice.py               ← ADR-004 challenger + benchmark_rtf()
│   ├── voice_profile/
│   │   ├── store.py                   ← read/write profiles JSON
│   │   └── extractor.py               ← best-clip selection, dB-variance quality score
│   ├── vocab/
│   │   ├── store.py                   ← load/save/extract_new_terms/get_vocab_hint
│   │   └── shortcut_expander.py       ← Phase 3 placeholder
│   └── output/
│       ├── formatter.py               ← mode headers, whitespace normalisation, display tags
│       ├── router.py                  ← clipboard + session .md log + vocab extraction
│       ├── session_log.py             ← {session_id}.json matching session.schema.json
│       └── audio_player.py            ← sounddevice → playsound → shell fallback
├── installer/
│   ├── download_models.py             ← resumable downloader, SHA256 verify, manifest write
│   └── model_manifest.yaml            ← all model URLs, sizes, tiers
├── platform/
│   ├── windows/shell.py       ← PyQt6 MainWindow + WaveformWidget + TranscriptPanel
│   ├── windows/audio_win.py   ← WindowsAudioCapture (sounddevice, 16kHz mono)
│   ├── windows/hotkey.py      ← HotkeyThread (Win32 RegisterHotKey, Ctrl+Shift+Space)
│   ├── windows/overlay.py     ← OverlayWindow (280×80, frameless, bottom-right, always-on-top)
│   └── windows/onboarding.py  ← 7-screen PyQt6 wizard + DownloadWorker + first-run detection
│   ├── android/
│   │   ├── audio_android.py       ← AndroidAudioCapture (Chaquopy AudioRecord bridge)
│   │   ├── pipeline_bridge.py     ← PipelineBridge (JSON API for Kotlin)
│   │   ├── main.py                ← Chaquopy init entry point
│   │   ├── settings.gradle.kts   ← Gradle root settings
│   │   ├── build.gradle.kts      ← Root plugins (Android + Kotlin + Chaquopy 15.0.1)
│   │   └── app/
│   │       ├── build.gradle.kts  ← App module (minSdk 26, Chaquopy Python 3.11)
│   │       └── src/main/
│   │           ├── AndroidManifest.xml
│   │           ├── kotlin/com/vakya/app/
│   │           │   ├── VakyaApplication.kt  ← Chaquopy init + appScope
│   │           │   ├── VakyaBridge.kt        ← Kotlin↔Python singleton
│   │           │   ├── AudioRecordService.kt ← Foreground service + WAV mux
│   │           │   └── MainActivity.kt       ← Bottom sheet recording UI
│   │           └── res/layout|values/        ← Dark Material theme + layouts
│   └── ios/
│       ├── audio_ios.py          ← iOSAudioCapture (AVAudioEngine bridge)
│       ├── pipeline_bridge.py    ← iOSPipelineBridge (JSON API for Swift)
│       ├── main.py               ← BeeWare init entry point
│       ├── project.yml           ← XcodeGen spec
│       ├── Makefile              ← build shortcuts
│       ├── coreml/
│       │   ├── stt_coreml.py     ← CoreMLSTTEngine (whisper.cpp ctypes)
│       │   ├── llm_coreml.py     ← CoreMLLLMEngine (Phi-3 via coremltools)
│       │   └── tts_coreml.py     ← CoreMLTTSEngine (Kokoro ONNX→CoreML)
│       └── Sources/Vakya/
│           ├── VakyaApp.swift    ← @main App + BeeWare Python.shared.initialize()
│           ├── VakyaBridge.swift ← Swift↔Python singleton (PythonKit)
│           ├── AudioRecorder.swift ← AVAudioEngine Float32→Int16 + WAV mux
│           └── ContentView.swift ← SwiftUI recording UI + waveform + settings
├── tests/
│   ├── create_fixtures.py             ← generates silence/tone/speech-like WAVs
│   ├── fixtures/                      ← silence_5s, tone_30s, speech_like_30s, 2min WAVs
│   ├── test_llm_chunker.py            ← 7 tests
│   ├── test_vocab_store.py            ← 7 tests
│   ├── test_diarizer.py               ← 6 tests
│   ├── test_voice_profile.py          ← 8 tests
│   ├── test_output.py                 ← 9 tests
│   ├── test_vad.py                    ← 4 tests (3 skip if fixtures missing)
│   ├── test_stt_engines.py            ← 4 tests (3 skip if model missing)
│   ├── test_pipeline.py               ← 2 tests (1 skip if model missing)
│   ├── test_tts.py                    ← 21 tests
│   ├── test_windows_ui.py             ← 20 tests (Sprint 4)
│   ├── test_onboarding.py             ← 18 tests (Sprint 5)
│   ├── test_android.py               ← 29 tests (Sprint 6)
│   └── test_ios.py                   ← 43 tests (Sprint 7)
├── docs/           ← ARCHITECTURE.md, PIPELINE.md, MODELS.md, PLATFORMS.md,
│                      ONBOARDING.md, BUILD_SEQUENCE.md
├── decisions/      ← ADR-001, ADR-002-006
└── schemas/        ← session.schema.json, voice_profile.schema.json, vocab_store.schema.json
```

---

## Known Issues & Deferred Decisions

### 🔴 Blocked / Must Resolve Before Ship

| # | Issue | Location | Notes |
|---|-------|----------|-------|
| ~~B1~~ | ~~WhisperX requires `HF_TOKEN` env var. First-run would fail silently if not set.~~ | ✅ Fixed | `_load_hf_token()` in `pipeline.py` reads `config/hf_token.txt` and injects into env at startup. `whisperx.py` warns explicitly and skips diarization (returns `[]`) instead of crashing when token absent. |
| ~~B2~~ | ~~`faster_whisper.py` reads model from a hardcoded relative path~~ | ✅ Fixed | `_MODEL_DIR` now uses `Path(__file__).resolve()` — absolute, cwd-independent |

### 🟡 Deferred / Known Gaps

| # | Item | Deferred to | Notes |
|---|------|-------------|-------|
| D1 | OmniVoice CPU RTF benchmark not run | Phase 3 | Run `python -m vakya --benchmark-omnivoice` on target hardware. CLI prints exact lines to paste into `engine_factory.py`. `engine_factory.py` now logs a WARNING at startup when `OMNIVOICE_CPU_RTF is None`. |
| ~~D2~~ | ~~`faster_whisper.py` avg_logprob confidence normalisation~~ | ✅ Fixed | `confidence = max(0.0, 1.0 + avg_logprob / 10.0)` |
| ~~D3~~ | ~~`platform/windows/audio_win.py` — live mic capture not implemented~~ | ✅ Fixed | `WindowsAudioCapture` implemented with `sounddevice`, registered as "windows" |
| ~~D4~~ | ~~`models/manifest.json` — not written at first run. Pipeline returned `{}` silently.~~ | ✅ Fixed | `pipeline.py:run()` now logs a WARNING with install instructions when `manifest.json` is absent. |
| ~~D5~~ | ~~`numpy` missing from core deps~~ | ✅ Fixed | Added `numpy>=1.24` + `pyperclip>=1.8` to `pyproject.toml` core deps |
| D6 | `wiki_ingest.py` and `shortcut_expander.py` Phase 3 placeholders are not imported in `pipeline.py`. `wiki_ingest` is called but `shortcut_expander` is not wired in. | Phase 3 | Acceptable for now |
| S1 | HF token stored as plain text at `config/hf_token.txt`. On shared Windows machines, other local users can read it. | Phase 3 | Migrate to `keyring` library (Windows Credential Manager) — `pip install keyring`. Acceptable for Phase 2 single-user installs. Do NOT ship to enterprise / multi-user environments without this fix. |

### 🟢 Expected Skips in Test Suite

| Test | Skip Reason | How to Unblock |
|------|-------------|----------------|
| `test_stt_engines.py::test_whisper_cpp_english` | `models/stt/whisper-base-en.bin` absent | Run `download_models.py --tier bundled` |
| `test_stt_engines.py::test_faster_whisper_english` | `models/stt/faster-whisper-large-v3-turbo` absent | Run `download_models.py --tier recommended` |
| `test_pipeline.py::test_pipeline_full_cli_path` | Same as above | Same as above |

---

## Sprint 7 Complete — iOS Port (Swift + BeeWare + CoreML)

**Date:** April 27, 2026
**Tests:** 176 passed, 3 skipped (model-weight skips — unchanged)

### What was built

| File | Description |
|------|-------------|
| `platform/ios/audio_ios.py` | `iOSAudioCapture` — full bridge implementing `AudioCapture`; Swift sets WAV path via `set_wav_path()`, `delete_wav()` enforces audio-not-persisted constraint |
| `platform/ios/coreml/stt_coreml.py` | `CoreMLSTTEngine` — whisper.cpp CoreML backend via ctypes; reads `libwhisper.dylib` from app Frameworks/; graceful `FileNotFoundError` on non-iOS |
| `platform/ios/coreml/llm_coreml.py` | `CoreMLLLMEngine` — Phi-3 Mini via `coremltools.MLModel`; falls back to `RuleBasedEngine` when model absent |
| `platform/ios/coreml/tts_coreml.py` | `CoreMLTTSEngine` — Kokoro ONNX→CoreML via coremltools; writes silent WAV when model absent |
| `platform/ios/pipeline_bridge.py` | `iOSPipelineBridge` — Swift-callable adapter; exposes `transcribe()`, `synthesise()`, `set_enhanced_cleanup()`, `set_mode()`, `warm_up()` as JSON-returning methods |
| `platform/ios/main.py` | BeeWare init entry point; `init(config_dir, models_dir)` called once from `VakyaApp.init` |
| `platform/ios/project.yml` | XcodeGen spec — generates Vakya.xcodeproj; avoids committing binary pbxproj |
| `platform/ios/Makefile` | Build shortcuts: `gen`, `build`, `run`, `testflight`, `whisper-coreml`, `phi3-convert` |
| `platform/ios/Sources/Vakya/AudioRecorder.swift` | `AVAudioEngine` capture; Float32→Int16 converter; WAV mux; calls `VakyaBridge.wavReady()` |
| `platform/ios/Sources/Vakya/VakyaBridge.swift` | Singleton Swift↔Python bridge via PythonKit/BeeWare; `@Published` state for SwiftUI |
| `platform/ios/Sources/Vakya/VakyaApp.swift` | `@main App`; initialises BeeWare Python runtime before first view renders |
| `platform/ios/Sources/Vakya/ContentView.swift` | SwiftUI recording UI — mic FAB, waveform, transcript display, settings sheet (enhanced cleanup toggle) |
| `platform/ios/Resources/Info.plist` | `NSMicrophoneUsageDescription`, `UIBackgroundModes: audio`, `NSAppTransportSecurity: deny all` |
| `platform/ios/Resources/Vakya.entitlements` | `com.apple.developer.avfoundation.allow-background-audio` |
| `tests/test_ios.py` | 43 new tests — `iOSAudioCapture`, all three CoreML engines, `iOSPipelineBridge`, `main.init()` |

**iOS STT:** whisper.cpp CoreML backend (ggml-base.en, ~147 MB)
**iOS LLM:** Rule-based default; Phi-3 Mini CoreML opt-in (~1.8 GB RAM warning shown)
**iOS TTS:** Kokoro ONNX→CoreML (~84 MB)
**Audio constraint:** WAV written to `tmp/` directory (app-sandboxed), deleted immediately after STT
**Background:** AVAudioSession `.record` category + background mode entitlement allows capture; inference runs after foreground return (App Store compliant)

**Pre-requisites before device testing:**
- `make whisper-coreml` — build libwhisper.dylib with CoreML backend
- `make phi3-convert` — convert Phi-3 Mini to mlpackage (optional, ~20 min)
- Apple Developer account for signing

**Build command:**
```
cd vakya/platform/ios
xcodegen generate       # generates Vakya.xcodeproj
make build              # simulator build
make testflight         # release archive
```

---

## Sprint 6 Complete — Android Port (Kotlin + Chaquopy)

**Date:** April 27, 2026
**Tests:** 133 passed, 3 skipped (model-weight skips — unchanged)

### What was built

| File | Description |
|------|-------------|
| `platform/android/audio_android.py` | `AndroidAudioCapture` — full bridge implementing `AudioCapture`; Kotlin sets WAV path via `set_wav_path()`, Python reads via `get_wav_path()`; `delete_wav()` enforces audio-not-persisted constraint |
| `platform/android/pipeline_bridge.py` | `PipelineBridge` — Kotlin-callable adapter around `core/pipeline`; exposes `transcribe()`, `synthesise()`, `set_enhanced_cleanup()`, `warm_up()` as JSON-returning methods |
| `platform/android/main.py` | Chaquopy entry point; `init(config_dir, models_dir)` called from `VakyaApplication.onCreate()` |
| `platform/android/settings.gradle.kts` | Root Gradle settings |
| `platform/android/build.gradle.kts` | Root build file — Android + Kotlin + Chaquopy 15.0.1 plugins |
| `platform/android/app/build.gradle.kts` | App module — minSdk 26, targetSdk 35, Chaquopy Python 3.11, pip deps (moonshine-onnx, onnxruntime, numpy, soundfile) |
| `platform/android/app/src/main/AndroidManifest.xml` | RECORD_AUDIO, FOREGROUND_SERVICE_MICROPHONE permissions; declares `AudioRecordService` with `foregroundServiceType="microphone"` |
| `platform/android/app/src/main/kotlin/…/VakyaApplication.kt` | `Application` subclass — starts Chaquopy, calls `VakyaBridge.init()` async |
| `platform/android/app/src/main/kotlin/…/VakyaBridge.kt` | Kotlin singleton wrapping Chaquopy `PyObject`; Gson-deserialises JSON results into data classes |
| `platform/android/app/src/main/kotlin/…/AudioRecordService.kt` | Foreground service — `AudioRecord` 16kHz mono PCM_16BIT; writes WAV to `cacheDir`; calls `VakyaBridge.transcribe()`; broadcasts result via `ACTION_WAV_READY` |
| `platform/android/app/src/main/kotlin/…/MainActivity.kt` | Bottom sheet recording UI — mic FAB, transcript display, clipboard copy, settings sheet (enhanced cleanup toggle) |
| `platform/android/app/src/main/res/layout/activity_main.xml` | Dark-themed ConstraintLayout with scrollable transcript and FAB |
| `platform/android/app/src/main/res/layout/sheet_settings.xml` | Bottom sheet settings — enhanced cleanup switch |
| `platform/android/app/src/main/res/values/{strings,colors,themes}.xml` | Dark Material theme resources |
| `tests/test_android.py` | 29 new tests — `AndroidAudioCapture`, `PipelineBridge`, `main.init()` |

**Android STT:** Moonshine v2 Base (~58 MB, ~200 MB RAM)
**Android LLM:** Rule-based default; Phi-3 Mini opt-in via settings toggle (~2.3 GB RAM warning shown)
**Android TTS:** Kokoro ONNX via Android ONNX Runtime
**Audio constraint:** WAV written to `cacheDir` (app-sandboxed), deleted immediately after STT — satisfies zero-external-audio hard constraint

**Build command (requires Android Studio + NDK):**
```
cd vakya/platform/android
./gradlew assembleDebug
```

---

## Sprint 5 Complete — Onboarding + Model Downloader UI

**Date:** April 27, 2026  
**Tests:** 104 passed, 3 skipped (model-weight skips — unchanged)

### What was built

| File | Description |
|------|-------------|
| `platform/windows/onboarding.py` | 7-screen PyQt6 wizard: Welcome → Hardware detect → Language → Mic test → Model download → HF token → Mode select |
| `platform/windows/onboarding.py::DownloadWorker` | QThread wrapping `installer/download_models.py`; emits `progress`, `model_done`, `finished` Qt signals |
| `platform/windows/onboarding.py::is_first_run()` | Checks `models/manifest.json` absence + `onboarding_complete` flag in config |
| `platform/windows/shell.py` | `launch()` now checks `is_first_run()` — shows wizard before MainWindow on first run |
| `installer/vakya.spec` | PyInstaller one-folder build spec; bundles whisper-base-en.bin, config, schemas |
| `installer/version_info.txt` | Windows VERSIONINFO resource (embedded in Vakya.exe) |
| `vakya/tests/test_onboarding.py` | 18 new tests for all Sprint 5 modules |

**Config written by onboarding:** `config/default.yaml` — `hardware_tier`, `stt.language`, `default_mode`, `onboarding_complete: true`

**HF token stored:** `config/hf_token.txt` (local only, never transmitted)

**Build command (after `pip install pyinstaller`):**
```
pyinstaller vakya/installer/vakya.spec
```

---

## Sprint 4 Complete — Windows PyQt6 UI

**Date:** April 27, 2026  
**Tests:** 86 passed, 3 skipped (model-weight skips — unchanged from Sprint 3)

### What was built

| File | Description |
|------|-------------|
| `platform/windows/audio_win.py` | `WindowsAudioCapture` — sounddevice 16kHz mono live mic, level callback for waveform, temp WAV flush |
| `platform/windows/shell.py` | `MainWindow` — PyQt6 dark-themed traditional mode: record button, waveform, transcript panel, copy/save; hosts overlay via `_on_hotkey` |
| `platform/windows/hotkey.py` | `HotkeyThread` — Win32 `RegisterHotKey` Ctrl+Shift+Space in background QThread, emits `activated` signal |
| `platform/windows/overlay.py` | `OverlayWindow` — 280×80 frameless always-on-top bottom-right overlay; states: recording (waveform) → processing (spinner) → done (tick + preview); auto-paste via Win32 keyboard event |
| `vakya/cli.py` | `--ui` flag added; routes to `shell.launch()` |
| `vakya/tests/test_windows_ui.py` | 20 new unit tests for all Sprint 4 modules |

**Bugs fixed in Sprint 4:**
- B2: `faster_whisper.py` `_MODEL_DIR` now absolute (Path.resolve())
- D3: Live mic capture implemented (`WindowsAudioCapture`)

**Launch:**
```
pip install PyQt6 sounddevice pywin32   ← already installed
python -m vakya --ui
```

---

## Sprint 4 Plan (Windows PyQt6 UI)

Build order per `docs/BUILD_SEQUENCE.md`:

1. `platform/windows/shell.py` — PyQt6 app skeleton, traditional mode first
2. `platform/windows/audio_win.py` — `sounddevice` mic capture implementing `AudioCapture`
3. Traditional mode wired end-to-end: Record → pipeline.run() → display transcript
4. `platform/windows/hotkey.py` — Win32 global hotkey (`Ctrl+Shift+Space`, configurable)
5. `platform/windows/overlay.py` — 280×80px frameless bottom-right overlay, always-on-top
6. Wispr-mode: hotkey → record → pipeline.run() → paste to active window

**Sprint 4 test:** Dictate 30-second note via `Ctrl+Shift+Space`. Clean text appears in open Notepad.

**Install before Sprint 4:**
```
pip install PyQt6 sounddevice pywin32
```

---

## How to Start a New Session

1. Read `vakya/CLAUDE.md` (project identity + constraints)
2. Read this file (`PROGRESS.md`) — current state, what to do next
3. Run `python -m pytest vakya/tests/ -q` — confirm baseline is still green
4. Check `Known Issues` above before touching affected modules
5. Proceed with next sprint from `docs/BUILD_SEQUENCE.md`
