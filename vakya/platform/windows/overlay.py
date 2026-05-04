"""Wispr-mode floating overlay — 280×80px, bottom-right, always-on-top, frameless.

States:
  idle       — hidden (window not visible)
  recording  — blue waveform animation + "Recording…" label
  processing — spinner animation + "Processing…" label
  done       — green tick + brief text preview, auto-dismiss after 2s

Output: pastes transcript into the previously active window via clipboard.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from enum import Enum, auto
from typing import Optional

from PyQt6.QtCore import (
    QEasingCurve, QPoint, QPropertyAnimation, QRect, QSize,
    Qt, QThread, QTimer, pyqtSignal, pyqtSlot,
)
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from vakya.core.llm.base import CleanupMode
from vakya.platform.windows.audio_win import WindowsAudioCapture

log = logging.getLogger(__name__)

_W, _H = 280, 80
_MARGIN = 18  # pixels from screen edge


class _State(Enum):
    IDLE       = auto()
    RECORDING  = auto()
    PROCESSING = auto()
    DONE       = auto()


class _PipelineWorker(QThread):
    finished = pyqtSignal(object)
    errored  = pyqtSignal(str)

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
            log.exception("Overlay pipeline error")
            self.errored.emit(str(exc))
        finally:
            try:
                os.unlink(self._wav_path)
            except OSError:
                pass


class OverlayWindow(QWidget):
    """Frameless always-on-top overlay for Wispr dictation mode."""

    # Cross-thread level signal
    _level_signal = pyqtSignal(float)

    def __init__(self, mode: CleanupMode = CleanupMode.DICTATION, parent=None):
        super().__init__(
            parent,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,  # no taskbar entry
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(_W, _H)

        self._mode = mode
        self._state = _State.IDLE
        self._level = 0.0
        self._bars: list[float] = [0.0] * 28
        self._capture: Optional[WindowsAudioCapture] = None
        self._worker: Optional[_PipelineWorker] = None
        self._preview_text = ""

        self._level_signal.connect(self._on_level)

        # Waveform animation timer
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick_anim)

        # Spinner angle
        self._spinner_angle = 0
        self._spinner_timer = QTimer(self)
        self._spinner_timer.timeout.connect(self._tick_spinner)

        # Auto-dismiss timer after done
        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self.hide)

        self._position_bottom_right()

    # ── Public API ────────────────────────────────────────────────────────────

    def toggle_recording(self) -> None:
        if self._state == _State.IDLE:
            self._start_recording()
        elif self._state == _State.RECORDING:
            self._stop_recording()
        # In processing/done — ignore hotkey

    def show(self) -> None:
        super().show()
        self._start_recording()

    # ── Recording ─────────────────────────────────────────────────────────────

    def _start_recording(self) -> None:
        self._capture = WindowsAudioCapture()
        self._capture.set_level_callback(lambda lvl: self._level_signal.emit(lvl))
        try:
            self._capture.start()
        except Exception as exc:
            log.error("Overlay mic error: %s", exc)
            self._set_state(_State.DONE)
            self._preview_text = f"Mic error: {exc}"
            self.update()
            self._dismiss_timer.start(3000)
            return

        self._set_state(_State.RECORDING)

    def _stop_recording(self) -> None:
        if self._capture is None:
            return
        self._capture.stop()
        wav_path = self._capture.get_wav_path()
        self._capture = None

        self._set_state(_State.PROCESSING)

        self._worker = _PipelineWorker(wav_path, self._mode, parent=self)
        self._worker.finished.connect(self._on_done)
        self._worker.errored.connect(self._on_error)
        self._worker.start()

    # ── Pipeline callbacks ────────────────────────────────────────────────────

    @pyqtSlot(object)
    def _on_done(self, result) -> None:
        text = result.formatted_text
        self._paste_to_active_window(text)
        self._preview_text = text[:60] + ("…" if len(text) > 60 else "")
        self._set_state(_State.DONE)
        self._dismiss_timer.start(2000)

    @pyqtSlot(str)
    def _on_error(self, msg: str) -> None:
        self._preview_text = f"Error: {msg[:50]}"
        self._set_state(_State.DONE)
        self._dismiss_timer.start(3000)

    @pyqtSlot(float)
    def _on_level(self, level: float) -> None:
        self._level = level

    # ── Paste ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _paste_to_active_window(text: str) -> None:
        """Copy text to clipboard then send Ctrl+V to the previously focused window."""
        QApplication.clipboard().setText(text)
        # Small delay to let the clipboard settle
        import time
        time.sleep(0.08)
        try:
            import win32api
            import win32con
            win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
            win32api.keybd_event(ord("V"), 0, 0, 0)
            win32api.keybd_event(ord("V"), 0, win32con.KEYEVENTF_KEYUP, 0)
            win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
        except ImportError:
            log.warning("pywin32 not available — text is in clipboard, paste manually")

    # ── State machine ─────────────────────────────────────────────────────────

    def _set_state(self, state: _State) -> None:
        self._state = state
        self._anim_timer.stop()
        self._spinner_timer.stop()

        if state == _State.RECORDING:
            self._bars = [0.0] * 28
            self._anim_timer.start(50)
        elif state == _State.PROCESSING:
            self._spinner_angle = 0
            self._spinner_timer.start(30)
        elif state == _State.DONE:
            pass
        elif state == _State.IDLE:
            self.hide()
            return

        self.show()
        self.update()

    # ── Animation ticks ───────────────────────────────────────────────────────

    def _tick_anim(self) -> None:
        self._bars.pop(0)
        self._bars.append(self._level)
        self.update()

    def _tick_spinner(self) -> None:
        self._spinner_angle = (self._spinner_angle + 12) % 360
        self.update()

    # ── Painting ──────────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background pill
        bg = QColor(20, 20, 40, 230)
        p.setBrush(bg)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, _W, _H, 12, 12)

        if self._state == _State.RECORDING:
            self._draw_waveform(p)
            self._draw_label(p, "Recording…", "#4A90D9")

        elif self._state == _State.PROCESSING:
            self._draw_spinner(p)
            self._draw_label(p, "Processing…", "#E8A020")

        elif self._state == _State.DONE:
            self._draw_checkmark(p)
            self._draw_label(p, self._preview_text or "Done", "#27AE60", small=True)

    def _draw_waveform(self, p: QPainter) -> None:
        bar_w = (_W - 32) / len(self._bars)
        y_center = _H // 2 - 4
        for i, lvl in enumerate(self._bars):
            bar_h = max(2, int(lvl * 28))
            x = 16 + int(i * bar_w)
            p.fillRect(x, y_center - bar_h // 2, max(1, int(bar_w) - 1), bar_h, QColor("#4A90D9"))

    def _draw_spinner(self, p: QPainter) -> None:
        cx, cy, r = 24, _H // 2, 12
        pen = QPen(QColor("#E8A020"), 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(cx - r, cy - r, r * 2, r * 2, self._spinner_angle * 16, 270 * 16)

    def _draw_checkmark(self, p: QPainter) -> None:
        pen = QPen(QColor("#27AE60"), 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawLine(12, _H // 2, 20, _H // 2 + 8)
        p.drawLine(20, _H // 2 + 8, 32, _H // 2 - 6)

    def _draw_label(self, p: QPainter, text: str, colour: str, small: bool = False) -> None:
        p.setPen(QColor(colour))
        font = QFont("Segoe UI", 9 if small else 11)
        p.setFont(font)
        rect = QRect(44, 0, _W - 52, _H)
        p.drawText(rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)

    # ── Positioning ───────────────────────────────────────────────────────────

    def _position_bottom_right(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.right() - _W - _MARGIN
        y = geo.bottom() - _H - _MARGIN
        self.move(x, y)
