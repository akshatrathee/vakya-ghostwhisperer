"""Kokoro 82M ONNX TTS — fallback engine, all platforms.

~300MB on disk, ~200MB RAM, MOS 4.5, Apache 2.0.
No zero-shot voice cloning — default voice only.
"""

from __future__ import annotations

import io
import logging
import os
import struct
import wave
from typing import Optional

from .base import TTSEngine

log = logging.getLogger(__name__)

_MODEL_PATH = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "models", "tts", "kokoro-v1.0.onnx",
)
_VOICES_PATH = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "models", "tts", "kokoro-voices.bin",
)


class KokoroEngine(TTSEngine):
    def __init__(self, model_path: str | None = None) -> None:
        self._model_path = model_path or _MODEL_PATH
        self._session = None

    def _load(self) -> None:
        if self._session is not None:
            return
        if not os.path.exists(self._model_path):
            raise FileNotFoundError(
                f"Kokoro model not found at {self._model_path}. "
                "Run installer/download_models.py first."
            )
        try:
            import onnxruntime as ort  # type: ignore

            opts = ort.SessionOptions()
            opts.intra_op_num_threads = os.cpu_count() or 4
            self._session = ort.InferenceSession(
                self._model_path,
                sess_options=opts,
                providers=["CPUExecutionProvider"],
            )
            log.info("Kokoro ONNX loaded from %s", self._model_path)
        except ImportError as exc:
            raise ImportError(
                "onnxruntime not installed. Run: pip install onnxruntime"
            ) from exc

    def synthesise(self, text: str, voice_profile_id: Optional[str] = None) -> bytes:
        self._load()
        if voice_profile_id:
            log.warning(
                "Kokoro does not support voice cloning — ignoring voice_profile_id=%s",
                voice_profile_id,
            )

        log.info("Kokoro synthesising %d chars", len(text))
        try:
            import kokoro_onnx  # type: ignore

            samples, sample_rate = kokoro_onnx.generate(
                self._session, text, voice="af_heart", speed=1.0
            )
        except ImportError:
            samples = self._session.run(None, {"text": [text]})[0]
            sample_rate = 24000

        return _pcm_to_wav(samples, sample_rate)


def _pcm_to_wav(samples, sample_rate: int) -> bytes:
    import numpy as np

    pcm = (np.clip(samples.flatten(), -1.0, 1.0) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()
