"""Abstract STTEngine interface — all STT implementations must satisfy this."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class STTSegment:
    start: float
    end: float
    text: str
    confidence: float = 1.0
    speaker_id: Optional[str] = None


@dataclass
class STTResult:
    text: str
    segments: List[STTSegment] = field(default_factory=list)
    language_detected: str = "en"


class STTEngine(abc.ABC):
    @abc.abstractmethod
    def transcribe(
        self,
        audio_path: str,
        language: str = "auto",
        vocab_hint: List[str] | None = None,
    ) -> STTResult:
        """Transcribe audio file and return structured result.

        Args:
            audio_path: Path to WAV file (16kHz, mono, 16-bit).
            language: ISO 639-1 code or "auto" for detection.
            vocab_hint: Terms to inject as Whisper --initial_prompt prefix.
        """
