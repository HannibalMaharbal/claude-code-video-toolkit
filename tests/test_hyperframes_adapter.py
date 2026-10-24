"""Unit tests for HyperFrames Code-to-Video Adapter."""

from pathlib import Path
from tools.hyperframes_adapter import (
    find_hyperframes_bin,
    get_hyperframes_version,
    lint_composition,
)


def test_find_hyperframes_bin():
    bin_path = find_hyperframes_bin()
    assert bin_path is not None
    assert Path(bin_path).exists()


def test_get_hyperframes_version():
    ver = get_hyperframes_version()
    assert ver is not None
    assert "0.8." in ver


def test_lint_missing_directory(tmp_path):
    missing_dir = tmp_path / "does_not_exist"
    res = lint_composition(missing_dir)
    assert res["ok"] is False
    assert "Project directory not found" in res["error"]
