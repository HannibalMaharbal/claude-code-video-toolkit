#!/usr/bin/env python3
"""Local German dubbing using MLX Whisper, Argos and consent-gated Qwen3-TTS.

The generated voice replaces the source audio track. Original ambience/music
is not separated or retained. Source audio, translation, reference voice and
render remain local; this command has no cloud provider or upload path.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from local_voice import generate_audio
from subtitle_translate import _normalize_argos_lang, _translate, _translate_argos
from transcribe import transcribe

WHISPER_MODELS = ("tiny", "small", "medium")


def _run(command: list[str]) -> str:
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _duration(path: Path) -> float:
    return float(_run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "csv=p=0", str(path),
    ]))


def _language_code(value: str) -> str:
    normalized = _normalize_argos_lang(value)
    return "de" if normalized == "de" else "en" if normalized == "en" else normalized


def dub_video(
    *,
    source: Path,
    output: Path,
    ref_audio: Path,
    ref_text: str,
    source_language: str,
    target_language: str,
    whisper_model: str,
    consent_confirmed: bool,
    preserve_bg: bool = True,
) -> dict:
    if not consent_confirmed:
        raise ValueError("Voice cloning benötigt --consent-confirmed für die Referenzstimme.")
    source = source.expanduser().resolve()
    output = output.expanduser().resolve()
    ref_audio = ref_audio.expanduser().resolve()
    if not source.is_file() or not ref_audio.is_file():
        raise ValueError("Video und lokale Referenzaufnahme müssen vorhanden sein.")
    if source == output or source == ref_audio or output == ref_audio or not ref_text.strip():
        raise ValueError("Ausgabe muss neu sein; Referenzaufnahme und Transkript sind erforderlich.")
    if output.exists():
        raise ValueError(f"Ausgabedatei existiert bereits: {output}")
    if output.suffix.lower() not in {".mp4", ".mov", ".m4v"}:
        raise ValueError("Ausgabe muss MP4, MOV oder M4V sein.")
    if whisper_model not in WHISPER_MODELS:
        raise ValueError(f"Modell muss eine dieser lokal unterstützten Größen sein: {WHISPER_MODELS}")

    payload = transcribe(
        str(source), model=whisper_model,
        language=_language_code(source_language), word_timestamps=False, verbose=True,
    )
    segments = payload.get("segments", []) if isinstance(payload, dict) else []
    if not segments:
        raise RuntimeError("Lokale MLX-Whisper-Transkription lieferte keine Segmente.")

    duration = _duration(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="local-dub-", dir=output.parent) as temp_dir:
        temp = Path(temp_dir)
        clips: list[tuple[Path, float, float]] = []
        for index, segment in enumerate(segments):
            text = str(segment.get("text", "")).strip()
            start, end = float(segment["start"]), float(segment["end"])
            if not text or start < 0 or end <= start or end > duration + 0.25:
                continue
            translated = _translate(
                text, target_language, "qwen2.5-coder:14b", "argos", source_language
            )
            clip_path = temp / f"segment-{index:04d}.wav"
            result = generate_audio(
                text=translated, output_path=clip_path, ref_audio=ref_audio,
                ref_text=ref_text, language=target_language,
                consent_confirmed=True,
            )
            if not result.get("success"):
                raise RuntimeError(f"Lokale TTS-Segmentgenerierung fehlgeschlagen: {result.get('error')}")
            clip_duration = float(result["duration_seconds"])
            slot_duration = end - start
            if clip_duration > slot_duration * 1.75:
                raise RuntimeError(
                    f"Übersetztes Segment {index + 1} ist zu lang ({clip_duration:.2f}s für "
                    f"{slot_duration:.2f}s). Text oder Quellsegment manuell kürzen."
                )
            clips.append((clip_path, start, end))
        if not clips:
            raise RuntimeError("Keine gültigen Sprachsegmente zum Synchronisieren.")

        inputs: list[str] = []
        filters: list[str] = []
        for index, (clip, start, _) in enumerate(clips):
            inputs.extend(["-i", str(clip)])
            delay_ms = round(start * 1000)
            filters.append(f"[{index}:a]adelay={delay_ms}|{delay_ms}[a{index}]")
        labels = "".join(f"[a{index}]" for index in range(len(clips)))
        filters.append(
            f"{labels}amix=inputs={len(clips)}:duration=longest:normalize=0,"
            f"alimiter=limit=0.95,apad,atrim=duration={duration:.3f}[dub]"
        )
        dub_audio = temp / "dubbed.wav"
        _run([
            "ffmpeg", "-nostdin", "-y", "-v", "error", *inputs,
            "-filter_complex", ";".join(filters), "-map", "[dub]",
            "-ar", "24000", "-ac", "1", "-c:a", "pcm_s24le", str(dub_audio),
        ])
        if preserve_bg:
            filter_complex = (
                "[0:a]volume=0.35,aresample=48000[orig_bg];"
                "[1:a]aresample=48000,asplit=2[voice_mix][voice_side];"
                "[orig_bg][voice_side]sidechaincompress=threshold=0.02:ratio=5:attack=30:release=400[ducked_bg];"
                "[ducked_bg][voice_mix]amix=inputs=2:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[aout]"
            )
            _run([
                "ffmpeg", "-nostdin", "-y", "-v", "error",
                "-i", str(source), "-i", str(dub_audio),
                "-filter_complex", filter_complex,
                "-map", "0:v:0", "-map", "[aout]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                "-t", f"{duration:.3f}", "-movflags", "+faststart", str(output),
            ])
        else:
            _run([
                "ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(source),
                "-i", str(dub_audio), "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", f"{duration:.3f}",
                "-movflags", "+faststart", str(output),
            ])

    return {
        "success": True,
        "output": str(output),
        "segments": len(clips),
        "source_language": source_language,
        "target_language": target_language,
        "translation_engine": "argos-or-ollama-qwen2.5",
        "tts_model": "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16",
        "local_only": True,
        "consent_confirmed": True,
        "source_audio_replaced": not preserve_bg,
        "bg_preserved": preserve_bg,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ref-audio", type=Path, required=True)
    parser.add_argument("--ref-text", required=True, help="Exact transcript of the reference voice")
    parser.add_argument("--source-language", default="English")
    parser.add_argument("--target-language", default="German")
    parser.add_argument("--whisper-model", choices=WHISPER_MODELS, default="small")
    parser.add_argument("--consent-confirmed", action="store_true")
    parser.add_argument(
        "--replace-audio",
        action="store_true",
        help="Completely replace original audio instead of preserving/ducking background music",
    )
    args = parser.parse_args()
    try:
        result = dub_video(
            source=args.input, output=args.output, ref_audio=args.ref_audio,
            ref_text=args.ref_text, source_language=args.source_language,
            target_language=args.target_language, whisper_model=args.whisper_model,
            consent_confirmed=args.consent_confirmed,
            preserve_bg=not args.replace_audio,
        )
    except Exception as error:
        print(f"Lokales Dubbing fehlgeschlagen: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
