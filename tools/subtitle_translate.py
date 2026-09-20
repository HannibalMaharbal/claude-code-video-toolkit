#!/usr/bin/env python3
"""Optional local SRT/VTT translation; existing subtitle tooling is untouched."""
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

DEFAULT_MODEL = "gemma-code:latest"
MARKER = re.compile(r"<translation>\s*(.*?)\s*</translation>", re.DOTALL | re.IGNORECASE)


def _translate(text: str, target_language: str, model: str) -> str:
    prompt = (
        f"Translate the subtitle text into {target_language}. Return exactly one XML fragment: "
        "<translation>translated subtitle text</translation>. No analysis, no thinking, no "
        f"other text.\n\n{text}"
    )
    result = subprocess.run(
        ["ollama", "run", model, prompt],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Ollama translation failed")
    match = MARKER.search(result.stdout)
    if not match or not match.group(1).strip():
        raise RuntimeError("Ollama response lacks a complete translation marker")
    return match.group(1).strip()


def translate_subtitle_file(
    source: Path, output: Path, *, target_language: str, model: str = DEFAULT_MODEL
) -> None:
    source, output = source.resolve(), output.resolve()
    if source == output:
        raise ValueError("output must differ from input")
    blocks = source.read_text(encoding="utf-8").split("\n\n")
    rendered = []
    for block in blocks:
        lines = block.splitlines()
        timestamp = next((i for i, line in enumerate(lines) if " --> " in line), None)
        if timestamp is None or not lines[timestamp + 1:]:
            rendered.append(block)
            continue
        translated = _translate(
            "\n".join(lines[timestamp + 1:]), target_language, model
        ).splitlines()
        rendered.append("\n".join(lines[:timestamp + 1] + translated))
    content = "\n\n".join(rendered)
    if source.read_text(encoding="utf-8").endswith("\n"):
        content += "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(output.suffix + ".tmp")
    temp.write_text(content, encoding="utf-8")
    temp.replace(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target-language", required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()
    translate_subtitle_file(
        args.input,
        args.output,
        target_language=args.target_language,
        model=args.model,
    )


if __name__ == "__main__":
    main()
