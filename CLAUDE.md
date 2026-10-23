# claude-code-video-toolkit

This file provides guidance to Claude Code (claude.ai/code) when working with this video production toolkit.

## Overview

**claude-code-video-toolkit** is an AI-native video production workspace. It provides Claude Code with the skills, commands, and tools to create professional videos from concept to final render.

**Key capabilities:**
- Programmatic video creation with Remotion (React-based)
- Local voiceover generation with Kokoro and Piper; local Qwen3-TTS cloning after setup
- AI music generation with ACE-Step 1.5 (text-to-music, vocals, covers, stems)
- Browser demo recording with Playwright
- Asset processing with FFmpeg

## Directory Structure

```
claude-code-video-toolkit/
├── .claude/
│   ├── skills/          # Domain knowledge for Claude
│   └── commands/        # Guided workflows
├── tools/               # Python CLI automation
├── templates/           # Video templates
│   ├── sprint-review/   # Sprint review video template
│   └── product-demo/    # Marketing/product demo template
├── brands/              # Brand profiles (colors, fonts, voice)
├── projects/            # Your video projects go here (gitignored)
├── examples/            # Curated showcase projects (shared)
├── assets/              # Shared assets (voices, images)
├── playwright/          # Browser recording infrastructure
├── docs/                # Documentation
└── _internal/           # Toolkit metadata & registry
```

## Registry

`_internal/toolkit-registry.json` is the canonical source for all skills, commands, tools, templates, components, transitions, and cloud endpoints — including their paths, status, options, presets, and env vars. Consult it for structured data. This file focuses on **workflow guidance, patterns, and knowledge** that the registry can't capture.

## Quick Start

**First-time setup (optional, ~5 minutes):**
```
/setup
```

Walks through cloud GPU, file transfer (R2), and voice configuration. Most features are free. Skip this if you just want to render videos with Node.js.

**Work on a video project:**
```
/video
```

This command will:
1. Scan for existing projects (resume or create new)
2. Choose template (sprint-review, product-demo)
3. Choose brand (or create one with `/brand`)
4. Plan scenes interactively
5. Create project with VOICEOVER-SCRIPT.md

**Multi-session support:** Projects span multiple sessions. Run `/video` to resume where you left off. Each project tracks its phase, scenes, assets, and session history in `project.json`.

**Or manually:**
```bash
cp -r templates/sprint-review projects/my-video
cd projects/my-video
npm install
npm run studio   # Preview
npm run render   # Export
```

> **Note:** After creating or modifying commands/skills, restart Claude Code to load changes.

## Templates

Templates live in `templates/`. Each is a standalone Remotion project. See registry `templates` section for the full list.

### sprint-review
Config-driven sprint review videos with theme system, config-driven content (`sprint-config.ts`), pre-built slides (Title, Overview, Summary, Credits), demo components (single video, split-screen), and audio integration.

### product-demo
Marketing/product demo videos with dark tech aesthetic, scene-based composition (title, problem, solution, demo, stats, CTA), animated background, Narrator PiP, browser/terminal chrome, and stats cards with spring animations.

## Brand Profiles

Brands live in `brands/`. Each defines visual identity:

```
brands/my-brand/
├── brand.json    # Colors, fonts, typography
├── voice.json    # Local voice provider settings
└── assets/       # Logo, backgrounds
```

See `docs/creating-brands.md` for details.

## Shared Components

Reusable video components in `lib/components/`. See registry `components` section for the full list with descriptions. Import in templates via:

```tsx
import { AnimatedBackground, SlideTransition, Label } from '../../../../lib/components';
```

## Python Tools

Audio, video, and image tools in `tools/`. See registry `tools` section for the full catalog with descriptions, options, presets, and env vars. Every tool supports `--help`.

```bash
# Setup (Python 3.12, locked)
uv sync --frozen
```

**Important: always invoke tools from the toolkit root directory.** When working inside a project (`projects/my-video/`), tool paths like `python3 tools/upscale.py` will fail because `tools/` is relative. Always use:
```bash
cd /path/to/claude-code-video-toolkit && python3 tools/upscale.py ...
```
This is especially critical for background commands where the working directory may not be obvious.

### Tool Categories

| Type | Tools | When to Use |
|------|-------|-------------|
| **Project tools** | voiceover, music, music_gen, sfx, sync_timing | During video creation workflow |
| **Utility tools** | redub, addmusic, notebooklm_brand, locate_watermark | Quick transformations on existing videos |
| **Free local** | transcribe, kokoro_tts, piper_tts, local_voice, redub, z_image, ltx2_local, seedvr2_mlx_adapter, subtitle_translate (`--engine argos`) | Local transcription (mlx-whisper), TTS (Kokoro/Piper), consent-gated Qwen3-TTS cloning/dubbing, image/video generation, video restoration/upscaling and offline translation — Apple Silicon, no API key |
| **Cloud GPU** | image_edit, upscale, dewatermark, sadtalker, qwen3_tts, music_gen, flux2 | Optional external GPU processing; provider pricing and usage limits must be checked before use. The local `local_voice`/`redub` path does not use this cloud tool. |
| **Cloud, low-cost** | gemini_tts, subtitle_translate (default engine) | Google Gemini API — rate-limited free tier + cheap paid tier; NOT local, NOT unconditionally free |
| **Cloud, paid** | higgsfield_video | Higgsfield CLI video generation — always cost-gated, shows credits before spending |

