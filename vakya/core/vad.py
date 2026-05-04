"""VAD wrapper — Step 1 of the pipeline.

Uses Silero VAD when available (bundled in faster-whisper).
Falls back to a simple energy-threshold heuristic so the pipeline
can run during development without model weights present.
"""

from __future__ import annotations

import logging
import struct
import wave
from dataclasses import dataclass
from typing import List

log = logging.getLogger(__name__)


@dataclass
class SpeechSegment:
    start_ms: int
    end_ms: int


def detect_speech_segments(wav_path: str, threshold: float = 0.5) -> List[SpeechSegment]:
    """Return list of (start_ms, end_ms) speech segments.

    Attempts Silero VAD first (via faster-whisper's bundled copy).
    Falls back to energy-based detection if Silero is unavailable.
    """
    try:
        return _silero_vad(wav_path, threshold)
    except Exception as exc:
        log.warning("Silero VAD unavailable (%s) — using energy fallback", exc)
        return _energy_vad(wav_path)


def _silero_vad(wav_path: str, threshold: float) -> List[SpeechSegment]:
    """Invoke Silero VAD via faster-whisper's bundled copy."""
    from faster_whisper.vad import get_speech_timestamps, load_silero_vad

    model = load_silero_vad()

    import torchaudio

    waveform, sample_rate = torchaudio.load(wav_path)
    if sample_rate != 16000:
        waveform = torchaudio.functional.resample(waveform, sample_rate, 16000)
    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)

    timestamps = get_speech_timestamps(
        waveform.squeeze(0),
        model,
        threshold=threshold,
        sampling_rate=16000,
    )
    segments = [
        SpeechSegment(
            start_ms=int(ts["start"] / 16),  # samples → ms at 16kHz
            end_ms=int(ts["end"] / 16),
        )
        for ts in timestamps
    ]
    log.debug("Silero VAD: %d speech segments found", len(segments))
    return segments


def _energy_vad(
    wav_path: str,
    frame_ms: int = 30,
    energy_threshold_pct: float = 0.02,
    min_speech_ms: int = 300,
    padding_ms: int = 200,
) -> List[SpeechSegment]:
    """Simple RMS-energy VAD. No model weights required."""
    with wave.open(wav_path, "rb") as wf:
        n_channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        frame_rate = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    samples_per_frame = int(frame_rate * frame_ms / 1000)
    fmt = {1: "B", 2: "h", 4: "i"}.get(sample_width, "h")
    all_samples = struct.unpack(f"{n_frames * n_channels}{fmt}", raw)
    if n_channels > 1:
        all_samples = all_samples[::n_channels]

    max_val = float(2 ** (8 * sample_width - 1))
    energies = []
    for i in range(0, len(all_samples), samples_per_frame):
        chunk = all_samples[i : i + samples_per_frame]
        rms = (sum(s * s for s in chunk) / len(chunk)) ** 0.5 / max_val if chunk else 0.0
        energies.append(rms)

    threshold = max(energies) * energy_threshold_pct if energies else 0.0
    is_speech = [e > threshold for e in energies]

    segments: List[SpeechSegment] = []
    in_speech = False
    start_frame = 0
    for i, speech in enumerate(is_speech):
        if speech and not in_speech:
            in_speech = True
            start_frame = i
        elif not speech and in_speech:
            in_speech = False
            dur = (i - start_frame) * frame_ms
            if dur >= min_speech_ms:
                segments.append(
                    SpeechSegment(
                        start_ms=max(0, start_frame * frame_ms - padding_ms),
                        end_ms=i * frame_ms + padding_ms,
                    )
                )
    if in_speech:
        segments.append(
            SpeechSegment(
                start_ms=max(0, start_frame * frame_ms - padding_ms),
                end_ms=len(energies) * frame_ms,
            )
        )

    log.debug("Energy VAD: %d speech segments found", len(segments))
    return segments
