"""Generate synthetic WAV fixture files for CI tests.

These files contain silence or simple tones — they let tests exercise
the audio-processing code paths without requiring real speech recordings.
Real STT tests require actual speech files (added manually to tests/fixtures/).

Usage:
    python -m vakya.tests.create_fixtures
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_RATE = 16000


def _write_wav(path: Path, samples: list[int], sample_rate: int = SAMPLE_RATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"{len(samples)}h", *samples))


def _silence(duration_sec: float) -> list[int]:
    return [0] * int(duration_sec * SAMPLE_RATE)


def _tone(frequency: float, duration_sec: float, amplitude: float = 0.3) -> list[int]:
    n = int(duration_sec * SAMPLE_RATE)
    return [
        int(amplitude * 32767 * math.sin(2 * math.pi * frequency * i / SAMPLE_RATE))
        for i in range(n)
    ]


def _speech_like(duration_sec: float) -> list[int]:
    """Simple alternating tone+silence to simulate speech VAD patterns."""
    samples = []
    t = 0.0
    while t < duration_sec:
        speech_dur = 0.4
        silence_dur = 0.1
        samples += _tone(440 + (len(samples) % 200), speech_dur)
        samples += _silence(silence_dur)
        t += speech_dur + silence_dur
    return samples[: int(duration_sec * SAMPLE_RATE)]


def create_all() -> None:
    fixtures = {
        "silence_5s.wav": _silence(5.0),
        "tone_30s.wav": _tone(440, 30.0),
        "speech_like_30s.wav": _speech_like(30.0),
        "speech_like_2min.wav": _speech_like(120.0),
    }

    for name, samples in fixtures.items():
        path = FIXTURES_DIR / name
        _write_wav(path, samples)
        print(f"  Created {path} ({len(samples) / SAMPLE_RATE:.1f}s)")


if __name__ == "__main__":
    print("Creating fixture WAV files...")
    create_all()
    print("Done. Add real speech recordings manually for STT accuracy tests.")
