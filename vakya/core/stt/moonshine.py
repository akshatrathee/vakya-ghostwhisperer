"""Moonshine v2 STT — primary mobile engine (Android / iOS CoreML).

English-only, ~58MB, ~200MB RAM. No 30-second padding limitation.
"""

from __future__ import annotations

import logging
import os
from typing import List

from .base import STTEngine, STTResult, STTSegment

log = logging.getLogger(__name__)

_MODEL_DIR = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "models", "stt", "moonshine-v2-base",
)


class MoonshineEngine(STTEngine):
    def __init__(self, model_dir: str | None = None) -> None:
        self._model_dir = model_dir or _MODEL_DIR
        self._model = None

    def _load(self) -> None:
        if self._model is not None:
            return
        if not os.path.exists(self._model_dir):
            raise FileNotFoundError(
                f"Moonshine v2 model not found at {self._model_dir}. "
                "Run installer/download_models.py first."
            )
        try:
            import moonshine  # type: ignore

            self._model = moonshine.load(self._model_dir)
            log.info("Moonshine v2 loaded from %s", self._model_dir)
        except ImportError as exc:
            raise ImportError(
                "moonshine not installed. Run: pip install moonshine-onnx"
            ) from exc

    def transcribe(
        self,
        audio_path: str,
        language: str = "auto",
        vocab_hint: List[str] | None = None,
    ) -> STTResult:
        self._load()
        log.info("Moonshine transcribing %s", audio_path)

        import numpy as np
        import soundfile as sf

        audio, sr = sf.read(audio_path, dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)

        text = self._model.transcribe(audio)
        segment = STTSegment(start=0.0, end=len(audio) / sr, text=text.strip())
        return STTResult(text=text.strip(), segments=[segment], language_detected="en")
