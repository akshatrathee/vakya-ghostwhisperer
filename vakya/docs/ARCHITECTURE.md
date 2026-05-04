# ARCHITECTURE.md — System Overview

## 1. Codebase Strategy

**Decision: Python core + platform-native shells**

The inference pipeline (STT, LLM, TTS, diarization) is written once in Python and runs identically on all platforms. Platform-native shells handle UI, audio I/O, and OS integration.

```
┌─────────────────────────────────────────────────────┐
│                  Platform Shell                      │
│   Windows (PyQt6)  │  Android (Kotlin+Chaquopy)  │ iOS  │
├─────────────────────────────────────────────────────┤
│              Vakya Core (Python 3.11+)               │
│  AudioCapture → Pipeline → OutputRouter             │
├──────────────┬──────────────┬───────────────────────┤
│  STT Engine  │  LLM Engine  │  TTS + Clone Engine   │
│ (faster-     │ (llama.cpp   │ (CosyVoice2 /         │
│  whisper)    │  / llama-    │  Kokoro / Piper)      │
│              │  cpp-python) │                       │
├──────────────┴──────────────┴───────────────────────┤
│           Diarization (pyannote 3.1)                 │
│           VAD (Silero, bundled in faster-whisper)    │
├─────────────────────────────────────────────────────┤
│         Local Storage Layer                          │
│  voice_profiles/  vocab_store.json  sessions/        │
└─────────────────────────────────────────────────────┘
```

**Why Python core:**
- faster-whisper, llama-cpp-python, pyannote, CosyVoice2 all have native Python bindings
- One pipeline test suite covers all platforms
- ONNX export paths exist for every model if needed for mobile
- Avoids reimplementing the pipeline three times in three languages

**Why native shells (not React Native / Flutter):**
- Audio capture at low latency requires direct OS API access
- Hotkey/overlay (Wispr-mode) on Windows requires Win32 API hooks — not available in cross-platform frameworks
- iOS background audio requires AVFoundation directly
- UI is thin; the complexity is in the inference pipeline, not the UI

**Platform launch sequence:**
1. **Windows** — first build. PyQt6 shell. Full pipeline. Hotkey overlay.
2. **Android** — second build. Kotlin shell + Chaquopy (CPython embedded in APK).
3. **iOS** — third build. Core ML model export required. Most constrained platform.

---

## 2. Repository Structure

```
vakya/
├── CLAUDE.md                    # Root instruction for Claude Code
├── core/                        # Platform-agnostic Python pipeline
│   ├── __init__.py
│   ├── pipeline.py              # Orchestrator — runs steps 1-6
│   ├── audio_capture.py         # Abstract AudioCapture interface + platform router.
│   │                            # Defines: start(), stop(), get_wav_path() -> str
│   │                            # Platform shells register their implementation at startup.
│   │                            # Core pipeline calls this interface — never platform code directly.
│   ├── vad.py                   # VAD wrapper (Silero)
│   ├── stt/
│   │   ├── base.py              # Abstract STTEngine interface
│   │   ├── faster_whisper.py    # faster-whisper implementation
│   │   ├── moonshine.py         # Moonshine v2 implementation (mobile)
│   │   ├── whisper_cpp.py       # whisper.cpp fallback
│   │   └── qwen3_asr.py         # Qwen3-ASR (Hindi priority)
│   ├── llm/
│   │   ├── base.py              # Abstract LLMEngine interface
│   │   ├── phi3_mini.py         # Phi-3 Mini via llama-cpp-python
│   │   └── chunker.py           # Context-window chunking logic
│   ├── tts/
│   │   ├── base.py              # Abstract TTSEngine interface
│   │   ├── cosyvoice2.py        # CosyVoice2 implementation
│   │   ├── kokoro.py            # Kokoro fallback
│   │   └── piper.py             # Piper (embedded/RPi fallback)
│   ├── diarizer/
│   │   ├── base.py              # Abstract Diarizer interface
│   │   ├── pyannote.py          # pyannote-audio 3.1
│   │   └── whisperx.py          # WhisperX (Windows unified layer)
│   ├── voice_profile/
│   │   ├── store.py             # Read/write voice_profiles/
│   │   └── extractor.py         # Pulls best clip per speaker
│   ├── vocab/
│   │   └── store.py             # Personal vocabulary JSON store
│   └── output/
│       ├── formatter.py         # Mode-aware text formatting
│       └── router.py            # Clipboard / file / display routing
├── platform/
│   ├── windows/
│   │   ├── shell.py             # PyQt6 app entry point
│   │   ├── hotkey.py            # Win32 global hotkey hooks
│   │   ├── overlay.py           # Floating overlay window
│   │   └── audio_win.py         # Windows audio capture (sounddevice)
│   ├── android/
│   │   ├── main.py              # Buildozer entry point
│   │   └── audio_android.py     # Android audio capture
│   └── ios/
│       ├── main.py              # BeeWare/Briefcase entry point
│       └── audio_ios.py         # AVFoundation bridge
├── models/                      # Downloaded at first run (gitignored)
│   ├── .gitkeep
│   └── manifest.json            # RUNTIME state: which models are present + verified checksums.
│                                # Written by download_models.py after each successful download.
│                                # Read by pipeline at startup to know which engines are available.
│                                # Never edited manually. SOURCE OF TRUTH: installer/model_manifest.yaml
├── data/
│   ├── voice_profiles/          # Per-speaker WAV clips + embeddings
│   ├── vocab_store.json         # Personal vocabulary
│   └── sessions/                # Session metadata (no audio stored)
├── config/
│   ├── default.yaml             # Default configuration
│   └── hardware_profiles.yaml   # Min-spec / recommended / RPi tiers
├── installer/
│   ├── download_models.py       # First-run model downloader
│   └── model_manifest.yaml      # Model URLs + checksums + RAM requirements
├── tests/
│   ├── test_pipeline.py
│   ├── test_stt_engines.py
│   ├── test_llm_chunker.py
│   └── fixtures/                # Short audio samples for CI
└── docs/                        # Architecture docs (these files)
```

