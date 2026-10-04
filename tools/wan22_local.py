#!/usr/bin/env python3
"""
Generate video locally with WAN2.2-I2V-A14B (GGUF, Q5_K_M) on Apple Silicon,
via a locally-installed ComfyUI + ComfyUI-GGUF instance.

Local, offline image-to-video generation - no API key, no cloud cost. Unlike
ltx2_local.py (LTX-2.5-MLX), this drives ComfyUI's own native GGUF loader,
because diffusers' from_single_file() path produces shape mismatches for
this specific QuantStack checkpoint (confirmed 2026-10-04, see
huggingface/diffusers#12009 for the related meta-tensor report).

Verified live 2026-10-04 on M4 Pro / 24GB RAM:
  - 320x192, 17 frames, 6 steps total (mechanics-only smoke test): ~209s.
  - 512x288, 33 frames, 12 steps total: ~1061s (~83s/step, stable).
  - 704x480, 49 frames, 20 steps total (kreativ-studio's default format):
    RAM dropped to ~2GB free of 24GB and the first sampling step did not
    complete after 10+ minutes (thrashing, not pure compute). NOT currently
    usable at full project resolution on this hardware - keep width*height
    at or below roughly 512x288 (~147,000 px) until further RAM/offload
    tuning (tiled VAE decode, lower-precision compute, etc.) is done.

CLI contract mirrors ltx2_local.py so storyboard_render.py can call either
wrapper interchangeably:
    python tools/wan22_local.py --prompt "..." --output clip.mp4 \\
        --mode two-stage --frames 33 --frame-rate 24 \\
        --width 512 --height 288 [--image photo.jpg] [--seed 42]

`--frames`/`--frame-rate` describe the REQUESTED duration at the caller's
frame rate (matching storyboard_project.py's DURATION_FRAMES convention:
frames = seconds * frame_rate + 1); this wrapper converts that duration to
WAN's native frame count internally and asks ComfyUI to tag the saved clip
with the native rate - the caller's downstream ffmpeg normalization step
(_normalize_clip in storyboard_render.py) retimes to the final frame rate,
exactly like it already does for LTX output.
"""

import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

COMFYUI_ROOT = Path.home() / "AI-Modelle" / "ComfyUI"
COMFYUI_PYTHON = COMFYUI_ROOT / ".venv" / "bin" / "python"
COMFYUI_PORT = 8199
COMFYUI_HOST = "127.0.0.1"
SERVER = f"http://{COMFYUI_HOST}:{COMFYUI_PORT}"

HIGH_NOISE_UNET = "Wan2.2-I2V-A14B-HighNoise-Q5_K_M.gguf"
LOW_NOISE_UNET = "Wan2.2-I2V-A14B-LowNoise-Q5_K_M.gguf"
CLIP_NAME = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
VAE_NAME = "wan_2.1_vae.safetensors"

WAN_NATIVE_FPS = 16
MODEL_SHIFT = 5.0
CFG = 3.5

# (high_steps, low_steps) per quality tier. Calibrated against the timings
# in the module docstring; "distilled" trades quality for speed the same
# way it does for the LTX backend.
MODE_STEPS = {
    "distilled": (4, 4),
    "two-stage": (8, 8),
    "two-stages-hq": (12, 12),
}

SERVER_START_TIMEOUT_S = 120
JOB_TIMEOUT_S = 4 * 60 * 60
NEGATIVE_PROMPT = "blurry, low quality, static, distorted, worst quality"


def _wan_native_frames(frames: int, frame_rate: int) -> int:
    """Convert a (frames, frame_rate) duration request into WAN's native
    frame count, snapped to 4k+1 for clean temporal VAE compression."""
    duration_s = max(0.1, (frames - 1) / frame_rate)
    raw = duration_s * WAN_NATIVE_FPS
    k = max(1, round((raw - 1) / 4))
    return k * 4 + 1


