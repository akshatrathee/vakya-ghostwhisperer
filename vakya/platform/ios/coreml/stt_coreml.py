"""CoreMLSTTEngine — whisper.cpp CoreML backend for iOS (Sprint 7).

whisper.cpp ships a CoreML backend (``make coreml``). It compiles to a
shared dylib (``libwhisper.dylib``) bundled in the app, and exposes a C API.
This wrapper calls that API via ctypes so the Python pipeline orchestrator
(``core/pipeline.py``) can call it through the standard ``STTEngine`` interface
without any Swift involvement.

On non-iOS platforms ctypes.CDLL will raise OSError — the engine falls back
gracefully and is never used outside the iOS bundle.

whisper.cpp C API reference:
  https://github.com/ggerganov/whisper.cpp/blob/master/whisper.h
"""

from __future__ import annotations

import ctypes
import logging
import os
import struct
import wave
from typing import List, Optional

from vakya.core.stt.base import STTEngine, STTResult, STTSegment

log = logging.getLogger(__name__)

# Bundled dylib path inside the iOS app bundle (.app/Frameworks/)
_DYLIB_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "Frameworks", "libwhisper.dylib"
)
_MODEL_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "models", "stt", "whisper-base-en"
)


def _load_lib() -> Optional[ctypes.CDLL]:
    path = os.environ.get("VAKYA_WHISPER_DYLIB", _DYLIB_PATH)
    if not os.path.exists(path):
        return None
    try:
        lib = ctypes.CDLL(path)
        _configure_ctypes(lib)
        return lib
    except OSError as exc:
        log.warning("Could not load libwhisper: %s", exc)
        return None


def _configure_ctypes(lib: ctypes.CDLL) -> None:
    """Set argtypes/restype for the C API calls we use."""
    lib.whisper_init_from_file.restype  = ctypes.c_void_p
    lib.whisper_init_from_file.argtypes = [ctypes.c_char_p]

    lib.whisper_full_default_params.restype  = ctypes.c_void_p   # whisper_full_params (returned by value — treat as opaque)
    lib.whisper_full_default_params.argtypes = [ctypes.c_int]

    lib.whisper_full.restype  = ctypes.c_int
    lib.whisper_full.argtypes = [
        ctypes.c_void_p,    # ctx
        ctypes.c_void_p,    # params (opaque struct)
        ctypes.POINTER(ctypes.c_float),  # samples
        ctypes.c_int,       # n_samples
    ]

    lib.whisper_full_n_segments.restype  = ctypes.c_int
    lib.whisper_full_n_segments.argtypes = [ctypes.c_void_p]

    lib.whisper_full_get_segment_text.restype  = ctypes.c_char_p
    lib.whisper_full_get_segment_text.argtypes = [ctypes.c_void_p, ctypes.c_int]

    lib.whisper_full_get_segment_t0.restype  = ctypes.c_int64
    lib.whisper_full_get_segment_t0.argtypes = [ctypes.c_void_p, ctypes.c_int]

    lib.whisper_full_get_segment_t1.restype  = ctypes.c_int64
    lib.whisper_full_get_segment_t1.argtypes = [ctypes.c_void_p, ctypes.c_int]

    lib.whisper_free.restype  = None
    lib.whisper_free.argtypes = [ctypes.c_void_p]

    # CoreML backend flag — WHISPER_SAMPLING_GREEDY = 0
    lib.whisper_full_default_params.restype = ctypes.c_void_p


# Sampling strategy constants (whisper.h)
_WHISPER_SAMPLING_GREEDY = 0


class CoreMLSTTEngine(STTEngine):
    """STT via whisper.cpp CoreML backend.

    Falls back gracefully to a ``FileNotFoundError`` when the dylib or model
    is absent (e.g. running tests on Windows CI).
    """

    def __init__(self, model_dir: str | None = None) -> None:
        self._model_dir = model_dir or _MODEL_DIR
        self._lib: Optional[ctypes.CDLL] = None
        self._ctx: Optional[ctypes.c_void_p] = None

    def _load(self) -> None:
        if self._ctx is not None:
            return
        lib = _load_lib()
        if lib is None:
            raise FileNotFoundError(
                f"libwhisper.dylib not found at {_DYLIB_PATH}. "
                "Build with: make coreml && cp libwhisper.dylib <AppBundle>/Frameworks/"
            )
        model_bin = os.path.join(self._model_dir, "ggml-base.en.bin")
        if not os.path.exists(model_bin):
            raise FileNotFoundError(
                f"Whisper CoreML model not found: {model_bin}. "
                "Run installer/download_models.py first."
            )
        ctx = lib.whisper_init_from_file(model_bin.encode())
        if not ctx:
            raise RuntimeError("whisper_init_from_file returned NULL")
        self._lib = lib
        self._ctx = ctypes.c_void_p(ctx)
        log.info("CoreMLSTTEngine loaded: %s", model_bin)

    def transcribe(
        self,
        audio_path: str,
        language: str = "en",
        vocab_hint: List[str] | None = None,
    ) -> STTResult:
        self._load()
        samples = _read_wav_float32(audio_path)
        n = len(samples)
        arr = (ctypes.c_float * n)(*samples)

        params = self._lib.whisper_full_default_params(_WHISPER_SAMPLING_GREEDY)
        ret = self._lib.whisper_full(self._ctx, ctypes.c_void_p(params), arr, n)
        if ret != 0:
            raise RuntimeError(f"whisper_full returned error code {ret}")

        n_seg = self._lib.whisper_full_n_segments(self._ctx)
        segments: List[STTSegment] = []
        full_text_parts: List[str] = []

        for i in range(n_seg):
            raw = self._lib.whisper_full_get_segment_text(self._ctx, i)
            text = raw.decode("utf-8", errors="replace").strip() if raw else ""
            t0 = self._lib.whisper_full_get_segment_t0(self._ctx, i) / 100.0
            t1 = self._lib.whisper_full_get_segment_t1(self._ctx, i) / 100.0
            segments.append(STTSegment(start=t0, end=t1, text=text))
            full_text_parts.append(text)

        full_text = " ".join(full_text_parts)
        return STTResult(text=full_text, segments=segments, language_detected="en")

    def __del__(self) -> None:
        if self._lib and self._ctx:
            try:
                self._lib.whisper_free(self._ctx)
            except Exception:
                pass


def _read_wav_float32(path: str) -> List[float]:
    """Read a 16kHz mono PCM_16BIT WAV and return samples as float32 in [-1, 1]."""
    with wave.open(path, "rb") as wf:
        raw = wf.readframes(wf.getnframes())
    n = len(raw) // 2
    shorts = struct.unpack(f"<{n}h", raw)
    return [s / 32768.0 for s in shorts]
