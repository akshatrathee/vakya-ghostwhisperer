"""CosyVoice2 0.5B TTS + zero-shot voice cloning — primary desktop engine.

~1GB on disk, ~1.5GB RAM, 150ms TTFB, Apache 2.0.
Accepts a reference WAV clip for zero-shot speaker cloning.
"""

from __future__ import annotations

import io
import logging
import os
import wave
from pathlib import Path
from typing import Optional

from .base import TTSEngine

log = logging.getLogger(__name__)

_MODEL_DIR = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "models", "tts", "cosyvoice2",
)
_PROFILES_DIR = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "data", "voice_profiles",
)


class CosyVoice2Engine(TTSEngine):
    def __init__(self, model_dir: str | None = None) -> None:
        self._model_dir = model_dir or _MODEL_DIR
        self._model = None

    def _load(self) -> None:
        if self._model is not None:
            return
        if not os.path.exists(self._model_dir):
            raise FileNotFoundError(
                f"CosyVoice2 model not found at {self._model_dir}. "
                "Run installer/download_models.py first."
            )
        try:
            from cosyvoice.cli.cosyvoice import CosyVoice2  # type: ignore

            self._model = CosyVoice2(self._model_dir)
            log.info("CosyVoice2 loaded from %s", self._model_dir)
        except ImportError as exc:
            raise ImportError(
                "CosyVoice2 not installed. See docs/MODELS.md for install instructions."
            ) from exc

    def synthesise(self, text: str, voice_profile_id: Optional[str] = None) -> bytes:
        self._load()

        reference_wav: Optional[str] = None
        if voice_profile_id:
            candidate = os.path.join(_PROFILES_DIR, voice_profile_id, "reference_clip.wav")
            if os.path.exists(candidate):
                reference_wav = candidate
            else:
                log.warning(
                    "Voice profile %s reference clip not found — using default voice",
                    voice_profile_id,
                )

        log.info(
            "CosyVoice2 synthesising %d chars (clone=%s)",
            len(text),
            reference_wav is not None,
        )

        import torchaudio  # type: ignore

        if reference_wav:
            prompt_speech, sr = torchaudio.load(reference_wav)
            output_iter = self._model.inference_zero_shot(
                text, prompt_text="", prompt_speech_16k=prompt_speech
            )
        else:
            output_iter = self._model.inference_sft(text, spk_id="English")

        audio_chunks = []
        for chunk in output_iter:
            audio_chunks.append(chunk["tts_speech"])

        import torch  # type: ignore

        audio = torch.cat(audio_chunks, dim=1)
        return _tensor_to_wav(audio, sample_rate=22050)


def _tensor_to_wav(tensor, sample_rate: int) -> bytes:
    import numpy as np

    pcm = (tensor.squeeze().numpy() * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()
