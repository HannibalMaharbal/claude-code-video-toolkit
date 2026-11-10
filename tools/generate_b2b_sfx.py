#!/usr/bin/env python3
"""Procedural B2B Sound Effects (SFX) Synthesizer.

Synthesizes 4 signature high-end UI/motion sound design cues for Remotion B2B reels:
1. whoosh_subtle.mp3 — Smooth motion transition (bandpassed pink noise envelope).
2. ui_pop_clean.mp3 — Apple-like clean UI pop for badge & counter pop-ins.
3. bass_impact.mp3 — Warm sub-bass cinematic impact for headline hook entrances.
4. gold_shimmer.mp3 — Soft harmonic chime for CTA and trust badge reveals.

100% royalty-free, locally generated, zero external dependencies beyond numpy/scipy/ffmpeg.
"""

from __future__ import annotations

import math
import os
import subprocess
import sys
from pathlib import Path
import numpy as np
from scipy.io import wavfile

SAMPLE_RATE = 48000


def synthesize_whoosh(duration: float = 0.45) -> np.ndarray:
    n_samples = int(SAMPLE_RATE * duration)
    # Pink-like noise
    white = np.random.normal(0, 1, n_samples)
    b = [0.049922035, -0.095993537, 0.050612699, -0.004408786]
    a = [1, -2.494956002, 2.017265875, -0.522189400]
    from scipy.signal import lfilter
    filtered = lfilter(b, a, white)

    # Smooth parabolic volume envelope
    t = np.linspace(0, 1, n_samples)
    envelope = np.sin(np.pi * t) ** 2.5
    whoosh = filtered * envelope
    return whoosh / (np.max(np.abs(whoosh)) + 1e-6)


def synthesize_pop(duration: float = 0.12) -> np.ndarray:
    n_samples = int(SAMPLE_RATE * duration)
    t = np.linspace(0, duration, n_samples)
    # Frequency sweep from 750 Hz down to 220 Hz
    freq = np.linspace(750, 220, n_samples)
    phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
    sine = np.sin(phase)
    envelope = np.exp(-t * 32.0)
    pop = sine * envelope
    return pop / (np.max(np.abs(pop)) + 1e-6)


def synthesize_bass_impact(duration: float = 0.9) -> np.ndarray:
    n_samples = int(SAMPLE_RATE * duration)
    t = np.linspace(0, duration, n_samples)
    # Sub-bass pitch drop from 90 Hz to 42 Hz
    freq = np.linspace(90, 42, n_samples)
    phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
    sub = np.sin(phase) + 0.3 * np.sin(2 * phase)
    envelope = np.exp(-t * 4.5)
    impact = sub * envelope
    # Soft saturation
    impact = np.tanh(impact * 1.5)
    return impact / (np.max(np.abs(impact)) + 1e-6)


def synthesize_shimmer(duration: float = 0.6) -> np.ndarray:
    n_samples = int(SAMPLE_RATE * duration)
    t = np.linspace(0, duration, n_samples)
    # Harmonic triad: 1200 Hz, 1500 Hz, 1800 Hz
    chord = (
        0.5 * np.sin(2 * np.pi * 1200 * t)
        + 0.35 * np.sin(2 * np.pi * 1500 * t)
        + 0.25 * np.sin(2 * np.pi * 1800 * t)
    )
    envelope = np.sin(np.pi * np.clip(t / 0.08, 0, 1) / 2) * np.exp(-t * 6.0)
    shimmer = chord * envelope
    return shimmer / (np.max(np.abs(shimmer)) + 1e-6)


def save_audio_file(samples: np.ndarray, wav_path: Path, mp3_path: Path) -> None:
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    mp3_path.parent.mkdir(parents=True, exist_ok=True)
    int16_samples = (samples * 32767).astype(np.int16)
    wavfile.write(str(wav_path), SAMPLE_RATE, int16_samples)

    # Convert to MP3 via ffmpeg
    cmd = [
        "ffmpeg", "-y", "-i", str(wav_path),
        "-codec:a", "libmp3lame", "-qscale:a", "2",
        str(mp3_path)
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    if wav_path.is_file():
        wav_path.unlink()  # Keep clean MP3 only


def generate_all_sfx(target_dir: Path) -> list[Path]:
    sfx_manifest = [
        ("whoosh_subtle.mp3", synthesize_whoosh()),
        ("ui_pop_clean.mp3", synthesize_pop()),
        ("bass_impact.mp3", synthesize_bass_impact()),
        ("gold_shimmer.mp3", synthesize_shimmer()),
    ]
    created: list[Path] = []
    for filename, samples in sfx_manifest:
        wav_file = target_dir / filename.replace(".mp3", ".wav")
        mp3_file = target_dir / filename
        save_audio_file(samples, wav_file, mp3_file)
        created.append(mp3_file)
    return created


def main() -> int:
    toolkit_root = Path(__file__).resolve().parents[1]
    sfx_target = toolkit_root / "templates" / "b2b-reel-remotion" / "public" / "sfx"
    assets_target = toolkit_root / "assets" / "sfx"

    created = generate_all_sfx(sfx_target)
    # Also sync to toolkit assets
    import shutil
    assets_target.mkdir(parents=True, exist_ok=True)
    for c in created:
        shutil.copy2(c, assets_target / c.name)

    print("=" * 60)
    print(" PROCEDURAL B2B SOUND DESIGN ENGINE")
    print("=" * 60)
    for c in created:
        print(f"  + SFX generiert: {c.name} ({c.stat().st_size} Bytes)")
    print(f"\n[+] Zielordner: {sfx_target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
