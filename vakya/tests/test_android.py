"""Sprint 6 — Android platform tests.

Tests cover:
- AudioAndroidCapture interface + WAV lifecycle
- PipelineBridge config + JSON contract
- main.init() wiring
- Kotlin-free path: all JVM calls are stubbed via _jvm_available() = False
"""

from __future__ import annotations

import json
import os
import struct
import tempfile
import wave
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_wav(path: str, duration_s: float = 1.0, sample_rate: int = 16_000) -> str:
    """Write a valid 16kHz mono PCM WAV to *path*."""
    n_frames = int(sample_rate * duration_s)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * n_frames)
    return path


# ---------------------------------------------------------------------------
# AudioAndroidCapture
# ---------------------------------------------------------------------------

class TestAudioAndroidCapture:
    def test_import(self):
        from vakya.platform.android.audio_android import AndroidAudioCapture
        assert AndroidAudioCapture is not None

    def test_implements_audio_capture(self):
        from vakya.core.audio_capture import AudioCapture
        from vakya.platform.android.audio_android import AndroidAudioCapture
        assert issubclass(AndroidAudioCapture, AudioCapture)

    def test_initial_state(self):
        from vakya.platform.android.audio_android import AndroidAudioCapture
        cap = AndroidAudioCapture()
        assert not cap.is_recording

    def test_get_wav_path_raises_before_set(self):
        from vakya.platform.android.audio_android import AndroidAudioCapture
        cap = AndroidAudioCapture()
        with pytest.raises(RuntimeError, match="No WAV path"):
            cap.get_wav_path()

    def test_set_wav_path_stores_path(self):
        from vakya.platform.android.audio_android import AndroidAudioCapture
        cap = AndroidAudioCapture()
        cap.set_wav_path("/data/user/0/com.vakya.app/cache/test.wav")
        assert cap.get_wav_path() == "/data/user/0/com.vakya.app/cache/test.wav"

    def test_set_wav_path_rejects_empty(self):
        from vakya.platform.android.audio_android import AndroidAudioCapture
        cap = AndroidAudioCapture()
        with pytest.raises(ValueError):
            cap.set_wav_path("")

    def test_delete_wav_removes_file(self, tmp_path):
        from vakya.platform.android.audio_android import AndroidAudioCapture
        wav = str(tmp_path / "test.wav")
        _make_wav(wav)
        cap = AndroidAudioCapture()
        cap.set_wav_path(wav)
        cap.delete_wav()
        assert not os.path.exists(wav)

    def test_delete_wav_clears_path(self, tmp_path):
        from vakya.platform.android.audio_android import AndroidAudioCapture
        wav = str(tmp_path / "test.wav")
        _make_wav(wav)
        cap = AndroidAudioCapture()
        cap.set_wav_path(wav)
        cap.delete_wav()
        with pytest.raises(RuntimeError):
            cap.get_wav_path()

    def test_delete_wav_silent_if_missing(self):
        from vakya.platform.android.audio_android import AndroidAudioCapture
        cap = AndroidAudioCapture()
        cap.set_wav_path("/nonexistent/path/file.wav")
        cap.delete_wav()   # must not raise

    def test_validate_wav_passes_correct_spec(self, tmp_path):
        from vakya.platform.android.audio_android import AndroidAudioCapture
        wav = str(tmp_path / "ok.wav")
        _make_wav(wav, sample_rate=16_000)
        cap = AndroidAudioCapture()
        cap.set_wav_path(wav)
        cap.validate_wav()   # no raise

    def test_validate_wav_rejects_wrong_sample_rate(self, tmp_path):
        from vakya.platform.android.audio_android import AndroidAudioCapture
        wav = str(tmp_path / "bad.wav")
        _make_wav(wav, sample_rate=44_100)
        cap = AndroidAudioCapture()
        cap.set_wav_path(wav)
        with pytest.raises(ValueError, match="16000"):
            cap.validate_wav()

    def test_start_sets_recording_flag_no_jvm(self):
        from vakya.platform.android import audio_android
        from vakya.platform.android.audio_android import AndroidAudioCapture
        with patch.object(audio_android, "_jvm_available", return_value=False):
            cap = AndroidAudioCapture()
            cap.start()
            assert cap.is_recording

    def test_stop_clears_recording_flag_no_jvm(self):
        from vakya.platform.android import audio_android
        from vakya.platform.android.audio_android import AndroidAudioCapture
        with patch.object(audio_android, "_jvm_available", return_value=False):
            cap = AndroidAudioCapture()
            cap.start()
            cap.stop()
            assert not cap.is_recording

    def test_sample_rate_constant(self):
        from vakya.platform.android.audio_android import AndroidAudioCapture
        assert AndroidAudioCapture.SAMPLE_RATE == 16_000

    def test_channels_constant(self):
        from vakya.platform.android.audio_android import AndroidAudioCapture
        assert AndroidAudioCapture.CHANNELS == 1


