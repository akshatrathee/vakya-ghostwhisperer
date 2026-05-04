"""Tests for core/tts/ — engine interface, factory, synthesis contracts.

All tests run without model weights.
Engine tests that need model files are skipped when files are absent.
"""

from __future__ import annotations

import io
import struct
import wave
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from vakya.core.tts.base import TTSEngine


# ── Interface contracts ───────────────────────────────────────────────────────

def test_tts_engine_not_instantiable():
    with pytest.raises(TypeError):
        TTSEngine()


def test_kokoro_engine_is_tts_engine():
    from vakya.core.tts.kokoro import KokoroEngine
    assert issubclass(KokoroEngine, TTSEngine)


def test_cosyvoice2_engine_is_tts_engine():
    from vakya.core.tts.cosyvoice2 import CosyVoice2Engine
    assert issubclass(CosyVoice2Engine, TTSEngine)


def test_piper_engine_is_tts_engine():
    from vakya.core.tts.piper import PiperEngine
    assert issubclass(PiperEngine, TTSEngine)


def test_omnivoice_engine_is_tts_engine():
    from vakya.core.tts.omnivoice import OmniVoiceEngine
    assert issubclass(OmniVoiceEngine, TTSEngine)


# ── Engine factory ────────────────────────────────────────────────────────────

class TestEngineFactory:
    def test_rpi_tier_returns_piper(self):
        from vakya.core.tts.engine_factory import select_tts_engine
        from vakya.core.tts.piper import PiperEngine

        with patch("vakya.core.tts.engine_factory._model_present", return_value=True):
            engine = select_tts_engine("rpi")
        assert isinstance(engine, PiperEngine)

    def test_minimum_tier_returns_kokoro(self):
        from vakya.core.tts.engine_factory import select_tts_engine
        from vakya.core.tts.kokoro import KokoroEngine

        with patch("vakya.core.tts.engine_factory._model_present", return_value=True):
            engine = select_tts_engine("minimum")
        assert isinstance(engine, KokoroEngine)

    def test_recommended_no_cloning_returns_cosyvoice2(self):
        from vakya.core.tts.engine_factory import select_tts_engine
        from vakya.core.tts.cosyvoice2 import CosyVoice2Engine

        with patch("vakya.core.tts.engine_factory._model_present", return_value=True):
            engine = select_tts_engine("recommended", cloning_required=False)
        assert isinstance(engine, CosyVoice2Engine)

    def test_recommended_cloning_no_omnivoice_returns_cosyvoice2(self):
        from vakya.core.tts.engine_factory import select_tts_engine
        from vakya.core.tts.cosyvoice2 import CosyVoice2Engine
        import vakya.core.tts.engine_factory as factory

        original = factory.USE_OMNIVOICE
        factory.USE_OMNIVOICE = False
        try:
            with patch("vakya.core.tts.engine_factory._model_present", return_value=True):
                engine = select_tts_engine("recommended", cloning_required=True)
            assert isinstance(engine, CosyVoice2Engine)
        finally:
            factory.USE_OMNIVOICE = original

    def test_recommended_cloning_with_omnivoice_benchmark_passed(self):
        from vakya.core.tts.engine_factory import select_tts_engine
        from vakya.core.tts.omnivoice import OmniVoiceEngine
        import vakya.core.tts.engine_factory as factory

        original_flag = factory.USE_OMNIVOICE
        original_rtf = factory.OMNIVOICE_CPU_RTF
        factory.USE_OMNIVOICE = True
        factory.OMNIVOICE_CPU_RTF = 1.2
        try:
            with patch("vakya.core.tts.engine_factory._model_present", return_value=True):
                engine = select_tts_engine("recommended", cloning_required=True)
            assert isinstance(engine, OmniVoiceEngine)
        finally:
            factory.USE_OMNIVOICE = original_flag
            factory.OMNIVOICE_CPU_RTF = original_rtf

    def test_no_models_raises_runtime_error(self):
        from vakya.core.tts.engine_factory import select_tts_engine

        with patch("vakya.core.tts.engine_factory._model_present", return_value=False):
            with pytest.raises(RuntimeError, match="No TTS model found"):
                select_tts_engine("recommended")

    def test_fallback_to_kokoro_when_cosyvoice2_absent(self):
        from vakya.core.tts.engine_factory import select_tts_engine
        from vakya.core.tts.kokoro import KokoroEngine

        def model_present(path: str) -> bool:
            return "kokoro" in path

        with patch("vakya.core.tts.engine_factory._model_present", side_effect=model_present):
            engine = select_tts_engine("recommended")
        assert isinstance(engine, KokoroEngine)

    def test_engine_name_helper(self):
        from vakya.core.tts.engine_factory import engine_name
        from vakya.core.tts.kokoro import KokoroEngine

        with patch("vakya.core.tts.engine_factory._model_present", return_value=True):
            eng = KokoroEngine()
        assert engine_name(eng) == "kokoro"


# ── Synthesis with mock engine ────────────────────────────────────────────────

def _make_test_wav(duration_sec: float = 1.0, sample_rate: int = 16000) -> bytes:
    """Create minimal valid WAV bytes for testing."""
    n = int(sample_rate * duration_sec)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"{n}h", *([0] * n)))
    return buf.getvalue()


