"""STT engine tests — run against fixture audio files.

Fixture files in tests/fixtures/:
  en_clean_30s.wav     — English, quiet room
  en_fillers_30s.wav   — English, heavy filler words
  hi_clean_30s.wav     — Hindi, quiet room
  multi_speaker_2min.wav
  outdoor_noisy_30s.wav

These tests are skipped if model weights are not present (CI-safe).
"""

import os
import pytest
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def skip_if_no_model(model_path: str):
    return pytest.mark.skipif(
        not os.path.exists(model_path),
        reason=f"Model not found: {model_path}",
    )


@skip_if_no_model("vakya/models/stt/whisper-base-en.bin")
def test_whisper_cpp_english(tmp_path):
    from vakya.core.stt.whisper_cpp import WhisperCppEngine

    fixture = FIXTURES / "en_clean_30s.wav"
    if not fixture.exists():
        pytest.skip("Fixture en_clean_30s.wav not present")

    engine = WhisperCppEngine()
    result = engine.transcribe(str(fixture), language="en")

    assert result.text.strip() != ""
    assert result.language_detected == "en"
    assert len(result.segments) > 0


@skip_if_no_model("vakya/models/stt/faster-whisper-large-v3-turbo")
def test_faster_whisper_english(tmp_path):
    from vakya.core.stt.faster_whisper import FasterWhisperEngine

    fixture = FIXTURES / "en_clean_30s.wav"
    if not fixture.exists():
        pytest.skip("Fixture en_clean_30s.wav not present")

    engine = FasterWhisperEngine()
    result = engine.transcribe(str(fixture), language="en")

    assert result.text.strip() != ""
    assert len(result.segments) > 0


def test_stt_base_interface():
    """STTEngine interface should not be directly instantiable."""
    from vakya.core.stt.base import STTEngine

    with pytest.raises(TypeError):
        STTEngine()


def test_stt_result_dataclass():
    from vakya.core.stt.base import STTResult, STTSegment

    seg = STTSegment(start=0.0, end=5.0, text="Hello world")
    result = STTResult(text="Hello world", segments=[seg], language_detected="en")

    assert result.text == "Hello world"
    assert len(result.segments) == 1
    assert result.language_detected == "en"
    assert result.segments[0].speaker_id is None
