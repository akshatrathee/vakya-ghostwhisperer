"""Windows PyQt6 application shell — traditional mode + Wispr-mode host.

Launch with: python -m vakya.platform.windows.shell
Or via the launcher:  python -m vakya --ui
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import (
    QSize, Qt, QThread, QTimer, pyqtSignal, pyqtSlot,
)
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QStatusBar,
    QSystemTrayIcon, QVBoxLayout, QWidget,
)

from vakya.core.llm.base import CleanupMode

log = logging.getLogger(__name__)

# Speaker colours for transcript display (up to 8 speakers)
_SPEAKER_COLOURS = [
    "#4A90D9", "#E67E22", "#27AE60", "#8E44AD",
    "#C0392B", "#16A085", "#D4AC0D", "#2C3E50",
]

_MODES = [
    ("Dictation", CleanupMode.DICTATION),
    ("Notes", CleanupMode.NOTES),
    ("Farm Log", CleanupMode.FARM_LOG),
    ("Meeting", CleanupMode.MEETING),
]


# ── Worker thread ─────────────────────────────────────────────────────────────

class PipelineWorker(QThread):
    """Runs pipeline.run() off the UI thread. Emits result or error."""

    finished = pyqtSignal(object)   # PipelineResult
    errored  = pyqtSignal(str)      # error message

    def __init__(self, wav_path: str, mode: CleanupMode, parent=None):
        super().__init__(parent)
        self._wav_path = wav_path
        self._mode = mode

    def run(self) -> None:
        try:
            from vakya.core import pipeline
            result = pipeline.run(
                self._wav_path,
                mode=self._mode,
                copy_to_clipboard=False,
                write_log=True,
            )
            self.finished.emit(result)
        except Exception as exc:
            log.exception("Pipeline error")
            self.errored.emit(str(exc))
        finally:
            # Clean up temp WAV produced by WindowsAudioCapture
            try:
                os.unlink(self._wav_path)
            except OSError:
                pass


# ── Waveform widget ───────────────────────────────────────────────────────────

class WaveformWidget(QWidget):
    """Animates a simple amplitude bar during recording."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(48)
        self._level = 0.0
        self._bars: list[float] = [0.0] * 40
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        self._timer.start(50)

    def stop(self) -> None:
        self._timer.stop()
        self._level = 0.0
        self._bars = [0.0] * 40
        self.update()

    def set_level(self, level: float) -> None:
        self._level = level

    def _tick(self) -> None:
        self._bars.pop(0)
        self._bars.append(self._level)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        bar_w = w / len(self._bars)
        painter.fillRect(0, 0, w, h, QColor("#1A1A2E"))
        pen = QPen(QColor("#4A90D9"), 1)
        painter.setPen(pen)
        for i, lvl in enumerate(self._bars):
            bar_h = max(2, int(lvl * (h - 4)))
            x = int(i * bar_w)
            y = (h - bar_h) // 2
            painter.fillRect(x + 1, y, int(bar_w) - 2, bar_h, QColor("#4A90D9"))


# ── Transcript panel ──────────────────────────────────────────────────────────

