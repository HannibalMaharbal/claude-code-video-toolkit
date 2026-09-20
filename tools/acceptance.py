#!/usr/bin/env python3
# ruff: noqa: E501
"""Run the internal-only acceptance baseline against installed local tooling.

This is deliberately a measurement harness: it creates all inputs in a temporary
directory, invokes existing project tools, and never enables egress or repairs a
missing capability.  Daily report files are created once and never replaced.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import json
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


ROOT = Path(__file__).resolve().parents[1]
REPORT_STEM = f"ACCEPTANCE-{date.today().isoformat()}"
REPORT_MARKDOWN = ROOT / "docs" / f"{REPORT_STEM}.md"
REPORT_JSON = ROOT / "docs" / f"{REPORT_STEM}.json"
STACK_MANIFEST = ROOT / "contracts" / "stack-manifest.json"
CAPABILITY_IDS = tuple(f"F{number:02d}" for number in range(1, 16))


@dataclass(frozen=True)
class Result:
    capability: str
    status: str
    reason: str
    measurements: dict[str, Any]
    duration_s: float


class MissingCapability(RuntimeError):
    """A required local component or a repository capability is absent."""

    def __init__(self, message: str, measurements: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.measurements = measurements or {}


def _run(command: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout)


def _which(command: str) -> str:
    value = shutil.which(command)
    if value is None:
        raise MissingCapability(f"Lokales Werkzeug fehlt: {command}.")
    return value


def _ffprobe(path: Path) -> dict[str, Any]:
    _which("ffprobe")
    result = _run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]
    )
    return json.loads(result.stdout)


def _duration(path: Path) -> float:
    return float(_ffprobe(path)["format"]["duration"])


def _video_stream(path: Path) -> dict[str, Any]:
    return next(
        stream for stream in _ffprobe(path)["streams"] if stream.get("codec_type") == "video"
    )


def _audio_stream(path: Path) -> dict[str, Any]:
    return next(
        stream for stream in _ffprobe(path)["streams"] if stream.get("codec_type") == "audio"
    )


def _result(capability: str, operation: Callable[[], tuple[str, dict[str, Any]]]) -> Result:
    started = time.monotonic()
    try:
        reason, measurements = operation()
        status = "PASS"
    except MissingCapability as error:
        status, reason, measurements = "MISSING", str(error), error.measurements
    except Exception as error:  # An existing capability was actually exercised and failed.
        status, reason, measurements = "FAIL", f"{type(error).__name__}: {error}", {}
    return Result(capability, status, reason, measurements, round(time.monotonic() - started, 3))


def _make_material(work: Path) -> dict[str, Path]:
    """Create deterministic local image, video, audio, and silence test inputs."""
    _which("ffmpeg")
    try:
        from PIL import Image
    except ImportError as error:
        raise MissingCapability("Pillow ist nicht installiert; PNG-Testmaterial fehlt.") from error

    image = work / "input.png"
    Image.new("RGBA", (640, 480), (40, 80, 160, 180)).save(image)
    video = work / "input.mp4"
    _run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=640x360:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000",
            "-t",
            "3",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(video),
        ]
    )
    paused_audio = work / "paused.wav"
    _run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=0.7",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=mono:d=0.8",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=660:sample_rate=48000:duration=0.7",
            "-filter_complex",
            "[0:a][1:a][2:a]concat=n=3:v=0:a=1",
            "-c:a",
            "pcm_s16le",
            str(paused_audio),
        ]
    )
    paused_video = work / "paused.mp4"
    _run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=640x360:rate=30:duration=2.2",
            "-i",
            str(paused_audio),
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(paused_video),
        ]
    )
    return {"image": image, "video": video, "paused_video": paused_video}


def _f01(work: Path, material: dict[str, Path]) -> tuple[str, dict[str, Any]]:
    try:
        from PIL import Image, ImageEnhance
    except ImportError as error:
        raise MissingCapability("Pillow ist nicht installiert.") from error
    source = Image.open(material["image"])
    transformed = ImageEnhance.Color(
        source.rotate(90, expand=True).crop((10, 10, 470, 630)).resize((300, 200))
    ).enhance(1.3)
    outputs = {"png": work / "image.png", "jpg": work / "image.jpg", "webp": work / "image.webp"}
    transformed.save(outputs["png"])
    transformed.convert("RGB").save(outputs["jpg"])
    transformed.save(outputs["webp"])
    raw_alpha = Image.open(outputs["png"]).getchannel("A").getextrema()
    if not isinstance(raw_alpha, tuple):
        raise RuntimeError("Alpha-Kanal hat keinen Wertebereich.")
    alpha = cast(tuple[int, int], raw_alpha)
    if (
        not all(path.is_file() and path.stat().st_size > 0 for path in outputs.values())
        or alpha[0] >= 255
    ):
        raise RuntimeError("Bildtransformation oder Transparenz nicht nachweisbar.")
    return "Pillow-Transformationen und drei Formate gerendert.", {
        "size": list(transformed.size),
        "alpha_range": list(alpha),
        "formats": list(outputs),
    }


def _f02(work: Path, material: dict[str, Path]) -> tuple[str, dict[str, Any]]:
    from tools.layout_render import render

    spec_path = work / "f02-spec.json"
    spec = {
        "canvas": {"preset": "custom", "width": 400, "height": 200},
        "layers": [
            {
                "id": "bg",
                "type": "shape",
                "color": "#ffffff",
                "x": 0,
                "y": 0,
                "width": 400,
                "height": 200,
            },
            {
                "id": "image",
                "type": "image",
                "path": str(material["image"]),
                "fit": "cover",
                "x": 0,
                "y": 0,
                "width": 400,
                "height": 120,
            },
            {
                "id": "label",
                "type": "text",
                "content": "Acceptance F02",
                "size_pt": 18,
                "color": "#000000",
                "x": 10,
                "y": 130,
                "width": 380,
                "height": 50,
            },
        ],
    }
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    png = work / "f02.png"
    render(spec_path, png)
    if not png.is_file() or png.stat().st_size == 0:
        raise RuntimeError("Layout-Renderer erzeugte keine PNG-Datei.")
    return "Spec-JSON-Vertrag (Form+Bild+Text) via Playwright/Chromium gerendert.", {
        "png_bytes": png.stat().st_size
    }


def _f03(work: Path, __: dict[str, Path]) -> tuple[str, dict[str, Any]]:
    from tools.layout_render import render, set_value

    flyer_dir = work / "flyer"
    shutil.copytree(ROOT / "templates" / "layout", flyer_dir)
    spec_path = flyer_dir / "flyer-a5.json"

    png_1, pdf_1 = work / "flyer-1.png", work / "flyer-1.pdf"
    render(spec_path, png_1, pdf_1)
    if not png_1.is_file() or not pdf_1.is_file():
        raise RuntimeError("Flyer-Renderer erzeugte kein PNG/PDF.")
    first_png = png_1.read_bytes()

    set_value(spec_path, "headline", "content=Geänderte Überschrift für run2")
    set_value(spec_path, "headline", "height=90")
    set_value(spec_path, "headline", "font_family=Georgia")
    png_2 = work / "flyer-2.png"
    render(spec_path, png_2)
    second_png = png_2.read_bytes()
    if first_png == second_png:
        raise RuntimeError("Geänderter Flyer erzeugte eine identische Ausgabe.")

    return (
        "A5-Flyer-Vorlage als PNG+PDF gerendert; Text/Höhe/Schrift per `set` geändert und "
        "neu gerendert unterscheidet sich vom ersten Lauf.",
        {"png_1_bytes": len(first_png), "png_2_bytes": len(second_png)},
    )


def _f04(work: Path, material: dict[str, Path]) -> tuple[str, dict[str, Any]]:
    clips: list[Path] = []
    for index, (start, end) in enumerate(((0.0, 0.8), (1.5, 2.5))):
        clip = work / f"clip-{index}.mp4"
        _run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                str(start),
                "-to",
                str(end),
                "-i",
                str(material["video"]),
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                str(clip),
            ]
        )
        clips.append(clip)
    listing = work / "concat.txt"
    listing.write_text("".join(f"file '{clip.as_posix()}'\n" for clip in clips), encoding="utf-8")
    output = work / "cut.mp4"
    _run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(listing),
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(output),
        ]
    )
    duration = _duration(output)
    fps = 30.0
    expected = 1.8
    if abs(duration - expected) > 1 / fps + 0.05:
        raise RuntimeError(f"Dauer {duration:.3f}s liegt nicht innerhalb ±1 Frame von {expected}s.")
    _audio_stream(output)
    return "Trim/Concat mit Audio gerendert.", {
        "duration_s": duration,
        "expected_s": expected,
        "fps": fps,
    }


def _f05(work: Path, material: dict[str, Path]) -> tuple[str, dict[str, Any]]:
    output = work / "vertical.mp4"
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(material["video"]),
            "-filter_complex",
            "[0:v]split=2[first][second];[first]trim=duration=1.5,setpts=PTS-STARTPTS[a];"
            "[second]trim=start=1.5:end=3,setpts=PTS-STARTPTS[b];[a][b]xfade=transition=fade:duration=0.3:offset=1.2[fade];"
            "[fade]scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
            "setpts=0.9*PTS,drawbox=x=20:y=20:w=220:h=80:color=red@0.6:t=fill[v];[0:a]atempo=1.111[a]",
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(output),
        ]
    )
    stream = _video_stream(output)
    if (stream["width"], stream["height"]) != (1080, 1920):
        raise RuntimeError("16:9→9:16-Reframe hat nicht die Zielauflösung.")
    return "Reframe, Tempo, XFade-Blende und Overlay gerendert.", {
        "width": stream["width"],
        "height": stream["height"],
        "duration_s": _duration(output),
    }


def _f06(work: Path, material: dict[str, Path]) -> tuple[str, dict[str, Any]]:
    from tools import silence_cutter

    silences = silence_cutter.detect_silences(str(material["paused_video"]), min_duration=0.5)
    segments = silence_cutter.compute_segments(
        silences, silence_cutter.get_video_duration(str(material["paused_video"]))
    )
    output = work / "silence-cut.mp4"
    if not silences or not silence_cutter.cut_segments(
        str(material["paused_video"]), segments, str(output)
    ):
        raise RuntimeError("Silence-Cutter erkannte oder renderte keine Segmente.")
    return "Silence-Cutter auf lokales Pausenmaterial angewendet.", {
        "silences": len(silences),
        "segments": len(segments),
        "duration_s": _duration(output),
    }


def _f07(work: Path, material: dict[str, Path]) -> tuple[str, dict[str, Any]]:
    from tools.media_validation import validate_audio

    voice = work / "voice.wav"
    music = work / "music.wav"
    mixed = work / "mixed.m4a"
    _run(["ffmpeg", "-y", "-i", str(material["video"]), "-vn", "-c:a", "pcm_s16le", str(voice)])
    _run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=220:sample_rate=48000:duration=3",
            "-c:a",
            "pcm_s16le",
            str(music),
        ]
    )
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(voice),
            "-i",
            str(music),
            "-filter_complex",
            "[0:a]afade=t=in:st=0:d=0.1,afade=t=out:st=2.7:d=0.2[v];[1:a]volume=0.12[m];[v][m]amix=inputs=2,"
            "loudnorm=I=-16:TP=-1.5:LRA=11[a]",
            "-map",
            "[a]",
            "-c:a",
            "aac",
            str(mixed),
        ]
    )
    report = validate_audio(mixed)
    loudness = float(report.details["loudnessLufs"])
    if abs(loudness - (-16)) > 2.5:
        raise RuntimeError(f"Gemessene Lautheit {loudness} LUFS weicht zu weit vom Ziel ab.")
    return "Sprache/Musik, Fades, Normalisierung und M4A-Konvertierung geprüft.", {
        "loudness_lufs": loudness,
        "codec": report.codec,
        "duration_s": report.duration,
    }


def _cached_kokoro() -> bool:
    cache = Path.home() / ".cache" / "kokoro-onnx"
    return (cache / "kokoro-v1.0.onnx").is_file() and (cache / "voices-v1.0.bin").is_file()


def _f08(work: Path, _: dict[str, Path]) -> tuple[str, dict[str, Any]]:
    if not _cached_kokoro():
        raise MissingCapability(
            "Kokoro-Modell/Voices sind nicht lokal gecacht; kein Download gestartet."
        )
    generate_audio = importlib.import_module("tools.kokoro_tts").generate_audio

    de = generate_audio(
        "Guten Tag, dies ist ein lokaler deutscher Test.",
        str(work / "de.wav"),
        voice="am_michael",
        verbose=False,
    )
    en = generate_audio(
        "Hello, this is a local English test.", str(work / "en.wav"), voice="bf_emma", verbose=False
    )
    if not de.get("success") or not en.get("success"):
        raise RuntimeError("Kokoro lieferte keinen erfolgreichen WAV-Output.")
    return "Lokale Kokoro-Ausgabe für Deutsch und Englisch erzeugt.", {
        "de_duration_s": de.get("duration_seconds"),
        "en_duration_s": en.get("duration_seconds"),
    }


def _cached_whisper(model: str = "tiny") -> bool:
    from tools.video_ingest import _cached_whisper_model

    return _cached_whisper_model(model)


def _f09(work: Path, _: dict[str, Path]) -> tuple[str, dict[str, Any]]:
    if not _cached_kokoro():
        raise MissingCapability(
            "Kein lokales TTS-Testmaterial möglich, weil Kokoro nicht vollständig gecacht ist."
        )
    if not _cached_whisper("tiny"):
        raise MissingCapability(
            "MLX-Whisper tiny ist nicht lokal gecacht; kein Download gestartet."
        )
    generate_audio = importlib.import_module("tools.kokoro_tts").generate_audio
    from tools.transcribe import transcribe

    outputs: dict[str, int] = {}
    for language, text, voice in (
        ("de", "Guten Tag, lokaler deutscher Test.", "am_michael"),
        ("en", "Hello, local English test.", "bf_emma"),
    ):
        audio = work / f"transcribe-{language}.wav"
        generate_audio(text, str(audio), voice=voice, verbose=False)
        transcript = transcribe(str(audio), model="tiny", language=language, verbose=False)
        if not isinstance(transcript, dict) or not transcript.get("segments"):
            raise RuntimeError(f"MLX-Whisper lieferte für {language} keine Zeitsegmente.")
        outputs[language] = len(transcript["segments"])
    return "Deutsch und Englisch lokal mit zeitgestempelten Segmenten transkribiert.", {
        "segments": outputs
    }


def _f10(work: Path, material: dict[str, Path]) -> tuple[str, dict[str, Any]]:
    from tools.subtitle_burn import SubtitleBurnError, burn_in
    from tools.transcribe import validate_subtitle_file, write_srt, write_vtt

    cues = [
        {"start": 0.0, "end": 1.0, "text": "Lokaler Untertitel"},
        {"start": 1.1, "end": 2.1, "text": "Subtitle local"},
    ]
    srt, vtt = work / "subtitles.srt", work / "subtitles.vtt"
    write_srt(cues, srt)
    write_vtt(cues, vtt)
    errors = validate_subtitle_file(srt) + validate_subtitle_file(vtt)
    if errors:
        raise RuntimeError("; ".join(errors))
    output = work / "burned.mp4"
    try:
        burn_in(material["video"], srt, output)
    except SubtitleBurnError as error:
        raise MissingCapability(f"Remotion-Subtitle-Burn nicht verfügbar: {error}") from error
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError("Subtitle-Burn erzeugte keine Ausgabedatei.")
    _audio_stream(output)
    return "SRT/VTT validiert und lokal via Remotion eingebrannt.", {
        "cues": len(cues),
        "output_bytes": output.stat().st_size,
        "style": "Remotion SubtitleBurn composition",
    }


def _local_ollama_model() -> str:
    _which("ollama")
    result = _run(["ollama", "list"])
    models = [line.split()[0] for line in result.stdout.splitlines()[1:] if line.split()]
    local = [model for model in models if not model.endswith("-cloud") and ":cloud" not in model]
    if not local:
        raise MissingCapability("Kein lokales Ollama-Modell gelistet.")
    return "gemma-code:latest" if "gemma-code:latest" in local else local[0]


def _cue_signature(path: Path) -> list[str]:
    return [line for line in path.read_text(encoding="utf-8").splitlines() if " --> " in line]


def _f11(work: Path, _: dict[str, Path]) -> tuple[str, dict[str, Any]]:
    from tools.subtitle_translate import translate_subtitle_file

    model = _local_ollama_model()
    source, english, german = work / "de.srt", work / "en.srt", work / "de-back.srt"
    source.write_text("1\n00:00:00,000 --> 00:00:01,000\nGuten Tag\n", encoding="utf-8")
    translate_subtitle_file(source, english, target_language="English", model=model)
    translate_subtitle_file(english, german, target_language="German", model=model)
    if _cue_signature(source) != _cue_signature(english) or _cue_signature(
        source
    ) != _cue_signature(german):
        raise RuntimeError("Cue-Anzahl oder Zeitcodes wurden verändert.")
    return "Lokale Ollama-Übersetzung Deutsch→Englisch→Deutsch mit stabilen Zeitcodes.", {
        "model": model,
        "cues": len(_cue_signature(source)),
    }


_TASK_TYPES = {
    "image_edit",
    "image_generate",
    "layout",
    "video_cut",
    "audio_process",
    "tts",
    "stt",
    "subtitle",
    "translate",
    "qc_visual",
    "semantic_analysis",
    "code",
}


def _f12(_: Path, __: dict[str, Path]) -> tuple[str, dict[str, Any]]:
    from tools.ai_router_check import check

    routing_path = ROOT / "contracts" / "task-routing.json"
    if not routing_path.is_file():
        raise MissingCapability("Routing-Tabelle contracts/task-routing.json fehlt.")
    routing = json.loads(routing_path.read_text(encoding="utf-8"))
    task_types = set(routing.get("routes", {}))
    missing_types = sorted(_TASK_TYPES - task_types)
    if missing_types:
        raise RuntimeError(f"Routing-Tabelle deckt nicht alle Aufgabentypen ab: {missing_types}")

    backends = check()
    if not backends["cloud_blocked"]:
        raise RuntimeError("Cloud-Backends sind nicht als blockiert bestätigt (internal_only).")
    missing_local = sorted(name for name, ok in backends.items() if name != "cloud_blocked" and not ok)
    return (
        "Routing-Tabelle deckt alle 12 Aufgabentypen ab; lokale Backends live geprüft "
        "(ai_router_check); Cloud-Backends bestätigt blockiert (internal_only).",
        {
            "routing": str(routing_path.relative_to(ROOT)),
            "backends": backends,
            "missing_local_backends": missing_local,
            "cloud_network_calls": 0,
        },
    )


def _version(command: list[str]) -> str | None:
    try:
        result = _run(command, timeout=30)
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    line = (result.stdout or result.stderr).strip().splitlines()
    return line[0] if line else None


def _stack_versions() -> dict[str, Any]:
    remotion = ROOT / "node_modules" / ".bin" / "remotion"
    versions: dict[str, Any] = {
        "ffmpeg": _version(["ffmpeg", "-version"]),
        "yt_dlp": _version(["yt-dlp", "--version"]),
        "node": _version(["node", "--version"]),
        "python": _version([sys.executable, "--version"]),
        "remotion": _version([str(remotion), "--version"]) if remotion.is_file() else None,
        "ollama": _version(["ollama", "--version"]),
    }
    try:
        versions["whisper"] = importlib.metadata.version("mlx-whisper")
    except importlib.metadata.PackageNotFoundError:
        versions["whisper"] = None
    try:
        versions["ollama_models"] = _run(["ollama", "list"]).stdout.splitlines()[1:]
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        versions["ollama_models"] = []
    return versions


def _f13(_: Path, __: dict[str, Path]) -> tuple[str, dict[str, Any]]:
    versions = _stack_versions()
    if not STACK_MANIFEST.exists():
        STACK_MANIFEST.write_text(
            json.dumps(
                {
                    "generated_at": datetime.now(UTC).isoformat(),
                    "versions": versions,
                    "minimum_versions": {},
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        action = "Startwert angelegt"
    else:
        manifest = json.loads(STACK_MANIFEST.read_text(encoding="utf-8"))
        action = (
            "mit vorhandenem Startwert verglichen"
            if manifest.get("versions")
            else "Manifest ohne Versionsblock"
        )
    missing = [name for name in ("ffmpeg", "node", "python") if not versions.get(name)]
    if missing:
        raise MissingCapability("Erforderliche Stack-Komponente fehlt: " + ", ".join(missing))
    return f"Versionen erfasst und {action}.", versions


def _f14(work: Path, material: dict[str, Path]) -> tuple[str, dict[str, Any]]:
    """Exercise the existing registry in a temporary asset root only."""
    from tools import asset_record, delivery_gate
    from tools.media_validation import validate_audio

    previous_asset_root, previous_gate_root = asset_record.ASSET_ROOT, delivery_gate.ASSET_ROOT
    asset_root = work / "asset-store"
    asset_record.ASSET_ROOT = asset_root
    delivery_gate.ASSET_ROOT = asset_root
    try:
        if not _cached_kokoro() or not _cached_whisper("tiny"):
            raise MissingCapability(
                "Lokales TTS- oder MLX-Whisper-Modell fehlt; End-to-End-Transkript wird nicht nachgebaut."
            )
        generate_audio = importlib.import_module("tools.kokoro_tts").generate_audio
        from tools.subtitle_translate import translate_subtitle_file
        from tools.transcribe import (
            build_subtitle_cues,
            transcribe,
            validate_subtitle_file,
            write_srt,
            write_vtt,
        )

        spoken = work / "pipeline-speech.wav"
        generate_audio(
            "Guten Tag, dies ist die interne Pipeline-Prüfung.",
            str(spoken),
            voice="am_michael",
            verbose=False,
        )
        pipeline_input = work / "pipeline-input.mp4"
        _run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(material["video"]),
                "-i",
                str(spoken),
                "-shortest",
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                str(pipeline_input),
            ]
        )
        source = asset_record.register_asset(pipeline_input)
        parent = str(source["asset_id"])
        analysis = work / "analysis"
        from tools.video_ingest import create_analysis_package

        create_analysis_package(str(pipeline_input), analysis, metadata_only=True)
        transcript = transcribe(str(spoken), model="tiny", language="de", verbose=False)
        if not isinstance(transcript, dict):
            raise RuntimeError("MLX-Whisper lieferte kein Pipeline-Transkript.")
        cues = build_subtitle_cues(transcript)
        if not cues:
            raise RuntimeError("MLX-Whisper lieferte keine Pipeline-Cues.")
        srt, vtt, translated = (
            work / "pipeline.srt",
            work / "pipeline.vtt",
            work / "pipeline-en.srt",
        )
        write_srt(cues, srt)
        write_vtt(cues, vtt)
        if validate_subtitle_file(srt) or validate_subtitle_file(vtt):
            raise RuntimeError("Pipeline-SRT/VTT bestand die Validierung nicht.")
        translate_subtitle_file(
            srt, translated, target_language="English", model=_local_ollama_model()
        )
        transcript_path = work / "pipeline-transcript.json"
        transcript_path.write_text(json.dumps(transcript, ensure_ascii=False), encoding="utf-8")
        srt_record = asset_record.register_derived(
            srt, parents=[parent], role="VARIANT", tool="mlx-whisper", operation="subtitle_srt"
        )
        asset_record.register_derived(
            vtt, parents=[parent], role="VARIANT", tool="mlx-whisper", operation="subtitle_vtt"
        )
        asset_record.register_derived(
            translated,
            parents=[str(srt_record["asset_id"])],
            role="VARIANT",
            tool="ollama",
            operation="subtitle_translate",
        )
        asset_record.register_derived(
            transcript_path,
            parents=[parent],
            role="VARIANT",
            tool="mlx-whisper",
            operation="transcript_json",
        )
        cut = work / "pipeline-cut.mp4"
        _run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                "0",
                "-t",
                "1",
                "-i",
                str(pipeline_input),
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                str(cut),
            ]
        )
        cut_record = asset_record.register_derived(
            cut, parents=[parent], role="MASTER", tool="ffmpeg", operation="trim"
        )
        normalized = work / "pipeline-normalized.m4a"
        _run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(cut),
                "-vn",
                "-af",
                "loudnorm=I=-16:TP=-1.5:LRA=11",
                "-c:a",
                "aac",
                str(normalized),
            ]
        )
        validate_audio(normalized)
        normalized_record = asset_record.register_derived(
            normalized,
            parents=[str(cut_record["asset_id"])],
            role="VARIANT",
            tool="ffmpeg",
            operation="loudnorm",
        )
        gate = delivery_gate.check(str(normalized_record["asset_id"]))
        records = list(asset_root.rglob("*.asset.json"))
        expected_records = 7  # source, srt, vtt, translated srt, transcript, cut, normalized
        if len(records) != expected_records:
            raise RuntimeError(
                f"Erwartete {expected_records} Asset-Records, gefunden: {len(records)}."
            )
        return (
            "Pipeline vollständig registriert: Video, SRT/VTT/Übersetzung/Transcript als "
            "abgeleitete Text-Assets sowie Schnitt (MASTER) und Normalisierung (VARIANT) mit "
            "vererbten Rechten.",
            {
                "media_records": len(records),
                "subtitle_cues": len(cues),
                "parent_ids": normalized_record["parent_ids"],
                "release_dry_run_allowed": gate["allowed"],
                "release_dry_run_reasons": gate["reasons"],
            },
        )
    finally:
        asset_record.ASSET_ROOT = previous_asset_root
        delivery_gate.ASSET_ROOT = previous_gate_root


def _f15(_: Path, __: dict[str, Path]) -> tuple[str, dict[str, Any]]:
    result = _run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_egress_guard.py",
            "tests/test_delivery_gate.py",
            "-q",
        ],
        timeout=180,
    )
    return "Bestehende Egress- und Delivery-Gate-Tests bestanden.", {
        "pytest": result.stdout.strip()
    }


def run_baseline() -> list[Result]:
    with tempfile.TemporaryDirectory(prefix="video-toolkit-acceptance-") as temporary:
        work = Path(temporary)
        try:
            material = _make_material(work)
        except MissingCapability as error:
            return [
                Result(capability, "MISSING", str(error), {}, 0.0) for capability in CAPABILITY_IDS
            ]
        operations: list[Callable[[], Result]] = [
            lambda: _result("F01", lambda: _f01(work, material)),
            lambda: _result("F02", lambda: _f02(work, material)),
            lambda: _result("F03", lambda: _f03(work, material)),
            lambda: _result("F04", lambda: _f04(work, material)),
            lambda: _result("F05", lambda: _f05(work, material)),
            lambda: _result("F06", lambda: _f06(work, material)),
            lambda: _result("F07", lambda: _f07(work, material)),
            lambda: _result("F08", lambda: _f08(work, material)),
            lambda: _result("F09", lambda: _f09(work, material)),
            lambda: _result("F10", lambda: _f10(work, material)),
            lambda: _result("F11", lambda: _f11(work, material)),
            lambda: _result("F12", lambda: _f12(work, material)),
            lambda: _result("F13", lambda: _f13(work, material)),
            lambda: _result("F14", lambda: _f14(work, material)),
            lambda: _result("F15", lambda: _f15(work, material)),
        ]
        return [operation() for operation in operations]


def _render_table(results: list[Result]) -> str:
    lines = ["| Fähigkeit | Status | Kurzgrund | Dauer |", "|---|---|---|---:|"]
    for result in results:
        reason = result.reason.replace("|", "\\|")
        lines.append(
            f"| {result.capability} | {result.status} | {reason} | {result.duration_s:.3f}s |"
        )
    return "\n".join(lines)


def _write_reports(
    results: list[Result], *, markdown_path: Path = REPORT_MARKDOWN, json_path: Path = REPORT_JSON
) -> None:
    for path in (markdown_path, json_path):
        if path.exists():
            raise FileExistsError(f"Report existiert bereits und wird nicht überschrieben: {path}")
    passed = sum(result.status == "PASS" for result in results)
    complete = passed == len(CAPABILITY_IDS)
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "results": [asdict(result) for result in results],
        "pass_count": passed,
        "total": len(CAPABILITY_IDS),
        "complete": complete,
    }
    markdown = (
        "# Acceptance Baseline\n\n"
        + _render_table(results)
        + f"\n\nFERTIG: {'ja' if complete else 'nein'}, PASS {passed} von 15\n"
    )
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(markdown, encoding="utf-8")


def main() -> int:
    results = run_baseline()
    print(_render_table(results))
    passed = sum(result.status == "PASS" for result in results)
    complete = passed == len(CAPABILITY_IDS)
    print(f"\nFERTIG: {'ja' if complete else 'nein'}, PASS {passed} von 15")
    try:
        _write_reports(results)
    except FileExistsError as error:
        print(f"Report: {error}", file=sys.stderr)
        return 1
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
