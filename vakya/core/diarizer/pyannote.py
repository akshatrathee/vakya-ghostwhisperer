"""pyannote-audio 3.1 diarizer — Linux/macOS primary.

Not supported on Windows (see ADR-005). On Windows, use WhisperXEngine instead.
Requires a one-time HuggingFace token acceptance at hf.co/pyannote/speaker-diarization-3.1.
"""

from __future__ import annotations

import logging
import os
import tracemalloc
from typing import List

from .base import Diarizer, DiarSegment

log = logging.getLogger(__name__)


class PyannoteEngine(Diarizer):
    def __init__(self, hf_token: str | None = None) -> None:
        self._hf_token = hf_token or os.environ.get("HF_TOKEN", "")
        self._pipeline = None

    def _load(self) -> None:
        if self._pipeline is not None:
            return
        if not self._hf_token:
            raise ValueError(
                "HF_TOKEN environment variable not set. "
                "Obtain token at https://hf.co/settings/tokens and accept "
                "pyannote/speaker-diarization-3.1 terms."
            )
        try:
            from pyannote.audio import Pipeline  # type: ignore

            self._pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=self._hf_token,
            )
            log.info("pyannote-audio 3.1 pipeline loaded")
        except ImportError as exc:
            raise ImportError(
                "pyannote-audio not installed. Run: pip install pyannote.audio"
            ) from exc

    def diarize(self, audio_path: str) -> List[DiarSegment]:
        self._load()

        tracemalloc.start()
        log.info("pyannote diarizing %s", audio_path)

        diarization = self._pipeline(audio_path)

        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        log.info("pyannote: peak RAM=%.1fMB", peak / 1e6)

        return [
            DiarSegment(
                speaker_id=label,
                start_sec=turn.start,
                end_sec=turn.end,
            )
            for turn, _, label in diarization.itertracks(yield_label=True)
        ]
