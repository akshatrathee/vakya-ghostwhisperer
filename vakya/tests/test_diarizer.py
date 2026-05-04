"""Tests for core/diarizer/ — interface contracts and merge logic."""

import pytest
from vakya.core.diarizer.base import Diarizer, DiarSegment


def test_diarizer_interface_not_instantiable():
    with pytest.raises(TypeError):
        Diarizer()


def test_diar_segment_dataclass():
    seg = DiarSegment(speaker_id="SPEAKER_00", start_sec=0.0, end_sec=5.5)
    assert seg.speaker_id == "SPEAKER_00"
    assert seg.start_sec == 0.0
    assert seg.end_sec == 5.5


def test_merge_speaker_labels_midpoint():
    """_merge_speaker_labels assigns correct speaker by midpoint overlap."""
    from vakya.core.pipeline import _merge_speaker_labels
    from vakya.core.stt.base import STTResult, STTSegment

    stt_result = STTResult(
        text="Hello world. Thank you.",
        segments=[
            STTSegment(start=0.0, end=2.0, text="Hello world."),
            STTSegment(start=3.0, end=5.0, text="Thank you."),
        ],
        language_detected="en",
    )
    diar_segments = [
        DiarSegment(speaker_id="SPEAKER_00", start_sec=0.0, end_sec=2.5),
        DiarSegment(speaker_id="SPEAKER_01", start_sec=2.5, end_sec=6.0),
    ]

    _merge_speaker_labels(stt_result, diar_segments)

    assert stt_result.segments[0].speaker_id == "SPEAKER_00"
    assert stt_result.segments[1].speaker_id == "SPEAKER_01"


def test_merge_speaker_labels_no_overlap_defaults_to_speaker1():
    """Segments outside all diarizer windows default to Speaker 1."""
    from vakya.core.pipeline import _merge_speaker_labels
    from vakya.core.stt.base import STTResult, STTSegment

    stt_result = STTResult(
        text="Mystery speaker.",
        segments=[STTSegment(start=100.0, end=105.0, text="Mystery speaker.")],
        language_detected="en",
    )
    diar_segments = [
        DiarSegment(speaker_id="SPEAKER_00", start_sec=0.0, end_sec=10.0),
    ]

    _merge_speaker_labels(stt_result, diar_segments)
    assert stt_result.segments[0].speaker_id == "Speaker 1"


def test_build_attributed_transcript_single_speaker():
    from vakya.core.pipeline import _build_attributed_transcript
    from vakya.core.stt.base import STTResult, STTSegment

    result = STTResult(
        text="Hello world.",
        segments=[
            STTSegment(start=0.0, end=1.0, text="Hello", speaker_id="Speaker 1"),
            STTSegment(start=1.0, end=2.0, text="world.", speaker_id="Speaker 1"),
        ],
        language_detected="en",
    )
    transcript = _build_attributed_transcript(result)
    assert transcript == "Speaker 1: Hello world."


def test_build_attributed_transcript_two_speakers():
    from vakya.core.pipeline import _build_attributed_transcript
    from vakya.core.stt.base import STTResult, STTSegment

    result = STTResult(
        text="Hello. How are you?",
        segments=[
            STTSegment(start=0.0, end=1.0, text="Hello.", speaker_id="Speaker 1"),
            STTSegment(start=1.5, end=3.0, text="How are you?", speaker_id="Speaker 2"),
        ],
        language_detected="en",
    )
    transcript = _build_attributed_transcript(result)
    assert "Speaker 1: Hello." in transcript
    assert "Speaker 2: How are you?" in transcript
