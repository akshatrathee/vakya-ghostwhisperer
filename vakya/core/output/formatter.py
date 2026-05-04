"""Mode-aware text formatter.

The LLM already applies mode formatting. This module handles
post-LLM polish: header injection, timestamp normalisation,
speaker colour-tag insertion for UI display.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from ..llm.base import CleanupMode


def format_transcript(
    text: str,
    mode: CleanupMode,
    session_id: str,
    timestamp: datetime | None = None,
) -> str:
    """Add a lightweight header and normalise whitespace. Returns display-ready text."""
    ts = timestamp or datetime.now(timezone.utc)
    ts_str = ts.strftime("%Y-%m-%d %H:%M UTC")

    header = _make_header(mode, ts_str, session_id)
    body = _normalise_whitespace(text)
    return f"{header}\n\n{body}"


def _make_header(mode: CleanupMode, timestamp: str, session_id: str) -> str:
    mode_labels = {
        CleanupMode.DICTATION: "Dictation",
        CleanupMode.NOTES: "Notes",
        CleanupMode.FARM_LOG: "Farm Log",
        CleanupMode.MEETING: "Meeting Notes",
    }
    label = mode_labels.get(mode, str(mode))
    return f"# {label} — {timestamp}\n_Session: {session_id}_"


def _normalise_whitespace(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def speaker_to_display_tag(text: str) -> str:
    """Replace 'Speaker N:' with HTML-like display tags for UI colour coding.

    Output: '<speaker id="N">Speaker N:</speaker>'
    The UI layer interprets these tags — plain text output strips them.
    """
    return re.sub(
        r"(Speaker (\w+)):",
        lambda m: f'<speaker id="{m.group(2)}">{m.group(1)}:</speaker>',
        text,
    )


def strip_display_tags(text: str) -> str:
    return re.sub(r"<speaker[^>]*>(.*?)</speaker>", r"\1", text)
