from __future__ import annotations

import json
from pathlib import Path

from tools.qc_verdict_log import append_verdict


def test_append_verdict_reads_source_and_appends_separate_jsonl_record(tmp_path: Path) -> None:
    source = tmp_path / "captions.srt"
    log_path = tmp_path / "qc-verdicts.jsonl"
    source.write_text("1\n00:00:00,000 --> 00:00:01,000\nHallo\n", encoding="utf-8")

    result = append_verdict(source, log_path, scope="subtitle", verdict="pass")

    record = json.loads(log_path.read_text(encoding="utf-8"))
    assert result == record
    assert record["scope"] == "subtitle"
    assert record["verdict"] == "pass"
    assert record["source"] == str(source.resolve())
    assert record["source_sha256"]
    assert source.read_text(encoding="utf-8").endswith("Hallo\n")


def test_append_verdict_rejects_unknown_verdict_without_creating_log(tmp_path: Path) -> None:
    source = tmp_path / "audio.wav"
    log_path = tmp_path / "qc-verdicts.jsonl"
    source.write_bytes(b"fixture")

    try:
        append_verdict(source, log_path, scope="audio", verdict="maybe")
    except ValueError as error:
        assert "verdict" in str(error)
    else:
        raise AssertionError("expected invalid verdict")

    assert not log_path.exists()