Utility tools work on any video file without requiring a project structure.

### Voiceover Generation

Default provider is **kokoro** (local, no API key). **piper** is local German TTS. **qwen3-local** is available for reference-voice cloning; it requires the optional `local-voice` extra, the already cached local model, an exact reference transcript and explicit consent. Azure Arabic is an optional explicit provider and is never a fallback.

```bash
# Per-scene generation (recommended) — Kokoro by default
python tools/voiceover.py --scene-dir public/audio/scenes --json

# Pick a specific Kokoro voice
python tools/voiceover.py --voice am_michael --scene-dir public/audio/scenes --json
python tools/voiceover.py --voice af_heart --scene-dir public/audio/scenes --json
python tools/voiceover.py --voice bm_george --speed 0.95 --scene-dir public/audio/scenes --json

# Local Qwen3-TTS voice cloning (requires a permitted reference voice)
uv run --extra local-voice tools/voiceover.py --provider qwen3-local \
  --script SCRIPT.md --ref-audio REFERENCE.wav \
  --ref-text "Exact transcript of the reference" --consent-confirmed \
  --output voiceover.wav

# Single file
python tools/voiceover.py --script SCRIPT.md --output out.mp3
```

### Timing Sync (after voiceover)

```bash
python3 tools/sync_timing.py                          # Dry run comparison
python3 tools/sync_timing.py --apply                  # Update config (1s default padding)
python3 tools/sync_timing.py --apply --padding 1.5    # Custom padding
python3 tools/sync_timing.py --voiceover-json vo.json # Use voiceover.py output
python3 tools/sync_timing.py --json                   # Machine-readable output
```

### Free Transcription (mlx-whisper, Apple Silicon)

```bash
python tools/transcribe.py --input video.mp4               # Auto transcript
python tools/transcribe.py --input audio.mp3 --output t.txt # Save to file
python tools/transcribe.py --input video.mp4 --model large-v3 # Best quality
python tools/transcribe.py --input video.mp4 --language de  # Force language
```

Models: `tiny` (fast) → `small` (default) → `medium` → `large-v3` (best quality)

### Subtitle Translation

```bash
python tools/subtitle_translate.py --input de.srt --output en.srt --target-language English
```

Default engine is **argos** (local, offline, no account). Gemini remains available only through explicit `--engine gemini` selection.

**Argos Translate** was added 2026-09-26 as the local default — a dedicated neural translation model, not an LLM being asked to follow a prompt. Live-verified end-to-end with a real 3-line SRT file (de→en, correct natural translation, exit 0) and again on 2026-09-27 with network access blocked. Requires the language pair to be installed once (`de`/`en` already installed at `~/.local/share/argos-translate/packages/`; use `install_argos_language_pair(from_code, to_code)` in `subtitle_translate.py` for others).

`--engine ollama` (local, offline, `devstral-small-2:latest`) exists only for explicit comparison — verified live to intermittently echo the prompt template's literal placeholder text instead of translating, and to occasionally not return within 60s+. It now fails loudly with a clear error in the common case instead of silently writing wrong subtitles, but is **not recommended**; use `--engine argos` instead for local/confidential translation.

### Piper TTS (Standalone, local, German)

Free, offline German voiceover — no API key, no cold start. Default voice is Thorsten (high quality).

```bash
python tools/piper_tts.py --text "Hallo Welt" --output hallo.mp3
python tools/piper_tts.py --text "Hallo Welt" --speed 0.9 --output langsam.mp3
python tools/piper_tts.py --list-voices
```

Also available as a `voiceover.py` provider:

```bash
python tools/voiceover.py --provider piper --scene-dir public/audio/scenes --json
python tools/voiceover.py --provider piper --piper-speed 0.9 --script script.txt --output out.mp3
```

Model: `~/AI-Modelle/piper/de/de_DE/thorsten/high/de_DE-thorsten-high.onnx`. `--speed` is a multiplier (>1 = faster), consistent with the other providers; converted internally to Piper's native `--length-scale`.

### Gemini TTS (Standalone, cloud, low-cost)

