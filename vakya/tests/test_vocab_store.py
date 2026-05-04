"""Unit tests for core/vocab/store.py"""

import json
import pytest
from pathlib import Path
from vakya.core.vocab import store as vocab_store


def test_empty_store_structure():
    s = vocab_store._empty_store()
    assert s["version"] == 1
    assert s["terms"] == []
    assert s["prompt_prefix_cache"] == ""
    assert "updated_at" in s


def test_add_term_new():
    s = vocab_store._empty_store()
    vocab_store.add_term(s, "Kharif", source="user_manual")
    assert len(s["terms"]) == 1
    assert s["terms"][0]["term"] == "Kharif"
    assert s["terms"][0]["source"] == "user_manual"
    assert s["terms"][0]["frequency"] == 1


def test_add_term_increments_frequency():
    s = vocab_store._empty_store()
    vocab_store.add_term(s, "Kharif")
    vocab_store.add_term(s, "kharif")  # case-insensitive dedup
    assert len(s["terms"]) == 1
    assert s["terms"][0]["frequency"] == 2


def test_get_vocab_hint():
    s = vocab_store._empty_store()
    vocab_store.add_term(s, "Rabi", source="user_manual")
    vocab_store.add_term(s, "Kharif", source="user_manual")
    vocab_store.add_term(s, "Drip irrigation", source="user_manual")
    hints = vocab_store.get_vocab_hint(s, max_terms=10)
    assert "Rabi" in hints
    assert "Kharif" in hints


def test_extract_new_terms_auto_adds_frequent():
    s = vocab_store._empty_store()
    # "Kharif" appears 2× as a non-sentence-start word → should be auto-added
    # "Priya" starts its sentences (sentence-start filter skips it by design)
    transcript = (
        "We discussed Kharif season. The Kharif harvest starts in October. "
        "She mentioned Priya twice. Ram also noted that Priya attended."
    )
    added = vocab_store.extract_new_terms(s, transcript)
    # "Kharif" appears 2× as non-sentence-start → auto-added
    assert "Kharif" in added or any(t["term"] == "Kharif" for t in s["terms"])
    # "Priya" appears 2× as non-sentence-start in second two sentences → auto-added
    assert "Priya" in added or any(t["term"] == "Priya" for t in s["terms"])


def test_extract_new_terms_skips_single_occurrence():
    s = vocab_store._empty_store()
    transcript = "Speaker 1: Today we saw Rajanpur village for the first time."
    added = vocab_store.extract_new_terms(s, transcript)
    # Single occurrence → not added
    assert "Rajanpur" not in added


def test_save_and_load_roundtrip(tmp_path):
    s = vocab_store._empty_store()
    vocab_store.add_term(s, "TestTerm", source="user_manual")
    p = tmp_path / "vocab_store.json"
    vocab_store.save(s, p)
    loaded = vocab_store.load(p)
    assert any(t["term"] == "TestTerm" for t in loaded["terms"])
