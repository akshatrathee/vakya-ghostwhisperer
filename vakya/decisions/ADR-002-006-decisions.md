# ADR-002 — STT Engine Selection

**Status:** Accepted  
**Date:** April 27, 2026

## Decision
faster-whisper Large-v3 Turbo (int8, CPU) as primary desktop STT.
Moonshine v2 Base as primary mobile STT.
whisper.cpp base.en bundled for immediate onboarding + minimum-spec fallback.

## Rationale

| Requirement | Why faster-whisper Turbo wins |
|---|---|
| Hindi support | 99+ languages including Hindi. Qwen3-ASR available as upgrade path. |
| CPU-only | int8 quantisation viable on i5/i7. Confirmed in literature. |
| No session limit | VAD-chunked — processes arbitrarily long audio sequentially. |
| Ecosystem | Largest open-source ASR ecosystem. Widest community support. |
| License | MIT. No restrictions. |

## Why Not NVIDIA Canary-Qwen 2.5B (#1 on leaderboard)
English-only. GPU required for practical use. Fails the farm constraint.

## Why Not Voxtral Mini (Mistral)
Strong candidate but needs CPU benchmarking. Add as an optional engine swap
if community benchmarks confirm competitive CPU RTF. Architecture supports
this via the `STTEngine` interface — no code changes needed.

## Bundled Model Rationale
whisper.cpp base.en ships in the installer because:
- The app must be usable before any download completes
- 140MB is acceptable in an installer
- Users see transcription working during onboarding → confidence builds

---

# ADR-003 — LLM Engine + Chunking Strategy

**Status:** Accepted  
**Date:** April 27, 2026

## Decision
Phi-3 Mini 3.8B Q4_K_M via llama-cpp-python.
Chunking is mandatory for all recordings. Never assume transcript fits in context.

## Chunking Design

**The problem:**
Phi-3 Mini 4K variant has a 4,096 token context window.
Speech generates ~150 words/minute = ~200 tokens/minute.
A 20-minute recording = ~4,000 tokens. Right at the limit.
A 30-minute recording = ~6,000 tokens. Exceeds limit by 50%.

**The solution (implemented in `core/llm/chunker.py`):**

```
MAX_CHUNK_TOKENS = 2800  # safety margin for system prompt + output
OVERLAP_TOKENS   = 200   # last ~2 sentences of previous chunk

Split strategy:
  1. Try to split at speaker boundary (ideal — no sentence interrupted)
  2. Fall back to sentence boundary (period/question mark)
  3. Never split mid-word

Reassembly:
  1. Run cleanup on each chunk independently
  2. Strip overlap on join
  3. Check that speaker labels are consistent across chunk boundaries
  4. Log all chunk boundaries with token counts
```

**Why not the 128K context variant?**
The 128K Phi-3 Mini variant exists but is less common in quantised form and
consumes significantly more RAM. Minimum-spec users (4GB) cannot load it.
Chunking is the correct solution — it also allows streaming partial results
to the UI as each chunk completes.

## Fallback
Rule-based regex on minimum-spec/RPi. Removes fillers, no restructuring.
This is an explicit, logged decision — not a silent degradation.

---

# ADR-004 — TTS + Voice Cloning Architecture

**Status:** Accepted (OmniVoice decision deferred pending benchmark)  
**Date:** April 27, 2026

## Decision
CosyVoice2 (0.5B) as primary TTS + zero-shot voice cloner on desktop.
Kokoro (82M ONNX) as fallback and default for minimum-spec + mobile.

## Voice Cloning Mechanism
Zero-shot only. No fine-tuning. No separate recording session.

1. pyannote-audio (or WhisperX) extracts per-speaker audio segments during diarization
2. `core/voice_profile/extractor.py` selects best clip (10-30s, clean speech)
3. Clip stored as `data/voice_profiles/{speaker_id}/reference_clip.wav`
4. CosyVoice2 accepts this WAV as reference → generates text in that voice
5. Profile improves automatically — new recordings replace shorter/noisier clips

## OmniVoice Decision Gate
OmniVoice (Apache 2.0, 3-second reference, 600 languages) is a strong candidate.
Its 40× realtime figure is GPU-measured. CPU performance unknown.

**Decision rule:**
- Benchmark OmniVoice in first build sprint on target CPU (i5, no GPU)
- If CPU RTF < 2.0 → use OmniVoice as primary voice cloner (CosyVoice2 as TTS)
- If CPU RTF > 2.0 → use CosyVoice2 for both TTS and cloning
- Architecture supports either via `TTSEngine` interface

## Minimum Reference Clip Length
Target: 10 seconds minimum usable, 30 seconds ideal.
Empirical testing required in build sprint. Until confirmed, extractor
will reject clips under 8 seconds and prefer clips 20+ seconds.

---

# ADR-005 — Diarization on Windows

**Status:** Accepted  
**Date:** April 27, 2026

## Problem
pyannote-audio 3.1 has no official Windows support.
Their documentation explicitly states Linux and macOS only.
Attempting a standalone Windows install is fragile and unsupported.

## Decision
**WhisperX as the unified STT + diarization layer for Windows.**

WhisperX (`m-bain/whisperX`, BSD-2 license) packages:
- faster-whisper (STT)
- pyannote-audio (diarization)
- Forced alignment model

Into a single pip-installable package that installs reliably on Windows via pip
because it manages pyannote's environment internally.

## Consequence
On Windows, the STT step and diarization step are combined into a single WhisperX call
rather than two separate calls. The `core/diarizer/whisperx.py` implementation wraps this.
The `STTEngine` and `Diarizer` interfaces are still respected — WhisperX adapter satisfies both.

On Linux/macOS, pyannote-audio runs standalone as documented.

## Alternative Considered
Run pyannote in WSL2 on Windows.
Rejected: Requires WSL2 installed (not universal), adds latency via named pipe IPC,
and is confusing for non-technical users.

---

# ADR-006 — UI Paradigm: Wispr Overlay + Traditional Mode

**Status:** Accepted  
**Date:** April 27, 2026

## Decision
Implement both UI modes. Wispr-mode is the primary experience on Windows.
Traditional mode is the secondary experience and the primary on mobile.

## Wispr-Mode (Windows Desktop — Primary)
- Global hotkey: `Ctrl+Shift+Space` (configurable)
- Floating overlay: 280×80px, bottom-right, always-on-top, frameless
- States: idle (hidden), recording (waveform), processing (spinner), done (text preview)
- Output: text pasted directly into active application via clipboard
- Design principle: invisible when not in use. Zero friction.

## Traditional Mode (All Platforms — Secondary on Desktop, Primary on Mobile)
- Full app window
- Big record button (Plaud-style: one press to start, one to stop)
- Live waveform during recording
- Transcript appears in scrollable panel after processing
- Mode selector: Dictation / Notes / Farm Log / Meeting
- Speaker colour-coding in transcript
- Export options: Copy / Save as .txt / Save as .md

## Switching Between Modes
- Settings toggle: "Hotkey mode" on/off
- When hotkey mode is off, the app behaves as traditional mode only
- Hotkey mode Windows-only in Phase 1 (Android/iOS do not support global hotkeys)

## Mobile UI Notes
- Bottom sheet for recording controls (thumb-reachable)
- Long press record button → continuous recording mode (for farm/field use)
- Floating action button when app is backgrounded (Android foreground service notification)
