from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.acceptance import CAPABILITY_IDS, Result, _render_table, _write_reports


def _results() -> list[Result]:
    return [
        Result(capability, "PASS", "gemessen", {"sample": 1}, 0.1) for capability in CAPABILITY_IDS
    ]


def test_render_table_contains_all_capabilities() -> None:
    table = _render_table(_results())
    assert all(capability in table for capability in CAPABILITY_IDS)
    assert "PASS" in table


def test_write_reports_creates_machine_and_human_readable_results(tmp_path: Path) -> None:
    markdown, report_json = tmp_path / "report.md", tmp_path / "report.json"
    _write_reports(_results(), markdown_path=markdown, json_path=report_json)
    assert "FERTIG: ja, PASS 15 von 15" in markdown.read_text(encoding="utf-8")
    assert json.loads(report_json.read_text(encoding="utf-8"))["pass_count"] == 15


def test_write_reports_refuses_to_overwrite(tmp_path: Path) -> None:
    markdown, report_json = tmp_path / "report.md", tmp_path / "report.json"
    markdown.write_text("existing", encoding="utf-8")
    with pytest.raises(FileExistsError):
        _write_reports(_results(), markdown_path=markdown, json_path=report_json)
    assert markdown.read_text(encoding="utf-8") == "existing"
