# Vakya — Offline Voice Intelligence

> **Your voice, your device, your data.**

Vakya (Sanskrit: वाक्य, *utterance*) is a fully offline, cross-platform
speech-to-text application that does what **Wispr Flow** does — live dictation
with AI cleanup — but runs **100% on-device** with no internet, no
subscriptions, and no cloud dependency.

It is built for people in low-connectivity environments: farmers dictating field
notes, rural clinicians, researchers in the field, and anyone who wants
Wispr-grade dictation without sending their voice to a server.

---

## Why This Exists

Every mainstream dictation tool — Whisper API, Otter, Fireflies, Wispr Flow —
requires an internet connection and sends audio to a third-party cloud. For a
farmer in a low-connectivity area, a clinician handling sensitive patient notes,
or anyone who simply does not want their voice recorded by a corporation, these
tools are not an option.

Vakya solves this with zero compromise on capability:

| | Wispr Flow | Otter.ai | **Vakya** |
|---|---|---|---|
| Offline | ✗ | ✗ | **✓** |
| No subscription | ✗ | ✗ | **✓** |
| Speaker labels | ✓ | ✓ | **✓** |
| AI text cleanup | ✓ | ✓ | **✓** |
| Voice cloning / TTS | ✓ | ✗ | **✓** |
| Hindi / Indic languages | Partial | ✗ | **✓** |
| Android | ✗ | ✓ | **✓** |
| iOS | ✓ | ✓ | **✓** |
| GPU required | Cloud | Cloud | **Never** |
| Audio stored | Server | Server | **Never** |

---

## Hard Constraints

These never change. Every line of code must satisfy all four.

1. **Zero network calls during operation.** Internet may only be used for
   one-time model downloads, with explicit user opt-in.
2. **No GPU requirement.** CPU-only inference on consumer hardware
   (₹25,000–40,000 laptops, mid-range Android/iOS phones).
3. **Audio never persists outside the app sandbox.** Raw audio lives in RAM
   only during transcription, then is discarded. On mobile, a temp WAV is
   written to the app's sandboxed cache directory as a pipeline intermediary
   and deleted immediately after STT completes.
4. **Free and open source stack.** Apache 2.0, MIT, or BSD-2-Clause licenses
   only throughout the entire dependency tree.

---

## Platform Support

| Platform | Shell | Status | Build command |
|---|---|---|---|
| **Windows 10/11** | PyQt6 | ✅ Shipped | `python -m vakya --ui` |
| **Android 8.0+** | Kotlin + Chaquopy | ✅ Shipped | `cd platform/android && ./gradlew assembleDebug` |
| **iOS 16+** | Swift + BeeWare + CoreML | ✅ Shipped | `cd platform/ios && xcodegen generate && make build` |
| Raspberry Pi 5 | Headless CLI | ✅ Supported | `python -m vakya --mode farm_log` |

---

## What It Does

### Wispr Mode (hotkey overlay)
Press `Ctrl+Shift+Space` (configurable). A small overlay appears. Speak.
Release the hotkey. Your clean, formatted text is pasted directly into whatever
window is active — a browser, Word, a terminal, anything. Target: under 5
seconds for a voice note under 60 seconds.

### Traditional Mode (full app window)
Open the app. Tap Record. Speak for as long as you need. Stop. The app shows a
formatted transcript with speaker labels, copies it to the clipboard, and saves
a session log. Works on Windows, Android, and iOS.

### Output Modes
The LLM cleanup pass is mode-aware. Set the mode once; the same audio produces
different formatted output.

| Mode | Output format |
|---|---|
| **Dictation** | Clean prose, fillers removed, self-corrections resolved |
| **Notes** | Bullet points with sub-bullets |
| **Farm Log** | Structured table: Date / Activity / Observations / Action Items |
| **Meeting** | Meeting notes: Attendees / Key Points / Decisions / Action Items |

### Voice Cloning + TTS
Record a 10–30 second clip of any speaker and Vakya builds a voice profile.
Later, ask Vakya to read back any text in that voice — 100% on-device.

