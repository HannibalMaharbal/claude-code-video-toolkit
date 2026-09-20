from __future__ import annotations

import pytest

from contracts.validate_contracts import validate
from tools import platform_profiles

EXPECTED_PROFILE_NAMES = {
    "youtube_long",
    "youtube_short",
    "instagram_reel",
    "instagram_feed",
    "facebook_video",
    "tiktok",
    "x_video",
    "website_hero",
    "ecommerce_video",
    "ecommerce_image",
    "ad_16x9",
    "ad_1x1",
    "ad_9x16",
}


def test_platform_profiles_validate_against_schema() -> None:
    data = platform_profiles.load_profiles()
    assert validate("platform_profiles", data) == []


def test_all_expected_profiles_present() -> None:
    data = platform_profiles.load_profiles()
    assert set(data["profiles"]) == EXPECTED_PROFILE_NAMES


def test_every_profile_starts_unverified() -> None:
    data = platform_profiles.load_profiles()
    for name, profile in data["profiles"].items():
        assert profile["status"] == "UNVERIFIED", name
        assert profile["verified_at"] is None, name
        assert profile["source_url"] is None, name


def test_nine_sixteen_profiles_share_the_universal_safe_zone() -> None:
    data = platform_profiles.load_profiles()
    expected = {"width": 900, "height": 1400, "x": 90, "y": 260}
    for name, profile in data["profiles"].items():
        if profile["aspect_ratio"] == "9:16" and profile["resolution"] == {
            "width": 1080,
            "height": 1920,
        }:
            assert profile["safe_zone"] == expected, name


def test_image_profiles_have_no_duration_fps_or_loudness() -> None:
    data = platform_profiles.load_profiles()
    for name, profile in data["profiles"].items():
        if profile["media_type"] == "image":
            assert profile["max_duration_s"] is None, name
            assert profile["fps"] is None, name
            assert profile["loudness_target_lufs"] is None, name


def test_get_profile_returns_a_copy() -> None:
    profile = platform_profiles.get_profile("tiktok")
    profile["status"] = "VERIFIED"
    assert platform_profiles.get_profile("tiktok")["status"] == "UNVERIFIED"


def test_get_profile_rejects_unknown_name() -> None:
    with pytest.raises(platform_profiles.PlatformProfileError, match="Unbekanntes"):
        platform_profiles.get_profile("not_a_real_platform")


def test_require_verified_rejects_unverified_profile() -> None:
    with pytest.raises(platform_profiles.PlatformProfileError, match="UNVERIFIED"):
        platform_profiles.require_verified("tiktok")


def test_schema_rejects_video_profile_missing_fps() -> None:
    data = platform_profiles.load_profiles()
    broken = dict(data)
    broken["profiles"] = dict(data["profiles"])
    broken["profiles"]["tiktok"] = {**data["profiles"]["tiktok"], "fps": None}
    assert validate("platform_profiles", broken) != []


def test_schema_rejects_verified_profile_without_source_url() -> None:
    data = platform_profiles.load_profiles()
    broken = dict(data)
    broken["profiles"] = dict(data["profiles"])
    broken["profiles"]["tiktok"] = {
        **data["profiles"]["tiktok"],
        "status": "VERIFIED",
        "verified_at": "2026-09-21T00:00:00+00:00",
    }
    assert validate("platform_profiles", broken) != []
