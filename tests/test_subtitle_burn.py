from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tools import subtitle_burn

SRT_CONTENT = (
    "1\n00:00:00,000 --> 00:00:01,000\nHello\n\n"
    "2\n00:00:01,200 --> 00:00:02,000\nWorld\nSecond line\n"
)
VTT_CONTENT = (
    "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello\n\n00:00:01.200 --> 00:00:02.000\nWorld\n"
)


def test_parse_subtitle_cues_srt(tmp_path: Path) -> None:
    srt = tmp_path / "cues.srt"
    srt.write_text(SRT_CONTENT, encoding="utf-8")

    cues = subtitle_burn.parse_subtitle_cues(srt)

    assert [cue["text"] for cue in cues] == ["Hello", "World\nSecond line"]
    assert cues[0]["start"] == 0.0
    assert cues[0]["end"] == 1.0
    assert cues[1]["start"] == 1.2


def test_parse_subtitle_cues_vtt(tmp_path: Path) -> None:
    vtt = tmp_path / "cues.vtt"
    vtt.write_text(VTT_CONTENT, encoding="utf-8")

    cues = subtitle_burn.parse_subtitle_cues(vtt)

    assert [cue["text"] for cue in cues] == ["Hello", "World"]


def test_parse_subtitle_cues_rejects_invalid_file(tmp_path: Path) -> None:
    srt = tmp_path / "broken.srt"
    srt.write_text("not a subtitle file", encoding="utf-8")

    with pytest.raises(subtitle_burn.SubtitleBurnError, match="QC"):
        subtitle_burn.parse_subtitle_cues(srt)


def test_font_data_uri_none_when_not_given() -> None:
    assert subtitle_burn._font_data_uri(None) is None


def test_font_data_uri_missing_file_raises() -> None:
    with pytest.raises(subtitle_burn.SubtitleBurnError, match="nicht gefunden"):
        subtitle_burn._font_data_uri("/no/such/font.ttf")


def test_font_data_uri_encodes_local_font(tmp_path: Path) -> None:
    font_path = tmp_path / "font.ttf"
    font_path.write_bytes(b"fake-font-bytes")

    uri = subtitle_burn._font_data_uri(str(font_path))

    assert uri is not None
    assert uri.startswith("data:font/ttf;base64,")


def test_build_props_structure(tmp_path: Path, monkeypatch) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake video bytes")
    monkeypatch.setattr(
        subtitle_burn,
        "probe_media",
        lambda _path: {"fps": 30.0, "duration": 2.0, "width": 640, "height": 360},
    )
    cues = [{"text": "Hi", "start": 0.0, "end": 1.0}]

    props = subtitle_burn.build_props(video, cues, {"color": "#ff0000"})

    assert props["videoSrc"] == "video.mp4"
    assert props["videoFps"] == 30.0
    assert props["videoDurationInFrames"] == 60
    assert props["cues"] == [{"text": "Hi", "startMs": 0, "endMs": 1000}]
    assert props["style"]["color"] == "#ff0000"
    assert props["style"]["fontFamily"] == "Arial"


def test_register_burn_output_inherits_rights(tmp_path: Path, monkeypatch) -> None:
    from tools import asset_record

    monkeypatch.setattr(asset_record, "ASSET_ROOT", tmp_path / "asset-store")
    monkeypatch.setattr(
        asset_record,
        "probe_media",
        lambda _p: {"duration": 1.0, "container": "mp4", "video_codec": "h264"},
    )

    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake video bytes")
    srt = tmp_path / "cues.srt"
    srt.write_text(SRT_CONTENT, encoding="utf-8")
    output = tmp_path / "burned.mp4"
    output.write_bytes(b"fake burned video bytes")

    record = subtitle_burn.register_burn_output(video, srt, output)

    assert record["role"] == "MASTER"
    assert record["derivation"]["operation"] == "subtitle_burn_in"
    assert len(record["parent_ids"]) == 2


@pytest.mark.integration
def test_burn_in_renders_video_with_audio(tmp_path: Path) -> None:
    video = tmp_path / "source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x240:rate=10",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000",
            "-t",
            "1.5",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(video),
        ],
        check=True,
        capture_output=True,
    )
    srt = tmp_path / "cues.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nHallo Welt\n", encoding="utf-8")
    output = tmp_path / "burned.mp4"

    subtitle_burn.burn_in(video, srt, output)

    assert output.is_file() and output.stat().st_size > 0
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(output)],
        check=True,
        capture_output=True,
        text=True,
    )
    import json

    streams = json.loads(probe.stdout)["streams"]
    assert any(stream["codec_type"] == "video" for stream in streams)
    assert any(stream["codec_type"] == "audio" for stream in streams)
