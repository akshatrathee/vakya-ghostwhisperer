"""Pipeline orchestrator — connects Steps 1-6.

Step 1: VAD        — core/vad.py
Step 2: STT        — core/stt/[engine].py
Step 3: Diarize    — core/diarizer/[engine].py  (or combined WhisperX pass)
Step 4: LLM        — core/llm/phi3_mini.py
Step 5a: Profiles  — core/voice_profile/extractor.py
Step 6: Output     — core/output/router.py

Hardware tier is auto-detected at startup and drives engine selection.
All peak RAM is logged after each step. Alert if within 20% of detected RAM.
"""

from __future__ import annotations

import logging
import os
import platform
import sys
import time
import tracemalloc
import uuid
import wave
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import psutil
import yaml

from .llm.base import CleanupMode
from .output import formatter, router, session_log
from .stt.base import STTResult
from .vad import SpeechSegment, detect_speech_segments
from .vocab import store as vocab_store

log = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "default.yaml"
_HW_PROFILE_PATH = Path(__file__).parent.parent / "config" / "hardware_profiles.yaml"


@dataclass
class PipelineResult:
    session_id: str
    formatted_text: str
    raw_transcript: str
    language_detected: str
    speaker_ids: list[str] = field(default_factory=list)
    timing: dict = field(default_factory=dict)
    peak_ram_mb: float = 0.0
    log_path: Optional[str] = None
    metadata_path: Optional[str] = None
    vocab_terms_added: list[str] = field(default_factory=list)
    profiles_updated: list[str] = field(default_factory=list)
    stt_engine_name: str = "unknown"
    llm_engine_name: str = "unknown"


_RUNTIME_MANIFEST = Path(__file__).parent.parent / "models" / "manifest.json"


def _load_runtime_manifest() -> dict:
    if not _RUNTIME_MANIFEST.exists():
        return {"models": {}}
    try:
        import json
        return json.loads(_RUNTIME_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, Exception):
        return {"models": {}}


def _load_config() -> dict:
    if not _CONFIG_PATH.exists():
        return {}
    return yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}


def _detect_hardware_tier(config: dict) -> str:
    if config.get("hardware_tier", "auto") != "auto":
        return config["hardware_tier"]

    node = platform.node().lower()
    if "raspberrypi" in node or "raspberrypi" in platform.machine().lower():
        log.info("Hardware tier: rpi")
        return "rpi"

    ram_gb = psutil.virtual_memory().total / 1e9
    cpu_cores = psutil.cpu_count(logical=False) or 1

    if ram_gb <= 5.5:
        log.info("Hardware tier: minimum (%.1f GB RAM, %d cores)", ram_gb, cpu_cores)
        return "minimum"

    log.info("Hardware tier: recommended (%.1f GB RAM, %d cores)", ram_gb, cpu_cores)
    return "recommended"


def _ram_alert_threshold_mb() -> float:
    total_mb = psutil.virtual_memory().total / 1e6
    return total_mb * 0.80


def _check_ram(peak_mb: float, label: str) -> None:
    threshold = _ram_alert_threshold_mb()
    if peak_mb > threshold:
        log.warning(
            "RAM ALERT: %s used %.0fMB — within 20%% of device limit (%.0fMB)",
            label,
            peak_mb,
            _ram_alert_threshold_mb() / 0.8,
        )


def _build_stt_engine(hw_tier: str, config: dict, language: str):
    stt_cfg = config.get("stt", {})
    engine_name = stt_cfg.get("engine", "faster_whisper")

    if hw_tier in ("minimum", "rpi"):
        engine_name = "whisper_cpp"

    if language == "hi" and hw_tier == "recommended":
        engine_name = "qwen3_asr"

    log.info("STT engine selected: %s", engine_name)

    if engine_name == "faster_whisper":
        from .stt.faster_whisper import FasterWhisperEngine
        return FasterWhisperEngine(int8=stt_cfg.get("int8", True))
    elif engine_name == "whisper_cpp":
        from .stt.whisper_cpp import WhisperCppEngine
        return WhisperCppEngine()
    elif engine_name == "qwen3_asr":
        from .stt.qwen3_asr import Qwen3ASREngine
        return Qwen3ASREngine()
    elif engine_name == "moonshine":
        from .stt.moonshine import MoonshineEngine
        return MoonshineEngine()
    else:
        raise ValueError(f"Unknown STT engine: {engine_name}")


