"""Unit tests for tools/timeline_export.py (FCPXML & OTIO export)."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from tools.timeline_export import (
    TimelineClip,
    TimelineMarker,
    TimelineProject,
    build_timeline_project_from_manifest,
    export_fcpxml,
    export_otio,
)


@pytest.fixture
def sample_timeline_project(tmp_path: Path):
    clips_dir = tmp_path / "clips"
    clips_dir.mkdir()

    clips = []
    for i in range(1, 4):
        p = clips_dir / f"clip_{i:02d}.mp4"
        p.write_bytes(b"dummy_mp4_bytes")
        clips.append(
            TimelineClip(
                name=f"Scene_{i:02d}",
                file_path=p,
                duration_frames=144,  # 6s @ 24fps
                start_frame=(i - 1) * 144,
                shot_id=f"shot-{i:02d}",
            )
        )

    vo_path = tmp_path / "voiceover.wav"
    vo_path.write_bytes(b"dummy_vo_bytes")

    bgm_path = tmp_path / "bgm.wav"
    bgm_path.write_bytes(b"dummy_bgm_bytes")

    project = TimelineProject(
        name="Test_Cinema_Commercial",
        fps=24.0,
        width=1920,
        height=1080,
        video_clips=clips,
        voiceover_path=vo_path,
        voiceover_duration_frames=432,
        bgm_path=bgm_path,
        bgm_duration_frames=432,
        markers=[
            TimelineMarker(frame=0, name="Color Pass Shot 1", color="cyan"),
            TimelineMarker(frame=144, name="Sound Design Shot 2", color="green"),
        ],
    )
    return project, tmp_path


def test_export_fcpxml_generates_valid_xml(sample_timeline_project):
    project, out_dir = sample_timeline_project
    fcpxml_file = out_dir / "timeline.fcpxml"

    result = export_fcpxml(project, fcpxml_file)
    assert result.is_file()

    # Parse XML and verify structure
    tree = ET.parse(result)
    root = tree.getroot()
    assert root.tag == "fcpxml"
    assert root.attrib["version"] == "1.9"

    # Check resources
    resources = root.find("resources")
    assert resources is not None
    assets = resources.findall("asset")
    assert len(assets) == 5  # 3 video clips + 1 VO + 1 BGM

    # Check sequence and spine
    spine = root.find(".//spine")
    assert spine is not None
    asset_clips = spine.findall("asset-clip")
    assert len(asset_clips) == 3

    # Check marker exists on first clip
    marker = asset_clips[0].find("marker")
    assert marker is not None
    assert marker.attrib["value"] == "Color Pass Shot 1"


def test_export_otio_generates_valid_timeline(sample_timeline_project):
    project, out_dir = sample_timeline_project
    otio_file = out_dir / "timeline.otio"

    result = export_otio(project, otio_file)
    assert result.is_file()

    import opentimelineio as otio

    timeline = otio.adapters.read_from_file(str(result))
    assert timeline.name == "Test_Cinema_Commercial"
    # Video track + Audio track
    assert len(timeline.tracks) >= 2
    video_track = timeline.tracks[0]
    assert len(video_track) == 3


def test_build_timeline_from_manifest(tmp_path: Path):
    manifest_file = tmp_path / "project_manifest.json"
    clip_file = tmp_path / "shot_01.mp4"
    clip_file.write_bytes(b"dummy")

    data = {
        "project_id": "manifest_test",
        "technical_specs": {"fps": 25.0, "resolution": "1080x1920"},
        "shots": [
            {
                "id": "shot-01",
                "source": "shot_01.mp4",
                "duration_frames": 150,
            }
        ],
    }
    manifest_file.write_text(json.dumps(data), encoding="utf-8")

    tp = build_timeline_project_from_manifest(manifest_file)
    assert tp.name == "manifest_test"
    assert tp.fps == 25.0
    assert tp.width == 1080
    assert tp.height == 1920
    assert len(tp.video_clips) == 1
    assert tp.video_clips[0].duration_frames == 150