# ---------------------------------------------------------------------------
# PipelineBridge
# ---------------------------------------------------------------------------

class TestPipelineBridge:
    def test_import(self):
        from vakya.platform.android.pipeline_bridge import PipelineBridge
        assert PipelineBridge is not None

    def test_instantiates(self, tmp_path):
        from vakya.platform.android.pipeline_bridge import PipelineBridge
        bridge = PipelineBridge(str(tmp_path / "cfg"), str(tmp_path / "models"))
        assert bridge is not None

    def test_config_contains_stt(self, tmp_path):
        from vakya.platform.android.pipeline_bridge import PipelineBridge
        bridge = PipelineBridge(str(tmp_path), str(tmp_path))
        cfg = json.loads(bridge.get_config_json())
        assert cfg["stt"]["engine"] == "moonshine"

    def test_config_default_llm_rule_based(self, tmp_path):
        from vakya.platform.android.pipeline_bridge import PipelineBridge
        bridge = PipelineBridge(str(tmp_path), str(tmp_path))
        cfg = json.loads(bridge.get_config_json())
        assert cfg["llm"]["engine"] == "rule_based"

    def test_enhanced_cleanup_switches_engine(self, tmp_path):
        from vakya.platform.android.pipeline_bridge import PipelineBridge
        bridge = PipelineBridge(str(tmp_path), str(tmp_path), enhanced_cleanup=True)
        cfg = json.loads(bridge.get_config_json())
        assert cfg["llm"]["engine"] == "phi3_mini"

    def test_set_enhanced_cleanup_runtime_toggle(self, tmp_path):
        from vakya.platform.android.pipeline_bridge import PipelineBridge
        bridge = PipelineBridge(str(tmp_path), str(tmp_path))
        bridge.set_enhanced_cleanup(True)
        cfg = json.loads(bridge.get_config_json())
        assert cfg["llm"]["engine"] == "phi3_mini"

    def test_set_enhanced_cleanup_false_restores_rule_based(self, tmp_path):
        from vakya.platform.android.pipeline_bridge import PipelineBridge
        bridge = PipelineBridge(str(tmp_path), str(tmp_path), enhanced_cleanup=True)
        bridge.set_enhanced_cleanup(False)
        cfg = json.loads(bridge.get_config_json())
        assert cfg["llm"]["engine"] == "rule_based"

    def test_transcribe_missing_wav_returns_error_json(self, tmp_path):
        from vakya.platform.android.pipeline_bridge import PipelineBridge
        bridge = PipelineBridge(str(tmp_path), str(tmp_path))
        result = json.loads(bridge.transcribe("/nonexistent/file.wav", delete_after=False))
        assert result["error"] is not None
        assert "WAV not found" in result["error"]

    def test_transcribe_result_has_expected_keys(self, tmp_path):
        from vakya.platform.android.pipeline_bridge import PipelineBridge
        bridge = PipelineBridge(str(tmp_path), str(tmp_path))
        result = json.loads(bridge.transcribe("/nonexistent/file.wav", delete_after=False))
        assert set(result.keys()) >= {"text", "language", "duration_s", "engine", "error"}

    def test_transcribe_deletes_wav_on_error(self, tmp_path):
        from vakya.platform.android.pipeline_bridge import PipelineBridge
        wav = str(tmp_path / "temp.wav")
        _make_wav(wav)

        # Pipeline.run will fail (no models loaded), but WAV should be deleted
        bridge = PipelineBridge(str(tmp_path / "cfg"), str(tmp_path / "models"))
        bridge.transcribe(wav, delete_after=True)
        assert not os.path.exists(wav)

    def test_synthesise_result_has_expected_keys(self, tmp_path):
        from vakya.platform.android.pipeline_bridge import PipelineBridge
        bridge = PipelineBridge(str(tmp_path), str(tmp_path))
        result = json.loads(bridge.synthesise("hello"))
        assert set(result.keys()) >= {"wav_path", "duration_s", "error"}

    def test_hardware_tier_is_mobile(self, tmp_path):
        from vakya.platform.android.pipeline_bridge import PipelineBridge
        bridge = PipelineBridge(str(tmp_path), str(tmp_path))
        cfg = json.loads(bridge.get_config_json())
        assert cfg["hardware_tier"] == "mobile"


# ---------------------------------------------------------------------------
# main.init()
# ---------------------------------------------------------------------------

class TestAndroidMain:
    def test_init_returns_pipeline_bridge(self, tmp_path):
        from vakya.platform.android import main
        from vakya.platform.android.pipeline_bridge import PipelineBridge
        bridge = main.init(str(tmp_path / "cfg"), str(tmp_path / "models"))
        assert isinstance(bridge, PipelineBridge)

    def test_init_creates_sessions_dir(self, tmp_path):
        from vakya.platform.android import main
        cfg = str(tmp_path / "cfg")
        main.init(cfg, str(tmp_path / "models"))
        assert os.path.isdir(os.path.join(cfg, "sessions"))
