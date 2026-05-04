"""Phase 3 placeholder — voice shortcut / snippet expansion.

Do not implement. Placeholder prevents ImportError when pipeline
imports this module. Logs skip message on call.
"""

import logging

log = logging.getLogger(__name__)


def expand(text: str) -> str:
    """Return text unchanged. Shortcut expansion is Phase 3."""
    log.debug("shortcuts skipped — Phase 3")
    return text