### Personal Vocabulary Store
Vakya learns proper nouns, domain terms, and names from your transcripts.
These are injected as vocabulary hints on the next recording, improving
accuracy for jargon, place names, and people without retraining any model.

---

## Architecture

### Strategy: Python Core + Native Shells

The inference pipeline (VAD → STT → Diarization → LLM cleanup → TTS) is
written once in Python and runs identically on all platforms. Platform-native
shells handle UI, audio I/O, and OS integration.

```
┌──────────────────────────────────────────────────────────────┐
│                       Platform Shell                          │
│  Windows (PyQt6)  │  Android (Kotlin+Chaquopy)  │  iOS (Swift) │
├──────────────────────────────────────────────────────────────┤
│                   Vakya Core  (Python 3.11+)                  │
│          AudioCapture → Pipeline → OutputRouter               │
├─────────────────┬─────────────────┬──────────────────────────┤
│   STT Engine    │   LLM Engine    │   TTS + Clone Engine     │
│  faster-whisper │  llama.cpp      │  CosyVoice2 / Kokoro     │
│  Moonshine v2   │  Phi-3 Mini     │  Piper (RPi)             │
│  whisper.cpp    │  Rule-based     │                          │
│  Qwen3-ASR      │                 │                          │
├─────────────────┴─────────────────┴──────────────────────────┤
│              Diarization  (WhisperX / pyannote 3.1)           │
│              VAD          (Silero)                            │
├──────────────────────────────────────────────────────────────┤
│                    Local Storage Layer                         │
│    voice_profiles/    vocab_store.json    sessions/           │
└──────────────────────────────────────────────────────────────┘
```

**Why Python core, not three native pipelines?**  
faster-whisper, llama-cpp-python, pyannote, and CosyVoice2 all have
first-class Python bindings. One pipeline test suite covers all platforms. All
platform bugs are pipeline bugs, not platform-divergence bugs.

**Why native shells, not Flutter/React Native?**  
Low-latency audio capture requires direct OS API access. The Windows hotkey
overlay requires Win32 `RegisterHotKey`. iOS background recording requires
`AVFoundation` directly. The UI is thin — the complexity is in the inference
pipeline, not the views.

**iOS exception:** iOS App Store rules require all neural inference through
CoreML. The Python core handles orchestration only on iOS; model inference is
CoreML via ctypes (whisper.cpp) and `coremltools` (Phi-3 Mini, Kokoro).

---

## The Inference Pipeline

Every recording — 10 seconds or 4 hours — flows through this exact sequence.

```
  Mic (16kHz mono PCM, RAM only — never written to disk as raw audio)
         │
  STEP 1 ▼  Voice Activity Detection
         Silero VAD  →  speech/silence segments
         Drops silence → 30-40% less STT work
         │
  STEP 2 ▼  Speech-to-Text Transcription
         STTEngine.transcribe(audio, vocab_hint=personal_vocab)
         → STTResult { text, segments[{start, end, text, confidence}], language }
         │
  STEP 3 ▼  Speaker Diarization
         Diarizer.diarize(audio)  →  speaker_id per segment
         Side effect: best audio clip per speaker saved to voice_profiles/
         │
  STEP 4 ▼  LLM Cleanup Pass
         Phi-3 Mini 3.8B Q4 (llama.cpp)
         Chunked at 2,800 tokens with 200-token speaker-preserving overlap
         Mode-aware system prompt (Dictation / Notes / Farm Log / Meeting)
         Fallback: regex filler removal (no model, 0MB RAM)
         │
    ┌────┴────┐
    │         │
  5a ▼       5b ▼  (parallel)
  Voice       Wiki Ingest
  Profile     (Phase 3)
  Update
         │
  STEP 6 ▼  Output Routing
         → Clipboard  (primary for Wispr-mode)
         → App window / overlay
         → sessions/{timestamp}_{mode}.md  (text only, no audio)
         → vocab_store.json  (new terms extracted, injected next session)
```

