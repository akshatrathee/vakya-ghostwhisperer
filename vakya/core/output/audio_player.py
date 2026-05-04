"""Platform audio playback for TTS output.

Tries sounddevice first (cross-platform, low latency).
Falls back to wave + platform default player.
No model weights required — pure stdlib + optional sounddevice.
"""

from __future__ import annotations

import io
import logging
import struct
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


def play_wav_bytes(wav_bytes: bytes) -> None:
    """Play WAV audio bytes through the system audio output.

    Tries (in order):
    1. sounddevice + numpy  — low latency, cross-platform
    2. playsound            — simple, cross-platform
    3. platform shell cmd   — last resort (aplay, afplay, PowerShell)
    """
    try:
        _play_sounddevice(wav_bytes)
        return
    except Exception as exc:
        log.debug("sounddevice playback failed (%s) — trying playsound", exc)

    try:
        _play_playsound(wav_bytes)
        return
    except Exception as exc:
        log.debug("playsound failed (%s) — trying shell fallback", exc)

    _play_shell(wav_bytes)


def play_wav_file(wav_path: str) -> None:
    """Play a WAV file by path."""
    with open(wav_path, "rb") as f:
        play_wav_bytes(f.read())


def _play_sounddevice(wav_bytes: bytes) -> None:
    import numpy as np
    import sounddevice as sd  # type: ignore

    with io.BytesIO(wav_bytes) as buf:
        with wave.open(buf, "rb") as wf:
            sample_rate = wf.getframerate()
            n_channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            raw = wf.readframes(wf.getnframes())

    dtype = {1: np.uint8, 2: np.int16, 4: np.int32}.get(sample_width, np.int16)
    samples = np.frombuffer(raw, dtype=dtype)
    if n_channels > 1:
        samples = samples.reshape(-1, n_channels)

    # Normalise to float32 [-1, 1]
    float_samples = samples.astype(np.float32) / float(2 ** (8 * sample_width - 1))

    log.debug("Playing %.2fs audio via sounddevice", len(float_samples) / sample_rate)
    sd.play(float_samples, samplerate=sample_rate)
    sd.wait()


def _play_playsound(wav_bytes: bytes) -> None:
    from playsound import playsound  # type: ignore

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(wav_bytes)
        tmp_path = f.name

    try:
        playsound(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _play_shell(wav_bytes: bytes) -> None:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(wav_bytes)
        tmp_path = f.name

    try:
        if sys.platform == "win32":
            subprocess.run(
                [
                    "powershell", "-c",
                    f"(New-Object Media.SoundPlayer '{tmp_path}').PlaySync()",
                ],
                check=True,
                timeout=120,
            )
        elif sys.platform == "darwin":
            subprocess.run(["afplay", tmp_path], check=True, timeout=120)
        else:
            subprocess.run(["aplay", tmp_path], check=True, timeout=120)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        log.error("Shell audio playback failed: %s", exc)
        raise
    finally:
        Path(tmp_path).unlink(missing_ok=True)
