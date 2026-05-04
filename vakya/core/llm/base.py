"""Abstract LLMEngine interface."""

from __future__ import annotations

import abc
from enum import Enum


class CleanupMode(str, Enum):
    DICTATION = "dictation"
    NOTES = "notes"
    FARM_LOG = "farm_log"
    MEETING = "meeting"


_SYSTEM_PROMPTS: dict[CleanupMode, str] = {
    CleanupMode.DICTATION: (
        "Remove fillers (um, uh, aah, hmm, you know, like). "
        "Resolve self-corrections — keep only the final intended meaning. "
        "Output clean prose. No bullet points. Preserve speaker labels."
    ),
    CleanupMode.NOTES: (
        "Remove fillers. Format as bullet points with sub-bullets for details. "
        "Preserve speaker labels."
    ),
    CleanupMode.FARM_LOG: (
        "Remove fillers. Format as a structured farm log: "
        "Date/Time | Activity | Observations | Action Items. "
        "Preserve speaker labels."
    ),
    CleanupMode.MEETING: (
        "Remove fillers. Format as meeting notes: "
        "Attendees | Key Points | Decisions | Action Items. "
        "Preserve speaker labels."
    ),
}


def get_system_prompt(mode: CleanupMode) -> str:
    return _SYSTEM_PROMPTS[mode]


class LLMEngine(abc.ABC):
    @abc.abstractmethod
    def cleanup(self, transcript: str, mode: CleanupMode) -> str:
        """Return cleaned, formatted transcript.

        Must chunk internally if transcript exceeds context window.
        Must never silently truncate content.
        """
