"""TTS engine factory — hw-tier-aware engine selection.

ADR-004 decision tree:
  RPi:       Piper (smallest, ~60MB)
  Minimum:   Kokoro ONNX (82M, ~200MB RAM)
  Recommended + cloning_needed: CosyVoice2 (or OmniVoice if CPU RTF < 2.0)
  Recommended + no cloning:     CosyVoice2 default voice

OmniVoice benchmark status: NOT YET RUN.
Update OMNIVOICE_CPU_RTF below after running core/tts/omnivoice.benchmark_rtf()
on the target CPU, then set USE_OMNIVOICE = True if RTF < 2.0.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from .base import TTSEngine

log = logging.getLogger(__name__)

# ── ADR-004 benchmark result ──────────────────────────────────────────────────
# Run once on target CPU:
#   python -m vakya --benchmark-omnivoice
# Then set OMNIVOICE_CPU_RTF and USE_OMNIVOICE below.
OMNIVOICE_CPU_RTF: Optional[float] = None  # None = benchmark not yet run
_ADR004_RTF_THRESHOLD = 2.0
USE_OMNIVOICE = False  # Set True after benchmark confirms RTF < 2.0

_MODELS_ROOT = Path(__file__).parent.parent.parent / "models"


def _model_present(relative_path: str) -> bool:
    return (_MODELS_ROOT / relative_path).exists()


def select_tts_engine(
    hw_tier: str,
    cloning_required: bool = False,
) -> TTSEngine:
    """Return the best available TTS engine for the given hardware tier.

    Degrades gracefully: CosyVoice2 → Kokoro → Piper → error.
    Never crashes — always returns something runnable if any model is present.
    """
    if OMNIVOICE_CPU_RTF is None:
        log.warning(
            "ADR-004: OmniVoice CPU RTF benchmark not yet run. "
            "CosyVoice2 will be used by default. "
            "Run `python -m vakya --benchmark-omnivoice` to close this decision."
        )
    log.info(
        "TTS engine selection: hw_tier=%s, cloning=%s, omnivoice_rtf=%s",
        hw_tier,
        cloning_required,
        OMNIVOICE_CPU_RTF,
    )

    if hw_tier == "rpi":
        return _load_piper()

    if hw_tier == "minimum":
        return _load_kokoro()

    # recommended tier
    if cloning_required:
        if USE_OMNIVOICE and _model_present("tts/omnivoice"):
            log.info("TTS: OmniVoice (ADR-004 benchmark passed, RTF=%.2f)", OMNIVOICE_CPU_RTF)
            return _load_omnivoice()
        if _model_present("tts/cosyvoice2"):
            log.info("TTS: CosyVoice2 (primary cloner)")
            return _load_cosyvoice2()
        log.warning("TTS: cloning requested but no cloning model present — falling back to Kokoro")

    if _model_present("tts/cosyvoice2"):
        log.info("TTS: CosyVoice2 (default voice, no cloning)")
        return _load_cosyvoice2()

    if _model_present("tts/kokoro-v1.0.onnx"):
        log.info("TTS: Kokoro (CosyVoice2 not present)")
        return _load_kokoro()

    if _model_present("tts/piper/en_US-lessac-medium.onnx"):
        log.info("TTS: Piper (last resort)")
        return _load_piper()

    raise RuntimeError(
        "No TTS model found. Run: python -m vakya.installer.download_models --tier recommended"
    )


def _load_cosyvoice2() -> TTSEngine:
    from .cosyvoice2 import CosyVoice2Engine
    return CosyVoice2Engine()


def _load_kokoro() -> TTSEngine:
    from .kokoro import KokoroEngine
    return KokoroEngine()


def _load_piper() -> TTSEngine:
    from .piper import PiperEngine
    return PiperEngine()


def _load_omnivoice() -> TTSEngine:
    from .omnivoice import OmniVoiceEngine
    return OmniVoiceEngine()


def engine_name(engine: TTSEngine) -> str:
    return type(engine).__name__.lower().replace("engine", "")
