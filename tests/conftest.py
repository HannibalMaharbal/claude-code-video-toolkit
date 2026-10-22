from __future__ import annotations

import os
from pathlib import Path

import pytest


def pytest_configure(config: pytest.Config) -> None:
    fnm_node = (
        Path.home()
        / ".local"
        / "share"
        / "fnm"
        / "node-versions"
        / "v22.23.2"
        / "installation"
        / "bin"
    )
    if fnm_node.is_dir():
        os.environ["PATH"] = str(fnm_node) + ":" + os.environ.get("PATH", "")
