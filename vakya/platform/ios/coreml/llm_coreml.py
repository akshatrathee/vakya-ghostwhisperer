"""CoreMLLLMEngine — Phi-3 Mini via coremltools on iOS (Sprint 7).

Phi-3 Mini is converted to CoreML using ``coremltools`` (Apple, BSD-3):
  python -m coremltools.converters.mil.testing_utils  (offline conversion)

The resulting ``phi3-mini-q4.mlpackage`` is loaded via the ``coremltools``
Python package, which calls CoreML's Objective-C API under the hood.

On non-iOS platforms ``coremltools`` is not installed — this engine raises
``ImportError`` on ``_load()`` and the pipeline falls back to ``RuleBasedEngine``.

Rule-based is the default on iOS (same as Android). Phi-3 is opt-in via the
"Enhanced cleanup" toggle in ContentView.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from vakya.core.llm.base import LLMEngine, CleanupMode

log = logging.getLogger(__name__)

_MODEL_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "models", "llm"
)
_MODEL_NAME = "phi3-mini-q4.mlpackage"


class CoreMLLLMEngine(LLMEngine):
    """Phi-3 Mini text cleanup via CoreML.

    Falls back to ``RuleBasedEngine`` if the model package is absent —
    never crashes the pipeline.
    """

    def __init__(self, model_dir: str | None = None) -> None:
        self._model_dir = model_dir or _MODEL_DIR
        self._model: Optional[Any] = None
        self._fallback: Optional[Any] = None

    def _load(self) -> None:
        if self._model is not None:
            return
        pkg_path = os.path.join(self._model_dir, _MODEL_NAME)
        if not os.path.exists(pkg_path):
            log.warning("CoreMLLLMEngine: model not found at %s — using rule-based fallback", pkg_path)
            self._use_fallback()
            return
        try:
            import coremltools as ct  # type: ignore
            self._model = ct.models.MLModel(pkg_path)
            log.info("CoreMLLLMEngine: loaded %s", pkg_path)
        except ImportError:
            log.warning("coremltools not installed — using rule-based fallback")
            self._use_fallback()

    def _use_fallback(self) -> None:
        from vakya.core.llm.phi3_mini import RuleBasedEngine  # type: ignore
        self._fallback = RuleBasedEngine()

    def cleanup(
        self,
        text: str,
        mode: CleanupMode = CleanupMode.DICTATION,
        vocab_hint: List[str] | None = None,
    ) -> str:
        self._load()
        if self._fallback is not None:
            return self._fallback.cleanup(text, mode=mode)

        # CoreML inference — Phi-3 Mini takes a text prompt and returns cleaned text
        prompt = _build_prompt(text, mode)
        try:
            prediction = self._model.predict({"prompt": prompt})
            # Output key depends on the CoreML export — typically "output" or "text"
            output = prediction.get("output") or prediction.get("text") or text
            return str(output).strip()
        except Exception as exc:
            log.error("CoreMLLLMEngine inference failed: %s — returning raw text", exc)
            return text


def _build_prompt(text: str, mode: CleanupMode) -> str:
    """Build a Phi-3 system+user prompt for text cleanup."""
    if mode == CleanupMode.DICTATION:
        instruction = "Clean up this dictated text: remove filler words, fix punctuation, preserve meaning."
    elif mode == CleanupMode.MEETING:
        instruction = "Clean up this meeting transcript: remove fillers, add speaker-aware punctuation."
    else:
        instruction = "Clean up this text."
    return f"<|system|>\n{instruction}<|end|>\n<|user|>\n{text}<|end|>\n<|assistant|>\n"
