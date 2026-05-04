"""Qwen3-ASR-0.6B STT — Hindi/Indic priority engine.

52 languages including Hindi dialects and code-mixed Hinglish.
Activated when user selects "Hindi priority" or STT detects lang=hi.
~600MB on disk, ~1.5GB RAM.
"""

from __future__ import annotations

import logging
import os
from typing import List

from .base import STTEngine, STTResult, STTSegment

log = logging.getLogger(__name__)

_MODEL_DIR = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "models", "stt", "qwen3-asr-0.6b",
)


class Qwen3ASREngine(STTEngine):
    def __init__(self, model_dir: str | None = None) -> None:
        self._model_dir = model_dir or _MODEL_DIR
        self._processor = None
        self._model = None

    def _load(self) -> None:
        if self._model is not None:
            return
        if not os.path.exists(self._model_dir):
            raise FileNotFoundError(
                f"Qwen3-ASR model not found at {self._model_dir}. "
                "Run installer/download_models.py first."
            )
        try:
            from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor  # type: ignore

            self._processor = AutoProcessor.from_pretrained(self._model_dir)
            self._model = AutoModelForSpeechSeq2Seq.from_pretrained(
                self._model_dir,
                low_cpu_mem_usage=True,
            )
            log.info("Qwen3-ASR loaded from %s", self._model_dir)
        except ImportError as exc:
            raise ImportError(
                "transformers not installed. Run: pip install transformers"
            ) from exc

    def transcribe(
        self,
        audio_path: str,
        language: str = "auto",
        vocab_hint: List[str] | None = None,
    ) -> STTResult:
        self._load()
        log.info("Qwen3-ASR transcribing %s (lang=%s)", audio_path, language)

        import numpy as np
        import soundfile as sf

        audio, sr = sf.read(audio_path, dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)

        lang_id = None if language == "auto" else language
        inputs = self._processor(audio, sampling_rate=sr, return_tensors="pt")
        generated = self._model.generate(
            **inputs,
            forced_decoder_ids=(
                self._processor.get_decoder_prompt_ids(language=lang_id, task="transcribe")
                if lang_id
                else None
            ),
        )
        text = self._processor.batch_decode(generated, skip_special_tokens=True)[0]
        segment = STTSegment(start=0.0, end=len(audio) / sr, text=text.strip())
        return STTResult(
            text=text.strip(),
            segments=[segment],
            language_detected=lang_id or "hi",
        )
