"""whisper.cpp STT implementation — bundled model, minimum-spec / onboarding fallback.

Uses pywhispercpp (Python bindings for whisper.cpp). Model: whisper-base.en.
This is the model bundled in the installer so the app works immediately
before heavy model downloads complete.
"""

from __future__ import annotations

import logging
import os
from typing import List

from .base import STTEngine, STTResult, STTSegment

log = logging.getLogger(__name__)

_DEFAULT_MODEL_PATH = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "models", "stt", "whisper-base-en.bin",
)


class WhisperCppEngine(STTEngine):
    def __init__(self, model_path: str | None = None) -> None:
        self._model_path = model_path or _DEFAULT_MODEL_PATH
        self._model = None

    def _load(self) -> None:
        if self._model is not None:
            return
        if not os.path.exists(self._model_path):
            raise FileNotFoundError(
                f"whisper.cpp model not found at {self._model_path}. "
                "Run the installer or download manually."
            )
        try:
            from pywhispercpp.model import Model
            self._model = Model(self._model_path, n_threads=os.cpu_count() or 4)
            log.info("whisper.cpp model loaded from %s", self._model_path)
        except ImportError as exc:
            raise ImportError(
                "pywhispercpp not installed. Run: pip install pywhispercpp"
            ) from exc

    def transcribe(
        self,
        audio_path: str,
        language: str = "auto",
        vocab_hint: List[str] | None = None,
    ) -> STTResult:
        self._load()

        prompt = ", ".join(vocab_hint) if vocab_hint else ""
        lang = None if language == "auto" else language

        kwargs: dict = {"initial_prompt": prompt} if prompt else {}
        if lang:
            kwargs["language"] = lang

        log.info("whisper.cpp transcribing %s", audio_path)
        segments_raw = self._model.transcribe(audio_path, **kwargs)

        segments = [
            STTSegment(
                start=seg.t0 / 100.0,
                end=seg.t1 / 100.0,
                text=seg.text.strip(),
            )
            for seg in segments_raw
        ]
        full_text = " ".join(s.text for s in segments)

        return STTResult(
            text=full_text,
            segments=segments,
            language_detected=lang or "en",
        )
