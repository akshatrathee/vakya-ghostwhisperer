"""Windows live mic capture via sounddevice — implements AudioCapture interface.

Records 16kHz mono 16-bit PCM to a temp WAV file. Caller must delete the
file after use (or let the OS clean up the temp dir).
"""

from __future__ import annotations

import logging
import queue
import tempfile
import threading
import wave
from pathlib import Path
from typing import Callable

import numpy as np
import sounddevice as sd

from vakya.core.audio_capture import AudioCapture, register

log = logging.getLogger(__name__)

_SAMPLE_RATE = 16_000
_CHANNELS = 1
_DTYPE = "int16"
_BLOCKSIZE = 1024  # ~64ms per callback


class WindowsAudioCapture(AudioCapture):
    """Mic capture using sounddevice. Thread-safe start/stop.

    Usage:
        cap = WindowsAudioCapture()
        cap.set_level_callback(fn)   # optional, receives float 0..1 each block
        cap.start()
        ...
        cap.stop()
        wav_path = cap.get_wav_path()
    """

    def __init__(self, device: int | str | None = None) -> None:
        self._device = device
        self._queue: queue.Queue[np.ndarray] = queue.Queue()
        self._wav_path: str | None = None
        self._stream: sd.InputStream | None = None
        self._level_cb: Callable[[float], None] | None = None
        self._lock = threading.Lock()
        self._recording = False

    def set_level_callback(self, cb: Callable[[float], None]) -> None:
        """Register a callback that receives RMS level (0.0–1.0) each audio block."""
        self._level_cb = cb

    # ── AudioCapture interface ────────────────────────────────────────────────

    def start(self) -> None:
        with self._lock:
            if self._recording:
                raise RuntimeError("WindowsAudioCapture.start() called while already recording")
            self._queue = queue.Queue()
            self._recording = True

        self._stream = sd.InputStream(
            samplerate=_SAMPLE_RATE,
            channels=_CHANNELS,
            dtype=_DTYPE,
            blocksize=_BLOCKSIZE,
            device=self._device,
            callback=self._callback,
        )
        self._stream.start()
        log.info("WindowsAudioCapture: recording started (device=%s, rate=%d)", self._device, _SAMPLE_RATE)

    def stop(self) -> None:
        with self._lock:
            if not self._recording:
                return
            self._recording = False

        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        self._wav_path = self._flush_to_wav()
        log.info("WindowsAudioCapture: stopped, WAV written to %s", self._wav_path)

    def get_wav_path(self) -> str:
        if self._wav_path is None:
            raise RuntimeError("get_wav_path() called before stop()")
        return self._wav_path

    # ── Internal ──────────────────────────────────────────────────────────────

    def _callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: object,
        status: sd.CallbackFlags,
    ) -> None:
        if status:
            log.warning("sounddevice status: %s", status)
        self._queue.put(indata.copy())
        if self._level_cb is not None:
            rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2))) / 32768.0
            self._level_cb(min(1.0, rms * 10.0))  # boost so quiet speech shows up

    def _flush_to_wav(self) -> str:
        chunks: list[np.ndarray] = []
        while not self._queue.empty():
            chunks.append(self._queue.get_nowait())

        if not chunks:
            log.warning("WindowsAudioCapture: no audio captured — returning empty WAV")

        fd, path = tempfile.mkstemp(suffix=".wav", prefix="vakya_rec_")
        with wave.open(path, "wb") as wf:
            wf.setnchannels(_CHANNELS)
            wf.setsampwidth(2)  # 16-bit = 2 bytes
            wf.setframerate(_SAMPLE_RATE)
            if chunks:
                wf.writeframes(np.concatenate(chunks, axis=0).tobytes())
        import os
        os.close(fd)
        return path


# Register so pipeline can resolve by name
register("windows", WindowsAudioCapture)