def _wait_for_server(proc: subprocess.Popen, timeout_s: int) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"ComfyUI exited early with code {proc.returncode} before becoming ready.")
        try:
            with urllib.request.urlopen(f"{SERVER}/system_stats", timeout=3):
                return
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(2)
    raise RuntimeError(f"ComfyUI did not become ready within {timeout_s}s on {SERVER}.")


def _build_graph(
    prompt: str,
    width: int,
    height: int,
    wan_frames: int,
    steps_high: int,
    steps_low: int,
    seed: int,
    image_filename: str | None,
    save_prefix: str,
) -> dict:
    total_steps = steps_high + steps_low
    graph: dict = {
        "high_unet": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": HIGH_NOISE_UNET}},
        "low_unet": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": LOW_NOISE_UNET}},
        "high_shift": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["high_unet", 0], "shift": MODEL_SHIFT}},
        "low_shift": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["low_unet", 0], "shift": MODEL_SHIFT}},
        "clip": {"class_type": "CLIPLoader", "inputs": {"clip_name": CLIP_NAME, "type": "wan"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": VAE_NAME}},
        "positive": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["clip", 0], "text": prompt}},
        "negative": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["clip", 0], "text": NEGATIVE_PROMPT}},
        "i2v": {
            "class_type": "WanImageToVideo",
            "inputs": {
                "positive": ["positive", 0],
                "negative": ["negative", 0],
                "vae": ["vae", 0],
                "width": width,
                "height": height,
                "length": wan_frames,
                "batch_size": 1,
            },
        },
        "sample_high": {
            "class_type": "KSamplerAdvanced",
            "inputs": {
                "model": ["high_shift", 0], "add_noise": "enable", "noise_seed": seed,
                "steps": total_steps, "cfg": CFG, "sampler_name": "euler", "scheduler": "simple",
                "positive": ["i2v", 0], "negative": ["i2v", 1], "latent_image": ["i2v", 2],
                "start_at_step": 0, "end_at_step": steps_high, "return_with_leftover_noise": "enable",
            },
        },
        "sample_low": {
            "class_type": "KSamplerAdvanced",
            "inputs": {
                "model": ["low_shift", 0], "add_noise": "disable", "noise_seed": seed,
                "steps": total_steps, "cfg": CFG, "sampler_name": "euler", "scheduler": "simple",
                "positive": ["i2v", 0], "negative": ["i2v", 1], "latent_image": ["sample_high", 0],
                "start_at_step": steps_high, "end_at_step": 10000, "return_with_leftover_noise": "disable",
            },
        },
        "decode": {"class_type": "VAEDecode", "inputs": {"samples": ["sample_low", 0], "vae": ["vae", 0]}},
        "create_video": {"class_type": "CreateVideo", "inputs": {"images": ["decode", 0], "fps": float(WAN_NATIVE_FPS)}},
        "save_video": {
            "class_type": "SaveVideo",
            "inputs": {"video": ["create_video", 0], "filename_prefix": save_prefix, "format": "mp4"},
        },
    }
    if image_filename:
        graph["load_image"] = {"class_type": "LoadImage", "inputs": {"image": image_filename}}
        graph["i2v"]["inputs"]["start_image"] = ["load_image", 0]
    return graph


def _submit_and_wait(graph: dict) -> dict:
    client_id = str(uuid.uuid4())
    payload = json.dumps({"prompt": graph, "client_id": client_id}).encode("utf-8")
    req = urllib.request.Request(f"{SERVER}/prompt", data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"ComfyUI rejected the workflow: {exc.read().decode()[:2000]}") from exc
    prompt_id = result["prompt_id"]

    start = time.monotonic()
    while True:
        time.sleep(5)
        if time.monotonic() - start > JOB_TIMEOUT_S:
            raise RuntimeError(f"WAN2.2 render timed out after {JOB_TIMEOUT_S}s.")
        with urllib.request.urlopen(f"{SERVER}/history/{prompt_id}", timeout=30) as resp:
            history = json.loads(resp.read())
        if prompt_id not in history:
            continue
        entry = history[prompt_id]
        status = entry.get("status", {})
        if status.get("status_str") == "error":
            raise RuntimeError(f"ComfyUI reported an error: {json.dumps(status)[:2000]}")
        if status.get("completed"):
            return entry.get("outputs", {})