**Not local, not free** — a Google cloud API call, distinct from Piper/Kokoro. Noticeably higher quality: natural prosody, emotional style direction, 130+ languages with automatic detection. Has a rate-limited free tier (free-tier content is used by Google to improve its products per Google's terms) plus paid tiers beyond that — check current pricing/limits at ai.google.dev/gemini-api/docs/pricing before heavy use.

```bash
python tools/gemini_tts.py --text "Hallo Welt" --output hallo.wav
python tools/gemini_tts.py --text "Hallo Welt" --style "cheerful and friendly" --output out.wav
python tools/gemini_tts.py --text "..." --model gemini-3.8-flash-tts --voice Puck --output out.wav
python tools/gemini_tts.py --list-voices
```

Also available as a `voiceover.py` provider:

```bash
python tools/voiceover.py --provider gemini --scene-dir public/audio/scenes --json
python tools/voiceover.py --provider gemini --gemini-style "warm and friendly" --script script.txt --output out.mp3
```

Requires `GEMINI_API_KEY` in the environment (already present in `~/.secrets`, sourced by `~/.zshrc` — no per-project `.env` entry needed). Two models: `gemini-3.8-flash-tts` (flagship, richest emotional range) and `gemini-3.8-flash-lite-tts` (default, cheaper, high-throughput). Verified live 2026-09-26: a German test phrase round-tripped through MLX Whisper at 92-99% word confidence.

### Azure Speech TTS (Arabic dialects, cloud, usage-billed)

The optional `azure` provider in `tools/voiceover.py` supports Tunisian
(`ar-TN`), Algerian (`ar-DZ`), Moroccan (`ar-MA`), Lebanese (`ar-LB`), Syrian
(`ar-SY`) and Egyptian (`ar-EG`) neural voices. Azure does not list a dedicated
Modern Standard Arabic locale; `ar-msa` is explicitly a Saudi voice reading
formal Arabic, not a neutral MSA voice. Each supported locale offers a female
and a male voice.

Requires `AZURE_SPEECH_KEY` and `AZURE_SPEECH_REGION` from an Azure Speech
resource. Each live run requires `--confirm-cloud`; it sends script text to
Microsoft. The Azure pricing page currently lists 0.5 million neural TTS
characters free per month; usage after the free allowance may be billed.
The real-time TTS path returns audio without Microsoft retaining the input text
or generated audio according to Microsoft's data-handling documentation.

```bash
uv run tools/voiceover.py --provider azure --azure-locale ar-TN \
  --azure-gender female --confirm-cloud --script SCRIPT.md --output voiceover.mp3
uv run tools/voiceover.py --provider azure --azure-locale ar-EG \
  --azure-gender male --confirm-cloud --scene-dir public/audio/scenes --json
```

### Kokoro TTS (Standalone, local)

```bash
python tools/kokoro_tts.py --text "Hello world" --output hello.mp3
python tools/kokoro_tts.py --text "Hello" --voice am_michael --output hello.mp3
python tools/kokoro_tts.py --text "Hello" --voice bm_george --speed 0.9 --output slow.mp3
python tools/kokoro_tts.py --list-voices   # 28 voices: af_heart, am_michael, bm_george, etc.
```

For production/video editing, prefer `.wav`: the local wrapper writes lossless
24-bit PCM. MP3 output uses maximum-quality VBR (`libmp3lame -q:a 0`) when a
smaller file is needed.

28 voices across 4 groups: American Female (af_*), American Male (am_*), British Female (bf_*), British Male (bm_*).
Best all-around: `af_heart` (warm female), `am_michael` (professional male, default), `bm_george` (British professional).
Model artifacts are cached locally; German WAV generation was verified on 2026-09-28.

### Qwen3-TTS (Standalone, Cloud; optional and potentially billed)

This standalone `qwen3_tts.py` command uses a Modal or RunPod GPU endpoint and is separate from the local `qwen3-local` provider above. It is not needed for local TTS or local dubbing. Check the selected provider's current price and account usage before running it; do not assume a free tier.

```bash
python tools/qwen3_tts.py --text "Hello world" --speaker Ryan --output hello.mp3
python tools/qwen3_tts.py --text "Hello world" --tone warm --output hello.mp3
python tools/qwen3_tts.py --text "Hello" --instruct "Speak enthusiastically" --output excited.mp3
python tools/qwen3_tts.py --text "Hello" --ref-audio sample.wav --ref-text "transcript" --output cloned.mp3
python tools/qwen3_tts.py --list-voices   # 9 speakers: Ryan, Aiden, Vivian, etc.
python tools/qwen3_tts.py --list-tones    # neutral, warm, professional, excited, etc.
```

Temperature controls expressiveness: `--temperature 1.2` (more expressive) or `--temperature 0.4` (more consistent).

### Cloud GPU Providers

All cloud GPU tools support two providers via `--cloud runpod|modal`. RunPod is the default. Modal was added as a reliability fallback after RunPod outages, and offers faster cold starts.

```bash
# --- RunPod setup (automated, one-time per tool) ---
echo "RUNPOD_API_KEY=your_key_here" >> .env
python tools/image_edit.py --setup
python tools/upscale.py --setup
python tools/qwen3_tts.py --setup
python tools/music_gen.py --setup

# --- Modal setup (deploy each app you need) ---
pip install modal && python3 -m modal setup
modal deploy docker/modal-upscale/app.py        # Then save URL to .env
modal deploy docker/modal-image-edit/app.py
# See docs/modal-setup.md for full guide
```

### AI Image Editing

```bash

# Image editing (Qwen-Image-Edit)
python tools/image_edit.py --input photo.jpg --prompt "Add sunglasses"
python tools/image_edit.py --input photo.jpg --prompt "Add sunglasses" --cloud modal
python tools/image_edit.py --input photo.jpg --style cyberpunk
python tools/image_edit.py --input photo.jpg --background office
python tools/image_edit.py --list-presets  # Full preset list

# Upscaling (RealESRGAN)
python tools/upscale.py --input photo.jpg --output photo_4x.png --cloud runpod
python tools/upscale.py --input photo.jpg --scale 2 --model anime --face-enhance --cloud runpod
```

See `docs/qwen-edit-patterns.md` and `.claude/skills/qwen-edit/` for prompting guidance.

### Z-Image Turbo (Standalone, local, MLX)

Free, offline text-to-image generation via `mlxgen` on Apple Silicon — no API key, no cloud cost.

```bash
python tools/z_image.py --prompt "A puffin on a cliff" --output puffin.png
python tools/z_image.py --prompt "Product shot" --width 1024 --height 1024 --steps 9
python tools/z_image.py --prompt "..." --seed 42 --output out.png
```

Uses the already-cached `AbstractFramework/z-image-turbo-4bit` snapshot by default, so no model download is triggered. Verified with a live test generation before being marked active in the registry (2026-09-26).

**Planned, not installed:** Qwen-Image (also via `mlxgen`) is noted as a future local image option in `_internal/toolkit-registry.json` (`qwen_image`, `status: planned`). No adapter exists and no download has been triggered — `mlxgen download --model Qwen/Qwen-Image` requires explicit approval first.

### LTX-2.5-MLX (Standalone, local, MLX)

Free, offline text-to-video / image-to-video generation with **synchronized audio** on Apple Silicon — no API key, no cloud cost, no Modal dependency. Distinct from `ltx2.py`, which wraps the cloud-hosted LTX-2.3 22B via Modal (paid).

```bash
python tools/ltx25_mlx_adapter.py --prompt "A sunset over the ocean" --output sunset.mp4
python tools/ltx25_mlx_adapter.py --prompt "..." --frames 49 --seed 42 --output clip.mp4
python tools/ltx25_mlx_adapter.py --prompt "Animate this" --image photo.jpg --output animated.mp4
python tools/ltx25_mlx_adapter.py --prompt "The action continues naturally" --continue-from previous.mp4 --output next.mp4

# Generate a whole local sequence; every follow-up clip uses --continue-from automatically
python tools/chain_video.py --scenes-dir images/ --output-dir videos/ --end 5 --prompt "The action continues naturally"
python tools/ltx25_mlx_adapter.py --prompt "..." --mode two-stages-hq --output hq.mp4   # native HQ defaults, no TeaCache
```

Runtime: `~/PROJEKTE/AI-Modelle/ltx-2-mlx` (github.com/MrMoferFRAN/ltx-2-mlx, branch `ltx25`, pinned commit `57952288`). Weights: `~/PROJEKTE/AI-Modelle/ltx-2.5-mlx-q8`. `--low-ram` (block streaming) is on by default and mandatory at 24GB RAM — the full model needs ~72GB without it. The shared adapter automatically adds continuity, motivated camera motion, anti-flicker and reference-lock constraints. `--continue-from` decodes the exact final frame available from the preceding clip into a temporary lossless PNG and supplies it as the next clip's first-frame conditioning anchor; the temporary file is removed after the run. It cannot be combined with `--image`. Of the modes installed in this pinned MLX runtime, `two-stages-hq` is the maximum-quality choice: it keeps the native 15-step `res_2s` path and disables TeaCache. `two-stage` is the balanced accelerated choice; `distilled` remains the fastest and only live-verified default.

Production capability boundaries and the evidence-based LoRA/alpha/realtime
assessment are documented in
`docs/LTX-PRODUCTION-ASSESSMENT-2026-10-20.md`. Do not describe upstream LoRA
training, the separate Alpha-Gen/Layout-to-Render IC-LoRAs, or realtime
generation as active features of the installed MLX adapter without a separate
local live test.

The official Lightricks LTX-2.5 stack recommends DFR for production quality, but DFR is not available in this pinned MLX runtime and the installed model pack does not contain its required detailing IC-LoRA. Do not describe the local HQ mode as equivalent to DFR, and do not update the protected runtime or download additional weights without Hannibal's explicit approval.

Verified with a live test generation before being marked active in the registry (2026-09-26): 704×448, 97 frames (4.0s), `--distilled --low-ram` on M4 Pro / 24GB RAM — **190.7s render time**. The audio track carries real synchronized speech generated purely from the prompt text: MLX Whisper transcribed the target German phrase back out of the rendered clip at 94-97% word confidence.

**Known limitation:** the model does not reliably honor camera-facing / "looks into the camera" framing instructions in the prompt — review the actual output frames before relying on visible lip-sync. Frame count must be `8k+1` (25, 49, 97, …); height/width must be divisible by 32.

### SeedVR2-MLX (Standalone, local video restoration)

Free, offline video restoration on Apple Silicon through the local
4-bit SeedVR2 3B checkpoint. The adapter preserves audio by default, applies
temporally overlapping chunks, refuses incomplete weights and never overwrites
an existing output.

```bash
# Guarded source-size restoration (verified envelope: up to 640x352, five frames)
python tools/seedvr2_mlx_adapter.py --input soft.mp4 --output proof-restored.mp4 \
  --temporal-chunk-size 5 --temporal-chunk-overlap 4 --max-frames 5 \
  --guarded-memory-override

# Validate the exact local command without inference
python tools/seedvr2_mlx_adapter.py --input soft.mp4 --output restored.mp4 \
  --dry-run --json
```

Runtime entry point: `mflux-upscale-seedvr2` from the locally installed
`mlx-gen`. Weights: `~/AI-Modelle/SeedVR2-MLX-4bit`. Defaults are conservative
for a 24 GB Mac: `1x`, wavelet color correction, low-RAM mode, 1 GB MLX cache,
49-frame temporal chunks and 16-frame overlap.

`mlx-gen` 0.38.0 recalculates its post-chunk budget from RAM availability after
model allocation, causing a false rejection even when the host had sufficient
headroom. Because its unsafe flag disables upstream runtime limits, this adapter
reproduces the upstream workload estimator before launch, adds measured model
residency, a 2 GB system reserve and a conservative 24x Metal calibration factor.
The factor is based on a real 640x360→1280x720 OOM that exposed severe upstream
underestimation. Upscaling above source size is therefore blocked on this 24 GB
host; source-size restoration is allowed only when the complete workload-specific
budget fits and remains within the verified 640x352/5-frame envelope. Guarded
mode requires an explicit `--max-frames` of at most 5 and caps MLX cache at 1 GB.
The stricter of the dynamic plan and the empirically verified 13 GB available-RAM
floor always applies.
Live Metal verification on 2026-10-23 produced valid 5-frame H.264
outputs at 128x128 and 640x352; the latter completed in 14.79 seconds. Retain the
CAS/LTX/Topaz cascade for upscaling or when the preflight refuses execution.

### Higgsfield Video (Cloud, paid, cost-gated)

Wraps the installed and authenticated `higgsfield` CLI. **Always shows the credit cost and account balance before spending anything** — generation only runs with `--confirm`.

```bash
# Cost preview only — no job created, no charge
python tools/higgsfield_video.py --prompt "cinematic product shot" --output clip.mp4

# Generate for real (only after reviewing the cost)
python tools/higgsfield_video.py --prompt "cinematic product shot" --output clip.mp4 --confirm

# Image-to-video
python tools/higgsfield_video.py --prompt "camera pans right" --image photo.jpg --output clip.mp4 --confirm

# List available video models
python tools/higgsfield_video.py --list-models
```

Default model is `seedance_2_0_mini` (cost-efficient); override with `--model <job_type>`. Without `--confirm` the tool only runs `higgsfield generate cost` and `higgsfield account status` — verified live to be free of charge (balance unchanged after a dry cost check).

### AI Music Generation (ACE-Step 1.5)

Default provider is **acemusic** (official cloud API, free key from [acemusic.ai/api-key](https://acemusic.ai/api-key)). Uses XL Turbo 4B model with 5Hz LM thinking mode. Falls back to Modal/RunPod for self-hosted 2B model.

```bash
# Background music (acemusic cloud API by default)
python tools/music_gen.py --prompt "Upbeat tech corporate" --duration 60 --bpm 128 --key "G Major" --output music.mp3

# Generate 4 variations, pick the best
python tools/music_gen.py --prompt "Subtle corporate tech" --duration 60 --variations 4 --output bg.mp3

# Fast mode (disable thinking)
python tools/music_gen.py --no-thinking --prompt "Quick draft" --duration 30 --output draft.mp3

# Scene presets for video production
python tools/music_gen.py --preset corporate-bg --duration 60 --output bg.mp3
python tools/music_gen.py --preset tension --duration 20 --output problem.mp3
python tools/music_gen.py --preset cta --brand digital-samba --output cta.mp3

# Song with vocals and lyrics (use structure tags for sections)
python tools/music_gen.py \
  --prompt "Indie pop anthem, male vocal, bright guitar, studio polish" \
  --lyrics "[Verse]\nWalking through the morning light\nCoffee in my hand feels right\n\n[Chorus - anthemic]\nWE KEEP MOVING FORWARD\nThrough the noise and doubt\n\n[Outro - fade]\n(Moving forward...)" \
  --duration 60 --bpm 128 --key "G Major" --output song.mp3

# Cover / style transfer
python tools/music_gen.py --cover --reference theme.mp3 --prompt "Jazz piano version" --output cover.mp3

# Repaint a weak section (acemusic only)
python tools/music_gen.py --repaint --input track.mp3 --repaint-start 15 --repaint-end 25 --prompt "Guitar solo" --output fixed.mp3

# Continue from existing audio (acemusic only)
python tools/music_gen.py --continuation --input track.mp3 --prompt "Continue with jazz piano" --output extended.mp3

# Stem extraction
python tools/music_gen.py --extract vocals --input mixed.mp3 --output vocals.mp3

# Fall back to self-hosted
python tools/music_gen.py --cloud modal --prompt "Background music" --duration 60 --output bg.mp3

# List presets
python tools/music_gen.py --list-presets
```

8 scene presets: `corporate-bg`, `upbeat-tech`, `ambient`, `dramatic`, `tension`, `hopeful`, `cta`, `lofi`. See `.claude/skills/acestep/` for prompt engineering patterns and video production integration guide.

### Watermark Removal

```bash
# Locate watermark coordinates
python tools/locate_watermark.py --input video.mp4 --grid --output-dir ./review/
python tools/locate_watermark.py --input video.mp4 --preset notebooklm --verify

# Remove watermark (RunPod)
python tools/dewatermark.py --input video.mp4 --region 1080,660,195,40 --output clean.mp4 --runpod
python tools/dewatermark.py --setup  # One-time setup
```

**Workflow:** grid overlay → note coordinates → verify with `--region` → remove with dewatermark.

**Local mode** requires NVIDIA GPU (8GB+ VRAM). Mac users should use `--runpod`.

### Talking Head Generation (SadTalker)

```bash
# Basic usage
python tools/sadtalker.py --image portrait.png --audio voiceover.mp3 --output talking.mp4

# For NarratorPiP integration (recommended settings)
# CRITICAL: --preprocess full preserves image dimensions (otherwise outputs square crop)
python tools/sadtalker.py \
  --image presenter_16x9.png \
  --audio voiceover.mp3 \
  --preprocess full --still --expression-scale 0.8 \
  --output narrator.mp4
```

**Key flags for NarratorPiP:**
- `--preprocess full` — **Critical!** Preserves input dimensions (default `crop` outputs square)
- `--still` — Reduces head movement for professional look
- `--expression-scale 0.8` — Calmer expression (default 1.0)

**Image requirements:** Face 30-70% of frame, front-facing, 16:9 for NarratorPiP, 512px+ recommended.

See `docs/sadtalker.md` for detailed options and troubleshooting.

### Local Dubbing (Qwen3-TTS)

```bash
uv run --extra local-voice tools/redub.py \
  --input video.mp4 \
  --ref-audio REFERENCE.wav \
  --ref-text "Exact transcript of the reference" \
  --source-language English --target-language German \
  --output dubbed.mp4 --consent-confirmed
```

This workflow runs MLX Whisper → local Argos translation → local Qwen3-TTS → FFmpeg. It requires permission to use the reference voice and never falls back to a cloud provider. The generated dub replaces the original audio track; the original ambience and music are not retained separately. Listen to the result and check translation/timing before release.

### NotebookLM Branding

Post-processes NotebookLM videos with custom branding. Solves the problem where redubbed TTS audio extends beyond the safe visual trim point.

```bash
python tools/notebooklm_brand.py \
    --input video_synced.mp4 \
    --logo assets/logo.png \
    --url "mysite.com" \
    --output video_final.mp4
```

Trims NotebookLM visuals, keeps full audio, bridges with freeze frame, adds branded outro.

## Video Production Workflow

1. **Create/resume project** - Run `/video`, choose template and brand (or resume existing)
2. **Review script** - Edit `VOICEOVER-SCRIPT.md` to plan content
3. **Gather assets** - Record demos with `/record-demo` or add external videos
4. **Scene review** - Run `/scene-review` to verify visuals in Remotion Studio
5. **Design refinement** - Use `/design` or the "Refine" option in scene-review to improve slide visuals
6. **Generate audio** - Use `/generate-voiceover` for AI narration
7. **Sync timing** - Run `python3 tools/sync_timing.py --apply` to update config durations
8. **Preview** - `npm run studio` in project directory
9. **Iterate** - Adjust timing, content, styling with Claude Code
10. **Render** - `npm run render` for final MP4

## Project Lifecycle

Projects move through phases tracked in `project.json`:

```
planning → assets → review → audio → editing → rendering → complete
```

| Phase | Description |
|-------|-------------|
| `planning` | Defining scenes, writing script |
| `assets` | Recording demos, gathering materials |
| `review` | Scene-by-scene review in Remotion Studio (`/scene-review`) |
| `audio` | Generating voiceover, music |
| `editing` | Adjusting timing, previewing |
| `rendering` | Final render in progress |
| `complete` | Done |

See `lib/project/README.md` for details on the project system.

## Video Timing

Timing is critical. Keep these guidelines in mind:

### Pacing Rules
- **Voiceover drives timing** — Narration length determines scene duration
- **Reading pace** — ~150 words/minute (2.5 words/second) for standard narration
- **Demo pacing** — Real-time demos often need 1.5-2x speedup (`playbackRate`)
- **Transitions** — Add 1-2s padding between scenes
- **FPS** — All videos use 30fps (frames = seconds × 30)

### Speaking Rate Tiers

| Pace | WPM | Use When |
|------|-----|----------|
| Slow | 120-130 | Technical explanations, complex concepts |
| Standard | 140-160 | General narration, demos, overviews |
| Fast | 160-180 | Energetic intros, recaps, CTAs |

### Narration Density by Scene Type

| Scene Type | Duration | Narration Density | Notes |
|------------|----------|-------------------|-------|
| Title | 3-5s | 0-10% | Logo + headline, let visuals breathe |
| Overview | 10-20s | 70-90% | 3-5 bullet points, narration-heavy |
| Demo | 10-30s | 30-50% | Let the demo speak, narrate key moments only |
| Stats | 8-12s | 70-90% | Read out highlights, skip obvious numbers |
| Credits | 5-10s | 0-20% | Quick fade, maybe a closing line |
| Problem/Solution | 10-15s | 80-90% | Narration drives the story |
| CTA | 5-10s | 60-80% | Clear call to action, leave a beat at end |

### Word Count Budgeting

Before writing scripts, budget words per scene:

```
Target duration × 2.5 = word budget (at standard pace)
Pause seconds × 2.5 = words to subtract from budget

Example: 15s scene with a 1s pause
  15 × 2.5 = 37 words budget
  1 × 2.5 = 3 words for pause
  Available: ~34 words of narration
```

Use `[pause 1.0s]` markers in scripts. Each second of pause costs ~2-3 words from the budget.

### Timing Calculations
```
Script words ÷ 150 = voiceover minutes (estimate)
Raw demo length ÷ playbackRate = demo duration
Sum of scenes + transitions = total video
```

### When to Check Timing
- **During scene planning** — Budget word counts per scene before writing
- **After writing script** — Count words per scene, compare to budget
- **After generating audio** — Run `sync_timing.py` to compare actual vs estimated
- **Before rendering** — Ensure `durationInFrames` matches actual audio for each scene

### TTS Duration Drift (The Real Timing Problem)

TTS engines do NOT consistently produce 150 WPM output. In practice:
- Local TTS timing can vary; check pacing against the script before export.
- **Qwen3-TTS** varies by speaker and tone preset. Ryan at "professional" tone speaks ~10% faster than "warm."
- **Short scenes drift more** — a 5-second scene might be off by 30%, while a 30-second scene is off by 10%.

**The feedback loop after TTS generation:**

1. Generate per-scene audio files
2. Run `python3 tools/sync_timing.py` to compare actual vs config durations
3. Run `python3 tools/sync_timing.py --apply` to update config automatically
4. For demo scenes: recalculate `playbackRate = rawDemoDuration / actualNarrationDuration`
5. Re-preview in Remotion Studio before rendering

**Common drift patterns and fixes:**

| Problem | Symptom | Fix |
|---------|---------|-----|
| Audio shorter than scene | Dead air / awkward silence at end | Reduce `durationInFrames` to match audio |
| Audio longer than scene | Narration cut off | Increase `durationInFrames` or trim script |
| Demo too fast for narration | Viewer can't follow | Decrease `playbackRate` or cut narration |
| Demo too slow for narration | Waiting for demo to catch up | Increase `playbackRate` (1.5-2x typical) |
| Pauses lost in TTS | Script felt spacious, audio feels rushed | Add explicit `<break time="1s"/>` in SSML or extend scene padding |

### Fixing Mismatches
- **Voiceover too long**: Speed up demos, trim pauses, cut content
- **Voiceover too short**: Slow demos, add scenes, expand narration
- **Demo too long**: Increase `playbackRate` (1.5x-2x typical)
- **Demo too short**: Decrease `playbackRate`, or loop/extend

### Audio-Anchored Timelines (the prevention approach)

`sync_timing.py` is reactive — it fixes drift after the fact. You can prevent drift entirely by **generating the audio first, then anchoring visuals to known timestamps** instead of estimating durations upfront.

**The pattern:**

1. Write the script and split into per-scene segments
2. Generate per-scene VO files: `voiceover.py --scene-dir public/audio/scenes --json`
3. Read the actual durations from the JSON output
4. Anchor every visual element to absolute timestamps in the timeline

This is especially clean for Python/moviepy builds where each clip carries its own `start=` parameter:

```python
# Audio-anchored scene timeline (25s total):
#   Scene 1 tired      0.3 → 3.74  (audio 3.44s)
#   Scene 2 worries    4.0 → 8.88  (audio 4.88s)
#   Scene 3 introduce  9.1 → 11.90 (audio 2.80s)

text_clip("TIRED OF",     start=0.5,  duration=1.2)
text_clip("THIRD-PARTY",  start=1.0,  duration=1.8)
vo_clip("01_tired.mp3",   start=0.3)
vo_clip("02_worries.mp3", start=4.0)
```

The comment block at the top is the source of truth. Every `start=` references it. Drift is impossible because durations aren't being estimated — they're being read from the rendered audio.

**Trade-off vs. `<Series>`-style auto-chaining:**

| Approach | Best for | Downside |
|----------|----------|----------|
| Audio-anchored absolute starts | Tight ad-style edits, sub-30s spots, anything with exact timing | Manual bookkeeping when re-timing a scene |
| `<Series>` / auto-chained durations | Long-form sprint reviews where adjacent scenes flex | Drift compounds across the timeline; needs `sync_timing.py` to recover |

For Remotion projects you can mix the two: use `<Sequence from={...}>` with absolute frames for tight sections and let `<Series>` handle the rest. For pure-Python builds (`build.py` + moviepy), audio-anchored is the natural default.

## Key Patterns

### Animations (Remotion)
```tsx
const frame = useCurrentFrame();
const opacity = interpolate(frame, [0, 20], [0, 1], { extrapolateRight: 'clamp' });
```

### Sequencing
```tsx
<Series>
  <Series.Sequence durationInFrames={150}><TitleSlide /></Series.Sequence>
  <Series.Sequence durationInFrames={900}><DemoClip /></Series.Sequence>
</Series>
```

### Media

**Always use `<OffthreadVideo>`, never `<video>`** — Remotion requires its own video component for frame-accurate rendering. Using a raw `<video>` tag will not render correctly.

```tsx
<OffthreadVideo src={staticFile('demo.mp4')} />
<Audio src={staticFile('voiceover.mp3')} volume={1} />
<Audio src={staticFile('music.mp3')} volume={0.15} />
```

## Scene Transitions

The toolkit includes a transitions library at `lib/transitions/`. See registry `transitions` section for the full list with options and best-use descriptions.

### Using TransitionSeries

```tsx
import { TransitionSeries, linearTiming } from '@remotion/transitions';
import { glitch, lightLeak, zoomBlur } from '../../../lib/transitions';

<TransitionSeries>
  <TransitionSeries.Sequence durationInFrames={90}>
    <TitleSlide />
  </TransitionSeries.Sequence>
  <TransitionSeries.Transition
    presentation={glitch({ intensity: 0.8 })}
    timing={linearTiming({ durationInFrames: 20 })}
  />
  <TransitionSeries.Sequence durationInFrames={120}>
    <ContentSlide />
  </TransitionSeries.Sequence>
</TransitionSeries>
```

### Transition Options Examples

```tsx
glitch({ intensity: 0.8, slices: 8, rgbShift: true })      // Tech/cyberpunk
lightLeak({ temperature: 'warm', direction: 'right' })       // Warm celebration
zoomBlur({ direction: 'in', blurAmount: 20 })                // High energy
rgbSplit({ direction: 'diagonal', displacement: 30 })        // Chromatic aberration
```

### Timing Functions

```tsx
linearTiming({ durationInFrames: 30 })                                      // Constant speed
springTiming({ config: { damping: 200 }, durationInFrames: 45 })            // Physics bounce
```

### Transition Duration Guidelines

| Type | Frames | Notes |
|------|--------|-------|
| Quick cut | 10-15 | Fast, punchy |
| Standard | 20-30 | Most common |
| Dramatic | 40-60 | Slow reveals |
| Glitch effects | 15-25 | Should feel sudden |
| Light leak | 30-45 | Needs time to sweep |

Preview all transitions: `cd showcase/transitions && npm run studio`

See `lib/transitions/README.md` for full documentation.

## Design Refinement with frontend-design Skill

The `frontend-design` skill elevates slide visuals from generic to distinctive.

### Usage
- **During scene review** (`/scene-review`): Choose "Refine" for visual improvements
- **Focused sessions** (`/design`): Deep-dive on a specific scene — `/design title`, `/design cta`

### When to Use
- Slide scenes that feel generic
- When building visual contrast between scenes (e.g., calm title → harsh problem)
- When animations feel too basic or too busy

### Visual Narrative Arc
Consider how visual intensity builds across scenes:
- **Title**: Set the mood, plant visual seeds
- **Problem**: Create tension (harsh contrast)
- **Solution**: Relief and hope return
- **Demo**: Neutral, content-focused
- **Stats**: Build credibility
- **CTA**: Climax - maximum visual energy

## Toolkit vs Project Work

**Toolkit work** (evolves the toolkit itself):
- Skills, commands, templates, tools
- Tracked in `_internal/ROADMAP.md`

**Project work** (creates videos):
- Lives in `projects/`
- Each project has `project.json` (machine-readable state) and auto-generated `CLAUDE.md`

Keep these separate. Don't mix toolkit improvements with video production.

## Documentation

- `docs/getting-started.md` - First video walkthrough
- `docs/creating-templates.md` - Build new templates
- `docs/creating-brands.md` - Create brand profiles
- `docs/optional-components.md` - Setup for optional ML-based tools (ProPainter, etc.)
