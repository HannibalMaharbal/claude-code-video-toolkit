#!/usr/bin/env python3
"""
HANNIBAL AI OS — Remotion Social 9:16 Captions & Autopilot Generator
Wandelt Whisper-Wort-Timestamps in Remotion-Props für vertikale TikTok/Reels/Shorts
Videos um und erzwingt exakte Social-Media Safe Zones.

Safe Zones (1080 x 1920):
- Oben: 150px frei (Suchleiste/Tabs)
- Unten: 280px frei (Accountname, Sound, CTA)
- Rechts: 140px frei (Icons)
- Text-Zentrum: Y = 850 bis 1350 px (vertikal zentriert)
- Wort-Chunking: 3 bis maximal 4 Wörter pro Anzeige-Block
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class WordTiming:
    word: str
    start: float  # Sekunden
    end: float  # Sekunden


@dataclass
class CaptionChunk:
    text: str
    words: list[WordTiming]
    start_sec: float
    end_sec: float
    start_frame: int
    end_frame: int


@dataclass
class RemotionSocialProps:
    video_src: str
    width: int = 1080
    height: int = 1920
    fps: int = 30
    duration_in_frames: int = 0
    safe_zone: dict[str, int] = field(
        default_factory=lambda: {
            "top": 150,
            "bottom": 280,
            "right": 140,
            "left": 40,
            "caption_y_min": 850,
            "caption_y_max": 1350,
        }
    )
    theme: dict[str, str] = field(
        default_factory=lambda: {
            "font_family": "Inter, sans-serif",
            "font_size": "48px",
            "font_weight": "900",
            "text_color": "#FFFFFF",
            "highlight_color": "#FFD700",  # Gold / Gelb
            "stroke_color": "#000000",
            "stroke_width": "3px",
            "bg_box_color": "rgba(0, 0, 0, 0.4)",
        }
    )
    chunks: list[dict[str, Any]] = field(default_factory=list)


def parse_whisper_words(transcript_data: list[dict[str, Any]] | dict[str, Any]) -> list[WordTiming]:
    """
    Extrahiert Wort-Timings aus Whisper-JSON-Segmenten (mlx-whisper oder openai-whisper).
    """
    words_out: list[WordTiming] = []

    # Falls das Dict ein Root-Element "segments" oder "words" hat
    if isinstance(transcript_data, dict):
        if "words" in transcript_data and isinstance(transcript_data["words"], list):
            items = transcript_data["words"]
        elif "segments" in transcript_data and isinstance(transcript_data["segments"], list):
            items = []
            for seg in transcript_data["segments"]:
                if "words" in seg:
                    items.extend(seg["words"])
                else:
                    # Fallback ohne Word-Timestamps
                    text = seg.get("text", "").strip()
                    s = seg.get("start", 0.0)
                    e = seg.get("end", 0.0)
                    if text:
                        tokens = text.split()
                        seg_dur = max(e - s, 0.1)
                        token_dur = seg_dur / len(tokens)
                        for idx, tok in enumerate(tokens):
                            items.append(
                                {
                                    "word": tok,
                                    "start": round(s + (idx * token_dur), 2),
                                    "end": round(s + ((idx + 1) * token_dur), 2),
                                }
                            )
        else:
            items = []
    else:
        items = transcript_data

    for item in items:
        w_text = item.get("word", item.get("text", "")).strip()
        start = float(item.get("start", 0.0))
        end = float(item.get("end", start + 0.3))
        if w_text:
            words_out.append(WordTiming(word=w_text, start=start, end=end))

    return words_out


def build_caption_chunks(
    words: list[WordTiming], max_words_per_chunk: int = 4, fps: int = 30
) -> list[CaptionChunk]:
    """
    Gruppiert Wörter in kompakte 3-4 Wörter-Blöcke für maximale Lesbarkeit.
    """
    chunks: list[CaptionChunk] = []
    current_words: list[WordTiming] = []

    for word in words:
        current_words.append(word)
        if len(current_words) >= max_words_per_chunk:
            start_s = current_words[0].start
            end_s = current_words[-1].end
            text = " ".join(w.word for w in current_words)
            chunks.append(
                CaptionChunk(
                    text=text,
                    words=list(current_words),
                    start_sec=round(start_s, 2),
                    end_sec=round(end_s, 2),
                    start_frame=int(start_s * fps),
                    end_frame=int(end_s * fps),
                )
            )
            current_words = []

    if current_words:
        start_s = current_words[0].start
        end_s = current_words[-1].end
        text = " ".join(w.word for w in current_words)
        chunks.append(
            CaptionChunk(
                text=text,
                words=list(current_words),
                start_sec=round(start_s, 2),
                end_sec=round(end_s, 2),
                start_frame=int(start_s * fps),
                end_frame=int(end_s * fps),
            )
        )

    return chunks


def generate_remotion_social_props(
    video_path: Path | str,
    transcript_json_path: Path | str,
    output_props_path: Path | str,
    fps: int = 30,
    video_duration_sec: float = 60.0,
) -> Path:
    """
    Liest Transcript, baut Chunks und schreibt remotion inputProps JSON.
    """
    t_path = Path(transcript_json_path).resolve()
    with open(t_path, encoding="utf-8") as f:
        t_data = json.load(f)

    words = parse_whisper_words(t_data)
    chunks = build_caption_chunks(words, max_words_per_chunk=3, fps=fps)

    v_path = Path(video_path).resolve()
    props = RemotionSocialProps(
        video_src=str(v_path),
        fps=fps,
        duration_in_frames=int(video_duration_sec * fps),
        chunks=[
            {
                "text": c.text,
                "startFrame": c.start_frame,
                "endFrame": c.end_frame,
                "words": [asdict(w) for w in c.words],
            }
            for c in chunks
        ],
    )

    out_file = Path(output_props_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(asdict(props), f, indent=2, ensure_ascii=False)

    return out_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Remotion Social 9:16 Captions Props Generator")
    parser.add_argument("--video", "-v", required=True, help="Pfad zum Roh- oder Schnittvideo")
    parser.add_argument(
        "--transcript", "-t", required=True, help="Pfad zur Whisper-JSON-Transkription"
    )
    parser.add_argument(
        "--output", "-o", default="social_props.json", help="Ausgabepfad für Remotion Props JSON"
    )
    parser.add_argument("--duration", "-d", type=float, default=60.0, help="Videodauer in Sekunden")
    parser.add_argument("--fps", type=int, default=30, help="Frames per second (Standard: 30)")

    args = parser.parse_args()
    out = generate_remotion_social_props(
        video_path=args.video,
        transcript_json_path=args.transcript,
        output_props_path=args.output,
        fps=args.fps,
        video_duration_sec=args.duration,
    )
    print(f"[OK] Remotion Social Props generiert: {out}")
    print("Aufruf mit Remotion CLI:")
    print(f"  npx remotion render src/index.ts SocialAdMaster output.mp4 --props={out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
