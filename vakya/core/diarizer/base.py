"""Abstract Diarizer interface."""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import List


@dataclass
class DiarSegment:
    speaker_id: str
    start_sec: float
    end_sec: float


class Diarizer(abc.ABC):
    @abc.abstractmethod
    def diarize(self, audio_path: str) -> List[DiarSegment]:
        """Return speaker-attributed time segments for the given audio file."""
