"""Unit tests for core/llm/chunker.py — the most safety-critical module."""

import pytest
from vakya.core.llm.chunker import (
    MAX_CHUNK_TOKENS,
    OVERLAP_TOKENS,
    _approx_tokens,
    reassemble,
    split_transcript,
)


def make_transcript(n_words: int, speakers: int = 1) -> str:
    lines = []
    words_per_speaker = n_words // speakers
    for i in range(speakers):
        line = f"Speaker {i + 1}: " + " ".join(["word"] * words_per_speaker)
        lines.append(line)
    return "\n".join(lines)


def test_short_transcript_is_single_chunk():
    text = "Speaker 1: Hello, how are you today? I am doing fine."
    chunks = split_transcript(text)
    assert len(chunks) == 1
    assert chunks[0].index == 0
    assert chunks[0].text == text
    assert chunks[0].overlap_prefix == ""


def test_long_transcript_splits():
    # ~3200 tokens ≈ 12800 chars — must split
    text = make_transcript(n_words=4000, speakers=2)
    chunks = split_transcript(text)
    assert len(chunks) > 1
    for i, chunk in enumerate(chunks):
        assert chunk.index == i
        assert chunk.token_count <= MAX_CHUNK_TOKENS + 100  # +100 for rounding


def test_overlap_present_on_subsequent_chunks():
    text = make_transcript(n_words=4000, speakers=3)
    chunks = split_transcript(text)
    for chunk in chunks[1:]:
        assert chunk.overlap_prefix != ""
        assert _approx_tokens(chunk.overlap_prefix) <= OVERLAP_TOKENS + 50


def test_reassemble_single_chunk():
    chunks = split_transcript("Speaker 1: Hello world.")
    result = reassemble(["Speaker 1: Hello world."], chunks)
    assert result == "Speaker 1: Hello world."


def test_reassemble_merges_same_speaker():
    # Simulate same speaker spanning chunk boundary
    from vakya.core.llm.chunker import Chunk

    chunks = [
        Chunk(index=0, text="Speaker 1: Part one.", token_count=10, overlap_prefix=""),
        Chunk(index=1, text="Speaker 1: Part two.", token_count=10, overlap_prefix="Speaker 1: Part one."),
    ]
    cleaned = ["Speaker 1: Part one.", "Speaker 1: Part two."]
    result = reassemble(cleaned, chunks)
    # Same speaker paragraphs should be merged
    assert "Speaker 1:" in result
    assert "Part one" in result
    assert "Part two" in result


def test_approx_tokens():
    # 400 chars → ~100 tokens
    assert _approx_tokens("a" * 400) == 100
    assert _approx_tokens("") == 1  # min 1


def test_no_mid_sentence_split():
    """Chunks should not end mid-word."""
    text = make_transcript(n_words=4000, speakers=1)
    chunks = split_transcript(text)
    for chunk in chunks:
        # Each chunk text should not end with a partial word (trailing space OK)
        assert not chunk.text.endswith(" w") or chunk.text.strip()
