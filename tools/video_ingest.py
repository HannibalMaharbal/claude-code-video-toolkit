#!/usr/bin/env python3
"""Local, safe ingest and technical analysis for video and audio sources.

This tool deliberately accepts only local files, direct public media URLs, and
public single-video URLs handled by an already installed ``yt-dlp``. It never
passes cookies, credentials, or authentication options to a downloader.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


class IngestError(RuntimeError):
    """A source could not be safely ingested or inspected."""


class SourceType(StrEnum):
    LOCAL_FILE = "local_file"
    DIRECT_URL = "direct_url"
    YOUTUBE = "youtube"
    INSTAGRAM = "instagram"
    UNSUPPORTED_URL = "unsupported_url"


MEDIA_EXTENSIONS = {
    ".3gp", ".aac", ".avi", ".flac", ".m4a", ".mkv", ".mov", ".mp3",
    ".mp4", ".mpeg", ".mpg", ".oga", ".ogg", ".opus", ".wav", ".webm",
}
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"}
INSTAGRAM_HOSTS = {"instagram.com", "www.instagram.com", "m.instagram.com"}


def detect_source(source: str) -> SourceType:
    """Classify a source deterministically without contacting a platform."""
    parsed = urlparse(source)
    if parsed.scheme in {"http", "https"}:
        host = (parsed.hostname or "").lower().rstrip(".")
        if host in YOUTUBE_HOSTS:
            return SourceType.YOUTUBE
        if host in INSTAGRAM_HOSTS:
            return SourceType.INSTAGRAM
        if Path(parsed.path).suffix.lower() in MEDIA_EXTENSIONS:
            return SourceType.DIRECT_URL
        return SourceType.UNSUPPORTED_URL
    if parsed.scheme:
        return SourceType.UNSUPPORTED_URL
    path = Path(source).expanduser()
    if path.is_file() or path.suffix.lower() in MEDIA_EXTENSIONS:
        return SourceType.LOCAL_FILE
    return SourceType.UNSUPPORTED_URL


def sanitize_filename(value: str, fallback: str = "media") -> str:
    """Create a portable basename; never return a path supplied by a source."""
    basename = Path(value.replace("\\", "/")).name
    normalized = unicodedata.normalize("NFKD", basename)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    suffix = Path(ascii_name).suffix
    stem = ascii_name[: -len(suffix)] if suffix else ascii_name
    cleaned_stem = re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("._-")
    cleaned_suffix = re.sub(r"[^A-Za-z0-9.]", "", suffix)
    cleaned = f"{cleaned_stem}{cleaned_suffix}" if cleaned_stem else fallback
    if len(cleaned) > 100:
        cleaned = cleaned[:100]
    return cleaned


def safe_output_path(output_dir: Path, filename: str) -> Path:
    """Return an unused generated path contained directly in ``output_dir``."""
    root = output_dir.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = (root / sanitize_filename(filename)).resolve()
    try:
        target.relative_to(root)
    except ValueError as error:
        raise IngestError(
            "Generierter Ausgabepfad liegt außerhalb des Output-Verzeichnisses."
        ) from error
    if target.exists():
        raise IngestError(f"Ausgabedatei existiert bereits: {target.name}")
    return target


def _run(command: list[str], *, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as error:
        raise IngestError(f"Erforderliches lokales Werkzeug fehlt: {command[0]}") from error
    except subprocess.TimeoutExpired as error:
        raise IngestError(f"Lokales Werkzeug lief in ein Timeout: {command[0]}") from error
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip().splitlines()[-1] if error.stderr else "unbekannter Fehler"
        raise IngestError(f"{command[0]} fehlgeschlagen: {detail}") from error


def _as_float(value: object, label: str) -> float:
    try:
        parsed = float(str(value))
    except (TypeError, ValueError) as error:
        raise IngestError(f"Ungültiger {label}-Wert in den Medienmetadaten.") from error
    if not math.isfinite(parsed):
        raise IngestError(f"Ungültiger {label}-Wert in den Medienmetadaten.")
    return parsed


def _frame_rate(value: object) -> float | None:
    if value in (None, "", "0/0"):
        return None
    try:
        numerator, denominator = str(value).split("/", maxsplit=1)
        result = float(numerator) / float(denominator)
    except (ValueError, ZeroDivisionError):
        return None
    return result if result > 0 and math.isfinite(result) else None


def parse_probe(probe: dict[str, Any]) -> dict[str, object]:
    """Normalize ffprobe JSON and validate it has playable media streams."""
    format_data = probe.get("format")
    streams = probe.get("streams")
    if not isinstance(format_data, dict) or not isinstance(streams, list):
        raise IngestError("ffprobe lieferte unvollständige Medienmetadaten.")
    duration = _as_float(format_data.get("duration"), "Mediendauer")
    if duration <= 0:
        raise IngestError("Mediendauer muss größer als null sein.")
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    if video is None and audio is None:
        raise IngestError("ffprobe fand keinen Audio- oder Videostream.")
    width: int | None = None
    height: int | None = None
    if video is not None:
        try:
            width = int(video.get("width", 0))
            height = int(video.get("height", 0))
        except (TypeError, ValueError) as error:
            raise IngestError("Ungültige Videoauflösung in den Medienmetadaten.") from error
        if width <= 0 or height <= 0:
            raise IngestError("Ungültige Videoauflösung in den Medienmetadaten.")
    raw_tags = format_data.get("tags")
    tags: dict[str, object] = (
        {str(key): value for key, value in raw_tags.items()}
        if isinstance(raw_tags, dict)
        else {}
    )
    size = format_data.get("size")
    try:
        parsed_size = int(size) if size is not None else None
    except (TypeError, ValueError):
        parsed_size = None
    return {
        "title": str(tags.get("title", "")).strip() or None,
        "duration": duration,
        "container": str(format_data.get("format_name", "")) or None,
        "video_codec": (
            str(video.get("codec_name"))
            if video is not None and video.get("codec_name")
            else None
        ),
        "audio_codec": (
            str(audio.get("codec_name"))
            if audio is not None and audio.get("codec_name")
            else None
        ),
        "width": width,
        "height": height,
        "fps": _frame_rate(video.get("avg_frame_rate")) if video is not None else None,
        "filesize": parsed_size,
        "metadata": {"format_tags": tags},
    }


def probe_media(path: Path) -> dict[str, object]:
    """Validate a local media file with ffprobe and return normalized metadata."""
    if not path.is_file() or path.stat().st_size <= 0:
        raise IngestError("Mediendatei fehlt oder ist leer.")
    result = _run([
        "ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path),
    ])
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise IngestError("ffprobe lieferte kein gültiges JSON.") from error
    if not isinstance(parsed, dict):
        raise IngestError("ffprobe lieferte ungültige Medienmetadaten.")
    normalized = parse_probe(parsed)
    normalized["filesize"] = path.stat().st_size
    return normalized


def _is_youtube_collection(url: str) -> str | None:
    parsed = urlparse(url)
    if "list" in parse_qs(parsed.query):
        return "Playlist"
    parts = [part.lower() for part in parsed.path.split("/") if part]
    if any(part.startswith("@") or part in {"channel", "c", "user", "playlist"} for part in parts):
        return "Channel"
    return None


def _reject_private_network_target(host: str) -> None:
    """Reject non-public network targets before any direct URL fetch.

    Public direct media only: loopback, private, link-local, reserved,
    shared/CGNAT, multicast and unspecified IP literals, ``localhost``,
    ``.local`` mDNS names and single-label hostnames are refused. The URL's
    effective host (userinfo stripped by ``urlparse``) is used.
    """
    host = (host or "").strip().lower().rstrip(".")
    if not host:
        raise IngestError("Direkte Medien-URL ohne Host wird nicht unterstützt.")
    if host == "localhost" or host.endswith(".local"):
        raise IngestError(
            "Direkte Medien-URL auf lokale/private Netzwerkziele wird nicht unterstützt."
        )
    if "." not in host and ":" not in host:
        raise IngestError(
            "Direkte Medien-URL auf lokale Hostnamen ohne Domain wird nicht unterstützt."
        )
    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return
    if not address.is_global:
        raise IngestError(
            "Direkte Medien-URL auf private oder lokale Netzwerkziele wird nicht unterstützt."
        )


class _ValidatingRedirectHandler(HTTPRedirectHandler):
    """Refuse redirects to non-public targets, keeping every hop safe."""

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        parsed = urlparse(newurl)
        if parsed.scheme not in {"http", "https"}:
            raise IngestError(
                "Weiterleitung auf ein nicht unterstütztes Schema wird blockiert."
            )
        _reject_private_network_target(parsed.hostname or "")
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def _network_open(request: Request, timeout: int) -> Any:
    return build_opener(_ValidatingRedirectHandler()).open(request, timeout=timeout)


def download_direct_url(url: str, output_dir: Path) -> Path:
    """Download an unauthenticated direct media URL and validate before publish."""
    parsed = urlparse(url)
    _reject_private_network_target(parsed.hostname or "")
    filename = sanitize_filename(Path(parsed.path).name or "downloaded-media")
    target = safe_output_path(output_dir, filename)
    part = target.with_suffix(target.suffix + ".part")
    try:
        request = Request(url, headers={"User-Agent": "video-toolkit-ingest/1.0"})
        with _network_open(request, timeout=60) as response, part.open("wb") as handle:
            shutil.copyfileobj(response, handle)
        probe_media(part)
        part.replace(target)
        return target
    except (HTTPError, URLError, OSError, IngestError) as error:
        part.unlink(missing_ok=True)
        if isinstance(error, IngestError):
            raise IngestError(f"Download enthält keine gültige Mediendatei: {error}") from error
        raise IngestError(f"Download der direkten Medien-URL fehlgeschlagen: {error}") from error


def download_with_ytdlp(url: str, output_dir: Path, *, audio_only: bool = False) -> Path:
    """Download one public video using existing yt-dlp without credentials or cookies."""
    if shutil.which("yt-dlp") is None:
        raise IngestError(
            "yt-dlp ist lokal nicht installiert; Plattform-Ingest ist nicht verfügbar."
        )
    collection = _is_youtube_collection(url)
    if collection == "Playlist":
        raise IngestError("Playlist-URLs werden nicht automatisch heruntergeladen.")
    if collection == "Channel":
        raise IngestError("Channel-URLs werden nicht automatisch heruntergeladen.")
    root = output_dir.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    command = [
        "yt-dlp", "--no-playlist", "--no-part", "--paths", str(root),
        "--output", "%(id)s.%(ext)s", "--print", "after_move:filepath",
    ]
    if audio_only:
        command.extend(["--extract-audio", "--audio-format", "m4a"])
    command.extend(["--", url])
    try:
        result = _run(command, timeout=600)
    except IngestError as error:
        platform = "Instagram" if detect_source(url) is SourceType.INSTAGRAM else "YouTube"
        raise IngestError(
            f"yt-dlp konnte das öffentliche {platform}-Medium ohne Login nicht laden: {error}"
        ) from error
    paths = [Path(line.strip()).resolve() for line in result.stdout.splitlines() if line.strip()]
    if len(paths) != 1:
        raise IngestError("yt-dlp lieferte keinen eindeutigen lokalen Medienpfad.")
    path = paths[0]
    try:
        path.relative_to(root)
    except ValueError as error:
        raise IngestError(
            "yt-dlp lieferte einen Ausgabepfad außerhalb des Output-Verzeichnisses."
        ) from error
    try:
        probe_media(path)
    except IngestError:
        path.unlink(missing_ok=True)
        raise
    return path


def ingest_source(
    source: str, output_dir: Path, *, audio_only: bool = False
) -> tuple[SourceType, Path, str | None]:
    """Put supported input into the package's media directory without transcoding local media."""
    source_type = detect_source(source)
    media_dir = output_dir / "media"
    if source_type is SourceType.LOCAL_FILE:
        origin = Path(source).expanduser().resolve()
        if not origin.is_file():
            raise IngestError(f"Lokale Mediendatei nicht gefunden: {origin}")
        probe_media(origin)
        target = safe_output_path(media_dir, origin.name)
        try:
            shutil.copy2(origin, target)
        except OSError as error:
            raise IngestError(
                f"Lokale Mediendatei konnte nicht kopiert werden: {error}"
            ) from error
        return source_type, target, None
    if source_type is SourceType.DIRECT_URL:
        return source_type, download_direct_url(source, media_dir), source
    if source_type in {SourceType.YOUTUBE, SourceType.INSTAGRAM}:
        return source_type, download_with_ytdlp(source, media_dir, audio_only=audio_only), source
    raise IngestError(
        "Nicht unterstützte Quelle. Erlaubt sind lokale Medien, direkte Medien-URLs, "
        "YouTube und Instagram."
    )


