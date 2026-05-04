"""Tests for core/voice_profile/ — store + extractor."""

import json
import struct
import wave
import numpy as np
import pytest
from pathlib import Path
from unittest.mock import patch

from vakya.core.voice_profile import store as profile_store


def _write_test_wav(path: Path, duration_sec: float = 10.0, freq: float = 440.0) -> None:
    sample_rate = 16000
    n = int(sample_rate * duration_sec)
    import math
    samples = [
        int(0.3 * 32767 * math.sin(2 * math.pi * freq * i / sample_rate))
        for i in range(n)
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"{n}h", *samples))


class TestProfileStore:
    def test_create_profile(self, tmp_path):
        p = profile_store.create_profile("spk_001", root=tmp_path)
        assert p["profile_id"] == "spk_001"
        assert p["clip_duration_sec"] == 0.0
        assert (tmp_path / "spk_001" / "profile.json").exists()

    def test_load_missing_returns_none(self, tmp_path):
        result = profile_store.load_profile("nonexistent", root=tmp_path)
        assert result is None

    def test_save_and_load_roundtrip(self, tmp_path):
        profile = profile_store.create_profile("spk_002", root=tmp_path)
        profile["display_name"] = "Ram"
        profile_store.save_profile(profile, root=tmp_path)
        loaded = profile_store.load_profile("spk_002", root=tmp_path)
        assert loaded is not None
        assert loaded["display_name"] == "Ram"

    def test_list_speaker_ids(self, tmp_path):
        profile_store.create_profile("spk_a", root=tmp_path)
        profile_store.create_profile("spk_b", root=tmp_path)
        ids = profile_store.list_speaker_ids(root=tmp_path)
        assert set(ids) == {"spk_a", "spk_b"}

    def test_empty_root_returns_empty_list(self, tmp_path):
        assert profile_store.list_speaker_ids(root=tmp_path) == []


class TestExtractor:
    def test_extract_creates_profile(self, tmp_path):
        from vakya.core.voice_profile.extractor import extract_and_update_profiles
        from vakya.core.diarizer.base import DiarSegment

        # Create a 20s test WAV
        wav_path = tmp_path / "test.wav"
        _write_test_wav(wav_path, duration_sec=20.0)

        diar_segments = [
            DiarSegment(speaker_id="SPEAKER_00", start_sec=0.0, end_sec=19.0),
        ]

        updated = extract_and_update_profiles(
            str(wav_path), diar_segments, "test-session-001",
            profiles_root=tmp_path / "profiles",
        )

        assert "SPEAKER_00" in updated
        profile = profile_store.load_profile("SPEAKER_00", root=tmp_path / "profiles")
        assert profile is not None
        assert profile["clip_duration_sec"] >= 8.0
        assert profile["clip_quality_score"] > 0.0
        assert (tmp_path / "profiles" / "SPEAKER_00" / "reference_clip.wav").exists()

    def test_extract_skips_short_segments(self, tmp_path):
        from vakya.core.voice_profile.extractor import extract_and_update_profiles
        from vakya.core.diarizer.base import DiarSegment

        wav_path = tmp_path / "short.wav"
        _write_test_wav(wav_path, duration_sec=5.0)

        diar_segments = [
            DiarSegment(speaker_id="SPEAKER_00", start_sec=0.0, end_sec=4.0),  # < 8s min
        ]

        updated = extract_and_update_profiles(
            str(wav_path), diar_segments, "test-session-002",
            profiles_root=tmp_path / "profiles",
        )

        assert updated == []

    def test_extract_does_not_replace_better_profile(self, tmp_path):
        from vakya.core.voice_profile.extractor import extract_and_update_profiles
        from vakya.core.diarizer.base import DiarSegment

        wav_path = tmp_path / "test.wav"
        _write_test_wav(wav_path, duration_sec=20.0)
        profiles_root = tmp_path / "profiles"

        # First extraction
        diar_segments = [DiarSegment(speaker_id="SPEAKER_00", start_sec=0.0, end_sec=19.0)]
        extract_and_update_profiles(str(wav_path), diar_segments, "session-1", profiles_root=profiles_root)

        profile_before = profile_store.load_profile("SPEAKER_00", root=profiles_root)

        # Manually set very high quality score so second extraction won't replace it
        profile_before["clip_quality_score"] = 1.0
        profile_store.save_profile(profile_before, root=profiles_root)

        # Second extraction should NOT replace
        updated2 = extract_and_update_profiles(str(wav_path), diar_segments, "session-2", profiles_root=profiles_root)
        assert updated2 == []
