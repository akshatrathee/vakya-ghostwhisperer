"""Sprint 5 — First-run onboarding wizard (7 screens).

Screens:
  1. Welcome
  2. Hardware detection (auto)
  3. Language selection
  4. Mic permission + live test
  5. Model download (background thread, progress bars)
  6. HuggingFace token (optional, for diarization)
  7. Mode selection

Launched by shell.py when models/manifest.json is absent (first run).
Writes config/default.yaml with user choices on completion.
Calls OnboardingWizard.accepted() signal → shell launches MainWindow.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

import psutil
from PyQt6.QtCore import (
    QSize, Qt, QThread, QTimer, pyqtSignal, pyqtSlot,
)
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QProgressBar, QPushButton, QRadioButton,
    QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from vakya.core.llm.base import CleanupMode

log = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_RUNTIME_MANIFEST = _PROJECT_ROOT / "models" / "manifest.json"
_CONFIG_PATH = _PROJECT_ROOT / "config" / "default.yaml"
_HF_TOKEN_PATH = _PROJECT_ROOT / "config" / "hf_token.txt"

# Speaker colours reused from shell.py
_BLUE  = "#4A90D9"
_GREEN = "#27AE60"
_AMBER = "#E8A020"
_DIM   = "#888898"


# ── Download worker ───────────────────────────────────────────────────────────

class DownloadWorker(QThread):
    """Background thread that drives installer/download_models.py.

    Emits progress(model_id, bytes_done, bytes_total, status) and
    finished(success_count, fail_count).
    """

    progress = pyqtSignal(str, int, int, str)   # model_id, done, total, status
    model_done = pyqtSignal(str, bool)           # model_id, success
    finished = pyqtSignal(int, int)              # success_count, fail_count

    def __init__(self, tier: str, parent=None):
        super().__init__(parent)
        self._tier = tier
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        from vakya.installer.download_models import (
            load_model_manifest, load_runtime_manifest,
            is_model_present, download_model, save_runtime_manifest,
        )

        manifest = load_model_manifest()
        runtime = load_runtime_manifest()
        tier_order = ["bundled", "rpi", "minimum", "recommended"]
        tier_idx = tier_order.index(self._tier) if self._tier in tier_order else 99

        to_download = [
            m for m in manifest
            if m.get("tier") in tier_order
            and tier_order.index(m["tier"]) <= tier_idx
            and not is_model_present(m, runtime)
            and m.get("tier") not in ("optional_hindi", "recommended_mobile")
        ]

        success = fail = 0

        for model in to_download:
            if self._stop:
                break
            model_id = model["id"]

            def _cb(label: str, done: int, total: int, mid=model_id):
                self.progress.emit(mid, done, total, "downloading")

            ok = download_model(model, _cb)

            if ok:
                runtime.setdefault("models", {})[model_id] = {
                    "destination": model["destination"],
                    "verified": True,
                    "size_mb": model.get("size_mb"),
                }
                save_runtime_manifest(runtime)
                success += 1
            else:
                fail += 1

            self.model_done.emit(model_id, ok)

        self.finished.emit(success, fail)


# ── Shared UI helpers ─────────────────────────────────────────────────────────

def _heading(text: str, size: int = 22) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(QFont("Segoe UI", size, QFont.Weight.Bold))
    lbl.setStyleSheet(f"color: #E8E8FF;")
    lbl.setWordWrap(True)
    return lbl


def _body(text: str, size: int = 12, colour: str = "#B0B0C8") -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(QFont("Segoe UI", size))
    lbl.setStyleSheet(f"color: {colour};")
    lbl.setWordWrap(True)
    return lbl


def _btn(text: str, primary: bool = True) -> QPushButton:
    b = QPushButton(text)
    b.setFixedHeight(42)
    b.setFont(QFont("Segoe UI", 12))
    if primary:
        b.setStyleSheet(
            "QPushButton { background: #1E3A5F; color: #80C8FF;"
            " border: 1px solid #2A5A8F; border-radius: 8px; }"
            "QPushButton:hover { background: #254878; }"
            "QPushButton:disabled { color: #555570; border-color: #252540; }"
        )
    else:
        b.setStyleSheet(
            "QPushButton { background: transparent; color: #666688;"
            " border: 1px solid #333355; border-radius: 8px; }"
            "QPushButton:hover { color: #8888AA; border-color: #444466; }"
        )
    return b


def _divider() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet("color: #2A2A4A;")
    return f


# ── Individual screens ────────────────────────────────────────────────────────

class WelcomeScreen(QWidget):
    next_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setSpacing(20)
        lay.setContentsMargins(48, 60, 48, 40)

        lay.addStretch()
        lay.addWidget(_heading("Welcome to Vakya", 28))
        lay.addSpacing(8)
        lay.addWidget(_body(
            "Your voice stays on your device.\n\n"
            "Vakya transcribes and cleans up speech entirely offline — "
            "no internet, no subscription, no data leaving your machine.",
            13,
        ))
        lay.addStretch()
        lay.addWidget(_divider())

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        go = _btn("Get Started →")
        go.setFixedWidth(180)
        go.clicked.connect(self.next_requested)
        btn_row.addWidget(go)
        lay.addLayout(btn_row)


class HardwareScreen(QWidget):
    """Auto-detects RAM/CPU, shows selected tier, no user action needed."""

    next_requested = pyqtSignal()
    tier_detected  = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setSpacing(16)
        lay.setContentsMargins(48, 40, 48, 40)

        lay.addWidget(_heading("Checking your hardware"))
        self._result = _body("Detecting…", colour=_AMBER)
        lay.addWidget(self._result)

        self._detail = _body("", 11)
        lay.addWidget(self._detail)
        lay.addStretch()
        lay.addWidget(_divider())

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._ok = _btn("Looks good →")
        self._ok.setFixedWidth(180)
        self._ok.setEnabled(False)
        self._ok.clicked.connect(self.next_requested)
        btn_row.addWidget(self._ok)
        lay.addLayout(btn_row)

    def run_detection(self) -> str:
        ram_gb = psutil.virtual_memory().total / 1e9
        cpu_cores = psutil.cpu_count(logical=False) or 1

        import platform
        node = platform.node().lower()
        if "raspberrypi" in node:
            tier = "rpi"
        elif ram_gb <= 5.5:
            tier = "minimum"
        else:
            tier = "recommended"

        tier_labels = {
            "recommended": ("Recommended mode", f"{ram_gb:.0f}GB RAM · {cpu_cores} cores → full accuracy pipeline"),
            "minimum":     ("Lightweight mode",  f"{ram_gb:.0f}GB RAM → bundled model only (lower accuracy)"),
            "rpi":         ("RPi mode",          "Raspberry Pi detected → rule-based LLM, Piper TTS"),
        }
        label, detail = tier_labels.get(tier, ("Unknown", ""))

        self._result.setText(f"✓  {label}")
        self._result.setStyleSheet(f"color: {_GREEN};")
        self._detail.setText(detail)
        self._ok.setEnabled(True)
        self.tier_detected.emit(tier)
        return tier


class LanguageScreen(QWidget):
    next_requested = pyqtSignal(str)   # emits selected language code

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setSpacing(16)
        lay.setContentsMargins(48, 40, 48, 40)

        lay.addWidget(_heading("What language do you speak?"))
        lay.addWidget(_body("You can change this anytime in settings.", colour=_DIM))
        lay.addSpacing(12)

        self._radios: list[tuple[QRadioButton, str]] = []
        for label, code in [
            ("English", "en"),
            ("Hindi", "hi"),
            ("Hindi + English (mix)", "hi+en"),
        ]:
            rb = QRadioButton(label)
            rb.setFont(QFont("Segoe UI", 13))
            rb.setStyleSheet("color: #C8C8E8;")
            if code == "en":
                rb.setChecked(True)
            self._radios.append((rb, code))
            lay.addWidget(rb)

        lay.addStretch()
        lay.addWidget(_divider())

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        go = _btn("Continue →")
        go.setFixedWidth(180)
        go.clicked.connect(self._on_continue)
        btn_row.addWidget(go)
        lay.addLayout(btn_row)

    def _on_continue(self) -> None:
        for rb, code in self._radios:
            if rb.isChecked():
                self.next_requested.emit(code)
                return
        self.next_requested.emit("en")


class MicTestScreen(QWidget):
    """Records 5 seconds, transcribes with bundled model, shows result."""

    next_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setSpacing(14)
        lay.setContentsMargins(48, 40, 48, 40)

        lay.addWidget(_heading("Test your microphone"))
        lay.addWidget(_body("Say anything — we're just checking your mic works.", colour=_DIM))
        lay.addSpacing(8)

        self._waveform = _MiniWaveform()
        lay.addWidget(self._waveform)

        self._status = _body("Press Record to begin.", colour=_AMBER)
        lay.addWidget(self._status)

        self._transcript_box = QPlainTextEdit()
        self._transcript_box.setReadOnly(True)
        self._transcript_box.setMaximumHeight(80)
        self._transcript_box.setFont(QFont("Segoe UI", 11))
        self._transcript_box.setStyleSheet(
            "QPlainTextEdit { background: #12122A; color: #80FF80;"
            " border: 1px solid #2A2A4A; border-radius: 6px; padding: 6px; }"
        )
        self._transcript_box.setPlaceholderText("Your speech will appear here…")
        lay.addWidget(self._transcript_box)

        lay.addStretch()
        lay.addWidget(_divider())

        btn_row = QHBoxLayout()
        self._rec_btn = _btn("● Record (5s)")
        self._rec_btn.setFixedWidth(180)
        self._rec_btn.clicked.connect(self._start_record)
        btn_row.addWidget(self._rec_btn)
        btn_row.addStretch()
        self._next_btn = _btn("Continue →")
        self._next_btn.setFixedWidth(180)
        self._next_btn.clicked.connect(self.next_requested)
        btn_row.addWidget(self._next_btn)
        lay.addLayout(btn_row)

        self._capture = None
        self._level_signal = _LevelRelay()
        self._level_signal.level.connect(self._waveform.set_level)

    def _start_record(self) -> None:
        from vakya.platform.windows.audio_win import WindowsAudioCapture
        self._capture = WindowsAudioCapture()
        self._capture.set_level_callback(lambda lvl: self._level_signal.level.emit(lvl))
        try:
            self._capture.start()
        except Exception as exc:
            self._status.setText(f"Mic error: {exc}")
            return

        self._rec_btn.setEnabled(False)
        self._waveform.start()
        self._status.setText("Recording for 5 seconds…")
        self._status.setStyleSheet(f"color: {_AMBER};")
        QTimer.singleShot(5000, self._stop_record)

    def _stop_record(self) -> None:
        if self._capture is None:
            return
        self._waveform.stop()
        self._capture.stop()
        wav_path = self._capture.get_wav_path()
        self._capture = None
        self._status.setText("Transcribing…")
        self._try_transcribe(wav_path)

    def _try_transcribe(self, wav_path: str) -> None:
        bundled = _PROJECT_ROOT / "models" / "stt" / "whisper-base-en.bin"
        if not bundled.exists():
            self._status.setText("✓ Microphone is working. (Install bundled model to test transcription.)")
            self._status.setStyleSheet(f"color: {_GREEN};")
            self._rec_btn.setEnabled(True)
            try:
                os.unlink(wav_path)
            except OSError:
                pass
            return

        worker = _TranscribeWorker(wav_path, parent=self)
        worker.done.connect(self._on_transcribed)
        worker.start()

    @pyqtSlot(str)
    def _on_transcribed(self, text: str) -> None:
        self._transcript_box.setPlainText(text or "(nothing detected)")
        self._status.setText("✓ Microphone and transcription working!")
        self._status.setStyleSheet(f"color: {_GREEN};")
        self._rec_btn.setEnabled(True)


class _LevelRelay(QWidget):
    level = pyqtSignal(float)


class _MiniWaveform(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)
        self._bars = [0.0] * 32
        self._level = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def start(self): self._timer.start(50)
    def stop(self):
        self._timer.stop()
        self._bars = [0.0] * 32
        self._level = 0.0
        self.update()

    def set_level(self, v: float): self._level = v

    def _tick(self):
        self._bars.pop(0); self._bars.append(self._level); self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(0, 0, self.width(), self.height(), QColor("#12122A"))
        bw = self.width() / len(self._bars)
        for i, lvl in enumerate(self._bars):
            bh = max(2, int(lvl * (self.height() - 4)))
            p.fillRect(int(i * bw) + 1, (self.height() - bh) // 2, max(1, int(bw) - 2), bh, QColor(_BLUE))


class _TranscribeWorker(QThread):
    done = pyqtSignal(str)

    def __init__(self, wav_path: str, parent=None):
        super().__init__(parent)
        self._wav_path = wav_path

    def run(self):
        try:
            from vakya.core.stt.whisper_cpp import WhisperCppEngine
            engine = WhisperCppEngine()
            result = engine.transcribe(self._wav_path)
            self.done.emit(result.text)
        except Exception as exc:
            log.warning("Mic test transcription failed: %s", exc)
            self.done.emit("")
        finally:
            try:
                os.unlink(self._wav_path)
            except OSError:
                pass


class DownloadScreen(QWidget):
    """Screen 5 — model download with per-model progress bars."""

    next_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tier = "recommended"
        self._worker: Optional[DownloadWorker] = None
        self._bars: dict[str, QProgressBar] = {}
        self._labels: dict[str, QLabel] = {}

        lay = QVBoxLayout(self)
        lay.setSpacing(14)
        lay.setContentsMargins(48, 40, 48, 40)

        lay.addWidget(_heading("Downloading smarter models"))
        self._sub = _body("This runs in the background — you can skip to the app anytime.", colour=_DIM)
        lay.addWidget(self._sub)
        lay.addSpacing(8)

        self._bars_container = QVBoxLayout()
        self._bars_container.setSpacing(10)
        lay.addLayout(self._bars_container)
        lay.addStretch()
        lay.addWidget(_divider())

        btn_row = QHBoxLayout()
        self._skip_btn = _btn("Skip for now", primary=False)
        self._skip_btn.setFixedWidth(160)
        self._skip_btn.clicked.connect(self._skip)
        btn_row.addWidget(self._skip_btn)
        btn_row.addStretch()
        self._next_btn = _btn("Continue →")
        self._next_btn.setFixedWidth(160)
        self._next_btn.setEnabled(False)
        self._next_btn.clicked.connect(self.next_requested)
        btn_row.addWidget(self._next_btn)
        lay.addLayout(btn_row)

    def start_downloads(self, tier: str) -> None:
        self._tier = tier
        self._build_progress_rows(tier)

        self._worker = DownloadWorker(tier, parent=self)
        self._worker.progress.connect(self._on_progress)
        self._worker.model_done.connect(self._on_model_done)
        self._worker.finished.connect(self._on_all_done)
        self._worker.start()

    def _build_progress_rows(self, tier: str) -> None:
        from vakya.installer.download_models import load_model_manifest, load_runtime_manifest, is_model_present

        manifest = load_model_manifest()
        runtime = load_runtime_manifest()
        tier_order = ["bundled", "rpi", "minimum", "recommended"]
        tier_idx = tier_order.index(tier) if tier in tier_order else 99

        to_show = [
            m for m in manifest
            if m.get("tier") in tier_order
            and tier_order.index(m["tier"]) <= tier_idx
            and m.get("tier") not in ("optional_hindi", "recommended_mobile")
        ]

        for m in to_show:
            model_id = m["id"]
            row = QVBoxLayout()
            row.setSpacing(3)

            already = is_model_present(m, runtime)
            status_txt = "✓ Already present" if already else f"{m.get('size_mb', '?')} MB"
            lbl = _body(f"{m['name']}  —  {status_txt}", 11,
                        colour=_GREEN if already else "#C0C0D8")
            self._labels[model_id] = lbl
            row.addWidget(lbl)

            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(100 if already else 0)
            bar.setFixedHeight(8)
            bar.setTextVisible(False)
            bar.setStyleSheet(
                "QProgressBar { background: #1A1A2E; border-radius: 4px; }"
                "QProgressBar::chunk { background: #4A90D9; border-radius: 4px; }"
            )
            self._bars[model_id] = bar
            row.addWidget(bar)
            self._bars_container.addLayout(row)

    @pyqtSlot(str, int, int, str)
    def _on_progress(self, model_id: str, done: int, total: int, _status: str) -> None:
        if model_id in self._bars:
            pct = (done * 100 // total) if total else 0
            self._bars[model_id].setValue(pct)
            mb_done = done / 1_048_576
            mb_total = total / 1_048_576
            if model_id in self._labels:
                name_part = self._labels[model_id].text().split("  —  ")[0]
                self._labels[model_id].setText(f"{name_part}  —  {mb_done:.0f}/{mb_total:.0f} MB")

    @pyqtSlot(str, bool)
    def _on_model_done(self, model_id: str, success: bool) -> None:
        if model_id in self._bars:
            self._bars[model_id].setValue(100)
            colour = _GREEN if success else "#C0392B"
            self._bars[model_id].setStyleSheet(
                f"QProgressBar {{ background: #1A1A2E; border-radius: 4px; }}"
                f"QProgressBar::chunk {{ background: {colour}; border-radius: 4px; }}"
            )
            if model_id in self._labels:
                name_part = self._labels[model_id].text().split("  —  ")[0]
                self._labels[model_id].setText(f"{name_part}  —  {'✓ Done' if success else '✗ Failed'}")
                self._labels[model_id].setStyleSheet(f"color: {colour};")

    @pyqtSlot(int, int)
    def _on_all_done(self, success: int, fail: int) -> None:
        if fail == 0:
            self._sub.setText(f"All {success} model(s) downloaded successfully.")
            self._sub.setStyleSheet(f"color: {_GREEN};")
        else:
            self._sub.setText(f"{success} succeeded, {fail} failed. App will use available models.")
            self._sub.setStyleSheet(f"color: {_AMBER};")
        self._next_btn.setEnabled(True)

    def _skip(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.stop()
        self.next_requested.emit()


class HFTokenScreen(QWidget):
    """Screen 6 — optional HuggingFace token for pyannote diarization."""

    next_requested = pyqtSignal(str)  # emits token or ""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setSpacing(14)
        lay.setContentsMargins(48, 40, 48, 40)

        lay.addWidget(_heading("Speaker identification (optional)"))
        lay.addWidget(_body(
            "To label who is speaking, Vakya uses a model from HuggingFace "
            "that requires a free account token.\n\n"
            "Your token is stored only on this device — never transmitted.",
        ))
        lay.addSpacing(8)

        self._token_input = QLineEdit()
        self._token_input.setPlaceholderText("hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxx")
        self._token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._token_input.setFont(QFont("Consolas", 11))
        self._token_input.setStyleSheet(
            "QLineEdit { background: #12122A; color: #E0E0F0;"
            " border: 1px solid #2A2A4A; border-radius: 6px; padding: 6px 10px; }"
        )
        lay.addWidget(self._token_input)

        lay.addWidget(_body("Get a free token at huggingface.co/settings/tokens", 10, _DIM))
        lay.addStretch()
        lay.addWidget(_divider())

        btn_row = QHBoxLayout()
        skip = _btn("Skip speaker ID", primary=False)
        skip.setFixedWidth(180)
        skip.clicked.connect(lambda: self.next_requested.emit(""))
        btn_row.addWidget(skip)
        btn_row.addStretch()
        save = _btn("Save token →")
        save.setFixedWidth(180)
        save.clicked.connect(self._save)
        btn_row.addWidget(save)
        lay.addLayout(btn_row)

    def _save(self) -> None:
        token = self._token_input.text().strip()
        if token:
            _HF_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
            _HF_TOKEN_PATH.write_text(token, encoding="utf-8")
            os.environ["HF_TOKEN"] = token
            log.info("HF token saved")
        self.next_requested.emit(token)


class ModeSelectScreen(QWidget):
    """Screen 7 — pick default output mode."""

    next_requested = pyqtSignal(str)  # emits mode value string

    _MODES = [
        ("Dictation",    "dictation",  "Cleans up filler words. Good for notes, emails, messages."),
        ("Notes",        "notes",      "Converts speech into structured bullet points."),
        ("Farm Log",     "farm_log",   "Preserves field terms. Adds date/time stamps."),
        ("Meeting Notes","meeting",    "Labels speakers. Highlights action items."),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setSpacing(14)
        lay.setContentsMargins(48, 40, 48, 40)

        lay.addWidget(_heading("How will you use Vakya?"))
        lay.addWidget(_body("Sets your default output style. Change anytime in settings.", colour=_DIM))
        lay.addSpacing(12)

        self._radios: list[tuple[QRadioButton, str]] = []
        for label, val, desc in self._MODES:
            row = QVBoxLayout()
            row.setSpacing(2)
            rb = QRadioButton(label)
            rb.setFont(QFont("Segoe UI", 13))
            rb.setStyleSheet("color: #C8C8E8;")
            if val == "dictation":
                rb.setChecked(True)
            self._radios.append((rb, val))
            row.addWidget(rb)
            desc_lbl = _body(f"    {desc}", 10, _DIM)
            row.addWidget(desc_lbl)
            lay.addLayout(row)

        lay.addStretch()
        lay.addWidget(_divider())

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        go = _btn("Start using Vakya →")
        go.setFixedWidth(220)
        go.clicked.connect(self._on_done)
        btn_row.addWidget(go)
        lay.addLayout(btn_row)

    def _on_done(self) -> None:
        for rb, val in self._radios:
            if rb.isChecked():
                self.next_requested.emit(val)
                return
        self.next_requested.emit("dictation")


# ── Wizard container ──────────────────────────────────────────────────────────

class OnboardingWizard(QWidget):
    """Hosts all 7 screens in a QStackedWidget. Emits `accepted` when done."""

    accepted = pyqtSignal(dict)   # emits {"tier": ..., "language": ..., "mode": ...}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Vakya — Setup")
        self.setMinimumSize(640, 480)
        self.resize(700, 520)
        self._apply_theme()

        self._cfg: dict = {}

        self._stack = QStackedWidget()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        # Progress indicator dots
        self._dot_bar = _DotBar(7)
        root.addWidget(self._dot_bar)
        root.addWidget(self._stack)

        # Build screens
        self._s1 = WelcomeScreen()
        self._s2 = HardwareScreen()
        self._s3 = LanguageScreen()
        self._s4 = MicTestScreen()
        self._s5 = DownloadScreen()
        self._s6 = HFTokenScreen()
        self._s7 = ModeSelectScreen()

        for s in [self._s1, self._s2, self._s3, self._s4, self._s5, self._s6, self._s7]:
            self._stack.addWidget(s)

        # Wire signals
        self._s1.next_requested.connect(self._go_hardware)
        self._s2.next_requested.connect(self._go_language)
        self._s3.next_requested.connect(self._go_mic)
        self._s4.next_requested.connect(self._go_download)
        self._s5.next_requested.connect(self._go_hftoken)
        self._s6.next_requested.connect(self._go_mode)
        self._s7.next_requested.connect(self._finish)

        self._stack.setCurrentIndex(0)

    # ── Navigation ────────────────────────────────────────────────────────────

    def _go_hardware(self) -> None:
        self._stack.setCurrentIndex(1)
        self._dot_bar.set_active(1)
        tier = self._s2.run_detection()
        self._cfg["tier"] = tier

    def _go_language(self) -> None:
        self._stack.setCurrentIndex(2)
        self._dot_bar.set_active(2)

    @pyqtSlot(str)
    def _go_mic(self, language: str) -> None:
        self._cfg["language"] = language
        self._stack.setCurrentIndex(3)
        self._dot_bar.set_active(3)

    def _go_download(self) -> None:
        self._stack.setCurrentIndex(4)
        self._dot_bar.set_active(4)
        self._s5.start_downloads(self._cfg.get("tier", "recommended"))

    def _go_hftoken(self) -> None:
        self._stack.setCurrentIndex(5)
        self._dot_bar.set_active(5)

    @pyqtSlot(str)
    def _go_mode(self, token: str) -> None:
        self._cfg["hf_token"] = token
        self._stack.setCurrentIndex(6)
        self._dot_bar.set_active(6)

    @pyqtSlot(str)
    def _finish(self, mode: str) -> None:
        self._cfg["mode"] = mode
        _write_config(self._cfg)
        self.accepted.emit(self._cfg)
        self.close()

    def _apply_theme(self) -> None:
        self.setStyleSheet("""
            QWidget { background: #0F0F1E; color: #E0E0F0; }
            QRadioButton::indicator { width: 16px; height: 16px; }
            QRadioButton::indicator:checked { background: #4A90D9; border-radius: 8px; border: 2px solid #80C8FF; }
            QRadioButton::indicator:unchecked { background: #1A1A2E; border-radius: 8px; border: 2px solid #2A2A4A; }
        """)


class _DotBar(QWidget):
    """Seven small dots showing wizard progress."""

    def __init__(self, count: int, parent=None):
        super().__init__(parent)
        self._count = count
        self._active = 0
        self.setFixedHeight(20)

    def set_active(self, idx: int) -> None:
        self._active = idx
        self.update()

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = 5
        spacing = 18
        total_w = self._count * spacing
        x0 = (self.width() - total_w) // 2
        y = self.height() // 2
        for i in range(self._count):
            x = x0 + i * spacing + r
            colour = QColor(_BLUE) if i == self._active else QColor("#2A2A4A")
            p.setBrush(colour)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(x - r, y - r, r * 2, r * 2)


# ── Config writer ─────────────────────────────────────────────────────────────

def _write_config(cfg: dict) -> None:
    """Persist user choices to config/default.yaml."""
    import yaml

    lang = cfg.get("language", "en")
    # Normalise "hi+en" to "hi" for primary lang setting
    primary_lang = "hi" if "hi" in lang else lang

    updates = {
        "hardware_tier": cfg.get("tier", "auto"),
        "stt": {"language": primary_lang},
        "onboarding_complete": True,
        "default_mode": cfg.get("mode", "dictation"),
    }

    existing: dict = {}
    if _CONFIG_PATH.exists():
        try:
            existing = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
        except Exception:
            pass

    existing.update(updates)
    _CONFIG_PATH.write_text(yaml.dump(existing, allow_unicode=True), encoding="utf-8")
    log.info("Onboarding config written to %s", _CONFIG_PATH)


# ── First-run detection ───────────────────────────────────────────────────────

def is_first_run() -> bool:
    """True if no models/manifest.json exists OR onboarding_complete not set."""
    if not _RUNTIME_MANIFEST.exists():
        return True
    try:
        import yaml
        cfg = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) if _CONFIG_PATH.exists() else {}
        return not (cfg or {}).get("onboarding_complete", False)
    except Exception:
        return True


def launch_onboarding(on_complete) -> OnboardingWizard:
    """Create and show the wizard. Calls on_complete(cfg_dict) when done."""
    wizard = OnboardingWizard()
    wizard.accepted.connect(on_complete)
    wizard.show()
    return wizard
