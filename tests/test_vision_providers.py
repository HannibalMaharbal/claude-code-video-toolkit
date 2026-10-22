from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests

from tools.vision_providers import (
    CapabilityStatus,
    InvalidVisionResponseError,
    ModelUnavailableError,
    ProviderOfflineError,
    VisionSettings,
    create_provider,
    discover_local_providers,
    format_discovery,
    load_capability_statuses,
)


class FakeResponse:
    def __init__(self, payload: object, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self) -> object:
        return self._payload


class FakeSession:
    def __init__(self, responses: dict[str, object]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, dict[str, object] | None]] = []

    def get(self, url: str, *, timeout: float) -> FakeResponse:
        self.calls.append(("GET", url, None))
        result = self.responses[url]
        if isinstance(result, Exception):
            raise result
        return result  # type: ignore[return-value]

    def post(self, url: str, *, json: dict[str, object], timeout: float) -> FakeResponse:
        self.calls.append(("POST", url, json))
        result = self.responses[url]
        if isinstance(result, Exception):
            raise result
        return result  # type: ignore[return-value]


@pytest.fixture
def image(tmp_path: Path) -> Path:
    frame = tmp_path / "frame.png"
    frame.write_bytes(b"png-bytes")
    return frame


def test_lmstudio_online_discovers_openai_model_ids() -> None:
    url = "http://lm:1234/v1/models"
    provider = create_provider(
        VisionSettings(provider="lmstudio", model="gemma-local", base_url="http://lm:1234"),
        session=FakeSession({url: FakeResponse({"data": [{"id": "gemma-local"}]})}),
    )

    assert provider.models() == ["gemma-local"]


def test_ollama_online_discovers_installed_model_names() -> None:
    url = "http://ollama:11434/api/tags"
    provider = create_provider(
        VisionSettings(provider="ollama", model="vision-local", base_url="http://ollama:11434"),
        session=FakeSession({url: FakeResponse({"models": [{"name": "vision-local"}]})}),
    )

    assert provider.models() == ["vision-local"]


@pytest.mark.parametrize(
    "provider_name, models_url",
    [
        ("lmstudio", "http://local/v1/models"),
        ("ollama", "http://local/api/tags"),
    ],
)
def test_provider_offline_is_reported_fail_closed(provider_name: str, models_url: str) -> None:
    provider = create_provider(
        VisionSettings(provider=provider_name, model="configured", base_url="http://local"),
        session=FakeSession({models_url: requests.ConnectionError("offline")}),
    )

    with pytest.raises(ProviderOfflineError):
        provider.models()


def test_missing_configured_model_fails_closed(image: Path) -> None:
    session = FakeSession(
        {
            "http://local/api/tags": FakeResponse({"models": [{"name": "other-model"}]}),
        }
    )
    provider = create_provider(
        VisionSettings(provider="ollama", model="configured", base_url="http://local"),
        session=session,
    )

    with pytest.raises(ModelUnavailableError):
        provider.infer(image, "describe the frame")
    assert [method for method, _, _ in session.calls] == ["GET"]


def test_ollama_sends_base64_vision_input_and_returns_json(image: Path) -> None:
    session = FakeSession(
        {
            "http://local/api/tags": FakeResponse({"models": [{"name": "configured"}]}),
            "http://local/api/chat": FakeResponse({"message": {"content": '{"objects": ["bar"]}'}}),
        }
    )
    provider = create_provider(
        VisionSettings(provider="ollama", model="configured", base_url="http://local"),
        session=session,
    )

    assert provider.infer(image, "describe") == {"objects": ["bar"]}
    payload = session.calls[-1][2]
    assert payload is not None
    assert payload["model"] == "configured"
    assert payload["messages"][0]["images"]  # type: ignore[index]


def test_lmstudio_sends_data_url_vision_input(image: Path) -> None:
    session = FakeSession(
        {
            "http://local/v1/models": FakeResponse({"data": [{"id": "configured"}]}),
            "http://local/v1/chat/completions": FakeResponse(
                {"choices": [{"message": {"content": '{"objects": ["bar"]}'}}]}
            ),
        }
    )
    provider = create_provider(
        VisionSettings(provider="lmstudio", model="configured", base_url="http://local"),
        session=session,
    )

    provider.infer(image, "describe")
    content = session.calls[-1][2]["messages"][0]["content"]  # type: ignore[index,union-attr]
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")  # type: ignore[index]


def test_timeout_does_not_fall_back_to_another_provider(image: Path) -> None:
    session = FakeSession(
        {
            "http://local/api/tags": FakeResponse({"models": [{"name": "configured"}]}),
            "http://local/api/chat": requests.Timeout("slow"),
        }
    )
    provider = create_provider(
        VisionSettings(provider="ollama", model="configured", base_url="http://local"),
        session=session,
    )

    with pytest.raises(ProviderOfflineError, match="Timeout"):
        provider.infer(image, "describe")
    assert all("lmstudio" not in url for _, url, _ in session.calls)


def test_invalid_provider_answer_fails_closed(image: Path) -> None:
    session = FakeSession(
        {
            "http://local/api/tags": FakeResponse({"models": [{"name": "configured"}]}),
            "http://local/api/chat": FakeResponse({"message": {"content": "not-json"}}),
        }
    )
    provider = create_provider(
        VisionSettings(provider="ollama", model="configured", base_url="http://local"),
        session=session,
    )

    with pytest.raises(InvalidVisionResponseError):
        provider.infer(image, "describe")


def test_discovery_separates_technical_and_capability_status() -> None:
    sessions = {
        "lmstudio": FakeSession({"http://lm/v1/models": FakeResponse({"data": [{"id": "gemma"}]})}),
        "ollama": FakeSession(
            {"http://ollama/api/tags": FakeResponse({"models": [{"name": "qwen"}]})}
        ),
    }
    results = discover_local_providers(
        lmstudio_url="http://lm",
        ollama_url="http://ollama",
        sessions=sessions,
        capability_statuses={("ollama", "qwen"): CapabilityStatus.FAIL},
    )

    assert results[0].online is True
    assert results[0].models[0].vision_capability is CapabilityStatus.NOT_TESTED
    assert results[1].models[0].installed is True
    assert results[1].models[0].inference is True
    assert results[1].models[0].vision_capability is CapabilityStatus.FAIL
    assert "vision_capability: FAIL" in format_discovery(results)


def test_capability_status_file_never_implies_technical_readiness(tmp_path: Path) -> None:
    status_file = tmp_path / "capability.json"
    status_file.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "provider": "ollama",
                        "model": "tested-model",
                        "vision_capability": "FAIL",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert load_capability_statuses(status_file) == {
        ("ollama", "tested-model"): CapabilityStatus.FAIL
    }