### Processing Times (8GB laptop, Intel i5, CPU only)

| Recording | VAD | STT | Diarization | LLM | **Total** |
|---|---|---|---|---|---|
| 5-min note | real-time | ~15s | ~5s | ~5s | **~30s** |
| 30-min meeting | real-time | ~90s | ~20s | ~15s | **~2m 30s** |
| 1-hour recording | real-time | ~3m | ~40s | ~30s | **~5m** |
| 4-hour session | real-time | ~12m | ~3m | ~2m | **~18m** |

---

## Model Inventory

### Speech-to-Text

| Model | Size | RAM | WER | Platforms | Notes |
|---|---|---|---|---|---|
| **faster-whisper Large-v3 Turbo int8** | 1.5 GB | ~3 GB | ~5% | Windows, Linux, macOS | Primary desktop — 6–8× faster than Whisper Large-v3 |
| **Moonshine v2 Base** | 58 MB | ~200 MB | ~10% | Android, iOS | Primary mobile — no 30s padding limit |
| **whisper.cpp base.en** | 140 MB | ~300 MB | ~7% | All | Bundled (onboarding); RPi / minimum spec |
| **Qwen3-ASR 0.6B** | 600 MB | ~1.5 GB | — | Desktop, Android | 52 languages; auto-selected when Hindi detected |

### Language Model (Cleanup)

| Model | Size | RAM | Notes |
|---|---|---|---|
| **Phi-3 Mini 3.8B Q4_K_M** | 2.3 GB | ~2.3 GB | Primary; via llama-cpp-python; 4K context window — always chunked |
| **Rule-based filler removal** | 0 MB | 0 MB | Fallback (minimum spec / RPi); regex only |

### Text-to-Speech

| Model | Size | RAM | Cloning | Platforms |
|---|---|---|---|---|
| **CosyVoice2 0.5B** | ~1 GB | ~1.5 GB | ✓ Zero-shot | Desktop |
| **Kokoro 82M ONNX** | ~300 MB | ~200 MB | ✗ | All (ONNX, CPU real-time) |
| **Piper** | ~60 MB | ~100 MB | ✗ | All (RPi primary) |

### Diarization

| Model | RAM | Platforms |
|---|---|---|
| **WhisperX** (faster-whisper + pyannote) | ~500 MB | Windows (unified layer) |
| **pyannote-audio 3.1** | ~500 MB | Linux, macOS |

---

## Hardware Tiers

Vakya auto-detects your hardware at first run and selects the appropriate model chain.

| Tier | Target | STT | LLM | TTS | Diarization | Peak RAM |
|---|---|---|---|---|---|---|
| **RPi** | Raspberry Pi 5 | whisper.cpp base.en | Rule-based | Piper | Off | ~940 MB |
| **Minimum** | 4 GB laptop, any CPU | whisper.cpp base.en | Rule-based | Kokoro | Off | ~3.4 GB |
| **Recommended** | 8 GB laptop, i5/Ryzen | faster-whisper Turbo | Phi-3 Mini | CosyVoice2 | WhisperX | ~8.1 GB |

---

## Getting Started

### Prerequisites

```bash
# Python 3.11+ required
py --version

# Install core dependencies
pip install -r requirements.txt
```

### Windows

```bash
# Download bundled models (whisper.cpp base.en — ~140MB, runs immediately)
py -m vakya.installer.download_models --tier bundled

# First run: launches 7-screen onboarding wizard, then MainWindow
py -m vakya --ui

# Or headless CLI
py -m vakya --input audio.wav --mode dictation

# TTS
py -m vakya --tts "This text will be spoken aloud." --voice SPEAKER_ID
```

### Android

```bash
cd platform/android

# Build debug APK (requires Android Studio + NDK)
./gradlew assembleDebug

# Install on connected device
./gradlew installDebug
```