def _build_llm_engine(hw_tier: str, config: dict):
    if hw_tier in ("minimum", "rpi"):
        from .llm.phi3_mini import RuleBasedEngine
        log.info("LLM engine: rule_based (hw_tier=%s)", hw_tier)
        return RuleBasedEngine()
    from .llm.phi3_mini import load_best_available
    return load_best_available()


_HF_TOKEN_PATH = Path(__file__).parent.parent / "config" / "hf_token.txt"


def _load_hf_token() -> str:
    """Read the HF token from the saved file, falling back to the env var."""
    if _HF_TOKEN_PATH.exists():
        token = _HF_TOKEN_PATH.read_text(encoding="utf-8").strip()
        if token:
            os.environ.setdefault("HF_TOKEN", token)
            return token
    return os.environ.get("HF_TOKEN", "")


def _build_diarizer(hw_tier: str, config: dict, use_whisperx: bool):
    if hw_tier in ("minimum", "rpi"):
        return None  # diarization disabled

    diar_cfg = config.get("diarizer", {})
    if not diar_cfg.get("enabled", True):
        return None

    engine_name = diar_cfg.get("engine", "whisperx")

    if use_whisperx or engine_name == "whisperx":
        from .diarizer.whisperx import WhisperXEngine
        hf_token = _load_hf_token()
        log.info("Diarizer: whisperx (hf_token=%s)", "set" if hf_token else "missing")
        return WhisperXEngine(hf_token=hf_token)

    from .diarizer.pyannote import PyannoteEngine
    log.info("Diarizer: pyannote")
    return PyannoteEngine()


