#!/usr/bin/env python3
"""HyperFrames Code-to-Video Adapter for HANNIBAL AI OS.

Wraps the HeyGen HyperFrames CLI for rendering deterministic, pixel-perfect
HTML/CSS kinetic typography, motion graphics, lower-thirds, and overlays into
MP4 or transparent WebM video.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def find_hyperframes_bin() -> str | None:
    """Locate the hyperframes binary in PATH or common global npm locations."""
    found = shutil.which("hyperframes")
    if found:
        return found
    candidates = [
        Path.home() / ".local/share/fnm/current/bin/hyperframes",
        Path.home() / ".local/share/fnm/node-versions/v22.23.2/installation/bin/hyperframes",
        Path("/opt/homebrew/bin/hyperframes"),
        Path("/usr/local/bin/hyperframes"),
    ]
    for c in candidates:
        if c.is_file() and os.access(c, os.X_OK):
            return str(c)
    return None


def get_hyperframes_version() -> str | None:
    """Return the installed version of hyperframes, or None."""
    bin_path = find_hyperframes_bin()
    if not bin_path:
        return None
    try:
        res = subprocess.run([bin_path, "--version"], capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except Exception:
        return None


def lint_composition(project_dir: Path | str) -> Dict[str, Any]:
    """Run hyperframes lint against a composition project."""
    bin_path = find_hyperframes_bin()
    if not bin_path:
        return {"ok": False, "error": "hyperframes binary not found"}
    
    project_path = Path(project_dir).resolve()
    if not project_path.is_dir():
        return {"ok": False, "error": f"Project directory not found: {project_path}"}
    
    try:
        res = subprocess.run(
            [bin_path, "lint"],
            cwd=str(project_path),
            capture_output=True,
            text=True,
        )
        return {
            "ok": res.returncode == 0,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "returncode": res.returncode,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def render_composition(
    project_dir: Path | str,
    output_path: Path | str,
    format_type: str = "mp4",
    fps: int = 30,
) -> Dict[str, Any]:
    """Render a composition to an MP4 or transparent WebM video.

    Args:
        project_dir: Path to the HyperFrames project folder.
        output_path: Target path for the rendered video.
        format_type: Output format ('mp4' or 'webm').
        fps: Frames per second (default 30).
    """
    bin_path = find_hyperframes_bin()
    if not bin_path:
        return {"ok": False, "error": "hyperframes binary not found"}

    project_path = Path(project_dir).resolve()
    out_file = Path(output_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        bin_path,
        "render",
        "-o",
        str(out_file),
        "--fps",
        str(fps),
    ]
    if format_type.lower() == "webm":
        cmd.extend(["--format", "webm"])

    try:
        res = subprocess.run(
            cmd,
            cwd=str(project_path),
            capture_output=True,
            text=True,
        )
        success = res.returncode == 0 and out_file.is_file() and out_file.stat().st_size > 0
        return {
            "ok": success,
            "output_path": str(out_file),
            "file_size": out_file.stat().st_size if out_file.is_file() else 0,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "returncode": res.returncode,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def main() -> int:
    parser = argparse.ArgumentParser(description="HyperFrames Code-to-Video Adapter")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # version
    subparsers.add_parser("version", help="Print HyperFrames version")

    # lint
    lint_parser = subparsers.add_parser("lint", help="Lint a composition project")
    lint_parser.add_argument("project_dir", help="Path to project directory")

    # render
    render_parser = subparsers.add_parser("render", help="Render a composition")
    render_parser.add_argument("project_dir", help="Path to project directory")
    render_parser.add_argument("-o", "--output", required=True, help="Output video path")
    render_parser.add_argument("--format", choices=["mp4", "webm"], default="mp4", help="Format")
    render_parser.add_argument("--fps", type=int, default=30, help="Framerate")

    args = parser.parse_args()

    if args.command == "version":
        v = get_hyperframes_version()
        if v:
            print(f"HyperFrames version: {v}")
            return 0
        print("HyperFrames CLI not found", file=sys.stderr)
        return 1

    if args.command == "lint":
        res = lint_composition(args.project_dir)
        print(json.dumps(res, indent=2))
        return 0 if res.get("ok") else 1

    if args.command == "render":
        res = render_composition(args.project_dir, args.output, args.format, args.fps)
        print(json.dumps(res, indent=2))
        return 0 if res.get("ok") else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
