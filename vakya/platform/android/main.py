"""Chaquopy Python entry point for the Vakya Android APK (Sprint 6).

Chaquopy calls ``init(config_dir, models_dir)`` once when the app starts.
Kotlin holds the returned ``PipelineBridge`` instance for the app lifetime.

Lifecycle:
    1. App starts → Kotlin calls ``init()``
    2. User taps Record → Kotlin calls ``VakyaBridge.startRecording()``
    3. AudioRecordService writes WAV → Kotlin calls ``bridge.transcribe(wav_path)``
    4. Kotlin displays text → user taps Record again or app closes
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)


def init(config_dir: str, models_dir: str, enhanced_cleanup: bool = False):
    """Initialise the Python runtime and return a ``PipelineBridge``.

    Called exactly once from ``VakyaBridge.kt`` during ``Application.onCreate``.

    Parameters
    ----------
    config_dir:
        ``context.filesDir.absolutePath`` — private app storage.
    models_dir:
        External app storage path for model files (several GB).
    enhanced_cleanup:
        Whether to load Phi-3 Mini. Defaults False to keep startup RAM low.
    """
    _configure_logging()

    log.info(
        "Vakya Android init: config_dir=%s models_dir=%s enhanced=%s",
        config_dir, models_dir, enhanced_cleanup,
    )

    os.makedirs(os.path.join(config_dir, "sessions"), exist_ok=True)

    from vakya.platform.android.pipeline_bridge import PipelineBridge
    bridge = PipelineBridge(config_dir, models_dir, enhanced_cleanup)
    return bridge


def _configure_logging() -> None:
    """Route Python logs to Android logcat via Chaquopy's default handler."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(name)s: %(message)s",
    )
