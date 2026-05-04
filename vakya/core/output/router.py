"""Output router — Step 6 of the pipeline.

Actions (all configurable, applied in order):
  1. Copy to clipboard
  2. Write session log to data/sessions/{session_id}.md
  3. Extract and save new vocab terms to vocab_store.json

TTS synthesis is on-demand (user-triggered), not automatic.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..llm.base import CleanupMode
from ..vocab import store as vocab_store

log = logging.getLogger(__name__)

_SESSIONS_DIR = Path(__file__).parent.parent.parent / "data" / "sessions"


def route(
    formatted_text: str,
    raw_text: str,
    mode: CleanupMode,
    session_id: str,
    copy_to_clipboard: bool = True,
    write_log: bool = True,
    vocab_path: Optional[Path] = None,
) -> dict:
    """Route pipeline output to all configured destinations.

    Returns dict with keys: clipboard_ok, log_path, vocab_terms_added.
    """
    result: dict = {
        "clipboard_ok": False,
        "log_path": None,
        "vocab_terms_added": [],
    }

    if copy_to_clipboard:
        result["clipboard_ok"] = _copy_to_clipboard(formatted_text)

    if write_log:
        log_path = _write_session_log(formatted_text, session_id, mode)
        result["log_path"] = str(log_path) if log_path else None

    vocab = vocab_store.load(vocab_path)
    added = vocab_store.extract_new_terms(vocab, raw_text)
    if added:
        vocab_store.save(vocab, vocab_path)
        log.info("Vocab: added %d new terms: %s", len(added), added)
    result["vocab_terms_added"] = added

    return result


def _copy_to_clipboard(text: str) -> bool:
    try:
        import pyperclip  # type: ignore

        pyperclip.copy(text)
        log.debug("Copied %d chars to clipboard", len(text))
        return True
    except ImportError:
        log.warning("pyperclip not installed — clipboard copy skipped")
    except Exception as exc:
        log.warning("Clipboard copy failed: %s", exc)
    return False


def _write_session_log(text: str, session_id: str, mode: CleanupMode) -> Optional[Path]:
    _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{session_id}_{mode.value}.md"
    path = _SESSIONS_DIR / filename
    try:
        path.write_text(text, encoding="utf-8")
        log.debug("Session log written: %s", path)
        return path
    except OSError as exc:
        log.error("Failed to write session log: %s", exc)
        return None
