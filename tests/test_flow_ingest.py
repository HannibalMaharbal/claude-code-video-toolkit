"""Unit tests for tools/flow_ingest.py."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from tools.flow_ingest import get_video_metadata, extract_end_frame, ingest_flow_clip


def test_get_video_metadata_mocked():
    sample_probe_output = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "r_frame_rate": "24/1",
            },
            {
                "codec_type": "audio",
                "codec_name": "aac",
                "sample_rate": 48000,
            }
        ],
        "format": {
            "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
            "duration": "7.5",
            "size": "10485760",
        }
    }

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=json.dumps(sample_probe_output), returncode=0)
        meta = get_video_metadata(Path("/dummy/clip.mp4"))

        assert meta["duration_sec"] == 7.5
        assert meta["resolution"] == "1920x1080"
        assert meta["aspect_ratio"] == "16:9"
        assert meta["fps"] == 24.0
        assert meta["video_codec"] == "h264"
        assert meta["audio_codec"] == "aac"
        assert meta["has_video"] is True
        assert meta["has_audio"] is True


def test_ingest_flow_clip(tmp_path: Path):
    project_dir = tmp_path / "test_project"
    dummy_input = tmp_path / "flow_generation_test.mp4"
    dummy_input.write_bytes(b"dummy_video_bytes")

    fake_meta = {
        "duration_sec": 6.0,
        "resolution": "1920x1080",
        "aspect_ratio": "16:9",
        "fps": 24.0,
        "has_video": True,
    }

    with patch("tools.flow_ingest.get_video_metadata", return_value=fake_meta), \
         patch("tools.flow_ingest.extract_end_frame") as mock_extract:
        
        mock_extract.side_effect = lambda vid, out: out.write_bytes(b"png_frame") or out

        result = ingest_flow_clip(
            input_file=dummy_input,
            project_dir=project_dir,
            scene_number=1,
            extract_lock_frame=True,
        )

        assert result["status"] == "INGESTED"
        assert result["scene_index"] == 1
        assert Path(result["clip_path"]).exists()
        assert result["end_frame"] is not None
        assert result["next_scene_spec"]["next_scene_index"] == 2
        assert "input_start_frame" in result["next_scene_spec"]

        # Check manifest
        manifest_path = project_dir / "flow_manifest.json"
        assert manifest_path.exists()
        data = json.loads(manifest_path.read_text())
        assert data["total_scenes"] == 1
        assert data["scenes"][0]["scene_index"] == 1


def test_ingest_flow_clip_with_character_ref(tmp_path: Path):
    project_dir = tmp_path / "test_char_project"
    dummy_input = tmp_path / "scene1.mp4"
    dummy_input.write_bytes(b"dummy_video_bytes")
    char_ref = tmp_path / "hero_portrait.png"
    char_ref.write_bytes(b"char_bytes")

    fake_meta = {
        "duration_sec": 5.0,
        "resolution": "1920x1080",
        "aspect_ratio": "16:9",
        "fps": 24.0,
        "has_video": True,
    }

    with patch("tools.flow_ingest.get_video_metadata", return_value=fake_meta), \
         patch("tools.flow_ingest.extract_end_frame") as mock_extract:
        
        mock_extract.side_effect = lambda vid, out: out.write_bytes(b"png_frame") or out

        result = ingest_flow_clip(
            input_file=dummy_input,
            project_dir=project_dir,
            scene_number=1,
            extract_lock_frame=True,
            character_ref=char_ref,
            model_tier="veo_3_1_fast",
            prompt="Cinematic dolly shot of the hero",
        )

        assert result["status"] == "INGESTED"
        assert result["character_ref"] is not None
        assert Path(result["character_ref"]).exists()
        assert result["model_tier"] == "veo_3_1_fast"
        assert result["prompt"] == "Cinematic dolly shot of the hero"
