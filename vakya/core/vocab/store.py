"""Personal vocabulary store — read/write + term extraction.

Injected as STT --initial_prompt prefix to improve recognition
of domain-specific terms (farm names, crop varieties, people's names).

Pipeline steps that use this module:
  Step 2 (STT): reads prompt_prefix_cache → passes as vocab_hint
  Step 6 (Output): calls extract_new_terms() → adds frequent new terms
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

log = logging.getLogger(__name__)

_DEFAULT_PATH = Path(__file__).parent.parent.parent / "data" / "vocab_store.json"

_STOPWORDS = {
    # Common English stopwords (abbreviated — full list loaded from file if present)
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "up", "out", "is", "it", "its", "be",
    "was", "are", "were", "been", "has", "had", "have", "do", "does",
    "did", "will", "would", "could", "should", "may", "might", "shall",
    "can", "need", "dare", "ought", "used", "this", "that", "these",
    "those", "i", "you", "he", "she", "we", "they", "me", "him", "her",
    "us", "them", "my", "your", "his", "our", "their", "what", "which",
    "who", "whom", "when", "where", "why", "how", "all", "each", "every",
    "both", "few", "more", "most", "other", "some", "such", "no", "not",
    "only", "same", "so", "than", "too", "very", "just", "also", "as",
    "if", "while", "although", "because", "since", "until", "unless",
    "after", "before", "during", "about", "against", "between", "into",
    "through", "during", "before", "after", "above", "below", "over",
    "then", "once", "here", "there", "again", "further", "then", "once",
    "said", "like", "okay", "yeah", "yes", "no",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_store() -> dict:
    return {
        "version": 1,
        "updated_at": _now_iso(),
        "terms": [],
        "prompt_prefix_cache": "",
    }


def load(path: Path | None = None) -> dict:
    p = Path(path) if path else _DEFAULT_PATH
    if not p.exists():
        log.debug("vocab_store not found at %s — starting empty", p)
        return _empty_store()
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Failed to read vocab_store (%s) — starting empty", exc)
        return _empty_store()


def save(store: dict, path: Path | None = None) -> None:
    p = Path(path) if path else _DEFAULT_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    store["updated_at"] = _now_iso()
    p.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    log.debug("vocab_store saved (%d terms)", len(store["terms"]))


def get_vocab_hint(store: dict, max_terms: int = 50) -> List[str]:
    """Return top-N terms for STT prompt injection."""
    terms = sorted(store["terms"], key=lambda t: t.get("frequency", 1), reverse=True)
    return [t["term"] for t in terms[:max_terms]]


def add_term(
    store: dict,
    term: str,
    source: str = "user_manual",
    phonetic_hint: Optional[str] = None,
) -> None:
    """Add or update a term in the store."""
    for entry in store["terms"]:
        if entry["term"].lower() == term.lower():
            entry["frequency"] = entry.get("frequency", 1) + 1
            log.debug("vocab_store: incremented '%s' → %d", term, entry["frequency"])
            return
    store["terms"].append(
        {
            "term": term,
            "phonetic_hint": phonetic_hint,
            "added_at": _now_iso(),
            "source": source,
            "frequency": 1,
        }
    )
    log.debug("vocab_store: added '%s' (source=%s)", term, source)
    _rebuild_cache(store)


def extract_new_terms(store: dict, cleaned_transcript: str) -> List[str]:
    """Extract candidate terms from a cleaned transcript and add frequent ones.

    Algorithm (from PIPELINE.md Step 6):
    a. Tokenise into words
    b. Keep capitalised non-sentence-start words (likely proper nouns)
    c. Filter out stopwords and already-known terms
    d. Auto-add terms with frequency >= 2 within this session
    e. Log single-occurrence candidates but do not add
    Returns list of terms actually added.
    """
    existing = {t["term"].lower() for t in store["terms"]}
    sentences = re.split(r"(?<=[.!?])\s+", cleaned_transcript)

    word_re = re.compile(r"\b[A-Z][a-zA-Z]{2,}\b")
    frequency: dict[str, int] = {}

    for sentence in sentences:
        words = sentence.split()
        # Skip first word of each sentence (capitalised due to grammar, not proper noun)
        for word in words[1:]:
            m = word_re.match(word)
            if not m:
                continue
            term = m.group(0)
            if term.lower() in _STOPWORDS:
                continue
            if term.lower() in existing:
                continue
            frequency[term] = frequency.get(term, 0) + 1

    added = []
    for term, freq in frequency.items():
        if freq >= 2:
            add_term(store, term, source="auto_extracted")
            existing.add(term.lower())
            added.append(term)
        else:
            log.debug("vocab_store: single-occurrence candidate '%s' (not added)", term)

    if added:
        _rebuild_cache(store)
    return added


def _rebuild_cache(store: dict) -> None:
    top = get_vocab_hint(store)
    store["prompt_prefix_cache"] = ", ".join(top)
