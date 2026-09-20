from __future__ import annotations

import subprocess
from pathlib import Path

from tools.egress_audit import repo_remote_push_status


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True)


def _add_remote(path: Path, name: str, url: str) -> None:
    subprocess.run(["git", "-C", str(path), "remote", "add", name, url], check=True)


def test_no_git_repo_returns_empty(tmp_path: Path) -> None:
    assert repo_remote_push_status(tmp_path) == []


def test_repo_without_remotes_returns_empty(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    assert repo_remote_push_status(tmp_path) == []


def test_remote_with_matching_fetch_and_push_is_not_disabled(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _add_remote(tmp_path, "origin", "https://example.invalid/repo.git")

    remotes = repo_remote_push_status(tmp_path)

    assert len(remotes) == 1
    assert remotes[0]["name"] == "origin"
    assert remotes[0]["fetch_url"] == "https://example.invalid/repo.git"
    assert remotes[0]["push_url"] == "https://example.invalid/repo.git"
    assert remotes[0]["push_disabled"] is False


def test_remote_with_disabled_push_url_is_reported(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _add_remote(tmp_path, "origin", "https://example.invalid/repo.git")
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "remote",
            "set-url",
            "--push",
            "origin",
            "DISABLED_INTERNAL_ONLY",
        ],
        check=True,
    )

    remotes = repo_remote_push_status(tmp_path)

    assert remotes[0]["fetch_url"] == "https://example.invalid/repo.git"
    assert remotes[0]["push_url"] == "DISABLED_INTERNAL_ONLY"
    assert remotes[0]["push_disabled"] is True


def test_multiple_remotes_are_each_reported(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _add_remote(tmp_path, "origin", "https://example.invalid/repo.git")
    _add_remote(tmp_path, "backup", "https://example.invalid/backup.git")
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "remote",
            "set-url",
            "--push",
            "origin",
            "DISABLED_INTERNAL_ONLY",
        ],
        check=True,
    )

    remotes = {entry["name"]: entry for entry in repo_remote_push_status(tmp_path)}

    assert remotes["origin"]["push_disabled"] is True
    assert remotes["backup"]["push_disabled"] is False


def test_live_repos_are_reported_by_the_full_audit() -> None:
    from tools.egress_audit import audit

    status = audit()["repo_push_status"]

    assert set(status) == {"video-toolkit", "video-toolkit-media"}
    media_remotes = status["video-toolkit-media"]["remotes"]
    assert media_remotes, "video-toolkit-media should have at least one remote"
    assert all(remote["push_disabled"] for remote in media_remotes)
