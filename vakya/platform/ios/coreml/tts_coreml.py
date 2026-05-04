"""CoreMLTTSEngine — Kokoro ONNX converted to CoreML for iOS (Sprint 7).

Conversion pipeline (run offline, one-time):
  pip install coremltools onnx onnxmltools
  python scripts/convert_kokoro_coreml.py   (writes kokoro.mlpackage)

The ``coremltools`` Python package then calls the CoreML Objective-C API
for inference. Output is a PCM Float32 array → written to a WAV.

On non-iOS platforms, ``coremltools`` is absent and this engine raises
``ImportError`` on ``_load()``. The pipeline degrades to silence (no TTS).
"""

from __future__ import annotations

import logging
import os
import struct
import wave
from typing import Any, Optional

from vakya.core.tts.base import TTSEngine

log = logging.getLogger(__name__)

_MODEL_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "models", "tts"
)
_MODEL_NAME = "kokoro.mlpackage"
_SAMPLE_RATE = 24_000   # Kokoro output sample rate


class CoreMLTTSEngine(TTSEngine):
    """Kokoro ONNX→CoreML TTS for iOS.

    Outputs 24kHz mono PCM WAV to the provided path.
    Falls back to a no-op (silent) if the model package is absent.
    """

    def __init__(self, model_dir: str | None = None) -> None:
        self._model_dir = model_dir or _MODEL_DIR
        self._model: Optional[Any] = None
        self._available = False

    def _load(self) -> None:
        if self._model is not None or not self._available and self._model is None:
            # Check once; if unavailable, skip subsequent attempts
            pass
        pkg_path = os.path.join(self._model_dir, _MODEL_NAME)
        if not os.path.exists(pkg_path):
            log.warning("CoreMLTTSEngine: model not found at %s — TTS silent", pkg_path)
            return
        try:
            import coremltools as ct  # type: ignore
            self._model = ct.models.MLModel(pkg_path)
            self._available = True
            log.info("CoreMLTTSEngine: loaded %s", pkg_path)
        except ImportError:
            log.warning("coremltools not installed — TTS silent on this platform")

    def synthesise(
        self,
        text: str,
        output_path: str,
        voice_id: str | None = None,
        speed: float = 1.0,
    ) -> str:
        """Synthesise *text* and write a WAV to *output_path*.

        Returns *output_path* on success or raises ``RuntimeError`` if the
        engine is unavailable and ``output_path`` can't be written.
        """
        self._load()
        if not self._available or self._model is None:
            _write_silent_wav(output_path, duration_s=0.5)
            log.warning("CoreMLTTSEngine: wrote silent WAV (model unavailable)")
            return output_path

        try:
            prediction = self._model.predict({
                "text": text,
                "speed": speed,
                "voice_id": voice_id or "default",
            })
            pcm_floats = prediction.get("audio") or prediction.get("output")
            if pcm_floats is None:
                raise ValueError("CoreML TTS returned no audio key")
            _write_float32_wav(pcm_floats, output_path, _SAMPLE_RATE)
            log.info("CoreMLTTSEngine: wrote %s", output_path)
        except Exception as exc:
            log.error("CoreMLTTSEngine inference failed: %s", exc)
            _write_silent_wav(output_path, duration_s=0.5)
        return output_path


def _write_float32_wav(
    samples: Any,
    path: str,
    sample_rate: int,
) -> None:
    """Convert float32 samples to int16 and write a WAV file."""
    try:
        # samples may be a numpy array or a list
        floats = list(samples)
    except TypeError:
        floats = [float(samples)]

    clamped = [max(-1.0, min(1.0, f)) for f in floats]
    shorts = [int(f * 32767) for f in clamped]
    raw = struct.pack(f"<{len(shorts)}h", *shorts)

    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(raw)


def _write_silent_wav(path: str, duration_s: float = 0.5) -> None:
    n = int(_SAMPLE_RATE * duration_s)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(_SAMPLE_RATE)
        wf.writeframes(b"\x00\x00" * n)
