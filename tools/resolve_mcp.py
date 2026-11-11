#!/usr/bin/env python3
"""Local MCP server bridge for DaVinci Resolve Studio API.

Status: Inaktiv bis DaVinci Resolve Studio vorhanden ist (Resolve Free 21.1
bietet keine externe Python-Scripting-API). Das Fairlight-Lautheits-Gate
verwendet ffmpeg loudnorm für echte Messungen (-14 LUFS ±1, True Peak <= -1 dBTP).

Exposes standard MCP tools for Claude Code, Codex, and Antigravity:
  - resolve_status: Report local DaVinci Resolve & Scripting API health
  - resolve_setup_project: Set resolution (1080x1920 9:16 or 4K) & initialize standard bins
  - resolve_setup_bins: Create standard media bins (A-Roll, B-Roll, Graphics, Audio, Renders)
  - resolve_import_media: Import files into active timeline or specific bin
  - resolve_fairlight_gate: Inspect and apply -14 LUFS loudness standard
  - resolve_queue_render: Add timeline to render queue with preset (H.264 / ProRes)

Stdio JSON-RPC transport compliant with MCP Specification.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import resolve_adapter

TOOLS: list[dict[str, Any]] = [
    {
        "name": "resolve_status",
        "description": "Check if DaVinci Resolve is running and if the local Scripting API is available.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "resolve_setup_project",
        "description": "Configure project resolution (vertical 1080x1920 or 4K) and standard media bins.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Project or sequence name."},
                "vertical": {"type": "boolean", "default": True, "description": "True for 9:16 vertical reel."},
                "fps": {"type": "number", "default": 30.0, "description": "Timeline framerate."},
            },
            "required": ["name"],
        },
    },
    {
        "name": "resolve_setup_bins",
        "description": "Create standard production bins in Media Pool (01_A-Roll, 02_B-Roll, etc.).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "bins": {"type": "array", "items": {"type": "string"}, "description": "Custom bin names."},
            },
        },
    },
    {
        "name": "resolve_import_media",
        "description": "Import local media files into a specific bin or directly onto the active timeline.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "files": {"type": "array", "items": {"type": "string"}, "description": "Local file paths."},
                "bin": {"type": "string", "description": "Optional target bin name."},
                "timeline_name": {"type": "string", "description": "Optional timeline name."},
            },
            "required": ["files"],
        },
    },
    {
        "name": "resolve_fairlight_gate",
        "description": "Inspect and verify the -14 LUFS Fairlight broadcast/social loudness gate using ffmpeg loudnorm. Note: pass 'file' for real audio measurement; timeline inspection alone returns status 'not_measured'.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Optional exported audio/video file path to measure and validate."},
                "target_lufs": {"type": "number", "default": -14.0, "description": "Target LUFS value."},
            },
        },
    },
    {
        "name": "resolve_queue_render",
        "description": "Add the active timeline to the Resolve render queue without automatically starting it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_dir": {"type": "string", "description": "Output directory for rendered files."},
                "preset": {"type": "string", "description": "Render preset (e.g. H.264 Master)."},
                "name": {"type": "string", "description": "Output filename base."},
            },
            "required": ["target_dir"],
        },
    },
]


def handle_tool_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        if name == "resolve_status":
            return resolve_adapter.discover()
        elif name == "resolve_setup_project":
            proj_name = arguments.get("name") or arguments.get("project_name")
            if not proj_name:
                raise KeyError("name")
            return resolve_adapter.setup_project(
                proj_name,
                vertical=arguments.get("vertical", True),
                fps=arguments.get("fps", 30.0),
            )
        elif name == "resolve_setup_bins":
            return resolve_adapter.setup_bins(arguments.get("bins"))
        elif name == "resolve_import_media":
            paths = [Path(f) for f in arguments["files"]]
            target_bin = arguments.get("bin")
            if target_bin:
                return resolve_adapter.import_to_bin(target_bin, paths)
            return resolve_adapter.import_media(paths, timeline_name=arguments.get("timeline_name"))
        elif name == "resolve_fairlight_gate":
            file_path = Path(arguments["file"]) if arguments.get("file") else None
            return resolve_adapter.apply_fairlight_gate(
                target_lufs=arguments.get("target_lufs", -14.0),
                file_path=file_path,
            )
        elif name == "resolve_queue_render":
            return resolve_adapter.queue_render(
                Path(arguments["target_dir"]),
                preset=arguments.get("preset"),
                custom_name=arguments.get("name"),
            )
        else:
            raise resolve_adapter.ResolveAdapterError(f"Unknown tool: {name}")
    except resolve_adapter.ResolveAdapterError as err:
        return {"error": str(err)}


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue

        req_id = req.get("id")
        method = req.get("method")

        if method == "initialize":
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "davinci-resolve-mcp", "version": "1.0.0"},
                },
            }
        elif method == "tools/list":
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": TOOLS},
            }
        elif method == "tools/call":
            params = req.get("params", {})
            tool_name = params.get("name", "")
            args = params.get("arguments", {})
            result = handle_tool_call(tool_name, args)
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]
                },
            }
        else:
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }

        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