def generate_video(
    prompt: str,
    output_path: str,
    mode: str = "two-stage",
    width: int = 512,
    height: int = 288,
    frames: int = 97,
    frame_rate: int = 24,
    seed: int | None = None,
    image: str | None = None,
    verbose: bool = True,
) -> dict:
    if mode not in MODE_STEPS:
        return {"success": False, "error": f"Unknown mode '{mode}', expected one of {sorted(MODE_STEPS)}"}
    if not COMFYUI_PYTHON.is_file():
        return {"success": False, "error": f"ComfyUI venv not found at {COMFYUI_PYTHON}."}

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    steps_high, steps_low = MODE_STEPS[mode]
    wan_frames = _wan_native_frames(frames, frame_rate)
    if seed is None:
        seed = int.from_bytes(__import__("os").urandom(4), "big")

    if width * height > 320 * 192 * 3 and verbose:
        print(
            f"Warning: {width}x{height} is well above the ~512x288 ceiling verified stable on "
            "24GB RAM (2026-10-04); larger sizes risk memory-pressure stalls.",
            file=sys.stderr,
        )

    image_filename = None
    copied_image_path = None
    if image:
        src = Path(image).expanduser().resolve()
        if not src.is_file():
            return {"success": False, "error": f"Image not found: {src}"}
        image_filename = f"wan22-{uuid.uuid4().hex[:10]}{src.suffix}"
        copied_image_path = COMFYUI_ROOT / "input" / image_filename
        shutil.copy(src, copied_image_path)

    save_prefix = f"video/wan22-{uuid.uuid4().hex[:10]}"

    if verbose:
        print(
            f"WAN2.2-I2V-A14B ({mode}, {width}x{height}, {wan_frames} native frames "
            f"@ {WAN_NATIVE_FPS}fps, {steps_high}+{steps_low} steps)...",
            file=sys.stderr,
        )

    proc = subprocess.Popen(
        [str(COMFYUI_PYTHON), "main.py", "--listen", COMFYUI_HOST, "--port", str(COMFYUI_PORT), "--cache-none"],
        cwd=COMFYUI_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    start_time = time.time()
    try:
        _wait_for_server(proc, SERVER_START_TIMEOUT_S)
        graph = _build_graph(prompt, width, height, wan_frames, steps_high, steps_low, seed, image_filename, save_prefix)
        outputs = _submit_and_wait(graph)
    except Exception as error:  # noqa: BLE001 - surfaced to the caller below
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        return {"success": False, "error": str(error)}
    finally:
        if copied_image_path and copied_image_path.exists():
            copied_image_path.unlink(missing_ok=True)

    proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()

    elapsed_ms = int((time.time() - start_time) * 1000)
    save_info = outputs.get("save_video", {})
    saved = (save_info.get("images") or save_info.get("video") or [None])[0]
    if not saved or not isinstance(saved, dict):
        return {"success": False, "error": f"ComfyUI finished but no saved video found in outputs: {outputs}"}

    rendered_path = COMFYUI_ROOT / "output" / saved.get("subfolder", "") / saved["filename"]
    if not rendered_path.is_file():
        return {"success": False, "error": f"Expected rendered file missing: {rendered_path}"}

    shutil.move(str(rendered_path), str(output_path))

    return {
        "success": True,
        "output": str(output_path),
        "mode": mode,
        "width": width,
        "height": height,
        "frames": wan_frames,
        "frame_rate": WAN_NATIVE_FPS,
        "seed": seed,
        "inference_time_ms": elapsed_ms,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--mode", default="two-stage", choices=sorted(MODE_STEPS))
    parser.add_argument("--frames", type=int, default=97)
    parser.add_argument("--frame-rate", type=int, default=24)
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=288)
    parser.add_argument("--image", default=None)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

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
    )
    print(json.dumps(result))
    if not result.get("success"):
        sys.exit(1)


if __name__ == "__main__":
    main()
