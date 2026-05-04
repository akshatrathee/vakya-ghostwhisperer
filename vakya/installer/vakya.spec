# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for Vakya — Windows one-folder build
#
# Build:
#   pip install pyinstaller
#   pyinstaller vakya/installer/vakya.spec
#
# Output: dist/Vakya/  (one-folder, not one-file — faster cold start)
#
# The bundled whisper-base-en.bin ships inside the installer.
# All other models are downloaded by the onboarding wizard at first run.

import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent          # vakya/
PROJECT = ROOT.parent                 # Ghost Whisperer/

a = Analysis(
    [str(ROOT / "__main__.py")],
    pathex=[str(PROJECT)],
    binaries=[],
    datas=[
        # Bundled STT model (ships in installer — required from second 1)
        (str(ROOT / "models" / "stt" / "whisper-base-en.bin"),
         "models/stt"),

        # Config and manifest
        (str(ROOT / "config" / "default.yaml"),     "config"),
        (str(ROOT / "config" / "hardware_profiles.yaml"), "config"),
        (str(ROOT / "installer" / "model_manifest.yaml"), "installer"),

        # Schemas
        (str(ROOT / "schemas"), "schemas"),
    ],
    hiddenimports=[
        # PyQt6 platform plugins needed on Windows
        "PyQt6.sip",
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        # sounddevice pulls in CFFI + numpy
        "sounddevice",
        "numpy",
        "cffi",
        # pywin32
        "win32api",
        "win32con",
        # vakya platform modules (not auto-discovered)
        "vakya.platform.windows.shell",
        "vakya.platform.windows.onboarding",
        "vakya.platform.windows.audio_win",
        "vakya.platform.windows.hotkey",
        "vakya.platform.windows.overlay",
        # Core pipeline
        "vakya.core.pipeline",
        "vakya.core.vad",
        "vakya.core.stt.whisper_cpp",
        "vakya.core.stt.faster_whisper",
        "vakya.core.llm.phi3_mini",
        "vakya.core.llm.chunker",
        "vakya.core.tts.engine_factory",
        "vakya.core.tts.kokoro",
        "vakya.core.output.router",
        "vakya.core.output.formatter",
        "vakya.core.voice_profile.store",
        "vakya.core.vocab.store",
        "vakya.installer.download_models",
        # yaml / psutil
        "yaml",
        "psutil",
        "pyperclip",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Never needed — keeps build small
        "tkinter",
        "matplotlib",
        "IPython",
        "jupyter",
        "scipy",
        "sklearn",
        "pandas",
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Vakya",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # no terminal window
    disable_windowed_traceback=False,
    # icon="vakya/installer/vakya.ico",   # uncomment when icon is ready
    version="vakya/installer/version_info.txt",  # Windows VERSIONINFO resource
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Vakya",
)