class TranscriptPanel(QPlainTextEdit):
    """Scrollable read-only transcript with speaker colour-coding applied via HTML."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont("Segoe UI", 11))
        self.setStyleSheet(
            "QPlainTextEdit {"
            "  background: #12122A; color: #E8E8F0;"
            "  border: 1px solid #2A2A4A; border-radius: 6px;"
            "  padding: 8px;"
            "}"
        )
        self._speaker_colours: dict[str, str] = {}

    def set_transcript(self, text: str, speaker_ids: list[str]) -> None:
        self._speaker_colours = {
            spk: _SPEAKER_COLOURS[i % len(_SPEAKER_COLOURS)]
            for i, spk in enumerate(sorted(speaker_ids))
        }
        self.setPlainText(text)


# ── Main window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    """Traditional-mode Vakya window."""

    # Signal emitted from audio level callback (cross-thread safe)
    _level_signal = pyqtSignal(float)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Vakya — Offline Voice Intelligence")
        self.setMinimumSize(700, 520)
        self.resize(820, 600)
        self._apply_dark_theme()

        self._capture = None
        self._worker: Optional[PipelineWorker] = None
        self._recording = False

        self._level_signal.connect(self._on_level)

        self._build_ui()
        self._init_hotkey_support()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(10)
        root.setContentsMargins(16, 12, 16, 12)

        # ── Top bar: mode selector ─────────────────────────────────────────
        top = QHBoxLayout()
        top.addWidget(QLabel("Mode:"))
        self._mode_combo = QComboBox()
        for label, _ in _MODES:
            self._mode_combo.addItem(label)
        self._mode_combo.setFixedWidth(140)
        top.addWidget(self._mode_combo)
        top.addStretch()

        hotkey_hint = QLabel("Hotkey: Ctrl+Shift+Space")
        hotkey_hint.setStyleSheet("color: #666688; font-size: 11px;")
        top.addWidget(hotkey_hint)
        root.addLayout(top)

        # ── Waveform ───────────────────────────────────────────────────────
        self._waveform = WaveformWidget()
        root.addWidget(self._waveform)

        # ── Record button ──────────────────────────────────────────────────
        self._record_btn = QPushButton("● Record")
        self._record_btn.setFixedHeight(48)
        self._record_btn.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self._record_btn.setStyleSheet(self._btn_style_idle())
        self._record_btn.clicked.connect(self._toggle_recording)
        root.addWidget(self._record_btn)

        # ── Transcript panel ───────────────────────────────────────────────
        self._transcript = TranscriptPanel()
        root.addWidget(self._transcript, stretch=1)

        # ── Action bar: copy / save ────────────────────────────────────────
        action_bar = QHBoxLayout()
        action_bar.addStretch()

        self._copy_btn = QPushButton("Copy")
        self._copy_btn.setEnabled(False)
        self._copy_btn.clicked.connect(self._copy_transcript)
        action_bar.addWidget(self._copy_btn)

        self._save_btn = QPushButton("Save .txt")
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._save_transcript)
        action_bar.addWidget(self._save_btn)

        root.addLayout(action_bar)

        # ── Status bar ─────────────────────────────────────────────────────
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Ready")

    # ── Recording toggle ──────────────────────────────────────────────────────

    @pyqtSlot()
    def _toggle_recording(self) -> None:
        if self._recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        from vakya.platform.windows.audio_win import WindowsAudioCapture

        self._capture = WindowsAudioCapture()
        self._capture.set_level_callback(lambda lvl: self._level_signal.emit(lvl))
        try:
            self._capture.start()
        except Exception as exc:
            self._status.showMessage(f"Mic error: {exc}")
            log.error("Mic capture failed: %s", exc)
            return

        self._recording = True
        self._record_btn.setText("■ Stop")
        self._record_btn.setStyleSheet(self._btn_style_recording())
        self._waveform.start()
        self._transcript.setPlainText("")
        self._copy_btn.setEnabled(False)
        self._save_btn.setEnabled(False)
        self._status.showMessage("Recording…")

    def _stop_recording(self) -> None:
        self._recording = False
        self._record_btn.setEnabled(False)
        self._waveform.stop()
        self._status.showMessage("Processing…")

        self._capture.stop()
        wav_path = self._capture.get_wav_path()
        self._capture = None

        mode = _MODES[self._mode_combo.currentIndex()][1]
        self._worker = PipelineWorker(wav_path, mode, parent=self)
        self._worker.finished.connect(self._on_pipeline_done)
        self._worker.errored.connect(self._on_pipeline_error)
        self._worker.start()

    # ── Pipeline callbacks ────────────────────────────────────────────────────

    @pyqtSlot(object)
    def _on_pipeline_done(self, result) -> None:
        self._record_btn.setText("● Record")
        self._record_btn.setStyleSheet(self._btn_style_idle())
        self._record_btn.setEnabled(True)

        self._transcript.set_transcript(result.formatted_text, result.speaker_ids)
        self._copy_btn.setEnabled(True)
        self._save_btn.setEnabled(True)

        total = result.timing.get("total_sec", 0.0)
        self._status.showMessage(
            f"Done — {total:.1f}s  |  {result.stt_engine_name}  |  RAM peak {result.peak_ram_mb:.0f}MB"
        )

    @pyqtSlot(str)
    def _on_pipeline_error(self, msg: str) -> None:
        self._record_btn.setText("● Record")
        self._record_btn.setStyleSheet(self._btn_style_idle())
        self._record_btn.setEnabled(True)
        self._status.showMessage(f"Error: {msg}")
        self._transcript.setPlainText(f"[Pipeline error]\n{msg}")

    @pyqtSlot(float)
    def _on_level(self, level: float) -> None:
        self._waveform.set_level(level)

    # ── Action buttons ────────────────────────────────────────────────────────

    def _copy_transcript(self) -> None:
        text = self._transcript.toPlainText()
        QApplication.clipboard().setText(text)
        self._status.showMessage("Copied to clipboard")

    def _save_transcript(self) -> None:
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "Save transcript", "", "Text files (*.txt);;Markdown (*.md)"
        )
        if path:
            Path(path).write_text(self._transcript.toPlainText(), encoding="utf-8")
            self._status.showMessage(f"Saved to {path}")

    # ── Hotkey support ────────────────────────────────────────────────────────

    def _init_hotkey_support(self) -> None:
        """Start the overlay + hotkey thread if running on Windows."""
        if sys.platform != "win32":
            return
        try:
            from vakya.platform.windows.hotkey import HotkeyThread
            self._hotkey_thread = HotkeyThread(parent=self)
            self._hotkey_thread.activated.connect(self._on_hotkey)
            self._hotkey_thread.start()
        except Exception as exc:
            log.warning("Hotkey registration failed: %s", exc)

    @pyqtSlot()
    def _on_hotkey(self) -> None:
        """Ctrl+Shift+Space pressed — toggle overlay recording."""
        from vakya.platform.windows.overlay import OverlayWindow
        if not hasattr(self, "_overlay") or self._overlay is None:
            self._overlay = OverlayWindow(mode=_MODES[self._mode_combo.currentIndex()][1])
            self._overlay.show()
        else:
            self._overlay.toggle_recording()

    # ── Theming ───────────────────────────────────────────────────────────────

    def _apply_dark_theme(self) -> None:
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #0F0F1E;
                color: #E0E0F0;
            }
            QLabel { color: #C0C0D8; }
            QComboBox {
                background: #1A1A2E; color: #E0E0F0;
                border: 1px solid #2A2A4A; border-radius: 4px; padding: 4px 8px;
            }
            QComboBox QAbstractItemView {
                background: #1A1A2E; color: #E0E0F0; selection-background-color: #2A2A5A;
            }
            QPushButton {
                background: #1E1E3A; color: #C8C8E8;
                border: 1px solid #3A3A6A; border-radius: 6px;
                padding: 6px 16px; font-size: 12px;
            }
            QPushButton:hover  { background: #2A2A4A; }
            QPushButton:pressed { background: #333360; }
            QPushButton:disabled { color: #555570; border-color: #252540; }
            QStatusBar { color: #888898; font-size: 11px; }
        """)

    @staticmethod
    def _btn_style_idle() -> str:
        return (
            "QPushButton { background: #1E3A5F; color: #80C8FF;"
            " border: 1px solid #2A5A8F; border-radius: 8px; }"
            "QPushButton:hover { background: #254878; }"
        )

    @staticmethod
    def _btn_style_recording() -> str:
        return (
            "QPushButton { background: #5F1E1E; color: #FF8080;"
            " border: 1px solid #8F2A2A; border-radius: 8px; }"
            "QPushButton:hover { background: #782525; }"
        )

    def closeEvent(self, event) -> None:
        if self._recording and self._capture:
            try:
                self._capture.stop()
            except Exception:
                pass
        event.accept()


# ── Entry point ───────────────────────────────────────────────────────────────

def launch() -> None:
    """Launch Vakya. Shows onboarding wizard on first run, then MainWindow."""
    app = QApplication.instance() or QApplication(sys.argv)

    from vakya.platform.windows.onboarding import is_first_run, launch_onboarding

    if is_first_run():
        _wizard_ref = []  # keep reference so GC doesn't destroy it

        def _on_onboarding_done(_cfg: dict) -> None:
            win = MainWindow()
            win.show()

        wizard = launch_onboarding(_on_onboarding_done)
        _wizard_ref.append(wizard)
    else:
        win = MainWindow()
        win.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    launch()