def extract_audio(source: Path, output_dir: Path) -> Path:
    metadata = probe_media(source)
    if metadata["audio_codec"] is None:
        raise IngestError("Das Video enthält keine Audiospur für die Transkription.")
    target = safe_output_path(output_dir, "audio.m4a")
    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-n", "-i", str(source),
        "-map", "0:a:0", "-vn", "-c:a", "aac", str(target),
    ])
    probe_media(target)
    return target


def extract_frames(
    source: Path, output_dir: Path, *, interval: float, max_frames: int
) -> list[Path]:
    if interval <= 0 or max_frames < 1:
        raise IngestError("Frame-Intervall muss positiv und --max-frames mindestens eins sein.")
    metadata = probe_media(source)
    if metadata["video_codec"] is None:
        raise IngestError("Frame-Extraktion benötigt einen Videostream.")
    duration = float(str(metadata["duration"]))
    count = min(max_frames, max(1, math.ceil(duration / interval)))
    output_dir.mkdir(parents=True, exist_ok=True)
    frames: list[Path] = []
    for index in range(count):
        timestamp = min(index * interval, max(0.0, duration - 0.001))
        target = safe_output_path(output_dir, f"frame_{index + 1:04d}.jpg")
        _run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-n", "-ss", f"{timestamp:.3f}",
            "-i", str(source), "-frames:v", "1", "-q:v", "2", str(target),
        ])
        if not target.is_file() or target.stat().st_size <= 0:
            raise IngestError("FFmpeg erzeugte keinen gültigen Frame.")
        frames.append(target)
    return frames


