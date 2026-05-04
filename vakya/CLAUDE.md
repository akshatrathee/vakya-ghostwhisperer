# CLAUDE.md — Vakya: Offline Voice Intelligence
**Version:** 7.0 (Sprints 1–7 Complete — All Platforms)  
**Date:** April 27, 2026  
**Status:** Active development. Sprints 1–6 fully built and tested. **Read `PROGRESS.md` before writing any code.**

---

## What You Are Building

**Vakya** (Sanskrit: वाक्य, "utterance") is a fully offline, cross-platform speech-to-text application.

It does what Wispr Flow does — live dictation with AI cleanup — but runs 100% on-device with no internet, no subscriptions, no cloud dependency. It targets normal consumer hardware (₹25,000–40,000 laptops, mid-range Android/iOS phones) including farm environments with zero connectivity.

**The hard constraints — these never change:**
- Zero network calls during operation. Ever.
- No GPU requirement. CPU-only inference.
- Audio never written to a location accessible outside the app sandbox. On Android, writing to the app's sandboxed cache directory is permitted as a pipeline intermediary — this is not a violation. Raw audio is never written to shared external storage.
- Free and open source. Apache 2.0, MIT, or BSD-2-Clause licensed stack only. (BSD-2 is included to accommodate WhisperX — see ADR-005. All three licenses are permissive and commercially compatible.)

---

## Current Build State (updated each sprint)

**Next sprint:** Phase 3 — Second brain / Obsidian wiki ingest, voice shortcuts, command mode  
**Test suite:** 176 passed, 3 skipped (model-weight skips — expected)  
**Working CLI:** `python -m vakya --input audio.wav --mode dictation`  
**Working TTS:** `python -m vakya --tts "text" --voice SPEAKER_ID`  
**Working UI:** `python -m vakya --ui`  (shows onboarding wizard on first run, then MainWindow)  
**Installer build:** `pyinstaller vakya/installer/vakya.spec`  
**Android build:** `cd vakya/platform/android && ./gradlew assembleDebug`  
**iOS build:** `cd vakya/platform/ios && xcodegen generate && make build`

See `PROGRESS.md` for full sprint log, known issues, and deferred decisions.

---

## Architecture Documents (Read in Order)

Before writing any code, read these files in sequence:

0. `PROGRESS.md` ← **read first in any new session** — current state, known issues, what's next

1. `CLAUDE.md` ← this file (project identity + constraints)
2. `docs/ARCHITECTURE.md` — system overview, platform strategy, component map
3. `docs/PIPELINE.md` — the exact data flow from mic to output
4. `docs/MODELS.md` — every model, its role, RAM budget, and fallback
5. `docs/PLATFORMS.md` — per-platform implementation notes and constraints
6. `docs/ONBOARDING.md` — first-run model download + onboarding UX flow
7. `decisions/ADR-001-codebase-strategy.md` — why Python + platform bridges
8. `decisions/ADR-002-006-decisions.md` — STT, LLM chunking, TTS/cloning, Windows diarization, UI paradigm (all in one file)
9. `schemas/voice_profile.schema.json` — voice profile data structure
10. `schemas/vocab_store.schema.json` — personal vocabulary store
11. `schemas/session.schema.json` — session metadata structure

---

## Project Name and Identity

- **App name:** Vakya
- **Tagline:** "Your voice, your device, your data."
- **Primary user:** A person in a low-connectivity environment (farm, field, rural office) who needs to dictate notes, transcribe meetings, and organise knowledge — all offline.
- **Secondary user:** Any privacy-conscious professional who wants Wispr-like dictation without cloud dependency.

---

## What Is Out of Scope for This Build

- Second brain / Obsidian wiki ingest → Phase 3
- Voice shortcuts / snippet expansion → Phase 3
- Command mode ("rewrite this shorter") → Phase 3
- Mac support → Phase 3 (architecture should not block it, but do not build it now)
- GPU acceleration → never required, but code should not prevent it as optional future path

---

## Key Principles for All Code Written

1. **Model-agnostic interfaces.** STT, LLM, TTS, and Diarizer are each behind an abstract interface. Swapping models requires changing config, not app code.
2. **Fail gracefully.** If a heavy model is absent, fall to the next tier. Never crash — degrade.
3. **No silent truncation.** If a transcript exceeds the LLM context window, chunk it explicitly and log it. Never silently drop content.
4. **RAM budget is a first-class constraint.** Log peak RAM after every inference call. Alert if within 20% of device limit.
5. **Offline first, always.** No feature should conditionally require internet. If internet is present, it may be used for model updates only, and only with explicit user opt-in.
