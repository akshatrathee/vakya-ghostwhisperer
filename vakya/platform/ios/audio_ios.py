"""iOS AVAudioEngine bridge — BeeWare/Rubicon-ObjC (Sprint 7).

Architecture (from PLATFORMS.md):
  Swift (AVAudioEngine) → writes 16kHz PCM WAV → app cacheDir
  Python (BeeWare) reads path via set_wav_path() → pipeline runs → WAV deleted

AVAudioSession category .record must be set before capture starts (Swift side).
Background audio entitlement allows recording while app is backgrounded, but
inference runs ONLY after the user foregrounds the app and stops recording —
this is an App Store hard constraint.

On non-iOS platforms (CI, desktop tests) all Rubicon-ObjC calls are absent;
the class is fully importable and unit-testable via the stub path.
"""

from __future__ import annotations

import logging
import os
import threading
import wave
from typing import Optional

from vakya.core.audio_capture import AudioCapture

log = logging.getLogger(__name__)

SAMPLE_RATE   = 16_000
CHANNELS      = 1
SAMPLE_WIDTH  = 2   # Float32 from AVAudioEngine is converted to Int16 by Swift


def _rubicon_available() -> bool:
    """True when running inside a BeeWare app on a real iOS device/simulator."""
    try:
        import rubicon.objc  # type: ignore  # noqa: F401
        return True
    except ImportError:
        return False


class iOSAudioCapture(AudioCapture):
    """Python side of the AVAudioEngine bridge.

    Lifecycle (called from Swift PipelineBridge via BeeWare):
        1. ``start()``              — tells Swift to start AVAudioEngine tap
        2. Swift converts Float32 PCM → Int16, writes WAV to cacheDir
        3. Swift calls ``set_wav_path(path)``
        4. ``stop()``               — tells Swift to detach the tap
        5. ``get_wav_path()``       — returns the WAV path to PipelineBridge
        6. ``delete_wav()``         — deletes after STT completes
    """

    def __init__(self) -> None:
        self._wav_path: Optional[str] = None
        self._recording = False
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # AudioCapture interface
    # ------------------------------------------------------------------

    def start(self) -> None:
        with self._lock:
            self._wav_path = None
            self._recording = True
        log.info("iOSAudioCapture: start signal sent")

        if _rubicon_available():
            try:
                from rubicon.objc import ObjCClass  # type: ignore
                VakyaBridge = ObjCClass("VakyaBridge")
                VakyaBridge.shared.startCapture()
            except Exception as exc:
                log.error("Rubicon startCapture failed: %s", exc)
                raise

    def stop(self) -> None:
        with self._lock:
            self._recording = False
        log.info("iOSAudioCapture: stop signal sent")

        if _rubicon_available():
            try:
                from rubicon.objc import ObjCClass  # type: ignore
                VakyaBridge = ObjCClass("VakyaBridge")
                VakyaBridge.shared.stopCapture()
            except Exception as exc:
                log.error("Rubicon stopCapture failed: %s", exc)
                raise

    def get_wav_path(self) -> str:
        with self._lock:
            if self._wav_path is None:
                raise RuntimeError(
                    "No WAV path set — Swift hasn't called set_wav_path() yet."
                )
            return self._wav_path

    # ------------------------------------------------------------------
    # Called from Swift via BeeWare after AVAudioEngine flush
    # ------------------------------------------------------------------

    def set_wav_path(self, path: str) -> None:
        """Swift calls this after writing the temp WAV to the app cache dir."""
        if not path:
            raise ValueError("set_wav_path: path must be a non-empty string")
        with self._lock:
            self._wav_path = path
        log.info("iOSAudioCapture: WAV ready at %s", path)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def delete_wav(self) -> None:
        """Delete the temp WAV after STT.

        Hard constraint: audio must never persist in a location accessible
        outside the app sandbox. App cacheDir is private but we still delete
        immediately after transcription to minimise retention window.
        """
        with self._lock:
            path = self._wav_path
        if path and os.path.exists(path):
            try:
                os.remove(path)
                log.info("iOSAudioCapture: deleted temp WAV %s", path)
            except OSError as exc:
                log.warning("Could not delete temp WAV %s: %s", path, exc)
        with self._lock:
            self._wav_path = None

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._recording

    def validate_wav(self) -> None:
        """Raise if WAV written by Swift doesn't match 16kHz mono int16 spec."""
        path = self.get_wav_path()
        with wave.open(path, "rb") as wf:
            if wf.getframerate() != SAMPLE_RATE:
                raise ValueError(
                    f"Expected {SAMPLE_RATE} Hz, got {wf.getframerate()}"
                )
            if wf.getnchannels() != CHANNELS:
                raise ValueError(
                    f"Expected {CHANNELS} channel(s), got {wf.getnchannels()}"
                )
            if wf.getsampwidth() != SAMPLE_WIDTH:
                raise ValueError(
                    f"Expected {SAMPLE_WIDTH}-byte samples, got {wf.getsampwidth()}"
                )
