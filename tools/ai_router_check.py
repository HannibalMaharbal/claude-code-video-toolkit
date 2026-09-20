#!/usr/bin/env python3
"""Read-only internal-only backend readiness check.

Pings every local backend named in ``contracts/task-routing.json`` and proves
that cloud backends stay blocked while ``contracts/egress-policy.json`` is in
``internal_only`` mode. Never installs anything and never performs real
network I/O.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.egress_guard import EgressBlocked, require_egress

REPO_ROOT = Path(__file__).resolve().parents[1]
KOKORO_CACHE = Path.home() / ".cache" / "kokoro-onnx"
MLX_WHISPER_BIN = REPO_ROOT / ".venv" / "bin" / "mlx_whisper"
REMOTION_BIN = REPO_ROOT / "node_modules" / ".bin" / "remotion"


def _run_ok(command: list[str], *, timeout: int = 20) -> bool:
    try:
        subprocess.run(
            command, check=True, capture_output=True, text=True, timeout=timeout
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False
    return True


def _check_ollama() -> bool:
    if shutil.which("ollama") is None:
        return False
    return _run_ok(["ollama", "list"])


def _check_ffmpeg() -> bool:
    if shutil.which("ffmpeg") is None:
        return False
    return _run_ok(["ffmpeg", "-version"])


def _check_whisper() -> bool:
    return MLX_WHISPER_BIN.is_file()


def _check_kokoro() -> bool:
    return (KOKORO_CACHE / "kokoro-v1.0.onnx").is_file() and (
        KOKORO_CACHE / "voices-v1.0.bin"
    ).is_file()


def _check_playwright() -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        with sync_playwright() as playwright:
            return Path(playwright.chromium.executable_path).is_file()
    except Exception:
        return False


def _check_remotion() -> bool:
    if not REMOTION_BIN.is_file():
        return False
    return _run_ok([str(REMOTION_BIN), "versions"], timeout=30)


def _check_cloud_blocked() -> bool:
    """Prove require_egress refuses cloud backends while mode is internal_only."""
    try:
        require_egress("cloud_backend", "https://example.invalid")
    except EgressBlocked:
        return True
    return False


def check() -> dict[str, bool]:
    return {
        "ollama": _check_ollama(),
        "whisper": _check_whisper(),
        "kokoro": _check_kokoro(),
        "ffmpeg": _check_ffmpeg(),
        "playwright": _check_playwright(),
        "remotion": _check_remotion(),
        "cloud_blocked": _check_cloud_blocked(),
    }


def main() -> int:
    print(json.dumps(check(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
