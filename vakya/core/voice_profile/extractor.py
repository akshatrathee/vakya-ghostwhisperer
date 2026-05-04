"""Speaker clip extractor — Step 5a of the pipeline.

Selects the best audio clip per speaker from diarization segments,
computes a quality score, and updates the voice profile store.

"Better" clip heuristic (from PIPELINE.md):
- Longer is better (prefer 20–30s over 10s)
- Lower dB variance = cleaner speech
- Fewer VAD gaps within the segment = less silence
"""

from __future__ import annotations

import logging
import os
import struct
import wave
from pathlib import Path
from typing import List, Optional

import numpy as np

from ..diarizer.base import DiarSegment
from . import store as profile_store

log = logging.getLogger(__name__)

MIN_CLIP_SEC = 8.0
TARGET_CLIP_SEC = 30.0


def extract_and_update_profiles(
    audio_path: str,
    diar_segments: List[DiarSegment],
    session_id: str,
    profiles_root: Path | None = None,
) -> List[str]:
    """Extract best clip per speaker and update the voice profile store.

    Returns list of speaker_ids whose profiles were created or improved.
    """
    updated: List[str] = []

    by_speaker: dict[str, List[DiarSegment]] = {}
    for seg in diar_segments:
        by_speaker.setdefault(seg.speaker_id, []).append(seg)

    audio_samples, sample_rate = _read_wav(audio_path)

    for speaker_id, segments in by_speaker.items():
        best_seg = _select_best_segment(segments)
        if best_seg is None:
            continue

        dur = best_seg.end_sec - best_seg.start_sec
        if dur < MIN_CLIP_SEC:
            log.debug(
                "Speaker %s best clip %.1fs < %.1fs minimum — skipping",
                speaker_id,
                dur,
                MIN_CLIP_SEC,
            )
            continue

        quality = _compute_quality(audio_samples, sample_rate, best_seg)
        existing = profile_store.load_profile(speaker_id, profiles_root)

        if existing and existing.get("clip_quality_score", 0.0) >= quality:
            log.debug(
                "Speaker %s: existing clip better (%.3f >= %.3f) — keeping",
                speaker_id,
                existing["clip_quality_score"],
                quality,
            )
            continue

        clip_path = _save_clip(
            audio_samples, sample_rate, best_seg, speaker_id, profiles_root
        )
        if clip_path is None:
            continue

        if existing is None:
            profile = profile_store.create_profile(speaker_id, profiles_root)
        else:
            profile = existing

        profile["clip_path"] = str(clip_path)
        profile["clip_duration_sec"] = dur
        profile["clip_quality_score"] = quality
        profile["updated_at"] = profile_store._now_iso()
        if session_id not in profile.get("source_sessions", []):
            profile.setdefault("source_sessions", []).append(session_id)

        profile_store.save_profile(profile, profiles_root)
        log.info("Voice profile %s updated (quality=%.3f, dur=%.1fs)", speaker_id, quality, dur)
        updated.append(speaker_id)

    return updated


def _select_best_segment(segments: List[DiarSegment]) -> Optional[DiarSegment]:
    """Choose the single longest segment that stays under TARGET_CLIP_SEC."""
    candidates = sorted(segments, key=lambda s: s.end_sec - s.start_sec, reverse=True)
    for seg in candidates:
        dur = seg.end_sec - seg.start_sec
        if dur >= MIN_CLIP_SEC:
            # Clamp to TARGET_CLIP_SEC
            return DiarSegment(
                speaker_id=seg.speaker_id,
                start_sec=seg.start_sec,
                end_sec=min(seg.end_sec, seg.start_sec + TARGET_CLIP_SEC),
            )
    return None


def _compute_quality(samples: np.ndarray, sample_rate: int, seg: DiarSegment) -> float:
    """Heuristic quality score in [0, 1]. Higher = cleaner."""
    start_i = int(seg.start_sec * sample_rate)
    end_i = int(seg.end_sec * sample_rate)
    chunk = samples[start_i:end_i].astype(np.float32)

    if len(chunk) == 0:
        return 0.0

    # Lower dB variance → cleaner signal
    frame_size = sample_rate // 10  # 100ms frames
    rms_vals = []
    for i in range(0, len(chunk) - frame_size, frame_size):
        rms = np.sqrt(np.mean(chunk[i : i + frame_size] ** 2))
        if rms > 1e-9:
            rms_vals.append(20 * np.log10(rms))

    if not rms_vals:
        return 0.0

    db_variance = float(np.var(rms_vals))
    # Normalise: db_variance=0 → score=1, db_variance=100 → score≈0
    score = 1.0 / (1.0 + db_variance / 20.0)
    return round(float(score), 4)


def _save_clip(
    samples: np.ndarray,
    sample_rate: int,
    seg: DiarSegment,
    speaker_id: str,
    profiles_root: Optional[Path],
) -> Optional[Path]:
    root = profiles_root or (
        Path(__file__).parent.parent.parent / "data" / "voice_profiles"
    )
    d = root / speaker_id
    d.mkdir(parents=True, exist_ok=True)
    clip_path = d / "reference_clip.wav"

    start_i = int(seg.start_sec * sample_rate)
    end_i = int(seg.end_sec * sample_rate)
    clip = samples[start_i:end_i]

    try:
        with wave.open(str(clip_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(clip.astype(np.int16).tobytes())
        return clip_path
    except OSError as exc:
        log.error("Failed to save clip for %s: %s", speaker_id, exc)
        return None


def _read_wav(path: str) -> tuple[np.ndarray, int]:
    with wave.open(path, "rb") as wf:
        n_channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        sample_rate = wf.getframerate()
        raw = wf.readframes(wf.getnframes())

    fmt = {1: "B", 2: "h", 4: "i"}.get(sample_width, "h")
    count = len(raw) // sample_width
    samples = np.frombuffer(raw, dtype=np.dtype(fmt))

    if n_channels > 1:
        samples = samples.reshape(-1, n_channels).mean(axis=1)

    return samples.astype(np.float32), sample_rate
