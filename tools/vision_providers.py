"""Fail-closed local vision-provider adapters for LM Studio and Ollama.

This module only addresses local provider transport and discovery.  It never
selects a model, changes a QC decision, downloads a model, or falls back from
one provider to another.  Semantic capability remains an independently supplied
test result and defaults to ``NOT_TESTED``.
"""

from __future__ import annotations

import base64
import json
import mimetypes
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

import requests


class VisionProviderError(RuntimeError):
    """A local vision provider could not safely fulfill a request."""


class ProviderOfflineError(VisionProviderError):
    """The selected provider did not respond within its configured timeout."""


class ModelUnavailableError(VisionProviderError):
    """The explicitly configured model is not available from this provider."""


class InvalidVisionResponseError(VisionProviderError):
    """The provider returned an answer that cannot be consumed safely."""


class CapabilityStatus(StrEnum):
    """Semantic result from a separate real-world vision capability test."""

    PASS = "PASS"
    FAIL = "FAIL"
    NOT_TESTED = "NOT_TESTED"


@dataclass(frozen=True)
class VisionSettings:
    """Explicit transport configuration; provider and model are independent."""

    provider: str
    model: str
    timeout_ms: int = 120_000
    base_url: str | None = None

    def __post_init__(self) -> None:
        if self.provider not in {"lmstudio", "ollama"}:
            raise ValueError(f"Nicht unterstützter Vision-Provider: {self.provider}")
        if not self.model.strip():
            raise ValueError("vision_model muss explizit konfiguriert sein")
        if self.timeout_ms <= 0:
            raise ValueError("timeout_ms muss positiv sein")


@dataclass(frozen=True)
class ModelDiscovery:
    """Technical availability and semantic capability deliberately stay separate."""

    model_id: str
    installed: bool
    inference: bool
    vision_capability: CapabilityStatus


@dataclass(frozen=True)
class ProviderDiscovery:
    provider: str
    online: bool
    models: list[ModelDiscovery]
    error: str = ""

    @property
    def status(self) -> str:
        return "ONLINE" if self.online else "OFFLINE"


class Session(Protocol):
    def get(self, url: str, *, timeout: float) -> requests.Response: ...

    def post(self, url: str, *, json: dict[str, Any], timeout: float) -> requests.Response: ...


class VisionProvider:
    """Shared contract for local vision services."""

    provider_name: str

    def __init__(self, settings: VisionSettings, session: Session | None = None) -> None:
        self.settings = settings
        self.base_url = (settings.base_url or self.default_base_url).rstrip("/")
        self.session: Session = session or requests.Session()

    @property
    def default_base_url(self) -> str:
        raise NotImplementedError

    @property
    def timeout_seconds(self) -> float:
        return self.settings.timeout_ms / 1000

    def _request_json(self, method: str, url: str, payload: dict[str, Any] | None = None) -> Any:
        try:
            if method == "GET":
                response = self.session.get(url, timeout=self.timeout_seconds)
            else:
                response = self.session.post(url, json=payload or {}, timeout=self.timeout_seconds)
            response.raise_for_status()
            return response.json()
        except requests.Timeout as error:
            raise ProviderOfflineError(f"{self.provider_name} Timeout: {error}") from error
        except requests.RequestException as error:
            raise ProviderOfflineError(f"{self.provider_name} nicht erreichbar: {error}") from error
        except (TypeError, ValueError) as error:
            raise InvalidVisionResponseError(
                f"{self.provider_name} lieferte kein gültiges JSON: {error}"
            ) from error

    def models(self) -> list[str]:
        raise NotImplementedError

    def _assert_model_available(self) -> None:
        if self.settings.model not in self.models():
            raise ModelUnavailableError(
                f"Modell '{self.settings.model}' ist bei {self.provider_name} nicht verfügbar"
            )

    def infer(self, image_path: Path, prompt: str) -> dict[str, Any]:
        if not image_path.is_file() or image_path.stat().st_size <= 0:
            raise InvalidVisionResponseError(f"Vision-Bild ist nicht lesbar: {image_path}")
        self._assert_model_available()
        return self._infer(image_path, prompt)

    def _infer(self, image_path: Path, prompt: str) -> dict[str, Any]:
        raise NotImplementedError

    @staticmethod
    def _json_object(value: object, provider_name: str) -> dict[str, Any]:
        if not isinstance(value, str):
            raise InvalidVisionResponseError(f"{provider_name} Antwortinhalt fehlt")
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as error:
            raise InvalidVisionResponseError(
                f"{provider_name} Antwort ist kein gültiges JSON-Objekt"
            ) from error
        if not isinstance(parsed, dict):
            raise InvalidVisionResponseError(f"{provider_name} Antwort ist kein JSON-Objekt")
        return parsed


