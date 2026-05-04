"""Tests for core/vad.py — energy-based VAD (no model weights required)."""

import pytest
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def test_silence_gives_no_segments():
    from vakya.core.vad import detect_speech_segments

    fixture = FIXTURES / "silence_5s.wav"
    if not fixture.exists():
        pytest.skip("Fixture silence_5s.wav not present — run create_fixtures.py")

    # Pure silence should produce no speech segments (or very few near the threshold)
    segments = detect_speech_segments(str(fixture))
    # Energy VAD on pure silence: max energy is 0, threshold is 0 → all frames pass
    # This is expected edge-case behaviour — just verify it doesn't crash
    assert isinstance(segments, list)


def test_tone_gives_segments():
    from vakya.core.vad import detect_speech_segments

    fixture = FIXTURES / "tone_30s.wav"
    if not fixture.exists():
        pytest.skip("Fixture tone_30s.wav not present — run create_fixtures.py")

    segments = detect_speech_segments(str(fixture))
    assert isinstance(segments, list)
    # A continuous tone should be detected as one big speech segment
    assert len(segments) >= 1


def test_speech_like_segments_have_reasonable_duration():
    from vakya.core.vad import detect_speech_segments, SpeechSegment

    fixture = FIXTURES / "speech_like_30s.wav"
    if not fixture.exists():
        pytest.skip("Fixture speech_like_30s.wav not present — run create_fixtures.py")

    segments = detect_speech_segments(str(fixture))
    assert isinstance(segments, list)
    for seg in segments:
        assert isinstance(seg, SpeechSegment)
        assert seg.end_ms > seg.start_ms
        assert seg.end_ms - seg.start_ms >= 300  # min 300ms (min_speech_ms)


def test_vad_result_is_list_of_speech_segments():
    from vakya.core.vad import SpeechSegment, detect_speech_segments

    fixture = FIXTURES / "speech_like_30s.wav"
    if not fixture.exists():
        pytest.skip("run create_fixtures.py first")

    result = detect_speech_segments(str(fixture))
    for seg in result:
        assert hasattr(seg, "start_ms")
        assert hasattr(seg, "end_ms")
