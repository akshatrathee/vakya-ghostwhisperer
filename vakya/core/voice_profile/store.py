"""Voice profile store — read/write speaker profiles.

Profile layout:
  data/voice_profiles/{speaker_id}/
    reference_clip.wav   — best 10-30s speech clip (16kHz mono)
    embedding.npy        — speaker embedding from pyannote/WhisperX
    profile.json         — metadata matching voice_profile.schema.json
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_PROFILES_ROOT = Path(__file__).parent.parent.parent / "data" / "voice_profiles"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def profile_dir(speaker_id: str, root: Path | None = None) -> Path:
    return (root or _PROFILES_ROOT) / speaker_id


def load_profile(speaker_id: str, root: Path | None = None) -> dict | None:
    p = profile_dir(speaker_id, root) / "profile.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Failed to load profile %s: %s", speaker_id, exc)
        return None


def save_profile(profile: dict, root: Path | None = None) -> None:
    d = profile_dir(profile["profile_id"], root)
    d.mkdir(parents=True, exist_ok=True)
    (d / "profile.json").write_text(
        json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.debug("Saved voice profile %s", profile["profile_id"])


def create_profile(speaker_id: str, root: Path | None = None) -> dict:
    now = _now_iso()
    profile = {
        "profile_id": speaker_id,
        "display_name": None,
        "created_at": now,
        "updated_at": now,
        "clip_path": f"voice_profiles/{speaker_id}/reference_clip.wav",
        "clip_duration_sec": 0.0,
        "embedding_path": None,
        "source_sessions": [],
        "clip_quality_score": 0.0,
        "language": "en",
        "tts_engine_tested": None,
    }
    save_profile(profile, root)
    return profile


def list_speaker_ids(root: Path | None = None) -> list[str]:
    r = root or _PROFILES_ROOT
    if not r.exists():
        return []
    return [d.name for d in r.iterdir() if d.is_dir() and (d / "profile.json").exists()]
