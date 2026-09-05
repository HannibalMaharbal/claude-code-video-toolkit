#!/usr/bin/env python3
"""
Hybrid Video Orchestrator — hermes video

Pipeline:
  input_parser → scene_splitter → parallel asset gen → ffmpeg compose → MP4
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

# Toolkit root = parent of this file's directory
TOOLKIT_ROOT = Path(__file__).parent.parent.resolve()
TOOLS_DIR = TOOLKIT_ROOT / "tools"
BRANDS_DIR = TOOLKIT_ROOT / "brands"
OUTPUT_DIR = TOOLKIT_ROOT / "output"

sys.path.insert(0, str(TOOLS_DIR))

from input_parser import ParsedInput
from input_parser import parse as parse_input
from scene_splitter import Scene, total_duration
from scene_splitter import split as split_scenes


def stable_job_id(
    input_str: str,
    script_file: str | None,
    brand: str,
    duration: int,
    language: str,
    premium: bool = False,
    no_music: bool = False,
    no_voiceover: bool = False,
) -> str:
    """Build a stable ID from inputs that materially affect generated output."""
    script_digest = None
    if script_file:
        script_path = Path(script_file)
        if script_path.exists():
            script_digest = hashlib.sha256(script_path.read_bytes()).hexdigest()

    payload = {
        "brand": brand,
        "duration": duration,
        "input": input_str.strip(),
        "language": language,
        "no_music": no_music,
        "no_voiceover": no_voiceover,
        "premium": premium,
        "script": script_digest or script_file,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


class JobState:
    """Atomically persisted state for a repeatable orchestration job."""

    def __init__(self, path: Path, job_id: str) -> None:
        self.path = path
        self.job_id = job_id

    def read(self) -> dict[str, str] | None:
        if not self.path.exists():
            return None
        return json.loads(self.path.read_text(encoding="utf-8"))

    def write(self, status: str, *, step: str, **details: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "job_id": self.job_id,
            "status": status,
            "step": step,
            **details,
        }
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.path)


# ---------------------------------------------------------------------------
# Brand loader
# ---------------------------------------------------------------------------


def load_brand(brand: str) -> tuple[dict, dict]:
    brand_dir = BRANDS_DIR / brand
    if not brand_dir.exists():
        brand_dir = BRANDS_DIR / "default"
    brand_cfg = json.loads((brand_dir / "brand.json").read_text())
    voice_cfg = json.loads((brand_dir / "voice.json").read_text())
    return brand_cfg, voice_cfg


# ---------------------------------------------------------------------------
# Asset generation (per-scene, async)
# ---------------------------------------------------------------------------


async def generate_voiceover(
    scene: Scene,
    voice_cfg: dict,
    premium: bool,
    out_dir: Path,
    *,
    timeout_s: float = 300,
) -> Path | None:
    """Generate voiceover MP3 for a scene."""
    if not scene.text:
        return None

    out_file = out_dir / f"vo_{scene.index:02d}.mp3"
    if out_file.exists():
        return out_file

    # Write text to temp script file (voiceover.py reads --script FILE)
    script_file = out_dir / f"script_{scene.index:02d}.txt"
    script_file.write_text(scene.text, encoding="utf-8")

    provider = "elevenlabs" if premium else voice_cfg.get("provider", "kokoro")
    voice = voice_cfg.get("voice", "am_michael")
    speed = voice_cfg.get("speed", 1.0)

    cmd = [
        sys.executable,
        str(TOOLS_DIR / "voiceover.py"),
        "--script",
        str(script_file),
        "--output",
        str(out_file),
        "--provider",
        provider,
        "--voice",
        voice,
    ]
    if provider == "kokoro":
        cmd += ["--speed", str(speed)]

    print(f"  [VO] Szene {scene.index}: {provider}/{voice}", flush=True)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        print(f"  [VO] Timeout Szene {scene.index} nach {timeout_s:g}s", flush=True)
        return None
    except asyncio.CancelledError:
        proc.kill()
        await proc.wait()
        raise
    if proc.returncode != 0:
        print(f"  [VO] Warnung Szene {scene.index}: {err.decode()[:200]}", flush=True)
        return None
    return out_file


async def generate_music(
    duration_s: float,
    voice_cfg: dict,
    premium: bool,
    out_dir: Path,
    *,
    timeout_s: float = 600,
) -> Path | None:
    """Generate background music."""
    out_file = out_dir / "music.mp3"
    if out_file.exists():
        return out_file

    music_cfg = voice_cfg.get("music", {})
    preset = music_cfg.get("preset", "corporate-bg")
    bpm = music_cfg.get("bpm", 120)
    key = music_cfg.get("key", "A Minor")

    cmd = [
        sys.executable,
        str(TOOLS_DIR / "music_gen.py"),
        "--preset",
        preset,
        "--duration",
        str(int(duration_s + 4)),  # slight tail
        "--bpm",
        str(bpm),
        "--key",
        key,
        "--output",
        str(out_file),
    ]

    print(f"  [Music] preset={preset} {bpm}bpm {int(duration_s)}s", flush=True)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        print(f"  [Music] Timeout nach {timeout_s:g}s", flush=True)
        return None
    except asyncio.CancelledError:
        proc.kill()
        await proc.wait()
        raise
    return out_file if out_file.exists() else None


async def generate_assets(
    scenes: list[Scene],
    voice_cfg: dict,
    total_s: float,
    premium: bool,
    no_music: bool,
    out_dir: Path,
) -> dict:
    """Run all asset generation in parallel."""
    tasks = []

    # voiceover per scene
    for scene in scenes:
        if scene.text:
            tasks.append(generate_voiceover(scene, voice_cfg, premium, out_dir))

    # background music
    if not no_music:
        tasks.append(generate_music(total_s, voice_cfg, premium, out_dir))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    assets: dict = {"voiceovers": {}, "music": None}
    vo_idx = 0
    for i, scene in enumerate(scenes):
        if scene.text:
            r = results[vo_idx]
            vo_idx += 1
            if isinstance(r, Path) and r.exists():
                assets["voiceovers"][scene.index] = str(r)

    if not no_music and vo_idx < len(results):
        music_result = results[vo_idx]
        if isinstance(music_result, Path) and music_result.exists():
            assets["music"] = str(music_result)

    return assets


# ---------------------------------------------------------------------------
# ffmpeg compose
# ---------------------------------------------------------------------------


def _check_ffmpeg() -> None:
    if subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode != 0:
        sys.exit("ffmpeg nicht gefunden. Installiere: brew install ffmpeg")


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _render_scene_frame(
    scene: Scene,
    brand_cfg: dict,
    out_path: Path,
    width: int = 1920,
    height: int = 1080,
) -> None:
    """Render one PNG frame for a scene using Pillow."""
    from PIL import Image, ImageDraw, ImageFont

    bg_rgb = _hex_to_rgb(brand_cfg["colors"]["bgDark"])
    accent_rgb = _hex_to_rgb(brand_cfg["colors"]["primary"])
    text_rgb = _hex_to_rgb(brand_cfg["colors"]["textDark"])

    img = Image.new("RGB", (width, height), color=bg_rgb)
    draw = ImageDraw.Draw(img)

    # accent bar top
    draw.rectangle([(0, 0), (width, 6)], fill=accent_rgb)

    # scene type label (upper left)
    label_text = scene.type.value.upper()
    try:
        label_font: ImageFont.FreeTypeFont | ImageFont.ImageFont = ImageFont.truetype(
            "/System/Library/Fonts/Helvetica.ttc", 36
        )
    except OSError:
        label_font = ImageFont.load_default()
    draw.text((80, 60), label_text, font=label_font, fill=accent_rgb)

    # scene title (center)
    title_text = scene.title
    try:
        title_font: ImageFont.FreeTypeFont | ImageFont.ImageFont = ImageFont.truetype(
            "/System/Library/Fonts/Helvetica.ttc", 80
        )
    except OSError:
        title_font = ImageFont.load_default()

    # wrap long titles
    max_chars = 30
    if len(title_text) > max_chars:
        words = title_text.split()
        lines: list[str] = []
        line: list[str] = []
        for word in words:
            if len(" ".join(line + [word])) <= max_chars:
                line.append(word)
            else:
                lines.append(" ".join(line))
                line = [word]
        lines.append(" ".join(line))
        title_text = "\n".join(lines)

    bbox = draw.textbbox((0, 0), title_text, font=title_font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((width - tw) / 2, (height - th) / 2), title_text, font=title_font, fill=text_rgb)

    # accent bar bottom
    draw.rectangle([(0, height - 6), (width, height)], fill=accent_rgb)

    img.save(str(out_path), "PNG")


def _audio_duration(audio_file: str) -> float:
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            audio_file,
        ],
        capture_output=True,
        text=True,
    )
    info = json.loads(probe.stdout)
    return float(info["format"]["duration"])


def compose_video(
    scenes: list[Scene],
    assets: dict,
    brand_cfg: dict,
    voice_cfg: dict,
    out_path: Path,
    no_music: bool,
) -> None:
    """
    Compose final MP4 using Pillow frames per scene + ffmpeg for encoding.

    Strategy:
    - Per scene: render PNG frame with Pillow → ffmpeg loop → scene clip
    - Concat all scene clips → video track
    - Concat all voiceovers → audio track
    - Mix background music at low volume
    """
    _check_ffmpeg()

    voiceovers = assets["voiceovers"]
    music_file = assets.get("music")
    tmp_dir = out_path.parent / ".tmp_compose"
    tmp_dir.mkdir(exist_ok=True)

    # --- Step 1: render PNG per scene + encode clip ---
    scene_clips: list[str] = []
    clip_concat_list = tmp_dir / "video_concat.txt"

    for scene in scenes:
        png_path = tmp_dir / f"frame_{scene.index:02d}.png"
        clip_path = tmp_dir / f"clip_{scene.index:02d}.mp4"

        # get actual duration from VO if available, else estimate
        if scene.index in voiceovers:
            duration_s = _audio_duration(voiceovers[scene.index])
        else:
            duration_s = scene.duration_s

        _render_scene_frame(scene, brand_cfg, png_path)

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loop",
                "1",
                "-i",
                str(png_path),
                "-t",
                f"{duration_s:.3f}",
                "-vf",
                "scale=1920:1080",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-r",
                "30",
                str(clip_path),
            ],
            check=True,
            capture_output=True,
        )

        scene_clips.append(str(clip_path))

    # write concat list
    with open(clip_concat_list, "w") as f:
        for clip in scene_clips:
            f.write(f"file {clip}\n")

    # concat video clips
    video_track = tmp_dir / "video_track.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(clip_concat_list),
            "-c",
            "copy",
            str(video_track),
        ],
        check=True,
        capture_output=True,
    )

    # --- Step 2: concat voiceovers ---
    vo_files = [voiceovers[s.index] for s in scenes if s.index in voiceovers]
    audio_track = tmp_dir / "audio_track.mp3"

    if not vo_files:
        total_s = sum(s.duration_s for s in scenes)
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=44100:cl=stereo",
                "-t",
                str(total_s),
                str(audio_track),
            ],
            check=True,
            capture_output=True,
        )
    else:
        vo_concat_list = tmp_dir / "audio_concat.txt"
        with open(vo_concat_list, "w") as f:
            for vf in vo_files:
                f.write(f"file {vf}\n")
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(vo_concat_list),
                "-c",
                "copy",
                str(audio_track),
            ],
            check=True,
            capture_output=True,
        )

    # --- Step 3: combine video + audio (+ music) ---
    if music_file and not no_music and Path(music_file).exists():
        music_vol = voice_cfg.get("music", {}).get("volume", 0.12)
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(video_track),
                "-i",
                str(audio_track),
                "-i",
                music_file,
                "-filter_complex",
                f"[1:a]volume=1.0[vo];[2:a]volume={music_vol}[bg];[vo][bg]amix=inputs=2:duration=first[aout]",
                "-map",
                "0:v",
                "-map",
                "[aout]",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
                str(out_path),
            ],
            check=True,
            capture_output=True,
        )
    else:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(video_track),
                "-i",
                str(audio_track),
                "-map",
                "0:v",
                "-map",
                "1:a",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
                str(out_path),
            ],
            check=True,
            capture_output=True,
        )

    # cleanup
    import shutil

    shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Main orchestrate function
# ---------------------------------------------------------------------------


def orchestrate(
    input_str: str,
    script_file: str | None = None,
    brand: str = "default",
    premium: bool = False,
    duration: int = 60,
    no_music: bool = False,
    no_voiceover: bool = False,
    output_dir: str | None = None,
    language: str = "de",
) -> Path:
    out_base = Path(output_dir) if output_dir else OUTPUT_DIR
    out_base.mkdir(parents=True, exist_ok=True)

    job_id = stable_job_id(
        input_str,
        script_file,
        brand,
        duration,
        language,
        premium=premium,
        no_music=no_music,
        no_voiceover=no_voiceover,
    )
    job_dir = out_base / ".jobs" / job_id
    state = JobState(job_dir / "status.json", job_id)
    previous = state.read()
    if previous and previous.get("status") == "completed":
        previous_output = previous.get("output")
        if previous_output and Path(previous_output).is_file():
            return Path(previous_output)

    state.write("running", step="parse")

    print(f"\n{'=' * 60}", flush=True)
    print("  Hybrid Video Orchestrator", flush=True)
    print(f"  Brand: {brand} | Premium: {premium} | Ziel: {duration}s", flush=True)
    print(f"{'=' * 60}\n", flush=True)

    # 1. Parse input
    print("[1/5] Input parsen...", flush=True)
    parsed: ParsedInput = parse_input(
        input_str=input_str,
        script_file=script_file,
        duration=duration,
        brand=brand,
        language=language,
    )
    print(f"  Type: {parsed.type.value} | Title: {parsed.title}", flush=True)

    safe_title = parsed.title.replace(" ", "-")[:40]
    out_path = out_base / f"{safe_title}-{job_id}.mp4"

    # 2. Split scenes
    print("[2/5] Szenen aufteilen...", flush=True)
    scenes = split_scenes(parsed.script, brand=brand)
    total_s = total_duration(scenes)
    print(f"  {len(scenes)} Szenen | ~{total_s:.0f}s", flush=True)
    for s in scenes:
        print(f"  [{s.index}] {s.type.value:<10} {s.title}", flush=True)

    # 3. Load brand
    brand_cfg, voice_cfg = load_brand(brand)

    # 4. Asset generation (working dir per run)
    assets_dir = job_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    state.write("running", step="assets", output=str(out_path))
    print("[3/5] Assets generieren (parallel)...", flush=True)
    if no_voiceover:
        assets: dict = {"voiceovers": {}, "music": None}
        if not no_music:
            assets["music"] = asyncio.run(generate_music(total_s, voice_cfg, premium, assets_dir))
    else:
        assets = asyncio.run(
            generate_assets(scenes, voice_cfg, total_s, premium, no_music, assets_dir)
        )

    print(f"  Voiceovers: {len(assets['voiceovers'])}/{len(scenes)}", flush=True)
    print(f"  Musik: {'ja' if assets.get('music') else 'nein'}", flush=True)

    # 5. Render + compose
    state.write("running", step="compose", output=str(out_path))
    print("[4/5] Compositing...", flush=True)
    compose_video(scenes, assets, brand_cfg, voice_cfg, out_path, no_music)

    state.write("completed", step="complete", output=str(out_path))

    print("\n[5/5] Fertig!", flush=True)
    print(f"  → {out_path}", flush=True)
    print(f"  Größe: {out_path.stat().st_size / 1024 / 1024:.1f} MB", flush=True)

    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(
        description='Hybrid Video Orchestrator — "hermes video" backend',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  python tools/orchestrator.py "SAC Produktvideo"
  python tools/orchestrator.py "https://sac-online-world.de" --brand sac
  python tools/orchestrator.py --script mein-script.md --brand licbarska --premium
  python tools/orchestrator.py "React Hooks Tutorial" --duration 120 --no-music
""",
    )
    ap.add_argument("input", nargs="?", default="", help="Thema, URL, oder leer wenn --script")
    ap.add_argument("--script", help="Explizite Script-Datei (.md)")
    ap.add_argument("--brand", default="default", choices=["default", "sac", "licbarska"])
    ap.add_argument("--premium", action="store_true", help="ElevenLabs Voiceover + Music")
    ap.add_argument("--duration", type=int, default=60, help="Ziel-Länge in Sekunden")
    ap.add_argument("--no-music", action="store_true")
    ap.add_argument("--no-voiceover", action="store_true")
    ap.add_argument("--output", help="Ausgabe-Ordner (default: output/)")
    ap.add_argument("--language", default="de")
    args = ap.parse_args()

    if not args.input and not args.script:
        ap.print_help()
        sys.exit(1)

    out_path = orchestrate(
        input_str=args.input,
        script_file=args.script,
        brand=args.brand,
        premium=args.premium,
        duration=args.duration,
        no_music=args.no_music,
        no_voiceover=args.no_voiceover,
        output_dir=args.output,
        language=args.language,
    )

    print(f"\n✓ MP4: {out_path}")


if __name__ == "__main__":
    main()
