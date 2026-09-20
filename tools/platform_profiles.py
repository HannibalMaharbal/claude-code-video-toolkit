#!/usr/bin/env python3
"""Shared, schema-validated access to contracts/platform-profiles.json.

Every profile starts UNVERIFIED with conservative placeholder values.
require_verified() is the single gate later tools (reframe, platform_export,
release_package) use to refuse a not-yet-verified profile for anything but a
draft.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contracts.validate_contracts import validate

PROFILES_PATH = Path(__file__).resolve().parents[1] / "contracts" / "platform-profiles.json"


class PlatformProfileError(RuntimeError):
    """A platform profile could not be loaded, found, or is not verified."""


def load_profiles() -> dict[str, Any]:
    try:
        data = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PlatformProfileError(f"Plattform-Profile nicht lesbar: {error}") from error
    errors = validate("platform_profiles", data)
    if errors:
        raise PlatformProfileError(f"Plattform-Profile verletzen das Schema: {errors[0]}")
    return data


def get_profile(name: str) -> dict[str, Any]:
    profiles = load_profiles()["profiles"]
    if name not in profiles:
        raise PlatformProfileError(f"Unbekanntes Plattform-Profil: {name!r}")
    return dict(profiles[name])


def require_verified(name: str) -> dict[str, Any]:
    """Return the profile only if status is VERIFIED; raise otherwise."""
    profile = get_profile(name)
    if profile["status"] != "VERIFIED":
        raise PlatformProfileError(
            f"Profil {name!r} ist {profile['status']}, nicht VERIFIED."
        )
    return profile


def main() -> int:
    profiles = load_profiles()["profiles"]
    for name, profile in sorted(profiles.items()):
        print(f"{name}: {profile['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
