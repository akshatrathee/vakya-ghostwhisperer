"""First-run model downloader.

Reads installer/model_manifest.yaml, downloads missing models with:
- Resumable downloads (Content-Range)
- SHA256 checksum verification (where provided)
- Progress reporting via callback
- Updates models/manifest.json after each successful download

Usage:
    python -m vakya.installer.download_models
    python -m vakya.installer.download_models --tier recommended
    python -m vakya.installer.download_models --id phi3_mini_q4
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import urllib.request
from pathlib import Path
from typing import Callable, Optional

import yaml

log = logging.getLogger(__name__)

_MANIFEST_YAML = Path(__file__).parent / "model_manifest.yaml"
_RUNTIME_MANIFEST = Path(__file__).parent.parent / "models" / "manifest.json"
_PROJECT_ROOT = Path(__file__).parent.parent


def load_model_manifest() -> list[dict]:
    return yaml.safe_load(_MANIFEST_YAML.read_text(encoding="utf-8"))["models"]


def load_runtime_manifest() -> dict:
    if not _RUNTIME_MANIFEST.exists():
        return {"models": {}}
    try:
        return json.loads(_RUNTIME_MANIFEST.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"models": {}}


def save_runtime_manifest(data: dict) -> None:
    _RUNTIME_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    _RUNTIME_MANIFEST.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def is_model_present(model: dict, runtime: dict) -> bool:
    dest = _PROJECT_ROOT / model["destination"]
    if not dest.exists():
        return False
    model_id = model["id"]
    if model_id in runtime.get("models", {}):
        entry = runtime["models"][model_id]
        if entry.get("verified"):
            return True
    return False


def download_model(
    model: dict,
    progress_cb: Optional[Callable[[str, int, int], None]] = None,
    force: bool = False,
) -> bool:
    """Download a single model. Returns True on success."""
    dest = _PROJECT_ROOT / model["destination"]
    url = model["url"]
    model_id = model["id"]

    if dest.is_dir():
        # Directory model (e.g. faster-whisper) — download all listed files
        return _download_directory_model(model, progress_cb, force)

    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists() and not force:
        if _verify_checksum(dest, model.get("sha256")):
            log.info("%s: already present and verified", model_id)
            return True
        log.warning("%s: checksum mismatch — re-downloading", model_id)

    log.info("Downloading %s from %s", model["name"], url)
    try:
        _download_file(url, dest, model["name"], progress_cb)
    except Exception as exc:
        log.error("Download failed for %s: %s", model_id, exc)
        return False

    if not _verify_checksum(dest, model.get("sha256")):
        log.error("%s: checksum verification failed after download", model_id)
        return False

    return True


def _download_directory_model(
    model: dict,
    progress_cb: Optional[Callable],
    force: bool,
) -> bool:
    dest_dir = _PROJECT_ROOT / model["destination"]
    dest_dir.mkdir(parents=True, exist_ok=True)
    base_url = model["url"].rstrip("/")
    files = model.get("files", [])

    for filename in files:
        file_url = f"{base_url}/{filename}"
        file_dest = dest_dir / filename
        if file_dest.exists() and not force:
            continue
        log.info("  Downloading %s/%s", model["id"], filename)
        try:
            _download_file(file_url, file_dest, f"{model['name']}/{filename}", progress_cb)
        except Exception as exc:
            log.error("Failed to download %s: %s", filename, exc)
            return False

    return True


def _download_file(
    url: str,
    dest: Path,
    label: str,
    progress_cb: Optional[Callable[[str, int, int], None]],
) -> None:
    resume_pos = dest.stat().st_size if dest.exists() else 0
    headers = {}
    if resume_pos:
        headers["Range"] = f"bytes={resume_pos}-"
        log.debug("Resuming %s from byte %d", label, resume_pos)

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length", 0)) + resume_pos
        mode = "ab" if resume_pos else "wb"
        downloaded = resume_pos

        with open(dest, mode) as f:
            chunk_size = 65536
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if progress_cb:
                    progress_cb(label, downloaded, total)


def _verify_checksum(path: Path, expected_sha256: Optional[str]) -> bool:
    if not expected_sha256:
        return True
    if path.is_dir():
        return True
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    actual = sha.hexdigest()
    if actual != expected_sha256:
        log.error("SHA256 mismatch: expected %s, got %s", expected_sha256, actual)
        return False
    return True


def download_for_tier(
    tier: str,
    progress_cb: Optional[Callable] = None,
    force: bool = False,
) -> None:
    """Download all models required for a given hardware tier."""
    manifest = load_model_manifest()
    runtime = load_runtime_manifest()

    tier_order = ["bundled", "rpi", "minimum", "recommended"]
    tier_idx = tier_order.index(tier) if tier in tier_order else len(tier_order)

    to_download = [
        m for m in manifest
        if tier_order.index(m["tier"]) <= tier_idx
        if not is_model_present(m, runtime) or force
        if m["tier"] not in ("optional_hindi", "recommended_mobile")
    ]

    log.info("Downloading %d model(s) for tier=%s", len(to_download), tier)

    for model in to_download:
        ok = download_model(model, progress_cb, force)
        if ok:
            runtime.setdefault("models", {})[model["id"]] = {
                "destination": model["destination"],
                "verified": True,
                "size_mb": model.get("size_mb"),
            }
            save_runtime_manifest(runtime)
            log.info("✓ %s", model["name"])
        else:
            log.error("✗ %s — download failed", model["name"])


def _cli_progress(label: str, downloaded: int, total: int) -> None:
    if total:
        pct = downloaded * 100 // total
        bar = "#" * (pct // 5) + "-" * (20 - pct // 5)
        print(f"\r  [{bar}] {pct:3d}%  {label}", end="", flush=True)
    else:
        print(f"\r  {downloaded // 1024}KB  {label}", end="", flush=True)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Vakya model downloader")
    parser.add_argument("--tier", default="recommended",
                        choices=["bundled", "rpi", "minimum", "recommended"],
                        help="Hardware tier to download for")
    parser.add_argument("--id", help="Download a specific model by ID")
    parser.add_argument("--force", action="store_true", help="Re-download even if present")
    args = parser.parse_args()

    if args.id:
        manifest = load_model_manifest()
        model = next((m for m in manifest if m["id"] == args.id), None)
        if model is None:
            print(f"Unknown model ID: {args.id}")
            sys.exit(1)
        ok = download_model(model, _cli_progress, args.force)
        print()
        sys.exit(0 if ok else 1)

    download_for_tier(args.tier, _cli_progress, args.force)
    print()


if __name__ == "__main__":
    main()
