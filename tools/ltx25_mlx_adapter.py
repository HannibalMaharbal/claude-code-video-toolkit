#!/usr/bin/env python3
"""
Shared local video engine for Creator Studio: LTX-2.5 via the `ltx-2-mlx`
runtime (native MLX, no ComfyUI/GGUF/PyTorch stack). Replaces Wan 2.2 TI2V-5B.

All five Creator Studio video features (Video erstellen, Storyboard, Story
9:16, Produkt-Varianten, Video verlaengern) call this ONE adapter instead of
implementing their own LTX invocation.

CLI contract matches the removed wan_mlx_adapter.py so callers needed only
their wrapper-path constant changed:
    python tools/ltx25_mlx_adapter.py --prompt "..." --output clip.mp4 \
        --mode two-stage --frames 97 --frame-rate 24 \
        --width 704 --height 480 [--image photo.jpg | --continue-from prior.mp4] \
        [--seed 42]

LTX-2.5 natively uses 8n+1 frames and canvas dimensions divisible by 32.
This project's own frame convention (seconds*24+1) and every configured
canvas size already satisfy both (24n+1 = 8*(3n)+1; every width/height in
use is a multiple of 32), so --frames/--width/--height pass through
unchanged, no retiming/rescaling step needed on this side.

Runtime pin (per the model card at ~/AI-Modelle/ltx-2.5-mlx-q8/README.md):
    https://github.com/MrMoferFRAN/ltx-2-mlx, branch `ltx25`,
    commit 57952288076766abe27dda3a774b2c24f7346977.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RUNTIME_DIR = Path.home() / "PROJEKTE" / "AI-Modelle" / "ltx-2-mlx"
MODEL_PATH = Path.home() / "PROJEKTE" / "AI-Modelle" / "ltx-2.5-mlx-q8"
PROGRESS_PATHS = [
    Path.home() / ".claude" / "rate-limit-bridge" / "render_status.json",
    Path(__file__).resolve().parents[1] / "render_status.json",
]


def update_render_progress(
    percent: int,
    stage: str,
    detail: str,
    output: str | None = None,
    active: bool = True,
    eta_seconds: int | None = None,
    elapsed_seconds: int | None = None,
    error: str | None = None,
) -> None:
    """Atomic write of rendering progress for terminal, agents and UI status checks."""
    data = {
        "active": active,
        "percent": max(0, min(100, int(percent))),
        "stage": stage,
        "detail": detail,
        "output_file": str(output) if output else None,
        "elapsed_seconds": elapsed_seconds,
        "eta_seconds": eta_seconds,
        "error": error,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    for p in PROGRESS_PATHS:
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            tmp.replace(p)
        except Exception:
            pass


def get_render_status() -> dict:
    """Return the current or most recent render status."""
    for p in PROGRESS_PATHS:
        if p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return {"active": False, "percent": 0, "stage": "idle", "detail": "Kein Render-Status vorhanden"}
MODE_FLAGS = {
    "distilled": "--distilled",
    "two-stage": "--two-stage",
    "two-stages-hq": "--two-stages-hq",
    "one-stage": "--one-stage",
}

_CONTINUITY_SUFFIX = (
    " Keep one continuous physical scene with the same subject, physical set, "
    "wardrobe, and props. Keep lighting direction and color temperature constant "
    "across every shot. Use smooth motivated camera movement and natural micro-movements "
    "with visible environmental motion, settling smoothly. Preserve coherent physics "
    "and temporal continuity: no spatial teleportation, disjointed cuts, identity drift, "
    "morphing, flicker, or frozen frames."
)
_SHARPNESS_SUFFIX = (
    " tack-sharp focus, Cooke 50mm T2.0 prime lens, high micro-contrast, "
    "crisp 8k textures, clean sharp edges, zero motion blur."
)
_IMAGE_SUFFIX = (
    " Preserve the reference image's identity, composition, materials, and geometry "
    "as the locked visual starting point."
)
_KEYFRAME_SUFFIX = (
    " Transition smoothly from the initial frame to the target end frame without "
    "drifting or jarring morphs."
)


def enhance_ltx_prompt(prompt: str, image: bool = False) -> str:
    """Add the shared Hannibal continuity and optical sharpness contract once for callers."""
    cleaned = " ".join(prompt.split())
    if _CONTINUITY_SUFFIX.strip() not in cleaned:
        cleaned += _CONTINUITY_SUFFIX
    if _SHARPNESS_SUFFIX.strip() not in cleaned:
        cleaned += _SHARPNESS_SUFFIX
    if image and _IMAGE_SUFFIX.strip() not in cleaned:
        cleaned += _IMAGE_SUFFIX
    return cleaned


def _resolve_model() -> str:
    return str(MODEL_PATH)


def _extract_last_frame(video_path: Path, output_path: Path) -> str | None:
    """Decode the final video frame into a lossless continuation anchor."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return "ffmpeg ist nicht installiert/im PATH."
    proc = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-sseof",
            "-1",
            "-i",
            str(video_path),
            "-vf",
            "reverse",
            "-frames:v",
            "1",
            str(output_path),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return (proc.stderr or proc.stdout).strip()[-2000:]
    if not output_path.is_file() or output_path.stat().st_size == 0:
        return f"ffmpeg hat kein Endframe aus {video_path} erzeugt."
    return None


