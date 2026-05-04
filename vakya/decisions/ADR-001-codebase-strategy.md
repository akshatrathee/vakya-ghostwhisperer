# ADR-001 — Codebase Strategy: Python Core + Native Shells

**Status:** Accepted  
**Date:** April 27, 2026

## Decision
Python core pipeline with platform-native shells for UI and audio I/O.

## Context
Three platforms (Windows, Android, iOS) with a complex inference pipeline
(5-6 steps, multiple ML models, RAM budget constraints).

## Options Considered

| Option | Pro | Con | Verdict |
|---|---|---|---|
| React Native + native bridge | One JS codebase | Audio latency; no low-level mic access; ML libs have no RN bindings | Rejected |
| Flutter | Good cross-platform UI | Same ML binding problem; Dart-Python interop is painful | Rejected |
| Full native per platform | Best performance | 3× engineering cost; 3 codebases to maintain | Rejected |
| Python everywhere (Kivy/BeeWare) | True single codebase | Build toolchain fragile; llama-cpp-python ARM build unreliable | Partial |
| **Python core + native shells** | One pipeline codebase; native handles OS-specific needs | Shell code per platform | **Accepted** |

## Consequences

**Positive:**
- Pipeline code written and tested once. All platform bugs are pipeline bugs, not platform-divergence bugs.
- faster-whisper, llama-cpp-python, pyannote, CosyVoice2 all have first-class Python bindings.
- Windows shell (PyQt6) is the simplest possible — thin wrapper over Python core.

**Negative:**
- iOS requires CoreML export for most models — inference does not run through Python on iOS.
  The Python core on iOS handles orchestration only; model inference is CoreML.
- Android Chaquopy adds ~10MB APK overhead and a build step.
- Two shell codebases to maintain (desktop Python shell vs mobile native shell).

## Mobile Detail
- Android: Kotlin shell + Chaquopy (CPython embedded in APK)
- iOS: Swift shell + BeeWare Briefcase or Swift-only with CoreML models
- The Python pipeline's abstract interfaces (`STTEngine`, `LLMEngine`, etc.) define
  the contract that the iOS CoreML wrappers must satisfy.