def run(
    audio_path: str,
    mode: CleanupMode | str = CleanupMode.DICTATION,
    language: str | None = None,
    session_id: str | None = None,
    copy_to_clipboard: bool = True,
    write_log: bool = True,
) -> PipelineResult:
    """Run the full Vakya pipeline on a WAV file.

    Args:
        audio_path: Path to input WAV file (16kHz, mono, 16-bit).
        mode: Cleanup mode — dictation | notes | farm_log | meeting.
        language: ISO 639-1 code or None for auto-detection.
        session_id: UUID string; generated if not provided.
        copy_to_clipboard: Copy result to system clipboard.
        write_log: Write session log to data/sessions/.
    """
    if isinstance(mode, str):
        mode = CleanupMode(mode)

    session_id = session_id or str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)
    timing: dict[str, float] = {}
    peak_ram_overall = 0.0

    config = _load_config()
    hw_tier = _detect_hardware_tier(config)
    lang = language or config.get("stt", {}).get("language", "auto")

    if not _RUNTIME_MANIFEST.exists():
        log.warning(
            "Models not downloaded yet (manifest.json missing). "
            "Vakya will use the bundled base.en model — accuracy will be lower. "
            "Run `python -m vakya.installer.download_models` to install full models."
        )

    log.info(
        "Pipeline start — session=%s, mode=%s, hw_tier=%s, audio=%s",
        session_id, mode.value, hw_tier, audio_path,
    )

    # ── STEP 1: VAD ──────────────────────────────────────────────────────────
    t0 = time.monotonic()
    tracemalloc.start()
    speech_segments = detect_speech_segments(audio_path)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    timing["vad_sec"] = time.monotonic() - t0
    peak_mb = peak / 1e6
    peak_ram_overall = max(peak_ram_overall, peak_mb)
    log.info("VAD: %d segments, %.2fs, peak=%.1fMB", len(speech_segments), timing["vad_sec"], peak_mb)
    _check_ram(peak_mb, "VAD")

    # ── STEP 2+3: STT (+ optional diarization) ───────────────────────────────
    on_windows = sys.platform == "win32"
    diar_cfg = config.get("diarizer", {})
    diarization_enabled = (
        hw_tier not in ("minimum", "rpi")
        and diar_cfg.get("enabled", True)
    )

    diar_segments = []
    vocab = vocab_store.load()
    vocab_hint = vocab_store.get_vocab_hint(vocab)

    stt_engine_name = "whisperx" if (diarization_enabled and on_windows) else _stt_engine_name(hw_tier, config, lang)
    llm_engine_name = "rule_based" if hw_tier in ("minimum", "rpi") else "phi3_mini_q4"

    if diarization_enabled and on_windows:
        # WhisperX: combined STT + diarize in one pass (ADR-005)
        t0 = time.monotonic()
        tracemalloc.start()
        from .diarizer.whisperx import WhisperXEngine
        wx = WhisperXEngine()
        stt_result, diar_segments = wx.transcribe_and_diarize(
            audio_path, language=lang, vocab_hint=vocab_hint
        )
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        timing["stt_sec"] = time.monotonic() - t0
        timing["diarization_sec"] = 0.0
    else:
        # Separate STT then optional diarization
        t0 = time.monotonic()
        tracemalloc.start()
        stt_engine = _build_stt_engine(hw_tier, config, lang)
        stt_result = stt_engine.transcribe(audio_path, language=lang, vocab_hint=vocab_hint)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        timing["stt_sec"] = time.monotonic() - t0
        peak_mb = peak / 1e6
        peak_ram_overall = max(peak_ram_overall, peak_mb)
        log.info("STT: %d segments, lang=%s, %.2fs, peak=%.1fMB",
                 len(stt_result.segments), stt_result.language_detected,
                 timing["stt_sec"], peak_mb)
        _check_ram(peak_mb, "STT")

        if diarization_enabled:
            t0 = time.monotonic()
            tracemalloc.start()
            diarizer = _build_diarizer(hw_tier, config, use_whisperx=False)
            if diarizer is not None:
                diar_segments = diarizer.diarize(audio_path)
                _merge_speaker_labels(stt_result, diar_segments)
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            timing["diarization_sec"] = time.monotonic() - t0
            peak_mb = peak / 1e6
            peak_ram_overall = max(peak_ram_overall, peak_mb)
            log.info("Diarization: %d segments, %.2fs, peak=%.1fMB",
                     len(diar_segments), timing["diarization_sec"], peak_mb)
        else:
            timing["diarization_sec"] = 0.0
            for seg in stt_result.segments:
                seg.speaker_id = "Speaker 1"

    # Build speaker-attributed raw transcript
    raw_transcript = _build_attributed_transcript(stt_result)

    # ── STEP 4: LLM ──────────────────────────────────────────────────────────
    t0 = time.monotonic()
    tracemalloc.start()
    llm_engine = _build_llm_engine(hw_tier, config)
    cleaned_text = llm_engine.cleanup(raw_transcript, mode)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    timing["llm_sec"] = time.monotonic() - t0
    peak_mb = peak / 1e6
    peak_ram_overall = max(peak_ram_overall, peak_mb)
    log.info("LLM: %.2fs, peak=%.1fMB", timing["llm_sec"], peak_mb)
    _check_ram(peak_mb, "LLM")

    # ── STEP 5a: Voice Profile Update ────────────────────────────────────────
    profiles_updated: list[str] = []
    if diar_segments:
        try:
            from .voice_profile.extractor import extract_and_update_profiles
            profiles_updated = extract_and_update_profiles(
                audio_path, diar_segments, session_id
            )
        except Exception as exc:
            log.warning("Voice profile update failed: %s", exc)

    # ── STEP 5b: Wiki ingest placeholder ─────────────────────────────────────
    from .llm import wiki_ingest
    wiki_ingest.ingest(cleaned_text, session_id)

    # ── STEP 6: Output ────────────────────────────────────────────────────────
    formatted = formatter.format_transcript(
        cleaned_text, mode, session_id, timestamp=started_at
    )
    route_result = router.route(
        formatted_text=formatted,
        raw_text=cleaned_text,
        mode=mode,
        session_id=session_id,
        copy_to_clipboard=copy_to_clipboard,
        write_log=write_log,
    )

    timing["total_sec"] = sum(timing.values())
    completed_at = datetime.now(timezone.utc)

    speaker_ids = list({seg.speaker_id for seg in diar_segments} or {"Speaker 1"})

    log.info(
        "Pipeline complete — session=%s, total=%.2fs, speakers=%s",
        session_id,
        timing["total_sec"],
        speaker_ids,
    )

    # Derive approximate audio duration from STT segment timestamps
    audio_duration_sec = 0.0
    if stt_result.segments:
        audio_duration_sec = stt_result.segments[-1].end

    # Count LLM chunks (logged by chunker — estimate from timing ratio)
    from .llm.chunker import split_transcript as _split, _approx_tokens
    llm_chunk_count = len(_split(raw_transcript))

    # Write session metadata JSON
    meta_path = None
    if write_log:
        meta_path = session_log.write_session_metadata(
            session_id=session_id,
            started_at=started_at,
            completed_at=completed_at,
            mode=mode.value,
            language_detected=stt_result.language_detected,
            audio_duration_sec=audio_duration_sec,
            stt_engine=stt_engine_name,
            llm_engine=llm_engine_name,
            speaker_ids=speaker_ids,
            timing=timing,
            peak_ram_mb=round(peak_ram_overall, 1),
            transcript_path=route_result.get("log_path"),
            vocab_terms_extracted=route_result.get("vocab_terms_added", []),
            voice_profiles_updated=profiles_updated,
            llm_chunk_count=llm_chunk_count,
        )

    return PipelineResult(
        session_id=session_id,
        formatted_text=formatted,
        raw_transcript=raw_transcript,
        language_detected=stt_result.language_detected,
        speaker_ids=speaker_ids,
        timing=timing,
        peak_ram_mb=round(peak_ram_overall, 1),
        log_path=route_result.get("log_path"),
        metadata_path=str(meta_path) if meta_path else None,
        vocab_terms_added=route_result.get("vocab_terms_added", []),
        profiles_updated=profiles_updated,
        stt_engine_name=stt_engine_name,
        llm_engine_name=llm_engine_name,
    )


