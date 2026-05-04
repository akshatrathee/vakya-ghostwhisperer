"""faster-whisper STT implementation — primary desktop engine.

Model: Large-v3 Turbo int8, CPU. ~3GB RAM. ~15s for 5-min audio on i5.
WhisperX on Windows wraps this same model; see core/diarizer/whisperx.py.
"""

from __future__ import annotations

import logging
import os
import tracemalloc
from pathlib import Path
from typing import List

from .base import STTEngine, STTResult, STTSegment

log = logging.getLogger(__name__)

_MODEL_DIR = str(
    (Path(__file__).parent.parent.parent / "models" / "stt" / "faster-whisper-large-v3-turbo").resolve()
)


class FasterWhisperEngine(STTEngine):
    def __init__(self, model_dir: str | None = None, int8: bool = True) -> None:
        self._model_dir = model_dir or _MODEL_DIR
        self._int8 = int8
        self._model = None

    def _load(self) -> None:
        if self._model is not None:
            return
        if not os.path.exists(self._model_dir):
            raise FileNotFoundError(
                f"faster-whisper model not found at {self._model_dir}. "
                "Run installer/download_models.py first."
            )
        try:
            from faster_whisper import WhisperModel

            compute = "int8" if self._int8 else "float32"
            self._model = WhisperModel(
                self._model_dir,
                device="cpu",
                compute_type=compute,
            )
            log.info("faster-whisper loaded from %s (compute=%s)", self._model_dir, compute)
        except ImportError as exc:
            raise ImportError(
                "faster-whisper not installed. Run: pip install faster-whisper"
            ) from exc

    def transcribe(
        self,
        audio_path: str,
        language: str = "auto",
        vocab_hint: List[str] | None = None,
    ) -> STTResult:
        self._load()

        prompt = ", ".join(vocab_hint) if vocab_hint else None
        lang = None if language == "auto" else language

        tracemalloc.start()
        log.info("faster-whisper transcribing %s", audio_path)

        segments_raw, info = self._model.transcribe(
            audio_path,
            language=lang,
            initial_prompt=prompt,
            beam_size=5,
            word_timestamps=True,
        )

        segments = []
        for seg in segments_raw:
            # avg_logprob is in (-∞, 0]; normalise to [0, 1]
            confidence = max(0.0, 1.0 + seg.avg_logprob / 10.0)
            segments.append(
                STTSegment(
                    start=seg.start,
                    end=seg.end,
                    text=seg.text.strip(),
                    confidence=confidence,
                )
            )

        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        log.info(
            "faster-whisper: %d segments, lang=%s, peak RAM=%.1fMB",
            len(segments),
            info.language,
            peak / 1e6,
        )

        full_text = " ".join(s.text for s in segments)
        return STTResult(
            text=full_text,
            segments=segments,
            language_detected=info.language,
        )
