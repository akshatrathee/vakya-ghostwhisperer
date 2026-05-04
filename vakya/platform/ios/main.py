"""BeeWare entry point for the Vakya iOS app (Sprint 7).

BeeWare's Briefcase embeds CPython in the IPA. Swift calls Python via
``rubicon-objc``. This module exposes ``init()`` which is called once from
``VakyaBridge.swift`` during ``App.init``.

Architecture reminder (PLATFORMS.md):
  Swift UI layer
      ↓ rubicon-objc
  Python (BeeWare) — orchestration, vocab, session log, output formatting
      ↓ ctypes / coremltools
  CoreML models — all neural inference (STT, LLM, TTS)
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)


def init(
    config_dir: str,
    models_dir: str,
    enhanced_cleanup: bool = False,
) -> "iOSPipelineBridge":
    """Initialise the Python runtime and return an ``iOSPipelineBridge``.

    Called exactly once from ``VakyaBridge.swift`` on app launch.

    Parameters
    ----------
    config_dir:
        ``app.documentsDir`` — iCloud-backed private storage.
    models_dir:
        ``app.applicationSupportDir`` — model files (~1-2 GB).
    enhanced_cleanup:
        Whether to load Phi-3 Mini CoreML. Defaults False — lighter startup.
    """
    _configure_logging()

    log.info(
        "Vakya iOS init: config_dir=%s models_dir=%s enhanced=%s",
        config_dir, models_dir, enhanced_cleanup,
    )

    os.makedirs(os.path.join(config_dir, "sessions"), exist_ok=True)
    os.makedirs(os.path.join(config_dir, "vocab"), exist_ok=True)

    from vakya.platform.ios.pipeline_bridge import iOSPipelineBridge
    return iOSPipelineBridge(config_dir, models_dir, enhanced_cleanup)


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(name)s: %(message)s",
    )
