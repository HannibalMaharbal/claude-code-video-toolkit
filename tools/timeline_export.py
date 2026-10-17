#!/usr/bin/env python3
"""
HANNIBAL AI OS — Timeline Export Engine (FCPXML & OTIO)
Exportiert Video-Projekte und Storyboards als NLE-Timelines für DaVinci Resolve,
Final Cut Pro und Premiere Pro — vollkommen ohne DaVinci-Studio-Lizenz oder
proprietäre Python-Scripting-Abhängigkeiten.

Unterstützt:
1. FCPXML v1.9 / v1.10 (Kanonischer Standard für DaVinci Resolve Import)
2. OpenTimelineIO (.otio)
3. Automatische Spuren: V1 (Video-Clips), A1 (Voiceover), A2 (BGM)
4. Marker für Color Grading, Foley & Quality-Control
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TimelineClip:
    name: str
    file_path: Path
    duration_frames: int
    start_frame: int = 0
    shot_id: str = ""


@dataclass
class TimelineMarker:
    frame: int
    name: str
    color: str = "blue"  # blue, green, yellow, red, cyan
    note: str = ""


@dataclass
class TimelineProject:
    name: str
    fps: float = 24.0
    width: int = 1920
    height: int = 1080
    video_clips: list[TimelineClip] = field(default_factory=list)
    voiceover_path: Path | None = None
    voiceover_duration_frames: int = 0
    bgm_path: Path | None = None
    bgm_duration_frames: int = 0
    markers: list[TimelineMarker] = field(default_factory=list)


def export_fcpxml(project: TimelineProject, output_path: Path | str) -> Path:
    """
    Erzeugt eine standardkonforme FCPXML v1.9 Datei für DaVinci Resolve.
    """
    out_file = Path(output_path).resolve()
    fps = int(project.fps)
    frame_duration = f"1/{fps}s"

    # Wurzel-Element
    fcpxml = ET.Element("fcpxml", version="1.9")

    # Resources
    resources = ET.SubElement(fcpxml, "resources")
    ET.SubElement(
        resources,
        "format",
        id="r1",
        name=f"FFVideoFormat{project.width}x{project.height}p{fps}",
        frameDuration=frame_duration,
        width=str(project.width),
        height=str(project.height),
    )

    asset_id_map: dict[str, str] = {}
    res_counter = 2

    # Registriere Video-Assets
    for clip in project.video_clips:
        res_id = f"r{res_counter}"
        res_counter += 1
        asset_id_map[str(clip.file_path)] = res_id
        ET.SubElement(
            resources,
            "asset",
            id=res_id,
            name=clip.name,
            src=clip.file_path.as_uri(),
            duration=f"{clip.duration_frames}/{fps}s",
            format="r1",
        )

    # Registriere Audio-Assets
    if project.voiceover_path and project.voiceover_path.is_file():
        vo_res_id = f"r{res_counter}"
        res_counter += 1
        asset_id_map[str(project.voiceover_path)] = vo_res_id
        ET.SubElement(
            resources,
            "asset",
            id=vo_res_id,
            name="Voiceover_A1",
            src=project.voiceover_path.as_uri(),
            duration=f"{project.voiceover_duration_frames}/{fps}s",
            hasAudio="1",
        )

    if project.bgm_path and project.bgm_path.is_file():
        bgm_res_id = f"r{res_counter}"
        res_counter += 1
        asset_id_map[str(project.bgm_path)] = bgm_res_id
        ET.SubElement(
            resources,
            "asset",
            id=bgm_res_id,
            name="Music_A2",
            src=project.bgm_path.as_uri(),
            duration=f"{project.bgm_duration_frames}/{fps}s",
            hasAudio="1",
        )

    # Library & Event
    library = ET.SubElement(fcpxml, "library")
    event = ET.SubElement(library, "event", name=project.name)
    project_elem = ET.SubElement(event, "project", name=project.name)

    # Gesamt-Dauer berechnen
    total_video_frames = sum(c.duration_frames for c in project.video_clips)
    sequence = ET.SubElement(
        project_elem,
        "sequence",
        format="r1",
        duration=f"{total_video_frames}/{fps}s",
        tcStart="0s",
    )

    spine = ET.SubElement(sequence, "spine")

    # Video Clips auf Spine platzieren
    current_offset_frames = 0
    for idx, clip in enumerate(project.video_clips):
        clip_res_id = asset_id_map.get(str(clip.file_path), "r2")
        clip_elem = ET.SubElement(
            spine,
            "asset-clip",
            ref=clip_res_id,
            name=clip.name,
            duration=f"{clip.duration_frames}/{fps}s",
            start="0s",
            offset=f"{current_offset_frames}/{fps}s",
        )

        # Prüfe, ob Marker auf diesen Clip fallen
        for m in project.markers:
            if current_offset_frames <= m.frame < (current_offset_frames + clip.duration_frames):
                local_marker_frame = m.frame - current_offset_frames
                ET.SubElement(
                    clip_elem,
                    "marker",
                    start=f"{local_marker_frame}/{fps}s",
                    duration=frame_duration,
                    value=m.name,
                    note=m.note,
                )

        # Erstes Video-Element erhält die synchronisierten Audio-Spuren als verbundene Audio-Clips
        if idx == 0:
            if project.voiceover_path and project.voiceover_path.is_file():
                vo_id = asset_id_map[str(project.voiceover_path)]
                ET.SubElement(
                    clip_elem,
                    "asset-clip",
                    ref=vo_id,
                    lane="-1",
                    name="Voiceover_A1",
                    duration=f"{min(project.voiceover_duration_frames, total_video_frames)}/{fps}s",
                    start="0s",
                    offset=f"{current_offset_frames}/{fps}s",
                    role="dialogue",
                )
            if project.bgm_path and project.bgm_path.is_file():
                bgm_id = asset_id_map[str(project.bgm_path)]
                ET.SubElement(
                    clip_elem,
                    "asset-clip",
                    ref=bgm_id,
                    lane="-2",
                    name="BGM_A2",
                    duration=f"{min(project.bgm_duration_frames, total_video_frames)}/{fps}s",
                    start="0s",
                    offset=f"{current_offset_frames}/{fps}s",
                    role="music",
                )

        current_offset_frames += clip.duration_frames

    tree = ET.ElementTree(fcpxml)
    ET.indent(tree, space="  ", level=0)
    tree.write(out_file, encoding="utf-8", xml_declaration=True)
    return out_file


def export_otio(project: TimelineProject, output_path: Path | str) -> Path:
    """
    Erzeugt eine OpenTimelineIO-Datei (.otio).
    """
    try:
        import opentimelineio as otio
    except ImportError:
        raise RuntimeError("opentimelineio ist nicht installiert.")

    out_file = Path(output_path).resolve()
    rate = project.fps

    timeline = otio.schema.Timeline(name=project.name)
    video_track = otio.schema.Track(name="V1_Video", kind=otio.schema.TrackKind.Video)
    timeline.tracks.append(video_track)

    for clip in project.video_clips:
        media_ref = otio.schema.ExternalReference(
            target_url=clip.file_path.as_uri(),
            available_range=otio.opentime.TimeRange(
                start_time=otio.opentime.RationalTime(0, rate),
                duration=otio.opentime.RationalTime(clip.duration_frames, rate),
            ),
        )
        otio_clip = otio.schema.Clip(
            name=clip.name,
            media_reference=media_ref,
            source_range=otio.opentime.TimeRange(
                start_time=otio.opentime.RationalTime(0, rate),
                duration=otio.opentime.RationalTime(clip.duration_frames, rate),
            ),
        )
        video_track.append(otio_clip)

    # Audio Tracks
    if project.voiceover_path and project.voiceover_path.is_file():
        vo_track = otio.schema.Track(name="A1_Voiceover", kind=otio.schema.TrackKind.Audio)
        vo_ref = otio.schema.ExternalReference(target_url=project.voiceover_path.as_uri())
        vo_clip = otio.schema.Clip(
            name="Voiceover",
            media_reference=vo_ref,
            source_range=otio.opentime.TimeRange(
                start_time=otio.opentime.RationalTime(0, rate),
                duration=otio.opentime.RationalTime(project.voiceover_duration_frames, rate),
            ),
        )
        vo_track.append(vo_clip)
        timeline.tracks.append(vo_track)

    otio.adapters.write_to_file(timeline, str(out_file))
    return out_file


def build_timeline_project_from_manifest(manifest_path: Path | str) -> TimelineProject:
    """
    Erstellt ein TimelineProject direkt aus einem project_manifest.json.
    """
    m_path = Path(manifest_path).resolve()
    with open(m_path, encoding="utf-8") as f:
        data = json.load(f)

    base_dir = m_path.parent
    project_name = data.get("project_id", "Timeline_Export")
    tech_specs = data.get("technical_specs", {})
    fps = tech_specs.get("fps", 24.0)

    res_str = tech_specs.get("resolution", "1920x1080")
    if "x" in res_str:
        w_str, h_str = res_str.split("x", 1)
        width, height = int(w_str), int(h_str)
    else:
        width, height = 1920, 1080

    tp = TimelineProject(name=project_name, fps=fps, width=width, height=height)

    # Shots
    current_frame = 0
    for idx, shot in enumerate(data.get("shots", []), start=1):
        shot_id = shot.get("id", f"shot-{idx:02d}")
        src = shot.get("source", "")
        p_src = Path(src)
        if p_src.is_absolute() and p_src.is_file():
            clip_path = p_src
        elif (base_dir / p_src).is_file():
            clip_path = (base_dir / p_src).resolve()
        elif (base_dir.parent / p_src).is_file():
            clip_path = (base_dir.parent / p_src).resolve()
        else:
            clip_path = (base_dir / p_src).resolve()

        dur_frames = shot.get("duration_frames", int(shot.get("duration_sec", 6.0) * fps))
        tp.video_clips.append(
            TimelineClip(
                name=f"{shot_id}__{clip_path.stem}",
                file_path=clip_path,
                duration_frames=dur_frames,
                start_frame=current_frame,
                shot_id=shot_id,
            )
        )
        # Standard-Marker für Color Grading
        tp.markers.append(
            TimelineMarker(
                frame=current_frame,
                name=f"Color Pass: {shot_id}",
                color="cyan",
                note="Grade scene matching master asset.",
            )
        )
        current_frame += dur_frames

    # Audio
    audio_assets = data.get("audio_assets", {})
    if "voiceover" in audio_assets:
        vo_raw = audio_assets["voiceover"].get("path")
        if vo_raw:
            tp.voiceover_path = (
                (base_dir / vo_raw) if not Path(vo_raw).is_absolute() else Path(vo_raw)
            )
            tp.voiceover_duration_frames = int(
                audio_assets["voiceover"].get("duration_sec", current_frame / fps) * fps
            )

    if "bgm" in audio_assets:
        bgm_raw = audio_assets["bgm"].get("path")
        if bgm_raw:
            tp.bgm_path = (base_dir / bgm_raw) if not Path(bgm_raw).is_absolute() else Path(bgm_raw)
            tp.bgm_duration_frames = int(
                audio_assets["bgm"].get("duration_sec", current_frame / fps) * fps
            )

    return tp


def main() -> int:
    parser = argparse.ArgumentParser(description="HANNIBAL Timeline Export (FCPXML / OTIO)")
    parser.add_argument("--manifest", "-m", required=True, help="Pfad zu project_manifest.json")
    parser.add_argument("--output", "-o", help="Zielpfad (.fcpxml oder .otio)")
    parser.add_argument("--format", choices=["fcpxml", "otio", "both"], default="both")

    args = parser.parse_args()
    manifest_path = Path(args.manifest).resolve()

    if not manifest_path.is_file():
        print(f"Fehler: Manifest {manifest_path} nicht gefunden.", file=sys.stderr)
        return 1

    tp = build_timeline_project_from_manifest(manifest_path)
    base_out = (
        Path(args.output).resolve() if args.output else manifest_path.parent / f"{tp.name}_timeline"
    )

    if args.format in ("fcpxml", "both"):
        fcpxml_path = base_out.with_suffix(".fcpxml")
        export_fcpxml(tp, fcpxml_path)
        print(f"[OK] FCPXML erzeugt: {fcpxml_path}")

    if args.format in ("otio", "both"):
        otio_path = base_out.with_suffix(".otio")
        export_otio(tp, otio_path)
        print(f"[OK] OTIO erzeugt:   {otio_path}")

    print("\n>>> DaVinci Resolve Workflow:")
    print("1. DaVinci Resolve öffnen")
    print(f"2. Menü: File -> Import -> Timeline... -> Datei auswählen ({base_out.stem}.fcpxml)")
    print("3. Timeline liegt frame-genau mit V1 (Video), A1 (Voice) & A2 (Music) bereit.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
