"""PipelineBridge — Python entry point called from Kotlin via Chaquopy (Sprint 6).

Kotlin calls ``PipelineBridge`` methods through Chaquopy's JVM↔Python bridge.
All heavy lifting stays in ``vakya.core.pipeline``; this module is a thin
adapter that manages Android-specific concerns (WAV lifecycle, config path,
result serialisation to a plain dict so Kotlin can read it).

Usage from Kotlin (VakyaBridge.kt):
    val bridge = Python.getInstance()
                       .getModule("vakya.platform.android.pipeline_bridge")
                       .callAttr("PipelineBridge", configDir, modelsDir)
    val result  = bridge.callAttr("transcribe", wavPath).toJava(Map::class.java)
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy import of heavy core — avoids loading models at module import time.
# ---------------------------------------------------------------------------

def _build_config(config_dir: str, models_dir: str) -> Dict[str, Any]:
    """Build a minimal config dict that points the pipeline at Android paths."""
    return {
        "stt": {
            "engine": "moonshine",
            "model_dir": os.path.join(models_dir, "stt", "moonshine-v2-base"),
            "language": "auto",
        },
        "llm": {
            "engine": "rule_based",   # default on Android; Phi-3 is opt-in
            "model_path": os.path.join(models_dir, "llm", "phi3-mini-q4.gguf"),
            "enhanced_cleanup": False,
        },
        "tts": {
            "engine": "kokoro",
            "model_dir": os.path.join(models_dir, "tts", "kokoro"),
        },
        "diarizer": {
            "engine": "none",  # no diarization on Android Phase 1
        },
        "output": {
            "mode": "dictation",
            "clipboard": False,    # no clipboard on Android — return text to Kotlin
            "session_log_dir": os.path.join(config_dir, "sessions"),
        },
        "ram_budget_mb": 2048,
        "hardware_tier": "mobile",
    }


class PipelineBridge:
    """Android adapter around ``vakya.core.pipeline.Pipeline``.

    Parameters
    ----------
    config_dir:
        App's ``filesDir`` — writable, not accessible to other apps.
    models_dir:
        App external storage path for model files
        (``/sdcard/Android/data/com.vakya.app/files/models``).
    enhanced_cleanup:
        If True, use Phi-3 Mini instead of rule-based cleanup.
        User-visible toggle in MainActivity.
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
            self._cfg["llm"]["engine"] = "phi3_mini"
            self._cfg["llm"]["enhanced_cleanup"] = True
        self._pipeline: Optional[Any] = None
        log.info(
            "PipelineBridge init: config_dir=%s models_dir=%s enhanced=%s",
            config_dir, models_dir, enhanced_cleanup,
        )

    # ------------------------------------------------------------------
    # Lazy pipeline loader
    # ------------------------------------------------------------------

    def _get_pipeline(self) -> Any:
        if self._pipeline is None:
            from vakya.core.pipeline import Pipeline  # heavy import
            self._pipeline = Pipeline(self._cfg)
            log.info("Pipeline loaded (hardware_tier=mobile)")
        return self._pipeline

    # ------------------------------------------------------------------
    # Public API — called from Kotlin
    # ------------------------------------------------------------------

    def transcribe(self, wav_path: str, delete_after: bool = True) -> str:
        """Transcribe a WAV file and return a JSON string.

        Kotlin deserialises the JSON via Gson/Moshi. Returning a plain string
        avoids any Chaquopy type-marshalling edge cases with nested dicts.

        Returns JSON:
        {
            "text": "...",
            "language": "en",
            "duration_s": 12.3,
            "engine": "moonshine",
            "error": null          // or error message string
        }
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

            pipeline = self._get_pipeline()
            stt_result = pipeline.run(wav_path)

            result["text"] = stt_result.get("text", "")
            result["language"] = stt_result.get("language_detected", "en")
            result["duration_s"] = round(time.time() - t0, 2)

        except Exception as exc:
            log.error("PipelineBridge.transcribe error: %s", exc)
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
        """Run TTS and return path to the output WAV, or JSON error.

        Returns JSON:
        {
            "wav_path": "/path/to/output.wav",  // null on error
            "duration_s": 1.2,
            "error": null
        }
        """
        t0 = time.time()
        result: Dict[str, Any] = {"wav_path": None, "duration_s": 0.0, "error": None}
        try:
            pipeline = self._get_pipeline()
            out_path = os.path.join(self._config_dir, "tts_out.wav")
            pipeline.synthesise(text, voice_id=voice_id, output_path=out_path)
            result["wav_path"] = out_path
            result["duration_s"] = round(time.time() - t0, 2)
        except Exception as exc:
            log.error("PipelineBridge.synthesise error: %s", exc)
            result["error"] = str(exc)
            result["duration_s"] = round(time.time() - t0, 2)
        return json.dumps(result, ensure_ascii=False)

    def set_enhanced_cleanup(self, enabled: bool) -> None:
        """Toggle Phi-3 Mini cleanup at runtime (matches MainActivity toggle)."""
        self._enhanced_cleanup = enabled
        engine = "phi3_mini" if enabled else "rule_based"
        self._cfg["llm"]["engine"] = engine
        self._cfg["llm"]["enhanced_cleanup"] = enabled
        self._pipeline = None  # force pipeline reload with new config
        log.info("Enhanced cleanup set to %s (engine=%s)", enabled, engine)

    def warm_up(self) -> None:
        """Pre-load models so the first transcription isn't slow.

        Called from Kotlin after onboarding / model download completes.
        """
        log.info("PipelineBridge.warm_up: loading pipeline...")
        self._get_pipeline()
        log.info("PipelineBridge.warm_up: done")

    def get_config_json(self) -> str:
        """Expose current config to Kotlin for display in settings UI."""
        return json.dumps(self._cfg, ensure_ascii=False, indent=2)