**Dependencies bundled in APK:** CPython 3.11 (Chaquopy), moonshine-onnx,
onnxruntime, numpy, soundfile. Models download to external app storage
(`/sdcard/Android/data/com.vakya.app/files/models/`) at first run.

### iOS

```bash
cd platform/ios

# Prerequisites: Xcode 15+, xcodegen, Apple Developer account
brew install xcodegen

# Build whisper.cpp with CoreML backend (one-time, run on Mac)
make whisper-coreml

# Generate Xcode project and build
xcodegen generate
make build         # simulator
make testflight    # release archive
```

**Optional Phi-3 Mini CoreML conversion** (~20 min, needs `coremltools`):
```bash
make phi3-convert
```

### Raspberry Pi

```bash
# Headless CLI — same Python package, RPi tier auto-detected
python -m vakya --mode farm_log --output stdout
```

---

## Project Structure

```
vakya/
├── core/                        ← Platform-agnostic Python pipeline (tested on all platforms)
│   ├── pipeline.py              ← run() + synthesise() orchestrators
│   ├── audio_capture.py         ← Abstract AudioCapture interface
│   ├── vad.py                   ← Silero VAD
│   ├── stt/                     ← STTEngine interface + 4 implementations
│   ├── llm/                     ← LLMEngine interface, Phi-3 Mini, chunker
│   ├── tts/                     ← TTSEngine interface + CosyVoice2 / Kokoro / Piper
│   ├── diarizer/                ← Diarizer interface + WhisperX / pyannote
│   ├── voice_profile/           ← Speaker clip extraction + profile store
│   ├── vocab/                   ← Personal vocabulary store + hint injection
│   └── output/                  ← Mode-aware formatter + clipboard / file router
│
├── platform/
│   ├── windows/                 ← PyQt6 shell: MainWindow, hotkey, overlay, audio capture
│   ├── android/                 ← Python bridge (AudioAndroidCapture, PipelineBridge, main.py)
│   │   └── app/                 ← Kotlin/Gradle project (VakyaApplication, AudioRecordService,
│   │                               VakyaBridge, MainActivity)
│   └── ios/                     ← Python bridge (iOSAudioCapture, iOSPipelineBridge, main.py)
│       ├── coreml/              ← CoreML engine wrappers (STT/LLM/TTS via ctypes + coremltools)
│       └── Sources/Vakya/       ← Swift app (VakyaApp, VakyaBridge, AudioRecorder, ContentView)
│
├── installer/
│   ├── download_models.py       ← Resumable, SHA256-verified model downloader
│   ├── model_manifest.yaml      ← All model URLs, checksums, sizes, tier requirements
│   └── vakya.spec               ← PyInstaller Windows build spec
│
├── tests/                       ← 176 tests, 3 expected skips (model-weight skips)
├── docs/                        ← ARCHITECTURE.md, PIPELINE.md, MODELS.md, PLATFORMS.md,
│                                   ONBOARDING.md, BUILD_SEQUENCE.md
├── decisions/                   ← ADR-001 through ADR-006
├── schemas/                     ← JSON schemas for voice_profile, vocab_store, session
└── config/
    ├── default.yaml             ← Runtime configuration
    └── hardware_profiles.yaml  ← Tier auto-detection thresholds
```

---

## Core Tech Stack

