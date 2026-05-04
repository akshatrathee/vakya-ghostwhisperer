# BUILD_SEQUENCE.md — Implementation Order for Claude Code

## Guiding Principle
Build the pipeline depth-first, not breadth-first.
A working pipeline on one platform (Windows) is more valuable than
a partial pipeline on three platforms.

---

## Sprint 1 — Core Pipeline (Windows, No UI)
**Goal:** Clean transcript from audio file via CLI. All pipeline steps working.

Build order:
1. `core/vad.py` — Silero VAD wrapper. Input: WAV path. Output: segment list.
2. `core/stt/base.py` — Abstract interface only.
3. `core/stt/whisper_cpp.py` — First STT impl using bundled model. Unblocks all downstream.
4. `core/vocab/store.py` — Vocab store read/write + `extract_new_terms()`. Required before
   pipeline runs — STT vocab_hint injection and Step 6 extraction both depend on this.
5. `core/llm/chunker.py` — Chunking logic. Unit-test thoroughly with token counts.
6. `core/llm/phi3_mini.py` — LLM cleanup via llama-cpp-python.
7. `core/output/formatter.py` — Mode-aware text formatting.
8. `core/audio_capture.py` — Abstract AudioCapture interface (no platform impl yet — use
   file input for Sprint 1 CLI).
9. `core/pipeline.py` — Orchestrator connecting steps 1-4 + output.
10. CLI entry point: `python -m vakya.cli --input audio.wav --mode dictation`

**Test:** Record 2-minute audio with fillers. Get clean formatted text in < 60s.

---

## Sprint 2 — Upgrade STT + Diarization (Windows)
**Goal:** Full accuracy pipeline with speaker labels.

Build order:
1. `core/stt/faster_whisper.py` — Upgrade from base.en to Turbo int8.
2. `core/diarizer/base.py` — Abstract interface.
3. `core/diarizer/whisperx.py` — WhisperX unified layer for Windows.
4. `core/voice_profile/extractor.py` — Extract best speaker clip.
5. `core/voice_profile/store.py` — Read/write voice_profiles/.
6. Update `core/pipeline.py` — Wire diarization into step 3.

**Test:** 2-speaker recording. Transcript shows "Speaker 1: ..." / "Speaker 2: ...". Profile WAVs created.

---

## Sprint 3 — TTS + Voice Cloning (Windows)
**Goal:** Synthesise text in a cloned voice from a stored profile.

Build order:
1. `core/tts/base.py` — Abstract interface.
2. `core/tts/kokoro.py` — Kokoro ONNX. Baseline TTS working.
3. `core/tts/cosyvoice2.py` — CosyVoice2 with reference clip support.
4. **OmniVoice benchmark:** Run OmniVoice CPU RTF test. Apply ADR-004 decision rule.
5. Update pipeline step 6 — on-demand TTS synthesis path.

**Test:** Read back a stored transcript in Speaker 1's cloned voice.

---

## Sprint 4 — Windows UI (Hotkey Overlay + Traditional)
**Goal:** Usable Windows application. No more CLI only.

Build order:
1. `platform/windows/shell.py` — PyQt6 app skeleton. Traditional mode first.
2. `platform/windows/audio_win.py` — sounddevice mic capture.
3. Traditional mode: Record → Process → Display transcript.
4. `platform/windows/hotkey.py` — Win32 global hotkey registration.
5. `platform/windows/overlay.py` — Floating overlay window.
6. Wispr-mode: hotkey → record → pipeline → paste to active window.

**Test:** Dictate 30-second note via hotkey. Clean text appears in open Notepad.

---

## Sprint 5 — Onboarding + Model Downloader (Windows)
**Goal:** First-run experience as designed in ONBOARDING.md.

Build order:
1. `installer/download_models.py` — Resumable, checksummed downloader.
2. `installer/model_manifest.yaml` — Fill in real URLs and checksums.
3. Hardware detection logic → auto-select hardware tier.
4. Onboarding UI screens (7 screens per ONBOARDING.md).
5. Background download thread + progress events to UI.
6. Windows installer build: PyInstaller + NSIS/Inno Setup.

**Test:** Fresh Windows machine. Run installer. App functional in < 60 seconds. Heavy models download in background.

---

## Sprint 6 — Android Port
**Goal:** Core pipeline running on Android via Chaquopy.

Build order:
1. Android project skeleton (Kotlin + Chaquopy).
2. `platform/android/audio_android.py` — AudioRecord bridge.
3. Wire Python core pipeline via Chaquopy.
4. STT: Moonshine v2 Base (primary for Android).
5. LLM: Rule-based by default. Optional Phi-3 Mini toggle.
6. TTS: Kokoro ONNX via Android ONNX Runtime.
7. Traditional mode UI in Kotlin (bottom sheet recording control).
8. Foreground service for background recording.

**Test:** Record 5-min farm note on Android. Clean transcript in < 45s.

---

## Sprint 7 — iOS Port
**Goal:** Core pipeline on iOS. App Store submission ready.

Pre-requisites (evaluate before Sprint 7 starts):
- Moonshine v2 CoreML export — must be validated
- Phi-3 Mini CoreML conversion — community conversions evaluated
- BeeWare Briefcase Python embed — tested on Xcode

Build order:
1. Moonshine v2 CoreML export + benchmark on device.
2. iOS project skeleton (Swift + BeeWare or full Swift).
3. `platform/ios/audio_ios.py` — AVAudioEngine bridge.
4. CoreML inference wrappers satisfying STTEngine interface.
5. Traditional mode UI in SwiftUI.
6. Background audio entitlement + AVAudioSession setup.
7. TestFlight beta distribution.

---

## Phase 3 Placeholders (Do Not Build — Log Only)

These are called in the pipeline but do nothing in Phase 2:
- `core/llm/wiki_ingest.py` — `pass; log("wiki ingest skipped — Phase 3")`
- `core/vocab/shortcut_expander.py` — `pass; log("shortcuts skipped — Phase 3")`
- `core/llm/command_mode.py` — `pass; log("command mode skipped — Phase 3")`

Reason: Placeholder modules prevent "feature not found" errors when Phase 3
reuses the same pipeline orchestrator.

---

## Testing Strategy

| Level | Tool | Scope |
|---|---|---|
| Unit | pytest | chunker.py, formatter.py, schemas, extractor.py |
| Integration | pytest | Full pipeline on 30s fixture audio |
| STT benchmark | custom script | WER measurement on 5 fixture clips (EN + HI) |
| RAM profiling | tracemalloc | Peak RAM after each pipeline step |
| Platform | Manual | Hotkey paste on Windows, foreground service on Android |

Fixture audio files in `tests/fixtures/`:
- `en_clean_30s.wav` — English, quiet room
- `en_fillers_30s.wav` — English, heavy filler words
- `hi_clean_30s.wav` — Hindi, quiet room
- `multi_speaker_2min.wav` — 2 speakers, English
- `outdoor_noisy_30s.wav` — Field conditions simulation
