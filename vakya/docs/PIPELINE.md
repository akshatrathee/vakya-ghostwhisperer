# PIPELINE.md — Data Flow: Mic to Output

## The Complete Pipeline

Every recording — whether 10 seconds or 4 hours — flows through this exact sequence.
Steps run sequentially. Branches (5a, 5b) run in parallel after step 4.

```
INPUT
  Microphone audio stream (raw PCM, 16kHz mono, 16-bit)
  Captured by: platform/*/audio_*.py
  Buffered in: RAM only. Never written to disk as raw audio.
         │
         ▼
STEP 1 — Voice Activity Detection
  Module:  core/vad.py
  Model:   Silero VAD (bundled in faster-whisper; standalone for whisper.cpp path)
  Action:  Segments audio into speech/silence chunks
           Drops silence segments → 30-40% reduction in STT processing time
  Output:  List of (start_ms, end_ms) speech segments
  RAM:     < 50MB
  Latency: Real-time (runs during capture)
         │
         ▼
STEP 2 — Speech-to-Text Transcription
  Module:  core/stt/[engine].py  (via core/stt/base.py interface)
  Model:   See MODELS.md — selected by hardware tier + config
  Input:   VAD-segmented audio + vocab_hint from vocab_store.json
           vocab_hint passed as --initial_prompt prefix to Whisper-family models
  Output:  STTResult {
             text: str,                    # full raw transcript
             segments: [{                  # word/sentence level
               start: float,
               end: float,
               text: str,
               confidence: float
             }],
             language_detected: str        # ISO 639-1 code
           }
  Note:    For recordings > 30 minutes, VAD chunks are processed sequentially
           and STTResults are concatenated before Step 3.
         │
         ▼
STEP 3 — Speaker Diarization
  Module:  core/diarizer/[engine].py  (via core/diarizer/base.py interface)
  Model:   WhisperX (Windows) or pyannote-audio 3.1 (Linux/macOS)
  Input:   Full audio file path + STTResult segments
  Action:  Assigns speaker_id to each segment
           Aligns diarization timestamps with STT segment timestamps
  Output:  List[DiarSegment] {speaker_id, start_sec, end_sec}
           STTResult segments updated with speaker_id fields
  Side A:  Best audio clip per speaker (10-30s clean speech) extracted
           → passed to Step 5a (Voice Profile Update)
  Side B:  Speaker-attributed transcript string built
           → "Speaker 1: ...\nSpeaker 2: ..."
  Skip:    If diarizer.enabled=false (minimum spec), speaker_id="Speaker 1" for all
         │
         ▼
STEP 4 — LLM Cleanup Pass
  Module:  core/llm/phi3_mini.py + core/llm/chunker.py
  Model:   Phi-3 Mini 3.8B Q4_K_M (llama-cpp-python)
  Input:   Speaker-attributed raw transcript
  Context: 4,096 tokens (4K variant). MUST chunk if transcript > ~3,200 tokens.
           (~3,200 token safety margin leaves room for system prompt + output)

  Chunking rules (core/llm/chunker.py):
    - Max chunk: 2,800 tokens of transcript content
    - Overlap:   200 tokens (last ~2 sentences of previous chunk prepended)
    - Split on:  Speaker boundaries preferred, else sentence boundaries
    - Never split mid-sentence.
    - Log every chunk boundary with token counts.
    - Reassemble: strip overlap on join, preserve speaker labels

  Chunk boundary speaker label rule (critical for correctness):
    - The 200-token overlap is prepended to the NEXT chunk as READ-ONLY context,
      wrapped in a system note: "CONTEXT ONLY — do not repeat this in output:"
    - This tells the LLM who was speaking at the end of the previous chunk
      without risking duplication in the reassembled output.
    - After reassembly, a post-processing pass checks that the same speaker_id
      does not appear on consecutive output paragraphs separated by a chunk join.
      If detected: merge the paragraphs (they are the same speaker continuing).
    - If speaker label is absent on the first sentence of a chunk output,
      inherit the last speaker label from the previous chunk.

  System prompt variables (injected per mode):
    DICTATION:  "Remove fillers (um, uh, aah, hmm, you know, like).
                 Resolve self-corrections — keep only the final intended meaning.
                 Output clean prose. No bullet points. Preserve speaker labels."
    NOTES:      "Remove fillers. Format as bullet points with sub-bullets for details.
                 Preserve speaker labels."
    FARM_LOG:   "Remove fillers. Format as a structured farm log:
                 Date/Time | Activity | Observations | Action Items.
                 Preserve speaker labels."
    MEETING:    "Remove fillers. Format as meeting notes:
                 Attendees | Key Points | Decisions | Action Items.
                 Preserve speaker labels."

  Output:  Clean, formatted text string
  Fallback: If Phi-3 Mini not loaded (minimum spec), run regex filler removal:
            Remove: \b(um+|uh+|aah+|hmm+|you know|like)\b
            No reformatting. Return cleaned raw transcript.
         │
    ┌────┴────┐
    │         │
    ▼         ▼
STEP 5a     STEP 5b
Voice       [PHASE 3 — NOT BUILT NOW]
Profile     Wiki Ingest Pass
Update      (Placeholder: log "wiki ingest skipped — Phase 3")

STEP 5a — Voice Profile Update
  Module:  core/voice_profile/extractor.py + store.py
  Input:   Per-speaker audio clips from Step 3 (Side A)
  Action:  For each speaker_id:
             If no profile exists → create new profile
             If profile exists → replace clip only if new clip is longer and cleaner
             "Cleaner" heuristic: lower dB variance + fewer VAD gaps in segment
  Store:   data/voice_profiles/{speaker_id}/
             reference_clip.wav    # 10-30s best clip, 16kHz mono
             embedding.npy         # speaker embedding vector (from pyannote/diarizer)
             profile.json          # metadata — see schemas/voice_profile.schema.json
  Output:  Updated profile store. No output to main pipeline.
         │
         ▼
STEP 6 — Output Routing
  Module:  core/output/router.py + formatter.py
  Input:   Clean text from Step 4
  Actions (all configurable, applied in order):
    1. Copy to clipboard (default: on) — Wispr-mode primary output
    2. Display in overlay/app window
    3. Write to sessions/{session_id}.md (session log — text only, no audio)
    4. Update vocab_store.json: extract candidate terms for future STT vocab hint injection.
       Extraction mechanism (implemented in core/vocab/store.py::extract_new_terms()):
         a. Tokenise cleaned transcript into words
         b. Filter to capitalised non-sentence-start words (likely proper nouns)
         c. Filter to words not in a base English/Hindi stopword list (~2,000 words)
         d. Filter to words NOT already in vocab_store
         e. Candidates with frequency >= 2 across the session are auto-added
         f. Single-occurrence candidates are logged but not added (avoid noise)
         g. User can manually promote logged candidates via settings UI
       This is pure Python — no model call. Runs in < 100ms.
  TTS (on demand, not automatic):
    Triggered by: user button press or hotkey
    Input:  Selected text + speaker_id (optional)
    Engine: core/tts/[engine].py
    Output: Audio playback via platform audio output

OUTPUTS (end state after pipeline completes):
  ✓ Clean formatted transcript → clipboard + display
  ✓ Session log file → data/sessions/{timestamp}_{mode}.md
  ✓ Updated voice profiles → data/voice_profiles/
  ✓ Updated vocabulary store → data/vocab_store.json
  ✗ Raw audio → NOT stored (RAM only during session, released after Step 2)
```