| Layer | Technology | License | Notes |
|---|---|---|---|
| **Language** | Python 3.11+ | — | Core pipeline |
| **STT (desktop)** | faster-whisper | MIT | CTranslate2 backend, int8 quantisation |
| **STT (mobile)** | Moonshine v2 (ONNX) | Apache 2.0 | ~58 MB, no 30s padding limit |
| **STT (fallback)** | whisper.cpp | MIT | All platforms; CoreML backend for iOS |
| **STT (Hindi)** | Qwen3-ASR 0.6B | Apache 2.0 | 52 languages, Hinglish support |
| **VAD** | Silero VAD | MIT | Bundled with faster-whisper |
| **LLM cleanup** | Phi-3 Mini 3.8B | MIT | Via llama-cpp-python, Q4_K_M GGUF |
| **LLM runtime** | llama-cpp-python | MIT | CPU-only GGUF inference |
| **TTS (primary)** | CosyVoice2 0.5B | Apache 2.0 | Zero-shot voice cloning |
| **TTS (fallback)** | Kokoro 82M | Apache 2.0 | ONNX, CPU real-time, MOS 4.5 |
| **TTS (RPi)** | Piper | MIT | Extremely lightweight |
| **Diarization (Win)** | WhisperX | BSD-4 | STT + pyannote unified layer |
| **Diarization (nix)** | pyannote-audio 3.1 | MIT | HF token required (one-time) |
| **Windows UI** | PyQt6 | LGPL | Full Win32 access, no Electron overhead |
| **Android shell** | Kotlin + Chaquopy 15 | Commercial-free tier | CPython 3.11 embedded in APK |
| **iOS shell** | Swift + BeeWare | Apache 2.0 | PythonKit bridge; CoreML for inference |
| **iOS inference** | coremltools | BSD-3 | Phi-3 Mini + Kokoro → CoreML |
| **Windows installer** | PyInstaller + Inno Setup | MIT / LGPL | Single-folder bundle |
| **Config** | PyYAML | MIT | |
| **Audio capture** | sounddevice (Win) / AudioRecord API (Android) / AVAudioEngine (iOS) | MIT / Apache 2.0 / Apple | 16kHz mono PCM_16BIT |

---

## Configuration

All runtime behaviour is controlled by `config/default.yaml`. Hardware tier is
auto-detected at first run and written to `models/manifest.json`.

```yaml
hardware_tier: auto          # auto | minimum | recommended | rpi

stt:
  engine: faster_whisper     # faster_whisper | moonshine | whisper_cpp | qwen3_asr
  language: auto             # auto | en | hi | ...
  int8: true

llm:
  engine: phi3_mini          # phi3_mini | rule_based
  context_tokens: 4096
  chunk_overlap_tokens: 200  # speaker-preserving overlap between chunks

tts:
  engine: cosyvoice2         # cosyvoice2 | kokoro | piper

diarizer:
  engine: whisperx           # whisperx | pyannote
  enabled: true

output:
  default_mode: dictation    # dictation | notes | farm_log | meeting
  copy_to_clipboard: true
```

---

## Testing

```bash
# Run full test suite (176 tests)
py -m pytest vakya/tests/ -q

# Platform-specific
py -m pytest vakya/tests/test_android.py -v
py -m pytest vakya/tests/test_ios.py -v
py -m pytest vakya/tests/test_windows_ui.py -v

# Generate test fixtures (silence / tone / speech-like WAVs)
py vakya/tests/create_fixtures.py
```

**Test matrix:**

| Suite | Tests | Coverage |
|---|---|---|
| `test_pipeline.py` | 2 | Core orchestrator (1 model-weight skip) |
| `test_stt_engines.py` | 4 | STT engines (2 model-weight skips) |
| `test_llm_chunker.py` | 7 | Token chunking + overlap + reassembly |
| `test_vocab_store.py` | 7 | Personal vocabulary store |
| `test_diarizer.py` | 6 | Diarization interface |
| `test_voice_profile.py` | 8 | Speaker clip extraction + store |
| `test_output.py` | 9 | Formatter + router |
| `test_vad.py` | 4 | VAD wrapper |
| `test_tts.py` | 21 | TTS engines + voice cloning |
| `test_windows_ui.py` | 20 | PyQt6 shell + hotkey + overlay |
| `test_onboarding.py` | 18 | 7-screen wizard + download worker |
| `test_android.py` | 29 | Android audio bridge + PipelineBridge |
| `test_ios.py` | 43 | iOS audio bridge + CoreML engines + bridge |
| **Total** | **176 pass + 3 skip** | **3 skips are model-weight skips — expected in CI** |

