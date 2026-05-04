# MODELS.md — Model Inventory, RAM Budgets, and Fallback Chains

## Selection Criteria Applied
All models must satisfy: Apache 2.0 / MIT license, CPU-viable, no GPU hard requirement,
offline after download, model file size feasible for first-run download (<5GB total primary stack).

---

## STT Models

### Primary: faster-whisper Large-v3 Turbo (int8)
- **File:** `models/stt/faster-whisper-large-v3-turbo/`
- **Size:** ~1.5GB on disk
- **RAM at runtime:** ~3GB
- **WER:** ~5% clean audio, higher in field conditions
- **Languages:** 99+ including Hindi, Hinglish
- **Speed:** ~6-8× faster than Whisper Large-v3
- **Platform:** Windows, Linux, macOS desktop
- **Bundled tiny model:** faster-whisper `tiny.en` (~75MB) — used during onboarding

### Mobile Primary: Moonshine v2 Base
- **File:** `models/stt/moonshine-v2-base/`
- **Size:** ~58MB
- **RAM at runtime:** ~200MB
- **WER:** ~10%
- **Languages:** English only
- **Platform:** Android, iOS (needs Core ML export for iOS — see PLATFORMS.md)
- **Note:** No 30-second padding limitation (Whisper's key mobile weakness)

### Whisper.cpp (fallback / minimum spec / RPi)
- **File:** `models/stt/whisper-base-en.bin` (~140MB)
- **RAM at runtime:** ~300MB
- **WER:** ~7% (base.en)
- **Platform:** All — whisper.cpp has Android JNI + iOS Core ML bindings
- **Note:** This is the bundled model for onboarding phase

### Qwen3-ASR-0.6B (Hindi/Indic priority)
- **File:** `models/stt/qwen3-asr-0.6b/`
- **Size:** ~600MB
- **RAM at runtime:** ~1.5GB
- **Languages:** 52 including Hindi dialects, code-mixed Hinglish
- **Trigger:** User selects "Hindi priority" in settings, or auto-detected language = hi
- **Platform:** Desktop + Android (not iOS Phase 1)

---

## LLM Models

### Primary: Phi-3 Mini 3.8B Q4_K_M
- **File:** `models/llm/phi-3-mini-4k-instruct-q4_k_m.gguf`
- **Size:** ~2.3GB on disk
- **RAM at runtime:** ~2.3GB (Q4 quantisation)
- **Context window:** 4,096 tokens (4K variant)
  - ⚠️ **CRITICAL:** 1hr meeting ≈ 9,000 words ≈ 12,000 tokens. ALWAYS chunk. See PIPELINE.md.
- **Inference speed:** ~5-15s for 5-min transcript on i5 CPU
- **License:** MIT
- **Backend:** llama-cpp-python

### Fallback: Rule-based filler removal
- **No model file.** Pure Python regex.
- **Removes:** um, uh, aah, hmm, you know, like (with word boundary matching)
- **Does NOT:** reformat, restructure, or summarise
- **RAM:** 0MB
- **Used when:** Phi-3 Mini not loaded OR hardware_tier = minimum/rpi

---

## TTS Models

### Primary: CosyVoice2 (0.5B)
- **File:** `models/tts/cosyvoice2/`
- **Size:** ~1GB est.
- **RAM at runtime:** ~1.5GB est. (needs benchmark — see decisions/ADR-004)
- **Latency:** 150ms streaming TTFB
- **Zero-shot cloning:** Yes — pass reference WAV clip
- **Languages:** English, Chinese, Japanese, Korean + dialects
- **License:** Apache 2.0
- **Platform:** Desktop (Windows, Linux, macOS)

### Fallback: Kokoro (82M parameters)
- **File:** `models/tts/kokoro-v1.0.onnx`
- **Size:** ~300MB
- **RAM at runtime:** ~200MB
- **MOS:** 4.5
- **Zero-shot cloning:** No
- **Platform:** All — ONNX, CPU real-time
- **License:** Apache 2.0

### Embedded/RPi fallback: Piper
- **File:** `models/tts/piper/en_US-lessac-medium.onnx` (~60MB)
- **RAM at runtime:** ~100MB
- **Zero-shot cloning:** No
- **Platform:** All — extremely lightweight
- **License:** MIT

### Voice Cloning Challenger: OmniVoice
- **File:** `models/tts/omnivoice/`
- **Status:** Benchmark required before committing
- **3-second reference audio** → voice clone
- **600+ languages**
- **License:** Apache 2.0
- **Decision point:** If OmniVoice CPU RTF < 2.0 (i.e., faster than 2× realtime), prefer over CosyVoice2 for cloning. Benchmark in first build sprint.

---

## Diarization Models

### Primary (Windows): WhisperX bundle
- **Includes:** faster-whisper + pyannote-audio + alignment model
- **RAM:** ~500MB additional over STT
- **Note:** Abstracts the pyannote Windows compatibility issue
- **Output:** Word-level timestamps + speaker diarization in one pass

### Primary (Linux/macOS): pyannote-audio 3.1
- **Requires:** HuggingFace account + one-time token acceptance (free)
- **RAM:** ~500MB
- **DER:** 11-19% (better with clearer audio)

---

## Indian Language Pack (Optional Download)

Downloaded separately if user selects Hindi-priority mode and Qwen3-ASR is insufficient.

| Model | Size | Purpose |
|---|---|---|
| IndicWav2Vec | ~1GB | STT for 40 Indian languages |
| Indic Parler-TTS | ~800MB | TTS for 21 Indian languages |

---

## Model Download Manifest Reference

See `installer/model_manifest.yaml` for download URLs, SHA256 checksums, and
minimum hardware tier per model. Claude Code must use this manifest — do not
hardcode download URLs in application code.

---

## Model Selection Logic (pseudo-code)

```
function select_stt_engine(platform, hardware_tier, language):
    if platform == MOBILE:
        return MoonshineV2 if hardware_tier >= RECOMMENDED else WhisperCpp
    if language == HINDI_PRIORITY:
        return Qwen3ASR if hardware_tier >= RECOMMENDED else WhisperLargeV3Turbo
    if hardware_tier == MINIMUM or hardware_tier == RPI:
        return WhisperCpp
    return FasterWhisperTurbo  # default

function select_llm_engine(hardware_tier):
    if hardware_tier in [MINIMUM, RPI]:
        return RuleBasedCleaner
    return Phi3Mini

function select_tts_engine(hardware_tier, cloning_required):
    if hardware_tier == RPI:
        return Piper
    if hardware_tier == MINIMUM:
        return Kokoro
    if cloning_required:
        return CosyVoice2  # or OmniVoice if benchmark passes
    return CosyVoice2
```