def synthesise(
    text: str,
    voice_profile_id: str | None = None,
    play: bool = True,
    save_path: str | None = None,
) -> bytes:
    """On-demand TTS synthesis path — Step 6 branch (PIPELINE.md).

    Triggered by user button press or hotkey, not automatically.

    Args:
        text: Text to synthesise (typically selected transcript text).
        voice_profile_id: Speaker ID from data/voice_profiles/. None = default voice.
        play: Immediately play audio through system audio output.
        save_path: If given, also write WAV bytes to this path.

    Returns:
        WAV audio bytes (16kHz/22kHz mono, 16-bit).
    """
    config = _load_config()
    hw_tier = _detect_hardware_tier(config)
    cloning_required = voice_profile_id is not None

    from .tts.engine_factory import select_tts_engine, engine_name

    t0 = time.monotonic()
    tracemalloc.start()

    tts_engine = select_tts_engine(hw_tier, cloning_required=cloning_required)
    wav_bytes = tts_engine.synthesise(text, voice_profile_id=voice_profile_id)

    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    elapsed = time.monotonic() - t0
    audio_sec = _wav_duration(wav_bytes)
    rtf = elapsed / audio_sec if audio_sec > 0 else 0.0

    log.info(
        "TTS: engine=%s, voice=%s, %.2fs synth, %.2fs audio, RTF=%.2f, peak=%.1fMB",
        engine_name(tts_engine),
        voice_profile_id or "default",
        elapsed,
        audio_sec,
        rtf,
        peak / 1e6,
    )
    _check_ram(peak / 1e6, "TTS")

    if save_path:
        Path(save_path).write_bytes(wav_bytes)
        log.debug("TTS output saved to %s", save_path)

    if play:
        from .output.audio_player import play_wav_bytes
        play_wav_bytes(wav_bytes)

    return wav_bytes


def _wav_duration(wav_bytes: bytes) -> float:
    import io
    with io.BytesIO(wav_bytes) as buf:
        with wave.open(buf, "rb") as wf:
            return wf.getnframes() / wf.getframerate()


def _merge_speaker_labels(stt_result: STTResult, diar_segments) -> None:
    """Assign speaker_id to each STT segment based on diarization overlap."""
    for stt_seg in stt_result.segments:
        mid = (stt_seg.start + stt_seg.end) / 2
        assigned = "Speaker 1"
        for d in diar_segments:
            if d.start_sec <= mid <= d.end_sec:
                assigned = d.speaker_id
                break
        stt_seg.speaker_id = assigned


def _stt_engine_name(hw_tier: str, config: dict, language: str) -> str:
    stt_cfg = config.get("stt", {})
    engine = stt_cfg.get("engine", "faster_whisper")
    if hw_tier in ("minimum", "rpi"):
        return "whisper_cpp_base_en"
    if language == "hi" and hw_tier == "recommended":
        return "qwen3_asr_0.6b"
    return {"faster_whisper": "faster_whisper_large_v3_turbo",
            "whisper_cpp": "whisper_cpp_base_en",
            "qwen3_asr": "qwen3_asr_0.6b",
            "moonshine": "moonshine_v2_base"}.get(engine, engine)


def _build_attributed_transcript(stt_result: STTResult) -> str:
    """Build 'Speaker N: text' transcript string from segments."""
    lines = []
    current_speaker = None
    current_parts: list[str] = []

    for seg in stt_result.segments:
        spk = seg.speaker_id or "Speaker 1"
        if spk != current_speaker:
            if current_speaker is not None and current_parts:
                lines.append(f"{current_speaker}: {' '.join(current_parts)}")
            current_speaker = spk
            current_parts = [seg.text]
        else:
            current_parts.append(seg.text)

    if current_speaker and current_parts:
        lines.append(f"{current_speaker}: {' '.join(current_parts)}")

    return "\n".join(lines) if lines else stt_result.text
