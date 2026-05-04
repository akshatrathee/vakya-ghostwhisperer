"""Abstract AudioCapture interface + platform registry.

Platform shells register their implementation at startup via register().
Core pipeline calls get_instance() — never imports platform code directly.
Sprint 1 CLI passes a file path; no live capture implementation needed yet.
"""

from __future__ import annotations

import abc
from typing import Callable

_registry: dict[str, type["AudioCapture"]] = {}
_active: "AudioCapture | None" = None


class AudioCapture(abc.ABC):
    @abc.abstractmethod
    def start(self) -> None:
        """Begin capturing audio from the microphone."""

    @abc.abstractmethod
    def stop(self) -> None:
        """Stop capturing. Blocks until the capture buffer is flushed."""

    @abc.abstractmethod
    def get_wav_path(self) -> str:
        """Return path to the captured audio WAV file (16kHz, mono, 16-bit)."""


def register(name: str, cls: type[AudioCapture]) -> None:
    _registry[name] = cls


def get_instance(name: str | None = None) -> AudioCapture:
    global _active
    if _active is not None:
        return _active
    if name is None:
        name = next(iter(_registry), None)
    if name is None or name not in _registry:
        raise RuntimeError(
            f"No AudioCapture implementation registered. "
            f"Available: {list(_registry.keys())}"
        )
    _active = _registry[name]()
    return _active


class FileAudioCapture(AudioCapture):
    """Sprint 1 stub: wraps a pre-existing WAV file as if it were a live capture."""

    def __init__(self, wav_path: str) -> None:
        self._path = wav_path

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def get_wav_path(self) -> str:
        return self._path
