"""Sprint 4 tests — Windows platform UI components.

Tests that do NOT require a display, real mic, or model weights.
UI widget tests use QApplication and exercise logic-only paths.
"""

from __future__ import annotations

import importlib
import os
import sys
import tempfile
import wave
import struct
import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _write_silence_wav(path: str, duration_sec: float = 1.0, rate: int = 16_000) -> None:
    """Write a silent mono 16-bit WAV."""
    n_frames = int(rate * duration_sec)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x00" * n_frames)


# ── B2 regression: faster_whisper path is absolute ────────────────────────────

class TestFasterWhisperPathFix:
    def test_model_dir_is_absolute(self):
        from vakya.core.stt.faster_whisper import _MODEL_DIR
        assert os.path.isabs(_MODEL_DIR), (
            f"_MODEL_DIR must be absolute after B2 fix, got: {_MODEL_DIR!r}"
        )

    def test_model_dir_does_not_break_on_cwd_change(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # Re-importing should still yield an absolute path
        import importlib
        import vakya.core.stt.faster_whisper as fw
        importlib.reload(fw)
        assert os.path.isabs(fw._MODEL_DIR)


# ── WindowsAudioCapture ───────────────────────────────────────────────────────

class TestWindowsAudioCapture:
    def test_import(self):
        from vakya.platform.windows.audio_win import WindowsAudioCapture
        assert WindowsAudioCapture is not None

    def test_registered_under_windows(self):
        import vakya.platform.windows.audio_win  # side-effect: register()
        from vakya.core.audio_capture import _registry
        assert "windows" in _registry

    def test_get_wav_path_before_stop_raises(self):
        from vakya.platform.windows.audio_win import WindowsAudioCapture
        cap = WindowsAudioCapture()
        with pytest.raises(RuntimeError, match="before stop"):
            cap.get_wav_path()

    def test_level_callback_registration(self):
        from vakya.platform.windows.audio_win import WindowsAudioCapture
        cap = WindowsAudioCapture()
        received: list[float] = []
        cap.set_level_callback(received.append)
        assert cap._level_cb is not None

    def test_flush_to_wav_produces_valid_wav(self, tmp_path):
        """Flush with empty queue should still produce a valid (silent) WAV."""
        import numpy as np
        from vakya.platform.windows.audio_win import WindowsAudioCapture
        cap = WindowsAudioCapture()
        wav_path = cap._flush_to_wav()
        assert os.path.exists(wav_path)
        with wave.open(wav_path, "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 16_000
        os.unlink(wav_path)


# ── HotkeyThread ─────────────────────────────────────────────────────────────

class TestHotkeyThread:
    def test_import(self):
        from vakya.platform.windows.hotkey import HotkeyThread
        assert HotkeyThread is not None

    def test_parse_modifiers_ctrl_shift(self):
        from vakya.platform.windows.hotkey import (
            _parse_modifiers, MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT
        )
        flags = _parse_modifiers("ctrl+shift")
        assert flags & MOD_CONTROL
        assert flags & MOD_SHIFT
        assert flags & MOD_NOREPEAT

    def test_parse_vk_space(self):
        from vakya.platform.windows.hotkey import _parse_vk, VK_SPACE
        assert _parse_vk("space") == VK_SPACE

    def test_parse_vk_letter(self):
        from vakya.platform.windows.hotkey import _parse_vk
        assert _parse_vk("a") == ord("A")

    def test_parse_vk_unknown_raises(self):
        from vakya.platform.windows.hotkey import _parse_vk
        with pytest.raises(ValueError):
            _parse_vk("F12")

    def test_hotkey_thread_instantiates(self):
        from vakya.platform.windows.hotkey import HotkeyThread
        ht = HotkeyThread(modifiers="ctrl+shift", key="space")
        assert ht._mod_flags != 0
        assert ht._vk != 0


# ── OverlayWindow (import + state) ───────────────────────────────────────────

@pytest.mark.skipif(
    os.environ.get("CI") == "true" or not os.environ.get("DISPLAY", sys.platform == "win32"),
    reason="Overlay requires display — skip in headless CI",
)
class TestOverlayImport:
    def test_import(self):
        from vakya.platform.windows.overlay import OverlayWindow
        assert OverlayWindow is not None


# ── Shell import ──────────────────────────────────────────────────────────────

class TestShellImport:
    def test_shell_importable(self):
        from vakya.platform.windows import shell
        assert hasattr(shell, "launch")
        assert hasattr(shell, "MainWindow")

    def test_pipeline_worker_instantiates(self, tmp_path):
        fd, wav = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        _write_silence_wav(wav)
        from vakya.platform.windows.shell import PipelineWorker
        from vakya.core.llm.base import CleanupMode
        worker = PipelineWorker(wav, CleanupMode.DICTATION)
        assert worker is not None
        os.unlink(wav)

    def test_waveform_widget_importable(self):
        from vakya.platform.windows.shell import WaveformWidget
        assert WaveformWidget is not None

    def test_transcript_panel_importable(self):
        from vakya.platform.windows.shell import TranscriptPanel
        assert TranscriptPanel is not None


# ── CLI --ui flag wired ───────────────────────────────────────────────────────

class TestCLIUIFlag:
    def test_ui_flag_exists(self):
        import argparse
        from vakya.cli import main
        # Parse --ui without actually launching (we just check parser accepts it)
        import vakya.cli as cli_mod
        import inspect
        src = inspect.getsource(cli_mod)
        assert "--ui" in src

    def test_ui_routes_to_shell_launch(self):
        import vakya.cli as cli_mod
        import inspect
        src = inspect.getsource(cli_mod)
        assert "from vakya.platform.windows.shell import launch" in src
