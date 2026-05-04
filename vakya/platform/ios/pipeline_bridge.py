"""iOSPipelineBridge — Python orchestrator called from Swift via BeeWare (Sprint 7).

Swift calls Python methods through BeeWare's ``rubicon-objc`` bridge.
All heavy inference stays in ``vakya.core`` or the CoreML wrappers in
``vakya.platform.ios.coreml``. This module is a thin iOS adapter that:
  - Routes STT to ``CoreMLSTTEngine`` (whisper.cpp CoreML backend)
  - Routes LLM to ``CoreMLLLMEngine`` (Phi-3 Mini via coremltools) or rule-based
  - Routes TTS to ``CoreMLTTSEngine`` (Kokoro ONNX→CoreML)
  - Manages the WAV lifecycle (delete after STT)
  - Returns JSON strings so Swift can parse via Codable without rubicon type issues

Usage from Swift (VakyaBridge.swift):
    let bridge = Python.shared.builtins["vakya_ios_init"]!(configDir, modelsDir)
    let json   = bridge.transcribe(wavPath).toString()
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)


def _build_config(config_dir: str, models_dir: str) -> Dict[str, Any]:
    return {
        "stt": {
            "engine": "coreml_whisper",
            "model_dir": os.path.join(models_dir, "stt", "whisper-base-en"),
            "language": "en",
        },
        "llm": {
            "engine": "rule_based",      # default; Phi-3 CoreML is opt-in
            "model_dir": os.path.join(models_dir, "llm"),
            "enhanced_cleanup": False,
        },
        "tts": {
            "engine": "coreml_kokoro",
            "model_dir": os.path.join(models_dir, "tts"),
        },
        "diarizer": {
            "engine": "none",            # no diarization on iOS Phase 1
        },
        "output": {
            "mode": "dictation",
            "clipboard": False,          # clipboard handled by Swift
            "session_log_dir": os.path.join(config_dir, "sessions"),
        },
        "ram_budget_mb": 3072,           # iPhone 14+ has ≥6GB
        "hardware_tier": "mobile_coreml",
    }


class iOSPipelineBridge:
    """iOS adapter — orchestrates CoreML inference via the STTEngine interface.

    Parameters
    ----------
    config_dir:
        ``app.documentsDir`` — private, backed up by iCloud.
    models_dir:
        ``app.applicationSupportDir`` — private model storage.
    enhanced_cleanup:
        If True, use Phi-3 Mini CoreML instead of rule-based cleanup.
    """

    def __init__(
        self,
        config_dir: str,
        models_dir: str,
        enhanced_cleanup: bool = False,
    ) -> None:
        self._config_dir = config_dir
        self._models_dir = models_dir
        self._enhanced_cleanup = enhanced_cleanup
        self._cfg = _build_config(config_dir, models_dir)
        if enhanced_cleanup:
            self._cfg["llm"]["engine"] = "coreml_phi3"
            self._cfg["llm"]["enhanced_cleanup"] = True
        self._stt: Optional[Any] = None
        self._llm: Optional[Any] = None
        self._tts: Optional[Any] = None
        log.info(
            "iOSPipelineBridge init: config_dir=%s enhanced=%s",
            config_dir, enhanced_cleanup,
        )

    # ------------------------------------------------------------------
    # Lazy engine loaders
    # ------------------------------------------------------------------

    def _get_stt(self) -> Any:
        if self._stt is None:
            from vakya.platform.ios.coreml.stt_coreml import CoreMLSTTEngine
            self._stt = CoreMLSTTEngine(
                model_dir=self._cfg["stt"]["model_dir"]
            )
        return self._stt

    def _get_llm(self) -> Any:
        if self._llm is None:
            if self._enhanced_cleanup:
                from vakya.platform.ios.coreml.llm_coreml import CoreMLLLMEngine
                self._llm = CoreMLLLMEngine(
                    model_dir=self._cfg["llm"]["model_dir"]
                )
            else:
                from vakya.core.llm.phi3_mini import RuleBasedEngine  # type: ignore
                self._llm = RuleBasedEngine()
        return self._llm

    def _get_tts(self) -> Any:
        if self._tts is None:
            from vakya.platform.ios.coreml.tts_coreml import CoreMLTTSEngine
            self._tts = CoreMLTTSEngine(
                model_dir=self._cfg["tts"]["model_dir"]
            )
        return self._tts

    # ------------------------------------------------------------------
    # Public API — called from Swift via BeeWare
    # ------------------------------------------------------------------

    def transcribe(self, wav_path: str, delete_after: bool = True) -> str:
        """Transcribe a WAV and return a JSON string.

        JSON schema matches Android's PipelineBridge for consistency:
        { "text": "", "language": "en", "duration_s": 0.0,
          "engine": "coreml_whisper", "error": null }
        """
        t0 = time.time()
        result: Dict[str, Any] = {
            "text": "",
            "language": "en",
            "duration_s": 0.0,
            "engine": self._cfg["stt"]["engine"],
            "error": None,
        }
        try:
            if not os.path.exists(wav_path):
                raise FileNotFoundError(f"WAV not found: {wav_path}")

            stt = self._get_stt()
            stt_result = stt.transcribe(wav_path, language="en")
            raw_text = stt_result.text

            llm = self._get_llm()
            from vakya.core.llm.base import CleanupMode
            mode_str = self._cfg["output"].get("mode", "dictation").upper()
            mode = CleanupMode[mode_str] if mode_str in CleanupMode.__members__ else CleanupMode.DICTATION
            cleaned = llm.cleanup(raw_text, mode=mode)

            result["text"] = cleaned
            result["language"] = stt_result.language_detected or "en"
            result["duration_s"] = round(time.time() - t0, 2)

        except Exception as exc:
            log.error("iOSPipelineBridge.transcribe error: %s", exc)
            result["error"] = str(exc)
            result["duration_s"] = round(time.time() - t0, 2)

        finally:
            if delete_after and os.path.exists(wav_path):
                try:
                    os.remove(wav_path)
                    log.info("Deleted temp WAV: %s", wav_path)
                except OSError as del_exc:
                    log.warning("Could not delete WAV %s: %s", wav_path, del_exc)

        return json.dumps(result, ensure_ascii=False)

    def synthesise(self, text: str, voice_id: Optional[str] = None) -> str:
        """Run TTS and return a JSON string with the output WAV path."""
        t0 = time.time()
        result: Dict[str, Any] = {"wav_path": None, "duration_s": 0.0, "error": None}
        try:
            out_path = os.path.join(self._config_dir, "tts_out.wav")
            tts = self._get_tts()
            tts.synthesise(text, output_path=out_path, voice_id=voice_id)
            result["wav_path"] = out_path
            result["duration_s"] = round(time.time() - t0, 2)
        except Exception as exc:
            log.error("iOSPipelineBridge.synthesise error: %s", exc)
            result["error"] = str(exc)
            result["duration_s"] = round(time.time() - t0, 2)
        return json.dumps(result, ensure_ascii=False)

    def set_enhanced_cleanup(self, enabled: bool) -> None:
        """Toggle Phi-3 CoreML cleanup at runtime (matches ContentView toggle)."""
        self._enhanced_cleanup = enabled
        self._cfg["llm"]["engine"] = "coreml_phi3" if enabled else "rule_based"
        self._cfg["llm"]["enhanced_cleanup"] = enabled
        self._llm = None    # force reload
        log.info("Enhanced cleanup set to %s", enabled)

    def set_mode(self, mode: str) -> None:
        """Set output mode ('dictation', 'meeting', 'farm_log')."""
        self._cfg["output"]["mode"] = mode

    def warm_up(self) -> None:
        """Pre-load STT engine. Called after first-run model download."""
        log.info("iOSPipelineBridge.warm_up: loading STT...")
        self._get_stt()
        log.info("iOSPipelineBridge.warm_up: done")

    def get_config_json(self) -> str:
        return json.dumps(self._cfg, ensure_ascii=False, indent=2)