---

## 3. Component Interfaces (Abstract Contracts)

Every engine implements a strict interface. Claude Code must not bypass these.

### STTEngine
```python
class STTEngine:
    def transcribe(self, audio_path: str, language: str = "auto",
                   vocab_hint: list[str] = []) -> STTResult
    # STTResult: { text, segments: [{start, end, text, speaker_id?}], language_detected }
```

### LLMEngine
```python
class LLMEngine:
    def cleanup(self, transcript: str, mode: CleanupMode) -> str
    # CleanupMode: DICTATION | NOTES | FARM_LOG | MEETING
    # Must chunk internally if transcript > context_window
```

### TTSEngine
```python
class TTSEngine:
    def synthesise(self, text: str, voice_profile_id: str | None = None) -> bytes
    # Returns WAV bytes. voice_profile_id=None → default voice
```

### Diarizer
```python
class Diarizer:
    def diarize(self, audio_path: str) -> list[DiarSegment]
    # DiarSegment: { speaker_id, start_sec, end_sec }
```

---

## 4. Configuration System

`config/default.yaml` controls all runtime behaviour. Hardware tier is auto-detected at startup and applied as an overlay on default config.

```yaml
hardware_tier: auto          # auto | minimum | recommended | rpi
stt:
  engine: faster_whisper     # faster_whisper | moonshine | whisper_cpp | qwen3_asr
  model_size: large-v3-turbo
  language: auto             # auto | hi | en | ...
  int8: true
llm:
  engine: phi3_mini
  model: phi-3-mini-4k-instruct-q4_k_m.gguf
  context_tokens: 4096
  chunk_overlap_tokens: 200
tts:
  engine: cosyvoice2         # cosyvoice2 | kokoro | piper
diarizer:
  engine: whisperx           # whisperx | pyannote
  enabled: true
output:
  default_mode: dictation    # dictation | notes | farm_log | meeting
  copy_to_clipboard: true
```

`config/hardware_profiles.yaml` — detection thresholds for auto tier selection:

```yaml
# Hardware detection logic (evaluated in order — first match wins)
tiers:
  rpi:
    # Raspberry Pi detected by platform string, not RAM
    platform_contains: "raspberrypi"

  minimum:
    # 4GB RAM machines: any CPU, any age
    ram_gb_max: 5.5           # detected RAM <= 5.5GB → minimum tier
    cpu_cores_min: 2

  recommended:
    # 8GB machines: i5/i7/Ryzen equivalent
    ram_gb_min: 5.5           # detected RAM > 5.5GB → recommended tier
    cpu_cores_min: 4

# Detection method:
#   RAM:      psutil.virtual_memory().total / 1e9
#   CPU:      psutil.cpu_count(logical=False)
#   Platform: platform.machine() + platform.node().lower()
# Tier written to models/manifest.json at first run. User can override in settings.
```

---

## 5. RAM Budget by Hardware Tier

| Component | Minimum (4GB) | Recommended (8GB) | RPi 5 (4GB) |
|---|---|---|---|
| whisper.cpp base.en | 140MB | — | 140MB |
| faster-whisper Turbo int8 | — | ~3GB | — |
| Phi-3 Mini Q4 | ~2.3GB | ~2.3GB | skip/rule-based |
| CosyVoice2 0.5B | skip | ~1.5GB est. | skip |
| Kokoro 82M | ~200MB | — | ~200MB |
| pyannote 3.1 | skip | ~500MB | skip |
| OS + app overhead | ~800MB | ~800MB | ~600MB |
| **Total peak** | **~3.4GB** | **~8.1GB** | **~940MB** |

**Minimum spec fallback chain:**
- STT: whisper.cpp base.en (not Turbo)
- LLM: rule-based filler removal only (regex, no model)
- TTS: Kokoro (82M) or Piper
- Diarization: disabled (single-speaker assumed)

**RPi 5 fallback chain:**
- STT: whisper.cpp base.en
- LLM: rule-based only
- TTS: Piper
- Diarization: disabled