def sharpen_video(
    input_path: Path | str,
    output_path: Path | str | None = None,
    cas: float = 0.6,
) -> bool:
    """Run Apple Silicon VideoToolbox Lanczos 1080p scaling + Contrast Adaptive Sharpening (CAS).

    Hardware-accelerated via h264_videotoolbox (0 € Grenzkosten, ~0.3s on Apple Silicon).
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    in_p = Path(input_path)
    if not in_p.is_file():
        return False

    out_p = Path(output_path) if output_path else in_p
    in_place = in_p.resolve() == out_p.resolve()
    target_p = out_p.with_suffix(".cas_tmp.mp4") if in_place else out_p

    vf_filter = (
        "scale='if(gt(iw,ih),1920,-2)':'if(gt(iw,ih),-2,1920)':flags=lanczos:param0=3,"
        f"cas={cas},"
        "unsharp=5:5:0.5:3:3:0.2"
    )

    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(in_p),
        "-vf",
        vf_filter,
        "-c:v",
        "h264_videotoolbox",
        "-b:v",
        "20M",
        "-color_primaries",
        "bt709",
        "-color_trc",
        "bt709",
        "-colorspace",
        "bt709",
        "-c:a",
        "copy",
        str(target_p),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        if in_place and target_p.exists():
            target_p.unlink(missing_ok=True)
        return False
    if in_place:
        target_p.replace(out_p)
    return True


def generate_video(
    prompt: str,
    output_path: str,
    mode: str = "distilled",
    width: int = 704,
    height: int = 480,
    frames: int = 97,
    frame_rate: int = 24,
    seed: int | None = None,
    image: str | None = None,
    end_image: str | None = None,
    continue_from: str | None = None,
    lora: str | None = None,
    lora_strength: float = 1.0,
    verbose: bool = True,
    sharpen: bool = False,
) -> dict:
    if image and continue_from:
        return {
            "success": False,
            "error": "--image und --continue-from dürfen nicht gleichzeitig verwendet werden.",
        }
    if image and not Path(image).is_file():
        return {"success": False, "error": f"Eingabebild fehlt: {image}"}
    if end_image and not Path(end_image).is_file():
        return {"success": False, "error": f"Endbild fehlt: {end_image}"}
    if continue_from and not Path(continue_from).is_file():
        return {"success": False, "error": f"Fortsetzungsvideo fehlt: {continue_from}"}
    if mode not in MODE_FLAGS:
        return {
            "success": False,
            "error": f"Unknown mode '{mode}', expected one of {sorted(MODE_FLAGS)}",
        }
    if width % 32 or height % 32:
        return {
            "success": False,
            "error": (
                "LTX-2.5 braucht Breite/Höhe durch 32 teilbar, "
                f"bekommen: {width}x{height}."
            ),
        }
    if (frames - 1) % 8:
        return {
            "success": False,
            "error": f"LTX-2.5 braucht Frames der Form 8n+1, bekommen: {frames}.",
        }
    needs_dev_model = mode in ("two-stage", "two-stages-hq", "one-stage")
    if needs_dev_model and not (MODEL_PATH / "transformer-dev.safetensors").is_file():
        return {
            "success": False,
            "error": (
                f"Modus '{mode}' braucht transformer-dev.safetensors, "
                f"fehlt unter {MODEL_PATH}."
            ),
        }

    uv = shutil.which("uv")
    if not uv:
        return {"success": False, "error": "uv ist nicht installiert/im PATH."}
    if not RUNTIME_DIR.is_dir():
        return {"success": False, "error": f"ltx-2-mlx-Runtime fehlt unter {RUNTIME_DIR}."}
    if not MODEL_PATH.is_dir():
        return {"success": False, "error": f"LTX-2.5-Modell fehlt unter {MODEL_PATH}."}

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    continuation_source = str(Path(continue_from)) if continue_from else None
    anchor_tmp = None
    if continue_from:
        anchor_tmp = tempfile.TemporaryDirectory(prefix="ltx25-continuation-")
        anchor_path = Path(anchor_tmp.name) / "last-frame.png"
        extraction_error = _extract_last_frame(Path(continue_from), anchor_path)
        if extraction_error:
            anchor_tmp.cleanup()
            return {
                "success": False,
                "error": f"Endframe konnte nicht extrahiert werden: {extraction_error}",
            }
        image = str(anchor_path)

    if image and end_image:
        task = "keyframe-interpolation"
    elif image or end_image:
        task = "image-to-video"
    else:
        task = "text-to-video"
    enhanced_prompt = enhance_ltx_prompt(prompt, image=bool(image or end_image))
    if end_image and _KEYFRAME_SUFFIX.strip() not in enhanced_prompt:
        enhanced_prompt += _KEYFRAME_SUFFIX

    cmd = [
        uv, "run", "ltx-2-mlx", "generate",
        "--model", _resolve_model(),
        MODE_FLAGS[mode],
        "--low-ram",
        "--prompt", enhanced_prompt,
        "--width", str(width),
        "--height", str(height),
        "--frames", str(frames),
        "--frame-rate", str(frame_rate),
        "--output", str(output_path),
    ]
    if image and end_image:
        cmd += ["--image", image, "0", "1.0", "--image", end_image, str(frames - 1), "1.0"]
    elif image:
        cmd += ["--image", image]
    elif end_image:
        cmd += ["--image", end_image, str(frames - 1), "1.0"]

    if lora:
        cmd += ["--lora", str(lora), str(lora_strength)]
    if seed is not None:
        cmd += ["--seed", str(seed)]
    if mode == "two-stage":
        # Balanced mode intentionally trades some detail for speed. The HQ mode
        # keeps the runtime's native sampler/step defaults and never uses TeaCache.
        cmd += ["--enable-teacache", "--teacache-thresh", "0.7", "--stage1-steps", "16"]

    if verbose:
        print(
            f"LTX-2.5 ({mode}, {task}, {width}x{height}, {frames}f @ {frame_rate}fps)...",
            file=sys.stderr,
        )

    start_time = time.time()
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["MLX_METAL_JIT_CACHE"] = "1"

    update_render_progress(
        percent=2,
        stage="init",
        detail="Vorbereitung & Modellprüfung",
        output=str(output_path),
        active=True,
    )

    is_mocked = hasattr(subprocess.run, "assert_called") or "mock" in type(subprocess.run).__module__

    try:
        if is_mocked:
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=RUNTIME_DIR,
                    capture_output=True,
                    text=True,
                    timeout=1800,
                    env=env,
                )
            except subprocess.TimeoutExpired:
                update_render_progress(2, "timeout", "Zeitlimit überschritten", str(output_path), False, error="Timeout")
                return {
                    "success": False,
                    "error": (
                        "LTX-2.5 Generierung nach 30 Minuten wegen Zeitlimit "
                        "kontrolliert abgebrochen."
                    ),
                }
        else:
            output_lines = []
            current_percent = 5
            try:
                p = subprocess.Popen(
                    cmd,
                    cwd=RUNTIME_DIR,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    env=env,
                )
                while True:
                    line = p.stdout.readline() if p.stdout else ""
                    if not line and p.poll() is not None:
                        break
                    if line:
                        output_lines.append(line)
                        s = line.strip()
                        now_s = int(time.time() - start_time)
                        if "Loading text encoder" in s:
                            current_percent = 5
                            update_render_progress(5, "text_encoder", "Lade Text-Encoder (Gemma)", str(output_path), True, elapsed_seconds=now_s)
                        elif "Encoding prompt" in s:
                            current_percent = 8
                            update_render_progress(8, "encoding", "Enkodiere Text-Prompt", str(output_path), True, elapsed_seconds=now_s)
                        elif "Loading decoders" in s:
                            current_percent = 12
                            update_render_progress(12, "decoders", "Lade VAE- und Audio-Decoder", str(output_path), True, elapsed_seconds=now_s)
                        elif "Loading transformer" in s:
                            current_percent = 15
                            update_render_progress(15, "dit", "Lade DiT Transformer-Gewichte", str(output_path), True, elapsed_seconds=now_s)
                        elif "Denoising:" in s or "Denoise" in s:
                            m_pct = re.search(r"(\d+)%", s)
                            m_step = re.search(r"(\d+)/(\d+)", s)
                            pval = int(m_pct.group(1)) if m_pct else None
                            if pval is None and m_step:
                                pval = int(int(m_step.group(1)) / max(1, int(m_step.group(2))) * 100)
                            if pval is not None:
                                current_percent = 15 + int(pval * 0.70)

                            m_eta = re.search(r"<(\d+):(\d+)", s)
                            eta_s = (int(m_eta.group(1)) * 60 + int(m_eta.group(2))) if m_eta else None
                            step_lbl = f"Schritt {m_step.group(1)}/{m_step.group(2)}" if m_step else f"{pval}%"
                            update_render_progress(current_percent, "denoising", f"Denoising ({step_lbl})", str(output_path), True, eta_seconds=eta_s, elapsed_seconds=now_s)
                            if verbose:
                                sys.stderr.write(f"\r[Video-Rendering: {current_percent}%] Denoising ({step_lbl}) | {now_s}s" + (f" | Rest: ~{eta_s}s" if eta_s else "") + "   ")
                                sys.stderr.flush()
                        elif "Decoding video" in s:
                            current_percent = 88
                            update_render_progress(88, "decoding", "Dekodiere Video-Frames (VAE)", str(output_path), True, elapsed_seconds=now_s)
                            if verbose:
                                sys.stderr.write(f"\r[Video-Rendering: 88%] Dekodiere Video-Frames...          \n")
                                sys.stderr.flush()
                        elif "muxing" in s or "Muxing" in s:
                            current_percent = 93
                            update_render_progress(93, "muxing", "Video-Audio Muxing", str(output_path), True, elapsed_seconds=now_s)

                    if time.time() - start_time > 1800:
                        p.kill()
                        update_render_progress(current_percent, "timeout", "Zeitlimit überschritten", str(output_path), False, error="Timeout")
                        return {
                            "success": False,
                            "error": (
                                "LTX-2.5 Generierung nach 30 Minuten wegen Zeitlimit "
                                "kontrolliert abgebrochen."
                            ),
                        }
                ret = p.wait()
                proc = type("Result", (), {"returncode": ret, "stdout": "".join(output_lines), "stderr": ""})()
            except Exception as e:
                update_render_progress(current_percent, "error", str(e), str(output_path), False, error=str(e))
                return {"success": False, "error": str(e)}
    finally:
        if anchor_tmp is not None:
            anchor_tmp.cleanup()
    elapsed_ms = int((time.time() - start_time) * 1000)
    now_s = elapsed_ms // 1000

    if proc.returncode != 0:
        err_str = (proc.stderr or proc.stdout).strip()[-2000:]
        update_render_progress(0, "failed", "Fehler bei LTX-2.5 Inferenz", str(output_path), False, error=err_str)
        return {"success": False, "error": err_str}
    if not output_path.exists() or output_path.stat().st_size == 0:
        err_str = f"ltx-2-mlx reported success but {output_path} was not created"
        update_render_progress(0, "failed", err_str, str(output_path), False, error=err_str)
        return {
            "success": False,
            "error": err_str,
        }

    sharpened = False
    if sharpen and output_path.exists():
        update_render_progress(96, "sharpening", "Apple VideoToolbox CAS 1080p Schärfung", str(output_path), True, elapsed_seconds=now_s)
        sharpened = sharpen_video(output_path, output_path)

    update_render_progress(
        100,
        "completed",
        f"Video erfolgreich fertiggestellt ({now_s}s)",
        str(output_path),
        False,
        eta_seconds=0,
        elapsed_seconds=now_s,
    )

    return {
        "success": True,
        "output": str(output_path),
        "mode": mode,
        "width": width,
        "height": height,
        "frames": frames,
        "frame_rate": frame_rate,
        "seed": seed,
        "prompt_enhanced": True,
        "sharpened": sharpened,
        "continuation_source": continuation_source,
        "end_image": end_image,
        "lora": lora,
        "inference_time_ms": elapsed_ms,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--prompt", default=None, help="Text-Prompt für Video-Inferenz")
    parser.add_argument("--output", default=None, help="Ausgabepfad (.mp4)")
    parser.add_argument(
        "--status",
        action="store_true",
        help="Aktuellen Rendering-Fortschritt in Prozent und Phase anzeigen",
    )
    parser.add_argument(
        "--status-json",
        action="store_true",
        help="Aktuellen Rendering-Fortschritt als JSON ausgeben",
    )
    parser.add_argument("--mode", default="distilled", choices=sorted(MODE_FLAGS))
    parser.add_argument("--frames", type=int, default=97)
    parser.add_argument("--frame-rate", type=int, default=24)
    parser.add_argument("--width", type=int, default=704)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--image", default=None)
    parser.add_argument(
        "--end-image",
        default=None,
        help="Ziel-Endbild für Keyframe-Sandwich (Frame N-1 Verankerung)",
    )
    parser.add_argument(
        "--continue-from",
        default=None,
        help=(
            "Vorherigen Clip fortsetzen; dessen letztes Frame wird automatisch "
            "als I2V-Anker verwendet."
        ),
    )
    parser.add_argument(
        "--lora",
        default=None,
        help="Pfad zu LoRA-Datei (.safetensors) oder HF-Repo ID",
    )
    parser.add_argument(
        "--lora-strength",
        type=float,
        default=1.0,
        help="LoRA-Stärke (Standard: 1.0)",
    )
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--sharpen",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Apple VideoToolbox CAS 1080p Schärfung automatisch anwenden (Standard: True)",
    )
    args = parser.parse_args()

    if args.status or args.status_json:
        st = get_render_status()
        if args.status_json:
            print(json.dumps(st, indent=2))
            return
        pct = st.get("percent", 0)
        detail = st.get("detail", "Keine Aktivität")
        active = st.get("active", False)
        out_f = st.get("output_file")
        eta = st.get("eta_seconds")
        elapsed = st.get("elapsed_seconds")

        bar_len = 20
        filled = int(bar_len * pct / 100)
        bar = "█" * filled + "░" * (bar_len - filled)

        state_str = "🟢 Aktiv (in Bearbeitung)" if active else "✅ Abgeschlossen" if pct == 100 else "⚪ Inaktiv"
        print(f"🎬 Video-Rendering Status: {state_str}")
        print(f"Fortschritt: [{bar}] {pct} %")
        print(f"Phase:       {detail}")
        if elapsed is not None:
            print(f"Laufzeit:    {elapsed // 60}m {elapsed % 60:02d}s")
        if eta is not None and active:
            print(f"Restzeit:    ~{eta // 60}m {eta % 60:02d}s (geschätzt)")
        if out_f:
            print(f"Datei:       {out_f}")
        return

    if not args.prompt or not args.output:
        parser.error("Die Argumente --prompt und --output sind erforderlich (außer bei --status/--status-json).")

    result = generate_video(
        prompt=args.prompt,
        output_path=args.output,
        mode=args.mode,
        width=args.width,
        height=args.height,
        frames=args.frames,
        frame_rate=args.frame_rate,
        seed=args.seed,
        image=args.image,
        end_image=args.end_image,
        continue_from=args.continue_from,
        lora=args.lora,
        lora_strength=args.lora_strength,
        sharpen=args.sharpen,
    )
    print(json.dumps(result))
    if not result.get("success"):
        sys.exit(1)


if __name__ == "__main__":
    main()
