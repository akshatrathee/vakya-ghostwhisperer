"""Abstract TTSEngine interface."""

from __future__ import annotations

import abc
from typing import Optional


class TTSEngine(abc.ABC):
    @abc.abstractmethod
    def synthesise(self, text: str, voice_profile_id: Optional[str] = None) -> bytes:
        """Synthesise text to audio.

        Args:
            text: Text to synthesise.
            voice_profile_id: Speaker ID from voice_profiles/ store.
                None → default engine voice (no cloning).

        Returns:
            WAV audio bytes (16kHz, mono, 16-bit).
        """
