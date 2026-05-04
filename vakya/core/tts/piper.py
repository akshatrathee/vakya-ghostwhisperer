"""Piper TTS — embedded/RPi fallback. ~60MB model, ~100MB RAM, MIT license."""

from __future__ import annotations

import io
import logging
import os
import wave
from typing import Optional

from .base import TTSEngine

log = logging.getLogger(__name__)

_MODEL_PATH = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "models", "tts", "piper", "en_US-lessac-medium.onnx",
)
_MODEL_CONFIG = _MODEL_PATH + ".json"


class PiperEngine(TTSEngine):
    def __init__(self, model_path: str | None = None) -> None:
        self._model_path = model_path or _MODEL_PATH
        self._voice = None

    def _load(self) -> None:
        if self._voice is not None:
            return
        if not os.path.exists(self._model_path):
            raise FileNotFoundError(
                f"Piper model not found at {self._model_path}. "
                "Run installer/download_models.py first."
            )
        try:
            from piper import PiperVoice  # type: ignore

            self._voice = PiperVoice.load(self._model_path, config_path=_MODEL_CONFIG)
            log.info("Piper loaded from %s", self._model_path)
        except ImportError as exc:
            raise ImportError(
                "piper-tts not installed. Run: pip install piper-tts"
            ) from exc

    def synthesise(self, text: str, voice_profile_id: Optional[str] = None) -> bytes:
        self._load()
        if voice_profile_id:
            log.warning("Piper does not support voice cloning — ignoring voice_profile_id")
        log.info("Piper synthesising %d chars", len(text))

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            self._voice.synthesize(text, wf)
        return buf.getvalue()
