"""Integration test — full pipeline on a 30s fixture audio file.

Skipped if model weights are not present (CI-safe).
"""

import os
import pytest
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def test_pipeline_result_structure():
    """Pipeline result dataclass has expected fields."""
    from vakya.core.pipeline import PipelineResult

    r = PipelineResult(
        session_id="test-123",
        formatted_text="# Dictation\n\nHello world.",
        raw_transcript="Speaker 1: Hello world.",
        language_detected="en",
        speaker_ids=["Speaker 1"],
        timing={"vad_sec": 0.1, "stt_sec": 1.0, "total_sec": 1.1},
        peak_ram_mb=100.0,
    )
    assert r.session_id == "test-123"
    assert "Hello world" in r.formatted_text
    assert r.peak_ram_mb == 100.0


@pytest.mark.skipif(
    not os.path.exists("vakya/models/stt/whisper-base-en.bin"),
    reason="whisper.cpp model not present",
)
def test_pipeline_full_cli_path():
    """End-to-end: WAV file → formatted transcript via pipeline.run()."""
    fixture = FIXTURES / "en_clean_30s.wav"
    if not fixture.exists():
        pytest.skip("Fixture en_clean_30s.wav not present")

    from vakya.core.pipeline import run

    result = run(
        audio_path=str(fixture),
        mode="dictation",
        copy_to_clipboard=False,
        write_log=False,
    )

    assert result.formatted_text.strip() != ""
    assert result.language_detected in ("en", "auto")
    assert result.timing.get("total_sec", 0) > 0
