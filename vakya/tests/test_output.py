"""Tests for core/output/ — formatter, router, session_log."""

import json
import pytest
from pathlib import Path
from datetime import datetime, timezone

from vakya.core.llm.base import CleanupMode
from vakya.core.output import formatter
from vakya.core.output import session_log


class TestFormatter:
    def test_format_adds_header(self):
        text = "Speaker 1: Hello world."
        result = formatter.format_transcript(
            text, CleanupMode.DICTATION, "test-session-1"
        )
        assert "# Dictation" in result
        assert "test-session-1" in result
        assert "Hello world." in result

    def test_format_notes_mode(self):
        text = "- Point one\n- Point two"
        result = formatter.format_transcript(text, CleanupMode.NOTES, "sess-2")
        assert "# Notes" in result

    def test_format_farm_log_mode(self):
        result = formatter.format_transcript("Activity: irrigation", CleanupMode.FARM_LOG, "sess-3")
        assert "# Farm Log" in result

    def test_normalise_collapses_blank_lines(self):
        text = "Line one.\n\n\n\nLine two."
        result = formatter.format_transcript(text, CleanupMode.DICTATION, "sess-4")
        assert "\n\n\n" not in result

    def test_speaker_to_display_tag(self):
        text = "Speaker 1: Hello. Speaker 2: World."
        tagged = formatter.speaker_to_display_tag(text)
        assert '<speaker id="1">' in tagged
        assert '<speaker id="2">' in tagged

    def test_strip_display_tags_roundtrip(self):
        text = "Speaker 1: Hello world."
        tagged = formatter.speaker_to_display_tag(text)
        stripped = formatter.strip_display_tags(tagged)
        assert "Speaker 1:" in stripped
        assert "<speaker" not in stripped


class TestSessionLog:
    def test_writes_valid_json(self, tmp_path):
        # Monkey-patch _SESSIONS_DIR
        import vakya.core.output.session_log as sl
        original = sl._SESSIONS_DIR
        sl._SESSIONS_DIR = tmp_path

        try:
            path = sl.write_session_metadata(
                session_id="test-abc-123",
                started_at=datetime(2026, 4, 27, 10, 0, 0, tzinfo=timezone.utc),
                completed_at=datetime(2026, 4, 27, 10, 0, 30, tzinfo=timezone.utc),
                mode="dictation",
                language_detected="en",
                audio_duration_sec=120.0,
                stt_engine="faster_whisper_large_v3_turbo",
                llm_engine="phi3_mini_q4",
                speaker_ids=["Speaker 1", "Speaker 2"],
                timing={"vad_sec": 0.1, "stt_sec": 15.0, "diarization_sec": 5.0, "llm_sec": 5.0, "total_sec": 25.1},
                peak_ram_mb=3200.0,
                transcript_path="sessions/test-abc-123_dictation.md",
                vocab_terms_extracted=["Kharif"],
                voice_profiles_updated=["Speaker 1"],
                llm_chunk_count=1,
            )
        finally:
            sl._SESSIONS_DIR = original

        assert path is not None
        assert path.exists()

        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["session_id"] == "test-abc-123"
        assert data["mode"] == "dictation"
        assert data["speaker_count"] == 2
        assert data["stt_engine"] == "faster_whisper_large_v3_turbo"
        assert data["wiki_ingest_status"] == "skipped_phase3"
        assert data["timing"]["total_sec"] == 25.1

    def test_schema_required_fields_present(self, tmp_path):
        """All required fields from session.schema.json must be present."""
        required = ["session_id", "started_at", "completed_at", "mode", "stt_engine", "llm_engine"]

        import vakya.core.output.session_log as sl
        original = sl._SESSIONS_DIR
        sl._SESSIONS_DIR = tmp_path

        try:
            path = sl.write_session_metadata(
                session_id="req-test",
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                mode="notes",
                language_detected="en",
                audio_duration_sec=30.0,
                stt_engine="whisper_cpp_base_en",
                llm_engine="rule_based",
                speaker_ids=["Speaker 1"],
                timing={},
                peak_ram_mb=300.0,
                transcript_path=None,
                vocab_terms_extracted=[],
                voice_profiles_updated=[],
            )
        finally:
            sl._SESSIONS_DIR = original

        data = json.loads(path.read_text(encoding="utf-8"))
        for field in required:
            assert field in data, f"Missing required field: {field}"


class TestRouter:
    def test_router_writes_log(self, tmp_path):
        import vakya.core.output.router as r
        original = r._SESSIONS_DIR
        r._SESSIONS_DIR = tmp_path

        try:
            result = r.route(
                formatted_text="# Dictation\n\nHello world.",
                raw_text="Hello world.",
                mode=CleanupMode.DICTATION,
                session_id="router-test-001",
                copy_to_clipboard=False,
                write_log=True,
            )
        finally:
            r._SESSIONS_DIR = original

        assert result["log_path"] is not None
        assert Path(result["log_path"]).exists()

    def test_router_extracts_vocab(self, tmp_path):
        import vakya.core.output.router as r
        import vakya.core.vocab.store as vs

        original_sessions = r._SESSIONS_DIR
        r._SESSIONS_DIR = tmp_path

        vocab_path = tmp_path / "vocab.json"

        transcript = (
            "We planted Kharif crops. The Kharif season started early. "
            "Priya confirmed the yield. Ram noted that Priya was satisfied."
        )

        try:
            result = r.route(
                formatted_text=transcript,
                raw_text=transcript,
                mode=CleanupMode.FARM_LOG,
                session_id="vocab-test-001",
                copy_to_clipboard=False,
                write_log=False,
                vocab_path=vocab_path,
            )
        finally:
            r._SESSIONS_DIR = original_sessions

        # Kharif appears 2× as non-sentence-start → auto-added
        store = vs.load(vocab_path)
        terms = [t["term"] for t in store["terms"]]
        assert "Kharif" in terms
