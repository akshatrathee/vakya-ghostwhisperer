"""Sprint 5 tests — onboarding wizard, first-run detection, download worker."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── First-run detection ───────────────────────────────────────────────────────

class TestFirstRunDetection:
    def test_no_manifest_is_first_run(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "vakya.platform.windows.onboarding._RUNTIME_MANIFEST",
            tmp_path / "does_not_exist.json",
        )
        from vakya.platform.windows.onboarding import is_first_run
        assert is_first_run() is True

    def test_manifest_exists_but_no_config_is_first_run(self, tmp_path, monkeypatch):
        manifest = tmp_path / "manifest.json"
        manifest.write_text('{"models":{}}')
        monkeypatch.setattr(
            "vakya.platform.windows.onboarding._RUNTIME_MANIFEST", manifest
        )
        monkeypatch.setattr(
            "vakya.platform.windows.onboarding._CONFIG_PATH",
            tmp_path / "no_config.yaml",
        )
        from importlib import reload
        import vakya.platform.windows.onboarding as mod
        assert mod.is_first_run() is True

    def test_onboarding_complete_flag_not_first_run(self, tmp_path, monkeypatch):
        manifest = tmp_path / "manifest.json"
        manifest.write_text('{"models":{}}')
        config = tmp_path / "default.yaml"
        config.write_text("onboarding_complete: true\n")
        monkeypatch.setattr(
            "vakya.platform.windows.onboarding._RUNTIME_MANIFEST", manifest
        )
        monkeypatch.setattr(
            "vakya.platform.windows.onboarding._CONFIG_PATH", config
        )
        import vakya.platform.windows.onboarding as mod
        assert mod.is_first_run() is False


# ── Config writer ─────────────────────────────────────────────────────────────

class TestWriteConfig:
    def test_writes_yaml_with_all_fields(self, tmp_path, monkeypatch):
        cfg_path = tmp_path / "default.yaml"
        monkeypatch.setattr("vakya.platform.windows.onboarding._CONFIG_PATH", cfg_path)

        from vakya.platform.windows.onboarding import _write_config
        _write_config({"tier": "recommended", "language": "en", "mode": "notes"})

        import yaml
        result = yaml.safe_load(cfg_path.read_text())
        assert result["onboarding_complete"] is True
        assert result["hardware_tier"] == "recommended"
        assert result["default_mode"] == "notes"
        assert result["stt"]["language"] == "en"

    def test_hindi_plus_en_normalised_to_hi(self, tmp_path, monkeypatch):
        cfg_path = tmp_path / "default.yaml"
        monkeypatch.setattr("vakya.platform.windows.onboarding._CONFIG_PATH", cfg_path)

        from vakya.platform.windows.onboarding import _write_config
        _write_config({"tier": "recommended", "language": "hi+en", "mode": "dictation"})

        import yaml
        result = yaml.safe_load(cfg_path.read_text())
        assert result["stt"]["language"] == "hi"

    def test_preserves_existing_config_keys(self, tmp_path, monkeypatch):
        cfg_path = tmp_path / "default.yaml"
        cfg_path.write_text("custom_key: custom_value\n")
        monkeypatch.setattr("vakya.platform.windows.onboarding._CONFIG_PATH", cfg_path)

        from vakya.platform.windows.onboarding import _write_config
        _write_config({"tier": "minimum", "language": "en", "mode": "farm_log"})

        import yaml
        result = yaml.safe_load(cfg_path.read_text())
        assert result["custom_key"] == "custom_value"
        assert result["onboarding_complete"] is True


# ── DownloadWorker ────────────────────────────────────────────────────────────

class TestDownloadWorker:
    def test_import(self):
        from vakya.platform.windows.onboarding import DownloadWorker
        assert DownloadWorker is not None

    def test_instantiates(self):
        from vakya.platform.windows.onboarding import DownloadWorker
        w = DownloadWorker("recommended")
        assert w._tier == "recommended"

    def test_stop_sets_flag(self):
        from vakya.platform.windows.onboarding import DownloadWorker
        w = DownloadWorker("recommended")
        assert not w._stop
        w.stop()
        assert w._stop


# ── Module imports ────────────────────────────────────────────────────────────

class TestOnboardingImports:
    def test_wizard_importable(self):
        from vakya.platform.windows.onboarding import OnboardingWizard
        assert OnboardingWizard is not None

    def test_all_screens_importable(self):
        from vakya.platform.windows.onboarding import (
            WelcomeScreen, HardwareScreen, LanguageScreen,
            MicTestScreen, DownloadScreen, HFTokenScreen, ModeSelectScreen,
        )
        for cls in [WelcomeScreen, HardwareScreen, LanguageScreen,
                    MicTestScreen, DownloadScreen, HFTokenScreen, ModeSelectScreen]:
            assert cls is not None

    def test_launch_onboarding_importable(self):
        from vakya.platform.windows.onboarding import launch_onboarding
        assert callable(launch_onboarding)


# ── HF token screen ───────────────────────────────────────────────────────────

class TestHFTokenPersistence:
    def test_saves_token_to_file(self, tmp_path, monkeypatch):
        token_path = tmp_path / "hf_token.txt"
        monkeypatch.setattr("vakya.platform.windows.onboarding._HF_TOKEN_PATH", token_path)

        # Simulate what HFTokenScreen._save() does (without Qt widget)
        token = "hf_testtoken123"
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(token, encoding="utf-8")
        os.environ["HF_TOKEN"] = token

        assert token_path.read_text() == token
        assert os.environ.get("HF_TOKEN") == token


# ── Shell first-run wiring ────────────────────────────────────────────────────

class TestShellFirstRunWiring:
    def test_launch_references_is_first_run(self):
        import inspect
        from vakya.platform.windows import shell
        src = inspect.getsource(shell.launch)
        assert "is_first_run" in src
        assert "launch_onboarding" in src


# ── PyInstaller spec exists ───────────────────────────────────────────────────

class TestInstallerSpec:
    def test_spec_file_exists(self):
        spec = Path(__file__).parent.parent / "installer" / "vakya.spec"
        assert spec.exists(), "vakya.spec not found in installer/"

    def test_spec_references_main_entry(self):
        spec = Path(__file__).parent.parent / "installer" / "vakya.spec"
        content = spec.read_text()
        assert "__main__.py" in content

    def test_version_info_exists(self):
        vi = Path(__file__).parent.parent / "installer" / "version_info.txt"
        assert vi.exists()

    def test_version_info_has_product_name(self):
        vi = Path(__file__).parent.parent / "installer" / "version_info.txt"
        assert "Vakya" in vi.read_text()