All tests are runnable on any platform — no iOS device, Android device, or
model weights required for the test suite to pass.

---

## Onboarding (First Run — Windows)

The first time you run `vakya --ui`, a 7-screen wizard appears:

1. **Welcome** — introduces Vakya and its offline-first philosophy
2. **Hardware detection** — auto-selects model tier (minimum / recommended)
3. **Language** — sets primary language (English, Hindi, Auto)
4. **Mic test** — verify the microphone works before downloading
5. **Model download** — resumable background download with progress bar
6. **HF token** — optional; required only if you enable speaker diarization
7. **Mode select** — choose your default output mode

After onboarding, the main window opens. The wizard never runs again (tracked
via `onboarding_complete` flag in `config/default.yaml`).

---

## Roadmap

**Phase 2** (complete — all 7 sprints shipped):
- [x] Sprint 1: Core pipeline CLI (VAD → STT → LLM → Output)
- [x] Sprint 2: Diarization + voice profiles
- [x] Sprint 3: TTS + voice cloning
- [x] Sprint 4: Windows PyQt6 UI + hotkey overlay (Wispr-mode)
- [x] Sprint 5: Onboarding + model downloader
- [x] Sprint 6: Android (Kotlin + Chaquopy)
- [x] Sprint 7: iOS (Swift + BeeWare + CoreML)

**Phase 3** (planned):
- [ ] Obsidian wiki ingest — build a personal knowledge graph from your voice notes
- [ ] Voice shortcuts — "expand this" → expands an abbreviation in any active window
- [ ] Command mode — "rewrite this shorter", "translate to Hindi", etc.
- [ ] Mac support — the architecture already supports it; shell needs building
- [ ] Windows Credential Manager — migrate HF token from plaintext to `keyring`

---

## Privacy

Vakya is designed so that privacy is the default, not a setting.

- **No telemetry.** No analytics calls. No error reporting to a server.
- **No model telemetry.** All models run as local files — they make no
  network calls.
- **Audio discarded immediately.** Raw audio lives in RAM only during
  transcription. On mobile, a temp WAV is written to the app sandbox and
  deleted after STT returns — before the result is shown to the user.
- **Session logs are text only.** The `.md` files in `data/sessions/`
  contain transcripts and metadata — never audio or embeddings.
- **Voice profiles are local.** Speaker embedding vectors and reference
  clips are stored in `data/voice_profiles/` on your device only.
- **HF token stored locally.** If you enable diarization, the HuggingFace
  token is stored in `config/hf_token.txt` on your device only and is
  never transmitted anywhere. (Phase 3 will migrate this to OS credential
  manager.)

---

## Contributing

This project is in active development. The architecture docs in `docs/` and
decision records in `decisions/` explain every significant design choice.
Start there before opening a PR.

Key files to read first:
1. `docs/ARCHITECTURE.md` — system overview + platform strategy
2. `docs/PIPELINE.md` — exact data flow from mic to output
3. `docs/MODELS.md` — every model, its role, RAM budget, and fallback
4. `decisions/ADR-001-codebase-strategy.md` — why Python core + native shells

The core rule: **every inference engine implements a strict abstract interface**
(`STTEngine`, `LLMEngine`, `TTSEngine`, `Diarizer`). Swapping models requires
changing config, not application code.

---

## License

Vakya itself: **MIT License**

Third-party model and library licenses:
- faster-whisper: MIT
- Phi-3 Mini: MIT
- CosyVoice2: Apache 2.0
- Kokoro: Apache 2.0
- Piper: MIT
- Moonshine v2: Apache 2.0
- Qwen3-ASR: Apache 2.0
- pyannote-audio: MIT
- WhisperX: BSD-4-Clause
- llama-cpp-python: MIT
- PyQt6: LGPL
- Chaquopy: Commercial-free tier for open source projects
- BeeWare: Apache 2.0

All dependencies are permissive and commercially compatible. No GPL dependencies.

---

*Built for the farmer with bad internet and a voice full of knowledge.*
