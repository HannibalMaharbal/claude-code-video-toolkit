import json
import subprocess
from io import BytesIO
from pathlib import Path

import pytest

from tools.video_ingest import (
    IngestError,
    SourceType,
    detect_source,
    extract_frames,
    parse_probe,
    safe_output_path,
    sanitize_filename,
)


def test_source_detection_is_deterministic(tmp_path: Path) -> None:
    local = tmp_path / "source.mp4"
    local.write_bytes(b"media")

    assert detect_source(str(local)) is SourceType.LOCAL_FILE
    assert detect_source("https://cdn.example.test/movie.mp4?download=1") is SourceType.DIRECT_URL
    assert detect_source("https://www.youtube.com/watch?v=abc123") is SourceType.YOUTUBE
    assert detect_source("https://youtu.be/abc123") is SourceType.YOUTUBE
    assert detect_source("https://www.instagram.com/reel/abc123/") is SourceType.INSTAGRAM
    assert detect_source("https://example.test/article") is SourceType.UNSUPPORTED_URL
    assert detect_source("ftp://example.test/movie.mp4") is SourceType.UNSUPPORTED_URL


def test_sanitize_filename_and_output_path_are_contained(tmp_path: Path) -> None:
    assert sanitize_filename("../../Grüße: Video?.mp4") == "Grue_Video.mp4"
    output = tmp_path / "package"
    candidate = safe_output_path(output, "../escape.mp4")
    assert candidate.parent == output.resolve()
    assert candidate.name == "escape.mp4"
    with pytest.raises(IngestError, match="existiert bereits"):
        candidate.write_bytes(b"x")
        safe_output_path(output, "escape.mp4")


def test_parse_probe_normalizes_video_and_audio_metadata() -> None:
    result = parse_probe(
        {
            "format": {
                "duration": "12.5",
                "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
                "size": "1234",
                "tags": {"title": "Grüße"},
            },
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1920,
                    "height": 1080,
                    "avg_frame_rate": "30000/1001",
                },
                {"codec_type": "audio", "codec_name": "aac"},
            ],
        }
    )
    assert result["duration"] == 12.5
    assert result["width"] == 1920
    assert result["height"] == 1080
    assert result["video_codec"] == "h264"
    assert result["audio_codec"] == "aac"
    assert result["fps"] == pytest.approx(29.970, rel=1e-3)


def test_parse_probe_accepts_audio_only_and_rejects_invalid_media() -> None:
    audio = parse_probe(
        {
            "format": {"duration": "1", "format_name": "wav"},
            "streams": [{"codec_type": "audio", "codec_name": "pcm_s16le"}],
        }
    )
    assert audio["audio_codec"] == "pcm_s16le"
    assert audio["video_codec"] is None
    with pytest.raises(IngestError, match="keinen Audio- oder Videostream"):
        parse_probe({"format": {"duration": "1"}, "streams": []})
    with pytest.raises(IngestError, match="Mediendauer"):
        parse_probe({"format": {"duration": "0"}, "streams": [{"codec_type": "audio"}]})


def test_probe_media_rejects_corrupt_file(tmp_path: Path) -> None:
    from tools.video_ingest import probe_media

    corrupt = tmp_path / "broken.mp4"
    corrupt.write_bytes(b"not media")
    with pytest.raises(IngestError, match="ffprobe"):
        probe_media(corrupt)


def test_download_failure_removes_partial_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools.video_ingest import download_direct_url

    def fail(*_args: object, **_kwargs: object) -> object:
        raise OSError("network unavailable")

    monkeypatch.setattr("tools.video_ingest._network_open", fail)
    with pytest.raises(IngestError, match="Download"):
        download_direct_url("https://cdn.example.test/video.mp4", tmp_path)
    assert not list(tmp_path.glob("*.part"))


def test_direct_url_http_success_is_not_accepted_without_media_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools.video_ingest import download_direct_url

    class Response(BytesIO):
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *_args: object) -> None:
            self.close()

    monkeypatch.setattr("tools.video_ingest._network_open", lambda *_a, **_k: Response(b"html"))
    monkeypatch.setattr(
        "tools.video_ingest.probe_media",
        lambda _path: (_ for _ in ()).throw(IngestError("ffprobe fand keinen Stream")),
    )
    with pytest.raises(IngestError, match="keine gültige Mediendatei"):
        download_direct_url("https://cdn.example.test/video.mp4", tmp_path)
    assert not list(tmp_path.iterdir())


