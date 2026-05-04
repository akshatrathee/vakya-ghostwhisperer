# ONBOARDING.md — First-Run Model Download + Onboarding UX

## Design Goal

The user should feel the app is working **immediately** on first launch.
The heavy models download in the background while onboarding occupies them.
Perception of readiness > actual readiness.

---

## Bundled Model (In the Installer)

One model ships inside the installer package — never downloaded:

| Model | Size | Purpose |
|---|---|---|
| `whisper-base-en.bin` | ~140MB | Immediate STT. Works from second 1. |

This model is extracted during install. The app is functional before any download completes.
Trade-off: ~7-10% WER (vs ~5% for Turbo). Acceptable for onboarding demo.

---

## Onboarding Flow

```
LAUNCH (first run detected via absence of models/manifest.json)
    │
    ▼
SCREEN 1 — Welcome (10 seconds)
  "Vakya — your voice stays on your device."
  One-sentence explanation. No feature list. 
  [Get Started →]
    │
    ▼
SCREEN 2 — Hardware Detection (auto, ~3 seconds)
  System checks RAM, CPU, platform.
  Selects appropriate model tier.
  "We've tuned Vakya for your device." 
  Shows selected profile (e.g., "Recommended — 8GB mode")
  [Looks good →]
    │
    ▼
SCREEN 3 — Language Selection
  Primary language: [English] [Hindi] [Hindi + English mix]
  "You can change this anytime."
  Selection determines which models to queue for download.
  [Continue →]
    │
    ▼
SCREEN 4 — Microphone Permission + Test
  Platform permission dialog fires here (not before).
  Live waveform shown from mic.
  "Say anything — we're just testing your microphone."
  5-second recording → transcribed with bundled base.en model → shown on screen
  This is the FIRST WOW MOMENT. App is already working.
  [That worked! Continue →]  or  [Try again]
    │
    ▼
SCREEN 5 — Model Download (background download starts here)
  "Downloading smarter models for better accuracy."
  Progress bar per model. Overall progress. Estimated time.
  Download queue (in priority order):
    Priority 1: faster-whisper-large-v3-turbo (~1.5GB) [starts immediately]
    Priority 2: phi-3-mini-4k-q4_k_m.gguf (~2.3GB) [starts after P1]
    Priority 3: cosyvoice2-0.5b (~1GB) [starts after P2, desktop only]
  While download runs → show interactive demo (see below)
  Download runs in background thread. User can skip to main app at any time.
  [Skip for now] [Continue in background]
    │
    ▼
INTERACTIVE DEMO (during download — keeps user engaged)
  Pre-recorded sample transcription shown step-by-step:
    1. "Raw speech" audio plays (with um/uh visible in raw transcript)
    2. "AI cleanup" animation → cleaned text appears
    3. "Your privacy" explainer — one screen showing no network icon
  User can record their own note with base.en model during this time.
    │
    ▼
SCREEN 6 — HuggingFace Token (if diarization enabled on hardware tier)
  "One-time setup for speaker identification."
  Explains: free HF account needed to download pyannote model.
  [I have an account — enter token] [Skip speaker ID for now]
  Token stored locally: never transmitted. Skip → diarization disabled.
    │
    ▼
SCREEN 7 — Mode Selection (default output mode)
  [Dictation] [Notes / Bullets] [Farm Log] [Meeting Notes]
  One-sentence description of each. User picks their primary use case.
  Affects default system prompt for LLM cleanup.
  [Start using Vakya →]
    │
    ▼
MAIN APP (functional from this point, even if heavy models still downloading)
  Status bar shows: "Using fast mode — full model at 67%"
  When primary download completes: "Full accuracy unlocked" notification
```

---

## Download Manager Requirements

`installer/download_models.py` must implement:

1. **Resumable downloads.** Partial files are kept. On restart, resume from byte offset.
2. **Checksum verification.** SHA256 verified before model is marked as available.
   Corrupted/partial files are deleted and re-queued.
3. **Manifest-driven.** All URLs and checksums come from `installer/model_manifest.yaml`.
   Never hardcode URLs in application code.
4. **Graceful network failure.** If download fails, app continues with bundled base model.
   Download retries on next launch automatically.
5. **Progress events.** Download manager emits events: `{model_id, bytes_downloaded, total_bytes, status}`.
   UI subscribes to these events — download logic and UI are decoupled.
6. **Tier-aware.** Only download models appropriate for the detected hardware tier.
   A 4GB RAM machine never downloads CosyVoice2.

---

## Model Manifest Format

`installer/model_manifest.yaml`:

```yaml
models:
  - id: whisper-base-en
    display_name: "Fast transcription model"
    path: models/stt/whisper-base-en.bin
    url: https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin
    sha256: "60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe"
    size_bytes: 147951465
    min_tier: minimum
    platform: all
    bundled: true  # ships in installer, not downloaded

  - id: faster-whisper-large-v3-turbo
    display_name: "High accuracy transcription"
    path: models/stt/faster-whisper-large-v3-turbo/
    url: https://huggingface.co/Systran/faster-whisper-large-v3-turbo/resolve/main/
    sha256: "..."
    size_bytes: 1610612736
    min_tier: recommended
    platform: desktop
    bundled: false
    download_priority: 1

  - id: phi3-mini-4k-q4
    display_name: "AI text cleanup"
    path: models/llm/phi-3-mini-4k-instruct-q4_k_m.gguf
    url: https://huggingface.co/microsoft/Phi-3-mini-4k-instruct-gguf/resolve/main/Phi-3-mini-4k-instruct-q4.gguf
    sha256: "..."
    size_bytes: 2300000000
    min_tier: recommended
    platform: all
    bundled: false
    download_priority: 2
```
