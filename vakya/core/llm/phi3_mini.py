"""Phi-3 Mini 3.8B Q4_K_M LLM cleanup engine via llama-cpp-python.

Primary LLM for transcript cleanup on recommended-spec hardware.
Context window: 4,096 tokens. Chunking handled by core/llm/chunker.py.
Falls back to RuleBasedEngine if model is absent (minimum-spec path).
"""

from __future__ import annotations

import logging
import os
import re
import tracemalloc
from typing import List

from .base import CleanupMode, LLMEngine, get_system_prompt
from .chunker import Chunk, reassemble, split_transcript

log = logging.getLogger(__name__)

_MODEL_PATH = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "models", "llm", "phi-3-mini-4k-instruct-q4_k_m.gguf",
)

_FILLER_RE = re.compile(
    r"\b(um+|uh+|aah+|hmm+|you\s+know|like)\b",
    re.IGNORECASE,
)


class RuleBasedEngine(LLMEngine):
    """Minimum-spec fallback: regex filler removal, no reformatting."""

    def cleanup(self, transcript: str, mode: CleanupMode) -> str:
        log.info("RuleBasedEngine: filler removal only (no LLM)")
        cleaned = _FILLER_RE.sub("", transcript)
        # Collapse multiple spaces left by removed fillers
        cleaned = re.sub(r"  +", " ", cleaned).strip()
        return cleaned


class Phi3MiniEngine(LLMEngine):
    def __init__(self, model_path: str | None = None) -> None:
        self._model_path = model_path or _MODEL_PATH
        self._llm = None

    def _load(self) -> None:
        if self._llm is not None:
            return
        if not os.path.exists(self._model_path):
            raise FileNotFoundError(
                f"Phi-3 Mini model not found at {self._model_path}. "
                "Run installer/download_models.py first."
            )
        try:
            from llama_cpp import Llama  # type: ignore

            self._llm = Llama(
                model_path=self._model_path,
                n_ctx=4096,
                n_threads=os.cpu_count() or 4,
                verbose=False,
            )
            log.info("Phi-3 Mini loaded from %s", self._model_path)
        except ImportError as exc:
            raise ImportError(
                "llama-cpp-python not installed. Run: pip install llama-cpp-python"
            ) from exc

    def cleanup(self, transcript: str, mode: CleanupMode) -> str:
        self._load()
        chunks = split_transcript(transcript)
        system_prompt = get_system_prompt(mode)
        cleaned_chunks: List[str] = []

        tracemalloc.start()
        for chunk in chunks:
            cleaned = self._cleanup_chunk(chunk, system_prompt)
            cleaned_chunks.append(cleaned)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        log.info(
            "Phi-3 Mini: processed %d chunk(s), peak RAM=%.1fMB",
            len(chunks),
            peak / 1e6,
        )

        return reassemble(cleaned_chunks, chunks)

    def _cleanup_chunk(self, chunk: Chunk, system_prompt: str) -> str:
        context_note = ""
        if chunk.overlap_prefix:
            context_note = (
                f"CONTEXT ONLY — do not repeat this in output:\n"
                f"{chunk.overlap_prefix}\n\n"
                f"---\n"
            )

        user_content = f"{context_note}{chunk.text}"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        response = self._llm.create_chat_completion(
            messages=messages,
            max_tokens=chunk.token_count + 200,
            temperature=0.1,
        )
        result = response["choices"][0]["message"]["content"].strip()

        # If LLM dropped speaker label from first line, inherit from overlap
        if chunk.overlap_prefix and not result.startswith("Speaker"):
            last_speaker = _extract_last_speaker(chunk.overlap_prefix)
            if last_speaker:
                result = f"{last_speaker}: {result}"

        return result


def _extract_last_speaker(text: str) -> str | None:
    import re

    matches = list(re.finditer(r"^(Speaker \w+):", text, re.MULTILINE))
    return matches[-1].group(1) if matches else None


def load_best_available(model_path: str | None = None) -> LLMEngine:
    """Return Phi3MiniEngine if model present, else RuleBasedEngine."""
    path = model_path or _MODEL_PATH
    if os.path.exists(path):
        try:
            engine = Phi3MiniEngine(path)
            engine._load()
            return engine
        except Exception as exc:
            log.warning("Phi-3 Mini load failed (%s) — falling back to rule-based", exc)
    log.info("Using RuleBasedEngine (Phi-3 Mini not available)")
    return RuleBasedEngine()
