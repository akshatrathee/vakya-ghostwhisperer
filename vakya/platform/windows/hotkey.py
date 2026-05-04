"""Win32 global hotkey registration — Ctrl+Shift+Space.

Runs in a background QThread so the Win32 message pump doesn't block Qt.
Emits `activated` signal when the hotkey fires.

The hotkey is configurable via vakya/config/default.yaml:
  hotkey:
    modifiers: ctrl+shift   # ctrl, shift, alt (any combination)
    key: space
"""

from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes

from PyQt6.QtCore import QThread, pyqtSignal

log = logging.getLogger(__name__)

# Win32 modifier constants
MOD_ALT     = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT   = 0x0004
MOD_WIN     = 0x0008
MOD_NOREPEAT = 0x4000

# Virtual key codes
VK_SPACE = 0x20

_HOTKEY_ID = 0x4B47  # arbitrary unique ID in user-defined range

user32 = ctypes.windll.user32


def _parse_modifiers(mod_str: str) -> int:
    flags = MOD_NOREPEAT
    for part in mod_str.lower().split("+"):
        part = part.strip()
        if part == "ctrl":
            flags |= MOD_CONTROL
        elif part == "shift":
            flags |= MOD_SHIFT
        elif part == "alt":
            flags |= MOD_ALT
        elif part == "win":
            flags |= MOD_WIN
    return flags


def _parse_vk(key_str: str) -> int:
    key_str = key_str.lower().strip()
    if key_str == "space":
        return VK_SPACE
    if len(key_str) == 1:
        return ord(key_str.upper())
    raise ValueError(f"Unsupported hotkey key: {key_str!r}")


class HotkeyThread(QThread):
    """Background thread that owns the Win32 hotkey and message pump.

    Emits `activated` on the Qt event loop when the hotkey fires.
    Cleans up the hotkey registration when the thread stops.
    """

    activated = pyqtSignal()

    def __init__(self, modifiers: str = "ctrl+shift", key: str = "space", parent=None):
        super().__init__(parent)
        self._mod_flags = _parse_modifiers(modifiers)
        self._vk = _parse_vk(key)
        self._registered = False

    def run(self) -> None:
        ok = user32.RegisterHotKey(None, _HOTKEY_ID, self._mod_flags, self._vk)
        if not ok:
            err = ctypes.get_last_error()
            log.error("RegisterHotKey failed (error %d) — hotkey will not work", err)
            return

        self._registered = True
        log.info(
            "Global hotkey registered (id=%#x, mods=%#x, vk=%#x)",
            _HOTKEY_ID, self._mod_flags, self._vk,
        )

        msg = wintypes.MSG()
        # Pump Win32 messages until the thread is asked to stop
        while not self.isInterruptionRequested():
            # PeekMessage with PM_REMOVE, timeout via a short sleep equivalent
            ret = user32.PeekMessageW(
                ctypes.byref(msg), None, 0, 0, 0x0001  # PM_REMOVE
            )
            if ret:
                if msg.message == 0x0312:  # WM_HOTKEY
                    if msg.wParam == _HOTKEY_ID:
                        log.debug("Hotkey activated")
                        self.activated.emit()
            else:
                # No message — yield a bit to avoid 100% CPU spin
                self.msleep(20)

        self._cleanup()

    def stop_hotkey(self) -> None:
        self.requestInterruption()
        self.wait(2000)

    def _cleanup(self) -> None:
        if self._registered:
            user32.UnregisterHotKey(None, _HOTKEY_ID)
            self._registered = False
            log.info("Global hotkey unregistered")
