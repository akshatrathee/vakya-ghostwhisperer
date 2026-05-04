"""Transcript chunker for LLM context-window management.

Phi-3 Mini 4K has a 4,096-token context window.
A 30-min recording ≈ 6,000 tokens — exceeds window by 50%.
Chunking is MANDATORY for all recordings, not just long ones.

Rules (from PIPELINE.md and ADR-003):
- MAX_CHUNK_TOKENS = 2800  (safety margin for system prompt + output)
- OVERLAP_TOKENS   = 200   (last ~2 sentences of previous chunk prepended as context)
- Split at speaker boundaries first, then sentence boundaries
- Never split mid-sentence
- Log every chunk boundary with token counts
- On reassembly: strip overlap, check speaker label continuity
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import List, Tuple

log = logging.getLogger(__name__)

MAX_CHUNK_TOKENS = 2800
OVERLAP_TOKENS = 200

_SPEAKER_RE = re.compile(r"^(Speaker \w+|[A-Z][a-z]+ \d*):", re.MULTILINE)
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")


def _approx_tokens(text: str) -> int:
    """~4 chars per token heuristic — fast, no model required."""
    return max(1, len(text) // 4)


@dataclass
class Chunk:
    index: int
    text: str
    token_count: int
    overlap_prefix: str  # read-only context from previous chunk (not in output)


def split_transcript(transcript: str) -> List[Chunk]:
    """Split transcript into chunks respecting speaker and sentence boundaries."""
    if _approx_tokens(transcript) <= MAX_CHUNK_TOKENS:
        log.debug("chunker: single chunk (%d tokens)", _approx_tokens(transcript))
        return [Chunk(index=0, text=transcript, token_count=_approx_tokens(transcript), overlap_prefix="")]

    # Split into natural segments (speaker turns or sentences)
    segments = _split_into_segments(transcript)
    chunks: List[Chunk] = []
    current_parts: List[str] = []
    current_tokens = 0
    prev_overlap = ""

    for seg in segments:
        seg_tokens = _approx_tokens(seg)
        if current_tokens + seg_tokens > MAX_CHUNK_TOKENS and current_parts:
            chunk_text = "".join(current_parts).strip()
            chunk = Chunk(
                index=len(chunks),
                text=chunk_text,
                token_count=current_tokens,
                overlap_prefix=prev_overlap,
            )
            chunks.append(chunk)
            log.debug(
                "chunker: chunk %d — %d tokens (overlap prefix: %d tokens)",
                chunk.index,
                current_tokens,
                _approx_tokens(prev_overlap),
            )

            overlap_text = _extract_overlap(chunk_text)
            prev_overlap = overlap_text
            current_parts = [seg]
            current_tokens = seg_tokens
        else:
            current_parts.append(seg)
            current_tokens += seg_tokens

    if current_parts:
        chunk_text = "".join(current_parts).strip()
        chunks.append(
            Chunk(
                index=len(chunks),
                text=chunk_text,
                token_count=current_tokens,
                overlap_prefix=prev_overlap,
            )
        )
        log.debug("chunker: final chunk %d — %d tokens", len(chunks) - 1, current_tokens)

    log.info("chunker: split into %d chunks", len(chunks))
    return chunks


def reassemble(cleaned_chunks: List[str], chunks: List[Chunk]) -> str:
    """Reassemble cleaned chunk outputs into a single transcript.

    - Strips overlap from joins
    - Merges consecutive paragraphs with same speaker label (chunk-boundary artefact)
    """
    if len(cleaned_chunks) == 1:
        return cleaned_chunks[0].strip()

    parts = [cleaned_chunks[0].strip()]
    for i, cleaned in enumerate(cleaned_chunks[1:], 1):
        cleaned = cleaned.strip()
        # If same speaker continues across a chunk boundary, merge paragraphs
        last_speaker = _last_speaker_label(parts[-1])
        first_speaker = _first_speaker_label(cleaned)
        if last_speaker and last_speaker == first_speaker:
            log.debug("chunker: merging chunk %d/%d (same speaker continues)", i - 1, i)
            parts[-1] = parts[-1].rstrip() + " " + _strip_first_speaker_label(cleaned)
        else:
            parts.append(cleaned)

    return "\n\n".join(parts)


def _split_into_segments(transcript: str) -> List[str]:
    speaker_spans = list(_SPEAKER_RE.finditer(transcript))
    if len(speaker_spans) > 1:
        segments = []
        for i, m in enumerate(speaker_spans):
            end = speaker_spans[i + 1].start() if i + 1 < len(speaker_spans) else len(transcript)
            segments.append(transcript[m.start():end])
        return segments
    return _SENTENCE_END_RE.split(transcript)


def _extract_overlap(text: str) -> str:
    """Return the last ~OVERLAP_TOKENS worth of text."""
    target_chars = OVERLAP_TOKENS * 4
    if len(text) <= target_chars:
        return text
    # Try to cut at sentence boundary
    cut_pos = len(text) - target_chars
    match = _SENTENCE_END_RE.search(text, cut_pos)
    if match:
        return text[match.end():]
    return text[-target_chars:]


def _last_speaker_label(text: str) -> str | None:
    matches = list(_SPEAKER_RE.finditer(text))
    return matches[-1].group(1) if matches else None


def _first_speaker_label(text: str) -> str | None:
    m = _SPEAKER_RE.match(text.lstrip())
    return m.group(1) if m else None


def _strip_first_speaker_label(text: str) -> str:
    return _SPEAKER_RE.sub("", text, count=1).lstrip()
