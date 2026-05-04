"""Session metadata JSON writer — matches schemas/session.schema.json.

Written to data/sessions/{session_id}.json after each pipeline run.
No audio is stored. The .md transcript is written by router.py.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_SESSIONS_DIR = Path(__file__).parent.parent.parent / "data" / "sessions"


def write_session_metadata(
    session_id: str,
    started_at: datetime,
    completed_at: datetime,
    mode: str,
    language_detected: str,
    audio_duration_sec: float,
    stt_engine: str,
    llm_engine: str,
    speaker_ids: list[str],
    timing: dict,
    peak_ram_mb: float,
    transcript_path: Optional[str],
    vocab_terms_extracted: list[str],
    voice_profiles_updated: list[str],
    llm_chunk_count: int = 1,
) -> Optional[Path]:
    """Write session metadata JSON. Returns path written, or None on failure."""
    _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    # Normalise timestamps to ISO 8601
    def _iso(dt: datetime) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()

    metadata = {
        "session_id": session_id,
        "started_at": _iso(started_at),
        "completed_at": _iso(completed_at),
        "mode": mode,
        "language_detected": language_detected,
        "audio_duration_sec": round(audio_duration_sec, 2),
        "speaker_count": len(speaker_ids),
        "speaker_ids": speaker_ids,
        "stt_engine": stt_engine,
        "llm_engine": llm_engine,
        "llm_chunk_count": llm_chunk_count,
        "peak_ram_mb": round(peak_ram_mb, 1),
        "timing": {
            "vad_sec": round(timing.get("vad_sec", 0.0), 3),
            "stt_sec": round(timing.get("stt_sec", 0.0), 3),
            "diarization_sec": round(timing.get("diarization_sec", 0.0), 3),
            "llm_sec": round(timing.get("llm_sec", 0.0), 3),
            "total_sec": round(timing.get("total_sec", 0.0), 3),
        },
        "transcript_path": transcript_path,
        "vocab_terms_extracted": vocab_terms_extracted,
        "voice_profiles_updated": voice_profiles_updated,
        "wiki_ingest_status": "skipped_phase3",
    }

    path = _SESSIONS_DIR / f"{session_id}.json"
    try:
        path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        log.debug("Session metadata written: %s", path)
        return path
    except OSError as exc:
        log.error("Failed to write session metadata: %s", exc)
        return None


def _audio_duration_from_timing(timing: dict) -> float:
    """Derive approximate audio duration from STT timing (rough heuristic)."""
    stt_sec = timing.get("stt_sec", 0.0)
    return stt_sec * 6.0  # ~6× realtime on recommended hardware
