"""Android AudioRecord bridge — Chaquopy (Sprint 6).

Kotlin calls ``AudioRecordService`` which writes a 16kHz mono PCM_16BIT WAV
to the app cache dir, then calls ``AudioAndroidCapture.set_wav_path()`` so the
Python pipeline can pick it up via ``get_wav_path()``.

This module is imported inside the Chaquopy Python runtime embedded in the APK.
On non-Android platforms (CI, desktop tests) Chaquopy JVM calls are stubbed so
the class is still importable and fully unit-testable.
"""

from __future__ import annotations

import logging
import os
import threading
import wave
from typing import Optional

from vakya.core.audio_capture import AudioCapture

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Chaquopy JVM interop — imported lazily so tests run on Windows/Linux.
# ---------------------------------------------------------------------------

def _jvm_available() -> bool:
    try:
        from java.lang import System  # type: ignore  # noqa: F401
        return True
    except ImportError:
        return False


class AndroidAudioCapture(AudioCapture):
    """Python side of the AudioRecord bridge.

    Lifecycle (called from Kotlin via Chaquopy):
        1. ``start()``              — signals Kotlin service to begin recording
        2. Kotlin writes WAV to cache dir and calls ``set_wav_path(path)``
        3. ``stop()``               — signals Kotlin service to stop recording
        4. ``get_wav_path()``       — returns the path written by Kotlin
        5. ``delete_wav()``         — removes the temp WAV (called after STT)
    """

    SAMPLE_RATE: int = 16_000
    CHANNELS: int = 1
    SAMPLE_WIDTH: int = 2  # PCM_16BIT = 2 bytes

    def __init__(self) -> None:
        self._wav_path: Optional[str] = None
        self._recording = False
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # AudioCapture interface
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Signal the Kotlin AudioRecordService to start capturing."""
        with self._lock:
            self._wav_path = None
            self._recording = True
        log.info("AndroidAudioCapture: start recording signal sent")

        if _jvm_available():
            try:
                from com.vakya.app import VakyaBridge  # type: ignore
                VakyaBridge.getInstance().startRecording()
            except Exception as exc:
                log.error("JVM startRecording failed: %s", exc)
                raise

    def stop(self) -> None:
        """Signal the Kotlin AudioRecordService to stop capturing."""
        with self._lock:
            self._recording = False
        log.info("AndroidAudioCapture: stop recording signal sent")

        if _jvm_available():
            try:
                from com.vakya.app import VakyaBridge  # type: ignore
                VakyaBridge.getInstance().stopRecording()
            except Exception as exc:
                log.error("JVM stopRecording failed: %s", exc)
                raise

    def get_wav_path(self) -> str:
        """Return the path of the WAV file written by Kotlin."""
        with self._lock:
            if self._wav_path is None:
                raise RuntimeError(
                    "No WAV path set. Either Kotlin hasn't finished writing "
                    "or set_wav_path() was never called."
                )
            return self._wav_path

    # ------------------------------------------------------------------
    # Called from Kotlin via Chaquopy after AudioRecord flush
    # ------------------------------------------------------------------

    def set_wav_path(self, path: str) -> None:
        """Kotlin calls this after writing the temp WAV to cache dir."""
        if not path:
            raise ValueError("set_wav_path: path must be a non-empty string")
        with self._lock:
            self._wav_path = path
        log.info("AndroidAudioCapture: WAV ready at %s", path)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def delete_wav(self) -> None:
        """Remove the temp WAV from the cache dir after STT completes.

        The hard constraint: raw audio must never persist in a location
        accessible outside the app sandbox. Called by PipelineBridge after
        transcription returns.
        """
        with self._lock:
            path = self._wav_path
        if path and os.path.exists(path):
            try:
                os.remove(path)
                log.info("AndroidAudioCapture: deleted temp WAV %s", path)
            except OSError as exc:
                log.warning("Could not delete temp WAV %s: %s", path, exc)
        with self._lock:
            self._wav_path = None

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._recording

    def validate_wav(self) -> None:
        """Raise if the WAV written by Kotlin doesn't match expected spec."""
        path = self.get_wav_path()
        with wave.open(path, "rb") as wf:
            if wf.getframerate() != self.SAMPLE_RATE:
                raise ValueError(
                    f"Expected {self.SAMPLE_RATE} Hz, got {wf.getframerate()}"
                )
            if wf.getnchannels() != self.CHANNELS:
                raise ValueError(
                    f"Expected {self.CHANNELS} channel(s), got {wf.getnchannels()}"
                )
            if wf.getsampwidth() != self.SAMPLE_WIDTH:
                raise ValueError(
                    f"Expected {self.SAMPLE_WIDTH}-byte samples, "
                    f"got {wf.getsampwidth()}"
                )
