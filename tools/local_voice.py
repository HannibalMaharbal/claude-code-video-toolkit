#!/usr/bin/env python3
"""Offline Qwen3-TTS voice cloning on Apple Silicon via MLX-Audio.

The model is never fetched implicitly during generation. Run ``--setup`` once
to download the free model, then generate with a local reference recording.
Cloning requires an explicit consent confirmation for that reference voice.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

MODEL_ID = "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16"
SAMPLE_RATE = 24_000
_MODEL = None


def _model_path(*, allow_download: bool = False) -> Path:
    from huggingface_hub import snapshot_download
    try:
        return Path(snapshot_download(
            repo_id=MODEL_ID,
            local_files_only=not allow_download,
        ))
    except Exception as error:
        if not allow_download:
            raise RuntimeError(
                f"Lokales Modell fehlt ({MODEL_ID}). Einmalig ohne Kosten einrichten: "
                "python tools/local_voice.py --setup"
            ) from error
        raise


def setup_model() -> Path:
    """Download the open model to the local Hugging Face cache."""
    try:
        return _model_path(allow_download=True)
    except Exception as error:
        raise RuntimeError(f"Lokaler Qwen3-TTS-Modellabruf fehlgeschlagen: {error}") from error


def _load_model():
    global _MODEL
    if _MODEL is None:
        from mlx_audio.tts.utils import load_model
        _MODEL = load_model(str(_model_path()))
    return _MODEL


def generate_audio(
    *,
    text: str,
    output_path: str | Path,
    ref_audio: str | Path,
    ref_text: str,
    language: str = "German",
    consent_confirmed: bool = False,
) -> dict:
    """Generate one local cloned-voice WAV or MP3; never makes a cloud call."""
    if not consent_confirmed:
        return {"success": False, "error": "Voice cloning requires --consent-confirmed."}
    reference = Path(ref_audio).expanduser().resolve()
    if not reference.is_file():
        return {"success": False, "error": f"Lokale Referenzaufnahme fehlt: {reference}"}
    if not text.strip() or not ref_text.strip():
        return {"success": False, "error": "Zieltext und exaktes Referenz-Transkript sind erforderlich."}
    if reference.stat().st_size > 25 * 1024 * 1024:
        return {"success": False, "error": "Referenzaufnahme ist größer als 25 MB."}

    target = Path(output_path).expanduser().resolve()
    if target == reference or target.with_suffix(".wav") == reference:
        return {"success": False, "error": "Ausgabepfad darf die Referenzaufnahme nicht überschreiben."}
    if target.exists() or (target.suffix.lower() != ".wav" and target.with_suffix(".wav").exists()):
        return {"success": False, "error": f"Ausgabedatei existiert bereits: {target}"}

    try:
        model_dir = _model_path()
        import numpy as np
        import soundfile as sf
        model = _load_model()
        results = list(model.generate(
            text=text.strip(),
            ref_audio=str(reference),
            ref_text=ref_text.strip(),
            lang_code=language.lower(),
            verbose=False,
        ))
        if not results:
            return {"success": False, "error": "Qwen3-TTS lieferte keine Audiodaten."}
        samples = np.asarray(results[0].audio).squeeze()
        if samples.ndim != 1 or samples.size == 0 or not np.isfinite(samples).all():
            return {"success": False, "error": "Qwen3-TTS lieferte ungültige Audiodaten."}
        target.parent.mkdir(parents=True, exist_ok=True)
        wav_path = target if target.suffix.lower() == ".wav" else target.with_suffix(".wav")
        sf.write(str(wav_path), samples, SAMPLE_RATE, subtype="PCM_24")
        if target != wav_path:
            import subprocess
            subprocess.run(
                ["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(wav_path),
                 "-codec:a", "libmp3lame", "-q:a", "0", str(target)],
                check=True, capture_output=True, text=True,
            )
            wav_path.unlink(missing_ok=True)
        return {
            "success": True,
            "output": str(target),
            "model": MODEL_ID,
            "language": language,
            "duration_seconds": round(samples.size / SAMPLE_RATE, 3),
            "local_only": True,
            "consent_confirmed": True,
        }
    except Exception as error:
        return {"success": False, "error": f"Lokale Sprachgenerierung fehlgeschlagen: {error}"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--setup", action="store_true", help="Lädt das ca. 2,5-GB-Modell kostenlos lokal herunter.")
    parser.add_argument("--text")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--ref-audio", type=Path)
    parser.add_argument("--ref-text")
    parser.add_argument("--language", default="German")
    parser.add_argument("--consent-confirmed", action="store_true")
    args = parser.parse_args()
    if args.setup:
        try:
            print(setup_model())
            return 0
        except RuntimeError as error:
            print(error, file=sys.stderr)
            return 1
    if not all((args.text, args.output, args.ref_audio, args.ref_text)):
        parser.error("--text, --output, --ref-audio und --ref-text sind beim Generieren erforderlich")
    result = generate_audio(
        text=args.text, output_path=args.output, ref_audio=args.ref_audio,
        ref_text=args.ref_text, language=args.language,
        consent_confirmed=args.consent_confirmed,
    )
    if not result["success"]:
        print(result["error"], file=sys.stderr)
        return 1
    print(result["output"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
