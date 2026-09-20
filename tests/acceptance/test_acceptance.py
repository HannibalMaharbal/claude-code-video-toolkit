from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.acceptance import (
    CAPABILITY_IDS,
    Result,
    _parse_version,
    _remotion_versions,
    _render_table,
    _version_ok,
    _write_reports,
)


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


def test_parse_version_extracts_first_dotted_number() -> None:
    assert _parse_version("ffmpeg version 9.0.2 Copyright ...") == (9, 0, 2)
    assert _parse_version("Python 3.12.14") == (3, 12, 14)
    assert _parse_version(None) is None
    assert _parse_version("no version here") is None


def test_version_ok_greater_equal() -> None:
    assert _version_ok("ffmpeg version 9.0.2", ">=9.0.2") is True
    assert _version_ok("ffmpeg version 9.0.2", ">=9.0.3") is False
    assert _version_ok("ffmpeg version 10.0.0", ">=9.0.2") is True


def test_version_ok_exact() -> None:
    assert _version_ok("4.0.526", "==4.0.526") is True
    assert _version_ok("4.0.520", "==4.0.526") is False


def test_version_ok_missing_actual_is_not_ok() -> None:
    assert _version_ok(None, ">=1.0.0") is False


def test_version_ok_rejects_malformed_constraint() -> None:
    with pytest.raises(RuntimeError, match="Versionsvorgabe"):
        _version_ok("1.0.0", "1.0.0")


def test_remotion_versions_reports_missing_binary(tmp_path: Path) -> None:
    result = _remotion_versions(tmp_path / "no-such-remotion")
    assert result == {"version": None, "consistent": False}


def test_installed_remotion_matches_pinned_minimum() -> None:
    from tools.acceptance import ROOT

    result = _remotion_versions(ROOT / "node_modules" / ".bin" / "remotion")
    assert result["version"] == "4.0.526"
    assert result["consistent"] is True


@pytest.mark.integration
def test_f13_fails_only_on_the_deliberately_pinned_python_minimum() -> None:
    """The project venv is deliberately pinned to <3.13 (mlx-whisper on Apple Silicon);
    contracts/stack-manifest.json requires python>=3.14.7. This is a known, accepted
    mismatch (see AI_HANDOFF.md), not a bug — F13 must keep failing on it, not silently
    pass, until either the pin or the minimum is deliberately revisited."""
    from tools.acceptance import _f13

    with pytest.raises(RuntimeError, match=r"python: Ist .* erfüllt nicht >=3\.14\.7"):
        _f13(Path("."), {})
