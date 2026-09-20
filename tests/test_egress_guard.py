from __future__ import annotations

import ast
import importlib
import sys
import types
from pathlib import Path

import pytest

from tools.egress_guard import (
    EgressBlocked,
    active_n8n_workflow_violations,
    load_policy,
    require_egress,
    scan_send_patterns,
    unallowlisted_send_patterns,
)


def _module(name: str, **attributes: object) -> types.ModuleType:
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def _load_youtube_upload(monkeypatch: pytest.MonkeyPatch):
    class FakeHttpError(Exception):
        pass

    modules = {
        "httplib2": _module("httplib2", HttpLib2Error=OSError),
        "google": _module("google"),
        "google.auth": _module("google.auth"),
        "google.auth.exceptions": _module("google.auth.exceptions", RefreshError=RuntimeError),
        "google.auth.transport": _module("google.auth.transport"),
        "google.auth.transport.requests": _module("google.auth.transport.requests", Request=object),
        "google.oauth2": _module("google.oauth2"),
        "google.oauth2.credentials": _module("google.oauth2.credentials", Credentials=object),
        "google_auth_oauthlib": _module("google_auth_oauthlib"),
        "google_auth_oauthlib.flow": _module(
            "google_auth_oauthlib.flow", InstalledAppFlow=object
        ),
        "googleapiclient": _module("googleapiclient"),
        "googleapiclient.discovery": _module(
            "googleapiclient.discovery", build=lambda **_kwargs: None
        ),
        "googleapiclient.http": _module("googleapiclient.http", MediaFileUpload=object),
        "googleapiclient.errors": _module("googleapiclient.errors", HttpError=FakeHttpError),
        "dotenv": _module("dotenv", load_dotenv=lambda: None),
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    sys.modules.pop("tools.youtube_upload", None)
    return importlib.import_module("tools.youtube_upload")


def test_upload_call_is_blocked_even_before_any_request(monkeypatch: pytest.MonkeyPatch) -> None:
    youtube_upload = _load_youtube_upload(monkeypatch)

    with pytest.raises(EgressBlocked, match="internal_only"):
        youtube_upload.resumable_upload(object())


def test_every_youtube_network_entrypoint_requires_egress() -> None:
    source = Path("tools/youtube_upload.py").read_text(encoding="utf-8")
    functions = {
        node.name: node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.FunctionDef)
    }
    for name in (
        "get_credentials",
        "build_service",
        "resumable_upload",
        "set_thumbnail",
        "add_caption",
        "add_to_playlist",
    ):
        calls = [
            node
            for node in ast.walk(functions[name])
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "require_youtube_egress"
        ]
        assert calls, f"{name} must require egress before network access"


def test_policy_is_internal_only_and_environment_cannot_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert load_policy() == {"mode": "internal_only", "allowed_actions": []}
    monkeypatch.setenv("EGRESS_POLICY_MODE", "release_enabled")

    with pytest.raises(EgressBlocked):
        require_egress("youtube_api", "upload")


def test_every_known_send_pattern_is_allowlisted() -> None:
    assert scan_send_patterns()
    assert unallowlisted_send_patterns() == []


def test_unallowlisted_temp_requests_post_is_detected(tmp_path: Path) -> None:
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()
    (tools_dir / "unknown_sender.py").write_text("import requests\nrequests.post('https://x')\n")

    findings = scan_send_patterns(tmp_path)

    assert {"path": "tools/unknown_sender.py", "pattern": "requests_send"} in findings


def test_active_n8n_workflows_have_only_internal_node_types() -> None:
    assert active_n8n_workflow_violations() == []