def _write_json(path: Path, payload: dict[str, object]) -> None:
    if path.exists():
        raise IngestError(f"Ausgabedatei existiert bereits: {path.name}")
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def _cached_whisper_model(model: str) -> bool:
    cache = Path.home() / ".cache" / "huggingface" / "hub"
    return (cache / f"models--mlx-community--whisper-{model}-mlx").is_dir()


def _register_imported_asset(
    source: Path,
    *,
    rights_status: str,
    commercial_use: str,
    person_consent: str,
    license_ref: str | None,
) -> None:
    """Best-effort registry handoff; a registry failure never invalidates ingest."""
    try:
        from tools.asset_record import AssetRecordError, register_asset
    except ImportError as error:
        print(f"Asset-Registrierung: WARN — Modul nicht verfügbar: {error}", file=sys.stderr)
        return
    try:
        register_asset(
            source,
            rights_status=rights_status,
            commercial_use=commercial_use,
            person_consent=person_consent,
            license_ref=license_ref,
        )
    except (AssetRecordError, OSError) as error:
        print(f"Asset-Registrierung: WARN — {error}", file=sys.stderr)


def create_analysis_package(
    source: str,
    output_dir: Path,
    *,
    metadata_only: bool = False,
    audio: bool = False,
    transcribe: bool = False,
    srt: bool = False,
    vtt: bool = False,
    frames: bool = False,
    frame_interval: float = 5.0,
    max_frames: int = 12,
    audio_only: bool = False,
    whisper_model: str = "tiny",
    language: str | None = None,
    rights_status: str = "UNKNOWN",
    commercial_use: str = "unknown",
    person_consent: str = "unknown",
    license_ref: str | None = None,
) -> dict[str, object]:
    """Run the normalized local pipeline and return its deterministic manifest."""
    if (srt or vtt) and not transcribe:
        raise IngestError("--srt und --vtt benötigen --transcribe.")
    root = output_dir.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    source_type, local_path, source_url = ingest_source(source, root, audio_only=audio_only)
    _register_imported_asset(
        local_path,
        rights_status=rights_status,
        commercial_use=commercial_use,
        person_consent=person_consent,
        license_ref=license_ref,
    )
    media = probe_media(local_path)
    normalized: dict[str, object] = {
        "source_type": source_type.value,
        "source_url": source_url,
        "local_path": str(local_path),
        **media,
    }
    metadata_path = root / "metadata.json"
    _write_json(metadata_path, normalized)
    artifacts: dict[str, object] = {
        "metadata": metadata_path.name,
        "media": str(local_path.relative_to(root)),
    }
    if not metadata_only and (audio or transcribe):
        audio_path = extract_audio(local_path, root)
        artifacts["audio"] = audio_path.name
    else:
        audio_path = None
    if not metadata_only and frames:
        frame_paths = extract_frames(
            local_path, root / "frames", interval=frame_interval, max_frames=max_frames
        )
        artifacts["frames"] = [str(path.relative_to(root)) for path in frame_paths]
    if not metadata_only and transcribe:
        if audio_path is None:
            raise IngestError("Transkription benötigt eine extrahierte Audiodatei.")
        if not _cached_whisper_model(whisper_model):
            raise IngestError(
                f"Lokales MLX-Whisper-Modell '{whisper_model}' ist nicht im Cache; "
                "kein Download gestartet."
            )
        try:
            from tools import transcribe as transcript_tools
        except ModuleNotFoundError:  # Direct `python tools/video_ingest.py` execution.
            import transcribe as transcript_tools  # type: ignore[no-redef]

        transcript = transcript_tools.transcribe(
            str(audio_path), model=whisper_model, language=language, verbose=False
        )
        if not isinstance(transcript, dict):
            raise IngestError("MLX Whisper lieferte kein Transcript.")
        transcript_path = root / "transcript.json"
        _write_json(transcript_path, transcript)
        artifacts["transcript"] = transcript_path.name
        cues = transcript_tools.build_subtitle_cues(transcript)
        errors = transcript_tools.validate_subtitle_cues(cues)
        if not cues:
            errors.append("Transcript enthält keine Subtitle-Cues.")
        if errors:
            raise IngestError("Subtitle-QC fehlgeschlagen: " + "; ".join(errors))
        if srt:
            srt_path = safe_output_path(root, "subtitles.srt")
            transcript_tools.write_srt(cues, srt_path)
            errors = transcript_tools.validate_subtitle_file(srt_path)
            if errors:
                srt_path.unlink(missing_ok=True)
                raise IngestError("SRT-QC fehlgeschlagen: " + "; ".join(errors))
            artifacts["srt"] = srt_path.name
        if vtt:
            vtt_path = safe_output_path(root, "subtitles.vtt")
            transcript_tools.write_vtt(cues, vtt_path)
            errors = transcript_tools.validate_subtitle_file(vtt_path)
            if errors:
                vtt_path.unlink(missing_ok=True)
                raise IngestError("VTT-QC fehlgeschlagen: " + "; ".join(errors))
            artifacts["vtt"] = vtt_path.name
    analysis: dict[str, object] = {
        "schema_version": 1,
        "source": {"type": source_type.value, "url": source_url},
        "media": normalized,
        "artifacts": artifacts,
        "analysis": {"kind": "technical", "semantic_analysis": "not_run"},
    }
    analysis_path = root / "analysis.json"
    _write_json(analysis_path, analysis)
    return analysis


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ingest local/public media into a local analysis package"
    )
    parser.add_argument("--source", required=True, help="Local media file or supported public URL")
    parser.add_argument(
        "--output-dir", required=True, type=Path, help="New local analysis package directory"
    )
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument("--audio", action="store_true", help="Extract audio.m4a")
    parser.add_argument("--transcribe", action="store_true", help="Run cached local MLX Whisper")
    parser.add_argument(
        "--srt", action="store_true", help="Write QC-passed subtitles.srt (requires --transcribe)"
    )
    parser.add_argument(
        "--vtt", action="store_true", help="Write QC-passed subtitles.vtt (requires --transcribe)"
    )
    parser.add_argument("--frames", action="store_true", help="Extract bounded JPEG frames")
    parser.add_argument("--frame-interval", type=float, default=5.0)
    parser.add_argument("--max-frames", type=int, default=12)
    parser.add_argument(
        "--audio-only", action="store_true", help="Request audio-only public platform download"
    )
    parser.add_argument(
        "--whisper-model",
        default="tiny",
        choices=["tiny", "base", "small", "medium", "large-v3"],
    )
    parser.add_argument("--language", help="Optional Whisper language code")
    parser.add_argument(
        "--rights-status",
        default="UNKNOWN",
        choices=["OWNED", "LICENSED", "USER_PROVIDED", "PUBLIC_DOMAIN", "UNKNOWN", "RESTRICTED"],
        help="Explicit asset rights status; default is fail-closed UNKNOWN",
    )
    parser.add_argument(
        "--commercial-use",
        default="unknown",
        choices=["allowed", "restricted", "unknown"],
        help="Explicit commercial-use status; default is fail-closed unknown",
    )
    parser.add_argument(
        "--person-consent",
        default="unknown",
        choices=["not_needed", "documented", "missing", "unknown"],
        help="Explicit person-consent status; default is fail-closed unknown",
    )
    parser.add_argument("--license-ref", help="Optional license reference; no license is inferred")
    args = parser.parse_args()
    try:
        report = create_analysis_package(
            args.source, args.output_dir, metadata_only=args.metadata_only, audio=args.audio,
            transcribe=args.transcribe, srt=args.srt, vtt=args.vtt, frames=args.frames,
            frame_interval=args.frame_interval, max_frames=args.max_frames,
            audio_only=args.audio_only, whisper_model=args.whisper_model, language=args.language,
            rights_status=args.rights_status, commercial_use=args.commercial_use,
            person_consent=args.person_consent, license_ref=args.license_ref,
        )
    except IngestError as error:
        print(f"Video ingest: FAIL — {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
