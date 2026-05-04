"""Sprint 7 — iOS platform tests.

Tests cover:
- iOSAudioCapture interface + WAV lifecycle
- CoreML engine wrappers (graceful degradation when libs absent)
- iOSPipelineBridge config + JSON contract
- main.init() wiring
- All Rubicon-ObjC / coremltools calls are absent — graceful fallback verified
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
    n = int(sample_rate * duration_s)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * n)
    return path


# ---------------------------------------------------------------------------
# iOSAudioCapture
# ---------------------------------------------------------------------------

class TestiOSAudioCapture:
    def test_import(self):
        from vakya.platform.ios.audio_ios import iOSAudioCapture
        assert iOSAudioCapture is not None

    def test_implements_audio_capture(self):
        from vakya.core.audio_capture import AudioCapture
        from vakya.platform.ios.audio_ios import iOSAudioCapture
        assert issubclass(iOSAudioCapture, AudioCapture)

    def test_initial_state_not_recording(self):
        from vakya.platform.ios.audio_ios import iOSAudioCapture
        cap = iOSAudioCapture()
        assert not cap.is_recording

    def test_get_wav_path_raises_before_set(self):
        from vakya.platform.ios.audio_ios import iOSAudioCapture
        cap = iOSAudioCapture()
        with pytest.raises(RuntimeError, match="No WAV path"):
            cap.get_wav_path()

    def test_set_wav_path_stores_path(self):
        from vakya.platform.ios.audio_ios import iOSAudioCapture
        cap = iOSAudioCapture()
        cap.set_wav_path("/var/mobile/Containers/Data/app/uuid/tmp/test.wav")
        assert "test.wav" in cap.get_wav_path()

    def test_set_wav_path_rejects_empty(self):
        from vakya.platform.ios.audio_ios import iOSAudioCapture
        cap = iOSAudioCapture()
        with pytest.raises(ValueError):
            cap.set_wav_path("")

    def test_delete_wav_removes_file(self, tmp_path):
        from vakya.platform.ios.audio_ios import iOSAudioCapture
        wav = str(tmp_path / "test.wav")
        _make_wav(wav)
        cap = iOSAudioCapture()
        cap.set_wav_path(wav)
        cap.delete_wav()
        assert not os.path.exists(wav)

    def test_delete_wav_clears_path(self, tmp_path):
        from vakya.platform.ios.audio_ios import iOSAudioCapture
        wav = str(tmp_path / "test.wav")
        _make_wav(wav)
        cap = iOSAudioCapture()
        cap.set_wav_path(wav)
        cap.delete_wav()
        with pytest.raises(RuntimeError):
            cap.get_wav_path()

    def test_delete_wav_silent_if_missing(self):
        from vakya.platform.ios.audio_ios import iOSAudioCapture
        cap = iOSAudioCapture()
        cap.set_wav_path("/nonexistent/file.wav")
        cap.delete_wav()   # must not raise

    def test_validate_wav_passes_correct_spec(self, tmp_path):
        from vakya.platform.ios.audio_ios import iOSAudioCapture
        wav = str(tmp_path / "ok.wav")
        _make_wav(wav, sample_rate=16_000)
        cap = iOSAudioCapture()
        cap.set_wav_path(wav)
        cap.validate_wav()

    def test_validate_wav_rejects_wrong_sample_rate(self, tmp_path):
        from vakya.platform.ios.audio_ios import iOSAudioCapture
        wav = str(tmp_path / "bad.wav")
        _make_wav(wav, sample_rate=44_100)
        cap = iOSAudioCapture()
        cap.set_wav_path(wav)
        with pytest.raises(ValueError, match="16000"):
            cap.validate_wav()

    def test_start_sets_recording_no_rubicon(self):
        from vakya.platform.ios import audio_ios
        from vakya.platform.ios.audio_ios import iOSAudioCapture
        with patch.object(audio_ios, "_rubicon_available", return_value=False):
            cap = iOSAudioCapture()
            cap.start()
            assert cap.is_recording

    def test_stop_clears_recording_no_rubicon(self):
        from vakya.platform.ios import audio_ios
        from vakya.platform.ios.audio_ios import iOSAudioCapture
        with patch.object(audio_ios, "_rubicon_available", return_value=False):
            cap = iOSAudioCapture()
            cap.start()
            cap.stop()
            assert not cap.is_recording

    def test_sample_rate_constant(self):
        from vakya.platform.ios import audio_ios
        assert audio_ios.SAMPLE_RATE == 16_000

    def test_channels_constant(self):
        from vakya.platform.ios import audio_ios
        assert audio_ios.CHANNELS == 1


# ---------------------------------------------------------------------------
# CoreML engine wrappers — graceful degradation on non-iOS
# ---------------------------------------------------------------------------

class TestCoreMLSTTEngine:
    def test_import(self):
        from vakya.platform.ios.coreml.stt_coreml import CoreMLSTTEngine
        assert CoreMLSTTEngine is not None

    def test_implements_stt_engine(self):
        from vakya.core.stt.base import STTEngine
        from vakya.platform.ios.coreml.stt_coreml import CoreMLSTTEngine
        assert issubclass(CoreMLSTTEngine, STTEngine)

    def test_load_raises_when_dylib_absent(self, tmp_path):
        from vakya.platform.ios.coreml.stt_coreml import CoreMLSTTEngine
        engine = CoreMLSTTEngine(model_dir=str(tmp_path))
        with pytest.raises(FileNotFoundError, match="libwhisper"):
            engine._load()

    def test_read_wav_float32_helper(self, tmp_path):
        from vakya.platform.ios.coreml.stt_coreml import _read_wav_float32
        wav = str(tmp_path / "test.wav")
        _make_wav(wav, duration_s=0.1)
        samples = _read_wav_float32(wav)
        assert len(samples) == 1600   # 16000 * 0.1
        assert all(-1.0 <= s <= 1.0 for s in samples)


class TestCoreMLLLMEngine:
    def test_import(self):
        from vakya.platform.ios.coreml.llm_coreml import CoreMLLLMEngine
        assert CoreMLLLMEngine is not None

    def test_implements_llm_engine(self):
        from vakya.core.llm.base import LLMEngine
        from vakya.platform.ios.coreml.llm_coreml import CoreMLLLMEngine
        assert issubclass(CoreMLLLMEngine, LLMEngine)

    def test_falls_back_to_rule_based_when_no_model(self, tmp_path):
        from vakya.platform.ios.coreml.llm_coreml import CoreMLLLMEngine
        from vakya.core.llm.base import CleanupMode
        engine = CoreMLLLMEngine(model_dir=str(tmp_path))
        # Should not raise — uses RuleBasedEngine fallback
        result = engine.cleanup("um yeah so basically I wanted to go to the store", mode=CleanupMode.DICTATION)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_build_prompt_dictation(self):
        from vakya.platform.ios.coreml.llm_coreml import _build_prompt
        from vakya.core.llm.base import CleanupMode
        prompt = _build_prompt("test text", CleanupMode.DICTATION)
        assert "dictated" in prompt.lower()
        assert "test text" in prompt


class TestCoreMLTTSEngine:
    def test_import(self):
        from vakya.platform.ios.coreml.tts_coreml import CoreMLTTSEngine
        assert CoreMLTTSEngine is not None

    def test_implements_tts_engine(self):
        from vakya.core.tts.base import TTSEngine
        from vakya.platform.ios.coreml.tts_coreml import CoreMLTTSEngine
        assert issubclass(CoreMLTTSEngine, TTSEngine)

    def test_writes_silent_wav_when_no_model(self, tmp_path):
        from vakya.platform.ios.coreml.tts_coreml import CoreMLTTSEngine
        engine = CoreMLTTSEngine(model_dir=str(tmp_path))
        out = str(tmp_path / "out.wav")
        engine.synthesise("hello world", output_path=out)
        assert os.path.exists(out)
        with wave.open(out, "rb") as wf:
            assert wf.getsampwidth() == 2

    def test_write_float32_wav_helper(self, tmp_path):
        from vakya.platform.ios.coreml.tts_coreml import _write_float32_wav
        out = str(tmp_path / "out.wav")
        samples = [0.0] * 1000 + [0.5] * 1000
        _write_float32_wav(samples, out, 24_000)
        assert os.path.exists(out)
        with wave.open(out, "rb") as wf:
            assert wf.getnframes() == 2000


# ---------------------------------------------------------------------------
# iOSPipelineBridge
# ---------------------------------------------------------------------------

class TestiOSPipelineBridge:
    def test_import(self):
        from vakya.platform.ios.pipeline_bridge import iOSPipelineBridge
        assert iOSPipelineBridge is not None

    def test_instantiates(self, tmp_path):
        from vakya.platform.ios.pipeline_bridge import iOSPipelineBridge
        bridge = iOSPipelineBridge(str(tmp_path / "cfg"), str(tmp_path / "models"))
        assert bridge is not None

    def test_config_stt_engine_is_coreml_whisper(self, tmp_path):
        from vakya.platform.ios.pipeline_bridge import iOSPipelineBridge
        bridge = iOSPipelineBridge(str(tmp_path), str(tmp_path))
        cfg = json.loads(bridge.get_config_json())
        assert cfg["stt"]["engine"] == "coreml_whisper"

    def test_config_default_llm_rule_based(self, tmp_path):
        from vakya.platform.ios.pipeline_bridge import iOSPipelineBridge
        bridge = iOSPipelineBridge(str(tmp_path), str(tmp_path))
        cfg = json.loads(bridge.get_config_json())
        assert cfg["llm"]["engine"] == "rule_based"

    def test_enhanced_cleanup_sets_coreml_phi3(self, tmp_path):
        from vakya.platform.ios.pipeline_bridge import iOSPipelineBridge
        bridge = iOSPipelineBridge(str(tmp_path), str(tmp_path), enhanced_cleanup=True)
        cfg = json.loads(bridge.get_config_json())
        assert cfg["llm"]["engine"] == "coreml_phi3"

    def test_set_enhanced_cleanup_toggle(self, tmp_path):
        from vakya.platform.ios.pipeline_bridge import iOSPipelineBridge
        bridge = iOSPipelineBridge(str(tmp_path), str(tmp_path))
        bridge.set_enhanced_cleanup(True)
        cfg = json.loads(bridge.get_config_json())
        assert cfg["llm"]["engine"] == "coreml_phi3"

    def test_set_enhanced_cleanup_false(self, tmp_path):
        from vakya.platform.ios.pipeline_bridge import iOSPipelineBridge
        bridge = iOSPipelineBridge(str(tmp_path), str(tmp_path), enhanced_cleanup=True)
        bridge.set_enhanced_cleanup(False)
        cfg = json.loads(bridge.get_config_json())
        assert cfg["llm"]["engine"] == "rule_based"

    def test_transcribe_missing_wav_returns_error_json(self, tmp_path):
        from vakya.platform.ios.pipeline_bridge import iOSPipelineBridge
        bridge = iOSPipelineBridge(str(tmp_path), str(tmp_path))
        result = json.loads(bridge.transcribe("/nonexistent/file.wav", delete_after=False))
        assert result["error"] is not None
        assert "WAV not found" in result["error"]

    def test_transcribe_result_has_required_keys(self, tmp_path):
        from vakya.platform.ios.pipeline_bridge import iOSPipelineBridge
        bridge = iOSPipelineBridge(str(tmp_path), str(tmp_path))
        result = json.loads(bridge.transcribe("/nonexistent/file.wav", delete_after=False))
        assert set(result.keys()) >= {"text", "language", "duration_s", "engine", "error"}

    def test_transcribe_deletes_wav_on_error(self, tmp_path):
        from vakya.platform.ios.pipeline_bridge import iOSPipelineBridge
        wav = str(tmp_path / "temp.wav")
        _make_wav(wav)
        bridge = iOSPipelineBridge(str(tmp_path / "cfg"), str(tmp_path / "models"))
        bridge.transcribe(wav, delete_after=True)
        assert not os.path.exists(wav)

    def test_synthesise_result_has_required_keys(self, tmp_path):
        from vakya.platform.ios.pipeline_bridge import iOSPipelineBridge
        bridge = iOSPipelineBridge(str(tmp_path), str(tmp_path))
        result = json.loads(bridge.synthesise("hello"))
        assert set(result.keys()) >= {"wav_path", "duration_s", "error"}

    def test_hardware_tier_is_mobile_coreml(self, tmp_path):
        from vakya.platform.ios.pipeline_bridge import iOSPipelineBridge
        bridge = iOSPipelineBridge(str(tmp_path), str(tmp_path))
        cfg = json.loads(bridge.get_config_json())
        assert cfg["hardware_tier"] == "mobile_coreml"

    def test_set_mode(self, tmp_path):
        from vakya.platform.ios.pipeline_bridge import iOSPipelineBridge
        bridge = iOSPipelineBridge(str(tmp_path), str(tmp_path))
        bridge.set_mode("meeting")
        cfg = json.loads(bridge.get_config_json())
        assert cfg["output"]["mode"] == "meeting"


# ---------------------------------------------------------------------------
# main.init()
# ---------------------------------------------------------------------------

class TestiOSMain:
    def test_init_returns_ios_pipeline_bridge(self, tmp_path):
        from vakya.platform.ios import main
        from vakya.platform.ios.pipeline_bridge import iOSPipelineBridge
        bridge = main.init(str(tmp_path / "cfg"), str(tmp_path / "models"))
        assert isinstance(bridge, iOSPipelineBridge)

    def test_init_creates_sessions_dir(self, tmp_path):
        from vakya.platform.ios import main
        cfg = str(tmp_path / "cfg")
        main.init(cfg, str(tmp_path / "models"))
        assert os.path.isdir(os.path.join(cfg, "sessions"))

    def test_init_creates_vocab_dir(self, tmp_path):
        from vakya.platform.ios import main
        cfg = str(tmp_path / "cfg")
        main.init(cfg, str(tmp_path / "models"))
        assert os.path.isdir(os.path.join(cfg, "vocab"))
