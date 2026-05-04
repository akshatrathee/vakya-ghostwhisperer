"""OmniVoice TTS — ADR-004 challenger, benchmark required before committing.

600+ languages, 3-second reference clip, Apache 2.0.
Published RTF of 40× is GPU-measured. CPU RTF is unknown.

ADR-004 decision rule (must be applied in Sprint 3 build):
  If CPU RTF < 2.0 → use OmniVoice as primary voice cloner (CosyVoice2 as TTS)
  If CPU RTF >= 2.0 → use CosyVoice2 for both TTS and cloning

Until benchmark is run, this engine is NOT selected by the factory.
Call benchmark_rtf() on target CPU and update engine_factory.py accordingly.
"""

from __future__ import annotations

import io
import logging
import os
import time
import wave
from typing import Optional

from .base import TTSEngine

log = logging.getLogger(__name__)

_MODEL_DIR = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "models", "tts", "omnivoice",
)
_PROFILES_DIR = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "data", "voice_profiles",
)

# Updated by benchmark_rtf() — None means not yet measured
_MEASURED_CPU_RTF: Optional[float] = None


class OmniVoiceEngine(TTSEngine):
    """OmniVoice TTS with 3-second reference clip voice cloning."""

    def __init__(self, model_dir: str | None = None) -> None:
        self._model_dir = model_dir or _MODEL_DIR
        self._model = None

    def _load(self) -> None:
        if self._model is not None:
            return
        if not os.path.exists(self._model_dir):
            raise FileNotFoundError(
                f"OmniVoice model not found at {self._model_dir}. "
                "Run installer/download_models.py --id omnivoice first."
            )
        try:
            import omnivoice  # type: ignore

            self._model = omnivoice.load(self._model_dir)
            log.info("OmniVoice loaded from %s", self._model_dir)
        except ImportError as exc:
            raise ImportError(
                "OmniVoice not installed. Check docs/MODELS.md for install path."
            ) from exc

    def synthesise(self, text: str, voice_profile_id: Optional[str] = None) -> bytes:
        self._load()

        reference_wav: Optional[str] = None
        if voice_profile_id:
            candidate = os.path.join(_PROFILES_DIR, voice_profile_id, "reference_clip.wav")
            if os.path.exists(candidate):
                reference_wav = candidate
                log.info("OmniVoice: using reference clip from %s", voice_profile_id)
            else:
                log.warning(
                    "Voice profile %s has no reference clip — using default voice",
                    voice_profile_id,
                )

        log.info("OmniVoice synthesising %d chars", len(text))
        audio = self._model.generate(text, reference_wav=reference_wav)
        return _to_wav_bytes(audio, sample_rate=24000)


def benchmark_rtf(text_sample: str = "The quick brown fox jumps over the lazy dog. " * 5) -> float:
    """Measure CPU real-time factor on this machine.

    RTF = synthesis_time / audio_duration.
    RTF < 1.0 = faster than realtime (good).
    RTF = 2.0 = takes 2× the audio duration to synthesise (ADR-004 threshold).

    Call this once in Sprint 3 and record the result in engine_factory.py.
    """
    engine = OmniVoiceEngine()
    engine._load()

    t0 = time.monotonic()
    wav_bytes = engine.synthesise(text_sample)
    elapsed = time.monotonic() - t0

    with io.BytesIO(wav_bytes) as buf:
        with wave.open(buf, "rb") as wf:
            audio_duration = wf.getnframes() / wf.getframerate()

    rtf = elapsed / audio_duration if audio_duration > 0 else float("inf")
    log.info(
        "OmniVoice CPU RTF benchmark: %.2f (synth=%.2fs, audio=%.2fs)",
        rtf,
        elapsed,
        audio_duration,
    )

    global _MEASURED_CPU_RTF
    _MEASURED_CPU_RTF = rtf

    decision = "USE OmniVoice as primary cloner" if rtf < 2.0 else "USE CosyVoice2 (OmniVoice too slow)"
    log.info("ADR-004 decision: RTF=%.2f → %s", rtf, decision)

    return rtf


def _to_wav_bytes(audio, sample_rate: int) -> bytes:
    import numpy as np

    pcm = (np.clip(audio.flatten(), -1.0, 1.0) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()
