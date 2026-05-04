"""Phase 3 placeholder — wiki/Obsidian ingest pass.

Do not implement. Placeholder prevents ImportError when pipeline
imports this module. Logs skip message on call.
"""

import logging

log = logging.getLogger(__name__)


def ingest(transcript: str, session_id: str) -> None:
    log.info("wiki ingest skipped — Phase 3")
