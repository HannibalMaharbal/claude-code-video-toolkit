#!/usr/bin/env python3
"""
immo-video: Autonome Exposé-to-Video Pipeline für Licbarska Immobilien
Erstellt aus Immobiliendaten und Bildern in Sekunden ein fertiges 9:16 Social Reel.
100 % lokal (Kokoro TTS + PIL Typography Overlay + FFmpeg VideoToolbox) bei exakt 0,00 € Kosten.
"""

import os
import sys
import argparse
import subprocess
import tempfile
from pathlib import Path

VENV_PYTHON = Path.home() / "Hannibal/02_AI/Projekte/video-toolkit/.venv/bin/python3"
KOKORO_SCRIPT = Path.home() / "Hannibal/02_AI/Projekte/video-toolkit/tools/kokoro_tts.py"
DEFAULT_EXPORT_DIR = Path.home() / "Hannibal/08_BUSINESS/Kunden/Licbarska/Projekt LICBARSKA-Immobilien/03_Export"

def generate_voiceover(text, audio_output):
    print("🎙️  [1/3] Generiere professionelles Makler-Voiceover mit Kokoro TTS (0 €)...")
    cmd = [
        str(VENV_PYTHON),
        str(KOKORO_SCRIPT),
        "--text", text,
        "--voice", "am_michael",
        "--speed", "1.0",
        "--output", str(audio_output)
    ]
    subprocess.run(cmd, check=True)
    print(f"    ✓ Audio erstellt: {audio_output}")

def get_audio_duration(audio_path):
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio_path)
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(out.stdout.strip())

def create_graphic_overlay(overlay_path, title, specs):
    # Generates a crisp transparent 1080x1920 overlay PNG using PIL in the venv
    pil_script = f"""
from PIL import Image, ImageDraw, ImageFont

img = Image.new('RGBA', (1080, 1920), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Top Banner Box (Dark Glassmorphism with gold accent)
draw.rectangle([(60, 120), (1020, 420)], fill=(15, 20, 30, 220), outline=(212, 175, 55, 255), width=3)

# Fonts
try:
    font_gold = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 34)
    font_title = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 44)
    font_specs = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 38)
    font_cta = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 36)
except Exception:
    font_gold = font_title = font_specs = font_cta = ImageFont.load_default()

# Top text
draw.text((540, 155), "LICBARSKA IMMOBILIEN", font=font_gold, fill=(212, 175, 55, 255), anchor="mm")
draw.text((540, 235), '''{title}''', font=font_title, fill=(255, 255, 255, 255), anchor="mm")
draw.text((540, 335), '''{specs}''', font=font_specs, fill=(255, 225, 120, 255), anchor="mm")

# Bottom CTA Box
draw.rectangle([(120, 1680), (960, 1820)], fill=(15, 20, 30, 230), outline=(255, 255, 255, 180), width=2)
draw.text((540, 1750), "Jetzt Besichtigung anfragen", font=font_cta, fill=(255, 255, 255, 255), anchor="mm")

img.save('{overlay_path}')
"""
    subprocess.run([str(VENV_PYTHON), "-c", pil_script], check=True)

def render_vertical_video(image_path, overlay_path, audio_path, output_path, duration):
    print(f"🎬  [2/3] Rendere 9:16 Video mit Apple VideoToolbox Hardware-Beschleunigung ({duration:.1f}s)...")
    
    fps = 30
    total_frames = int(duration * fps) + fps
    
    filter_complex = (
        f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
        f"crop=1080:1920,"
        f"zoompan=z='min(zoom+0.0005,1.15)':d={total_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps={fps}[bg];"
        f"[bg][1:v]overlay=0:0[v]"
    )

    cmd = [
        "ffmpeg", "-y", "-loglevel", "warning",
        "-loop", "1", "-i", str(image_path),
        "-i", str(overlay_path),
        "-i", str(audio_path),
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "2:a",
        "-c:v", "h264_videotoolbox", "-b:v", "6000k",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(output_path)
    ]
    subprocess.run(cmd, check=True)
    print(f"    ✓ Video erfolgreich gerendert: {output_path}")

def create_fallback_image(image_path):
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi",
        "-i", "color=c=0x111625:s=1080x1920:d=1",
        "-vframes", "1",
        str(image_path)
    ]
    subprocess.run(cmd, check=True)

def main():
    parser = argparse.ArgumentParser(description="Autonome Exposé-to-Video Pipeline für Licbarska Immobilien")
    parser.add_argument("--title", type=str, default="Exklusives Penthouse in Frankfurt", help="Objekttitel")
    parser.add_argument("--rooms", type=str, default="3.5 Zimmer", help="Zimmeranzahl")
    parser.add_argument("--area", type=str, default="118 m²", help="Wohnfläche")
    parser.add_argument("--price", type=str, default="785.000 €", help="Kauf- oder Mietpreis")
    parser.add_argument("--image", type=str, help="Pfad zum Objektfoto")
    parser.add_argument("--output", type=str, help="Zielpfad für das MP4-Video")
    parser.add_argument("--dry-run", action="store_true", help="Parameter-Check ohne Rendern")
    
    args = parser.parse_args()
    
    specs = f"{args.rooms}  •  {args.area}  •  {args.price}"
    script_text = (
        f"Willkommen zu Ihrem neuen Zuhause: {args.title}. "
        f"Diese Immobilie bietet {args.rooms} auf großzügigen {args.area} Wohnfläche. "
        f"Der Angebotspreis liegt bei {args.price}. "
        f"Kontaktieren Sie uns jetzt für ein persönliches Exposé bei Licbarska Immobilien."
    )
    
    if args.dry_run:
        print("[DRY-RUN] Exposé-to-Video Preflight:")
        print(f" - Titel: {args.title}")
        print(f" - Specs: {specs}")
        print(f" - Skript: \"{script_text}\"")
        print(f" - Image: {args.image or 'Automatischer Licbarska-Hintergrund'}")
        print(f" - Kosten: 0,00 € (100% lokal auf Mac M4 Pro)")
        print("[✓] Preflight erfolgreich.")
        return 0

    DEFAULT_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    out_file = Path(args.output) if args.output else DEFAULT_EXPORT_DIR / "expose_reel_latest.mp4"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        audio_file = tmp / "voiceover.wav"
        overlay_file = tmp / "overlay.png"
        
        # 1. Voiceover
        generate_voiceover(script_text, audio_file)
        duration = get_audio_duration(audio_file)
        
        # 2. Image & Graphic Overlay
        if args.image and Path(args.image).exists():
            img_file = Path(args.image)
        else:
            img_file = tmp / "base_img.png"
            create_fallback_image(img_file)
            
        create_graphic_overlay(overlay_file, args.title, specs)
            
        # 3. Video Render with VideoToolbox hardware acceleration
        render_vertical_video(img_file, overlay_file, audio_file, out_file, duration)
        
        print("\n" + "=" * 65)
        print(f"🎉 IMMO-REEL ERFOLGREICH FERTIGGESTELLT (0,00 € KLARE KOSTEN)!")
        print(f"📁 Zielort:  {out_file}")
        print(f"⏱️  Länge:    {duration:.1f} Sekunden (9:16 vertikal)")
        print(f"⚡ Hardware: Apple Silicon VideoToolbox H.264")
        print("=" * 65 + "\n")

    return 0

if __name__ == "__main__":
    sys.exit(main())
