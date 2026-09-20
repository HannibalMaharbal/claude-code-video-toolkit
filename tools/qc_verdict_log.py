#!/usr/bin/env python3
"""Append read-only QC verdict records for existing media or subtitle artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

ALLOWED_VERDICTS = {"pass", "fail", "not_run"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def append_verdict(
    source_path: Path, log_path: Path, *, scope: str, verdict: str
) -> dict[str, str]:
    """Read a source artifact and append one independent JSONL verdict record."""
    if verdict not in ALLOWED_VERDICTS:
        raise ValueError(f"verdict must be one of: {', '.join(sorted(ALLOWED_VERDICTS))}")
    source_path = source_path.resolve()
    log_path = log_path.resolve()
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    if not scope.strip():
        raise ValueError("scope must not be empty")

    record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "scope": scope,
        "verdict": verdict,
        "source": str(source_path),
        "source_sha256": _sha256(source_path),
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return record


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Append an independent, read-only QC verdict record"
    )
    parser.add_argument("--source", required=True, type=Path, help="Existing artifact to read")
    parser.add_argument("--log", required=True, type=Path, help="Separate JSONL verdict log")
    parser.add_argument("--scope", required=True, help="QC scope, for example subtitle or audio")
    parser.add_argument("--verdict", required=True, choices=sorted(ALLOWED_VERDICTS))
    args = parser.parse_args()
    print(json.dumps(append_verdict(args.source, args.log, scope=args.scope, verdict=args.verdict)))


if __name__ == "__main__":
    main()
