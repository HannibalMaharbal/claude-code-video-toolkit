import json

import pytest

from tools.capcut_editor import CapCutDraft


def _draft(tmp_path):
    data = {
        "duration": 6_000_000,
        "tracks": [{
            "type": "video",
            "flag": 0,
            "segments": [
                {
                    "id": str(index),
                    "target_timerange": {"start": index * 2_000_000, "duration": 2_000_000},
                    "source_timerange": {"start": index * 2_000_000, "duration": 2_000_000},
                    "clip": {"scale": {"x": 1.0, "y": 1.0}},
                }
                for index in range(3)
            ],
        }],
    }
    (tmp_path / "draft_content.json").write_text(json.dumps(data), encoding="utf-8")
    return CapCutDraft(str(tmp_path))


def test_punch_in_updates_alternating_segments_and_creates_backup(tmp_path):
    draft = _draft(tmp_path)
    assert draft.apply_punch_in_zooms(1.15, 2) == 1
    assert (tmp_path / "draft_content.json.bak").exists()
    reloaded = CapCutDraft(str(tmp_path))
    scales = [segment["clip"]["scale"]["x"] for segment in reloaded.get_main_video_track()["segments"]]
    assert scales == [1.0, 1.15, 1.0]


def test_remove_silence_compacts_timeline(tmp_path):
    draft = _draft(tmp_path)
    assert draft.remove_silence_ranges([(2.0, 4.0)]) == 1
    reloaded = CapCutDraft(str(tmp_path))
    assert reloaded.data["duration"] == 4_000_000
    assert len(reloaded.get_main_video_track()["segments"]) == 2


def test_punch_in_rejects_invalid_step(tmp_path):
    with pytest.raises(ValueError, match="step"):
        _draft(tmp_path).apply_punch_in_zooms(step=0)