class LmStudioVisionProvider(VisionProvider):
    """LM Studio's local OpenAI-compatible API adapter."""

    provider_name = "LM Studio"

    @property
    def default_base_url(self) -> str:
        return "http://127.0.0.1:1234"

    def models(self) -> list[str]:
        payload = self._request_json("GET", f"{self.base_url}/v1/models")
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise InvalidVisionResponseError("LM Studio Modellliste ist ungültig")
        return [
            item["id"]
            for item in payload["data"]
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        ]

    def _infer(self, image_path: Path, prompt: str) -> dict[str, Any]:
        media_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
        data_url = (
            f"data:{media_type};base64,{base64.b64encode(image_path.read_bytes()).decode('ascii')}"
        )
        payload = {
            "model": self.settings.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            "response_format": {"type": "json_object"},
        }
        response = self._request_json("POST", f"{self.base_url}/v1/chat/completions", payload)
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise InvalidVisionResponseError(
                "LM Studio Antwort enthält keine Chat-Completion"
            ) from error
        return self._json_object(content, self.provider_name)


class OllamaVisionProvider(VisionProvider):
    """Ollama's local API adapter."""

    provider_name = "Ollama"

    @property
    def default_base_url(self) -> str:
        return "http://127.0.0.1:11434"

    def models(self) -> list[str]:
        payload = self._request_json("GET", f"{self.base_url}/api/tags")
        if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
            raise InvalidVisionResponseError("Ollama Modellliste ist ungültig")
        return [
            item["name"]
            for item in payload["models"]
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        ]

    def _infer(self, image_path: Path, prompt: str) -> dict[str, Any]:
        payload = {
            "model": self.settings.model,
            "stream": False,
            "format": "json",
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [base64.b64encode(image_path.read_bytes()).decode("ascii")],
                }
            ],
        }
        response = self._request_json("POST", f"{self.base_url}/api/chat", payload)
        try:
            content = response["message"]["content"]
        except (KeyError, TypeError) as error:
            raise InvalidVisionResponseError(
                "Ollama Antwort enthält keine Chat-Nachricht"
            ) from error
        return self._json_object(content, self.provider_name)


def create_provider(settings: VisionSettings, session: Session | None = None) -> VisionProvider:
    """Create only the explicitly selected provider; never choose a fallback."""
    if settings.provider == "lmstudio":
        return LmStudioVisionProvider(settings, session)
    return OllamaVisionProvider(settings, session)


def discover_local_providers(
    *,
    lmstudio_url: str = "http://127.0.0.1:1234",
    ollama_url: str = "http://127.0.0.1:11434",
    timeout_ms: int = 3_000,
    sessions: dict[str, Session] | None = None,
    capability_statuses: dict[tuple[str, str], CapabilityStatus] | None = None,
) -> list[ProviderDiscovery]:
    """Read local provider state without installing, downloading, or probing models."""
    statuses = capability_statuses or {}
    settings = [
        VisionSettings("lmstudio", "__discovery__", timeout_ms, lmstudio_url),
        VisionSettings("ollama", "__discovery__", timeout_ms, ollama_url),
    ]
    results: list[ProviderDiscovery] = []
    for item in settings:
        provider = create_provider(item, (sessions or {}).get(item.provider))
        try:
            model_ids = provider.models()
        except VisionProviderError as error:
            results.append(ProviderDiscovery(provider.provider_name, False, [], str(error)))
            continue
        results.append(
            ProviderDiscovery(
                provider.provider_name,
                True,
                [
                    ModelDiscovery(
                        model,
                        True,
                        True,
                        statuses.get((item.provider, model), CapabilityStatus.NOT_TESTED),
                    )
                    for model in model_ids
                ],
            )
        )
    return results


def load_capability_statuses(path: Path) -> dict[tuple[str, str], CapabilityStatus]:
    """Load independently validated capability outcomes from a local file."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        entries = payload["models"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise InvalidVisionResponseError(f"Capability-Statusdatei ist ungültig: {error}") from error
    if not isinstance(entries, list):
        raise InvalidVisionResponseError("Capability-Statusdatei enthält keine Modellliste")
    statuses: dict[tuple[str, str], CapabilityStatus] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise InvalidVisionResponseError("Capability-Statusdatei enthält keinen Modell-Eintrag")
        provider = entry.get("provider")
        model = entry.get("model")
        status = entry.get("vision_capability")
        if not isinstance(provider, str) or not provider:
            raise InvalidVisionResponseError(
                "Capability-Statusdatei enthält unvollständigen Modell-Eintrag"
            )
        if not isinstance(model, str) or not model:
            raise InvalidVisionResponseError(
                "Capability-Statusdatei enthält unvollständigen Modell-Eintrag"
            )
        if not isinstance(status, str) or not status:
            raise InvalidVisionResponseError(
                "Capability-Statusdatei enthält unvollständigen Modell-Eintrag"
            )
        try:
            statuses[(provider, model)] = CapabilityStatus(status)
        except ValueError as error:
            raise InvalidVisionResponseError(
                f"Ungültiger Vision-Capability-Status: {status}"
            ) from error
    return statuses


def format_discovery(results: list[ProviderDiscovery]) -> str:
    """Render the requested compact local discovery report."""
    lines: list[str] = []
    for result in results:
        lines.extend([f"Provider: {result.provider}", f"Status: {result.status}"])
        lines.append("Models: [" + ", ".join(model.model_id for model in result.models) + "]")
        for model in result.models:
            lines.append(
                f"Model: {model.model_id} | installed: {str(model.installed).lower()} "
                f"| inference: {str(model.inference).lower()} "
                f"| vision_capability: {model.vision_capability}"
            )
        if result.error:
            lines.append(f"Error: {result.error}")
    return "\n".join(lines)