def test_ytdlp_failure_has_clear_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tools.video_ingest import download_with_ytdlp

    monkeypatch.setattr("tools.video_ingest.shutil.which", lambda _name: "/usr/local/bin/yt-dlp")

    def fail(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 1, "", "not available")

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(IngestError, match="yt-dlp"):
        download_with_ytdlp("https://youtube.com/watch?v=abc", tmp_path)


def test_youtube_playlist_and_channel_are_rejected(tmp_path: Path) -> None:
    from tools.video_ingest import download_with_ytdlp

    with pytest.raises(IngestError, match="Playlist"):
        download_with_ytdlp("https://youtube.com/watch?v=a&list=b", tmp_path)
    with pytest.raises(IngestError, match="Channel"):
        download_with_ytdlp("https://youtube.com/@channel", tmp_path)


def test_extract_frames_respects_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    frames = tmp_path / "frames"
    calls: list[list[str]] = []

    monkeypatch.setattr(
        "tools.video_ingest.probe_media",
        lambda _path: {"duration": 9.0, "video_codec": "h264"},
    )

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        Path(command[-1]).write_bytes(b"jpg")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    extracted = extract_frames(source, frames, interval=2.0, max_frames=3)
    assert [item.name for item in extracted] == [
        "frame_0001.jpg",
        "frame_0002.jpg",
        "frame_0003.jpg",
    ]
    assert len(calls) == 3


def test_video_without_audio_is_not_transcribable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools.video_ingest import extract_audio

    source = tmp_path / "silent.mp4"
    source.write_bytes(b"video")
    monkeypatch.setattr(
        "tools.video_ingest.probe_media",
        lambda _path: {"audio_codec": None, "video_codec": "h264", "duration": 1.0},
    )
    with pytest.raises(IngestError, match="keine Audiospur"):
        extract_audio(source, tmp_path)


def test_existing_subtitle_pipeline_regression(tmp_path: Path) -> None:
    from tools.transcribe import (
        build_subtitle_cues,
        validate_subtitle_cues,
        validate_subtitle_file,
        write_srt,
        write_vtt,
    )

    payload = {"segments": [{"start": 0, "end": 3, "text": "Grüße aus der Video-Pipeline."}]}
    cues = build_subtitle_cues(payload)
    assert validate_subtitle_cues(cues) == []
    srt = tmp_path / "subtitles.srt"
    vtt = tmp_path / "subtitles.vtt"
    write_srt(cues, srt)
    write_vtt(cues, vtt)
    assert validate_subtitle_file(srt) == []
    assert validate_subtitle_file(vtt) == []


def test_direct_url_rejects_local_and_private_network_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools.video_ingest import download_direct_url

    targets = [
        "http://localhost/video.mp4",
        "http://127.0.0.1/video.mp4",
        "http://[::1]/video.mp4",
        "http://192.168.1.10/video.mp4",
        "http://10.0.0.5/video.mp4",
        "http://172.16.0.1/video.mp4",
        "http://169.254.169.254/video.mp4",
        "http://intranet/video.mp4",
        "http://printer.local/video.mp4",
    ]
    opened: list[str] = []

    def record_open(*_args: object, **_kwargs: object) -> object:
        opened.append(str(_args[0]))
        raise AssertionError("Auf privates Ziel wurde ein Netzwerkzugriff versucht.")

    monkeypatch.setattr("tools.video_ingest._network_open", record_open)
    for url in targets:
        with pytest.raises(IngestError):
            download_direct_url(url, tmp_path)
        assert not list(tmp_path.glob("*.part"))
    assert opened == []


def test_direct_url_public_host_still_reaches_network_layer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools.video_ingest import download_direct_url

    opened: list[str] = []

    def record_open(request: object, **_kwargs: object) -> object:
        opened.append(str(getattr(request, "full_url", request)))
        raise OSError("downstream unavailable")

    monkeypatch.setattr("tools.video_ingest._network_open", record_open)
    with pytest.raises(IngestError, match="Download"):
        download_direct_url("https://cdn.example.test/movie.mp4", tmp_path)
    assert opened and "cdn.example.test" in opened[0]
    assert not list(tmp_path.iterdir())