---

## Timing Reference (8GB laptop, Intel i5, CPU only)

| Recording | Step 1 VAD | Step 2 STT | Step 3 Diar | Step 4 LLM | Total |
|---|---|---|---|---|---|
| 5-min note | real-time | ~15s | ~5s | ~5s | ~30s |
| 30-min meeting | real-time | ~90s | ~20s | ~15s | ~2m 30s |
| 1-hr recording | real-time | ~3m | ~40s | ~30s | ~5m |
| 4-hr session | real-time | ~12m | ~3m | ~2m | ~18m |

---

## Wispr-Mode vs Traditional Mode

**Wispr-mode (hotkey overlay):**
- Global hotkey activates recording (e.g., `Ctrl+Shift+Space` on Windows)
- Floating overlay appears showing "Recording..." with waveform
- On hotkey release → pipeline runs → result pasted to active window
- Target: < 5 seconds for voice notes under 60 seconds
- STT runs during capture (streaming) where engine supports it

**Traditional mode (app UI):**
- Full app window open
- Record / Stop / Transcribe buttons
- Transcript displayed in scrollable pane
- Mode selector (Dictation / Notes / Farm Log / Meeting)
- Speaker labels shown with colour coding
- Export button → copies to clipboard / saves to file

Both modes use the identical pipeline. Mode is a UI concern only.