class TestSynthesise:
    def test_synthesise_returns_wav_bytes(self):
        """pipeline.synthesise() with a mock engine returns WAV bytes."""
        from vakya.core import pipeline

        mock_engine = MagicMock(spec=TTSEngine)
        mock_engine.synthesise.return_value = _make_test_wav(2.0)

        with patch("vakya.core.pipeline._detect_hardware_tier", return_value="recommended"), \
             patch("vakya.core.pipeline._load_config", return_value={}), \
             patch("vakya.core.tts.engine_factory.select_tts_engine", return_value=mock_engine), \
             patch("vakya.core.output.audio_player.play_wav_bytes"):

            result = pipeline.synthesise("Hello world.", play=False)

        assert isinstance(result, bytes)
        assert len(result) > 0
        # Must be valid WAV
        with io.BytesIO(result) as buf:
            with wave.open(buf, "rb") as wf:
                assert wf.getnframes() > 0

    def test_synthesise_passes_voice_profile_id(self):
        from vakya.core import pipeline

        mock_engine = MagicMock(spec=TTSEngine)
        mock_engine.synthesise.return_value = _make_test_wav()

        with patch("vakya.core.pipeline._detect_hardware_tier", return_value="recommended"), \
             patch("vakya.core.pipeline._load_config", return_value={}), \
             patch("vakya.core.tts.engine_factory.select_tts_engine", return_value=mock_engine), \
             patch("vakya.core.output.audio_player.play_wav_bytes"):

            pipeline.synthesise("Test text.", voice_profile_id="SPEAKER_00", play=False)

        mock_engine.synthesise.assert_called_once_with(
            "Test text.", voice_profile_id="SPEAKER_00"
        )

    def test_synthesise_saves_to_file(self, tmp_path):
        from vakya.core import pipeline

        mock_engine = MagicMock(spec=TTSEngine)
        wav = _make_test_wav()
        mock_engine.synthesise.return_value = wav

        out_path = tmp_path / "out.wav"

        with patch("vakya.core.pipeline._detect_hardware_tier", return_value="minimum"), \
             patch("vakya.core.pipeline._load_config", return_value={}), \
             patch("vakya.core.tts.engine_factory.select_tts_engine", return_value=mock_engine), \
             patch("vakya.core.output.audio_player.play_wav_bytes"):

            pipeline.synthesise("Save this.", play=False, save_path=str(out_path))

        assert out_path.exists()
        assert out_path.read_bytes() == wav

    def test_synthesise_cloning_flag_propagated(self):
        """cloning_required=True when voice_profile_id is given."""
        from vakya.core import pipeline
        from vakya.core.tts import engine_factory

        mock_engine = MagicMock(spec=TTSEngine)
        mock_engine.synthesise.return_value = _make_test_wav()

        calls = []
        original_select = engine_factory.select_tts_engine

        def capture_select(hw_tier, cloning_required=False):
            calls.append({"hw_tier": hw_tier, "cloning_required": cloning_required})
            return mock_engine

        with patch("vakya.core.pipeline._detect_hardware_tier", return_value="recommended"), \
             patch("vakya.core.pipeline._load_config", return_value={}), \
             patch("vakya.core.tts.engine_factory.select_tts_engine", side_effect=capture_select), \
             patch("vakya.core.output.audio_player.play_wav_bytes"):

            pipeline.synthesise("Clone me.", voice_profile_id="SPEAKER_01", play=False)

        assert calls[0]["cloning_required"] is True


# ── Audio player ──────────────────────────────────────────────────────────────

class TestAudioPlayer:
    def test_play_wav_bytes_calls_sounddevice(self):
        from vakya.core.output import audio_player

        wav = _make_test_wav(0.5)
        mock_sd = MagicMock()
        mock_np = MagicMock()

        import numpy as np
        mock_np.frombuffer = np.frombuffer
        mock_np.float32 = np.float32
        mock_np.int16 = np.int16
        mock_np.uint8 = np.uint8
        mock_np.int32 = np.int32

        with patch("vakya.core.output.audio_player._play_sounddevice") as mock_play:
            audio_player.play_wav_bytes(wav)
            mock_play.assert_called_once_with(wav)

    def test_play_falls_back_on_error(self):
        from vakya.core.output import audio_player

        wav = _make_test_wav(0.5)

        with patch("vakya.core.output.audio_player._play_sounddevice", side_effect=ImportError("no sd")), \
             patch("vakya.core.output.audio_player._play_playsound") as mock_playsound:
            audio_player.play_wav_bytes(wav)
            mock_playsound.assert_called_once_with(wav)


# ── ADR-004 benchmark stub ────────────────────────────────────────────────────

def test_omnivoice_benchmark_rtf_function_exists():
    from vakya.core.tts.omnivoice import benchmark_rtf
    assert callable(benchmark_rtf)


def test_omnivoice_rtf_threshold_constants():
    from vakya.core.tts.engine_factory import _ADR004_RTF_THRESHOLD
    assert _ADR004_RTF_THRESHOLD == 2.0