def test_direct_url_rejects_redirect_to_private_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from urllib.request import Request

    from tools.video_ingest import IngestError, _ValidatingRedirectHandler

    handler = _ValidatingRedirectHandler()

    class FakeRequest(Request):
        def __init__(self) -> None:
            super().__init__("https://public.example.test/video.mp4")
            self.unredirected_hdrs = {}

    with pytest.raises(IngestError, match="private|blockiert|nicht unterstützt"):
        handler.redirect_request(
            FakeRequest(), None, 302, "Found", {"location": "http://127.0.0.1/video.mp4"},
            "http://127.0.0.1/video.mp4",
        )


def test_sanitize_filename_caps_length_without_uncaught_oserror(tmp_path: Path) -> None:
    huge = "x" * 1300 + ".mp4"
    sanitized = sanitize_filename(huge)
    assert len(sanitized) <= 100
    target = safe_output_path(tmp_path / "pkg", huge)
    assert len(target.name) <= 100
    assert target.parent == (tmp_path / "pkg").resolve()


def test_metadata_json_is_utf8_safe(tmp_path: Path) -> None:
    target = tmp_path / "metadata.json"
    target.write_text(json.dumps({"title": "München 🎬"}, ensure_ascii=False), encoding="utf-8")
    assert json.loads(target.read_text(encoding="utf-8"))["title"] == "München 🎬"


def test_successful_ingest_registers_asset_without_changing_analysis_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import asset_record
    from tools.video_ingest import create_analysis_package

    media = tmp_path / "media.mp4"
    media.write_bytes(b"media")
    registered: list[tuple[Path, dict[str, object]]] = []
    def fake_ingest(
        _source: str, output_dir: Path, **_kwargs: object
    ) -> tuple[SourceType, Path, None]:
        imported = output_dir / "media" / media.name
        imported.parent.mkdir(parents=True, exist_ok=True)
        imported.write_bytes(media.read_bytes())
        return SourceType.LOCAL_FILE, imported, None

    monkeypatch.setattr("tools.video_ingest.ingest_source", fake_ingest)
    monkeypatch.setattr("tools.video_ingest.probe_media", lambda _path: {
        "duration": 1.0, "container": "mp4", "video_codec": "h264", "audio_codec": "aac",
        "width": 10, "height": 10, "fps": 25.0,
    })
    monkeypatch.setattr(
        asset_record,
        "register_asset",
        lambda path, **kwargs: registered.append((path, kwargs)) or {"asset_id": "ast_test"},
    )

    report = create_analysis_package(
        str(media), tmp_path / "package", rights_status="LICENSED", commercial_use="allowed",
        person_consent="not_needed", license_ref="license-1",
    )

    assert report["artifacts"] == {
        "metadata": "metadata.json",
        "media": "media/media.mp4",
    }
    assert registered == [(
        tmp_path / "package" / "media" / "media.mp4",
        {
            "rights_status": "LICENSED", "commercial_use": "allowed",
            "person_consent": "not_needed", "license_ref": "license-1",
        },
    )]


def test_asset_registration_failure_does_not_fail_existing_ingest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from tools import asset_record
    from tools.video_ingest import create_analysis_package

    media = tmp_path / "media.mp4"
    media.write_bytes(b"media")

    def fake_ingest(
        _source: str, output_dir: Path, **_kwargs: object
    ) -> tuple[SourceType, Path, None]:
        imported = output_dir / "media" / media.name
        imported.parent.mkdir(parents=True, exist_ok=True)
        imported.write_bytes(media.read_bytes())
        return SourceType.LOCAL_FILE, imported, None

    monkeypatch.setattr("tools.video_ingest.ingest_source", fake_ingest)
    monkeypatch.setattr("tools.video_ingest.probe_media", lambda _path: {
        "duration": 1.0, "container": "mp4", "video_codec": "h264", "audio_codec": "aac",
        "width": 10, "height": 10, "fps": 25.0,
    })
    monkeypatch.setattr(
        asset_record,
        "register_asset",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            asset_record.AssetRecordError("registry refused")
        ),
    )

    report = create_analysis_package(str(media), tmp_path / "package")

    assert report["artifacts"]["media"] == "media/media.mp4"
    assert "Asset-Registrierung: WARN — registry refused" in capsys.readouterr().err
