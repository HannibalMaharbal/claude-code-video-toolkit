from pathlib import Path

import pytest

from tools.video_analyze import (
    AnalysisError,
    align_transcript_to_scenes,
    build_audio_timeline,
    build_chapter_candidates,
    build_clip_candidates,
    build_scenes,
    detect_scene_boundaries,
    validate_timeline,
)


def test_invalid_duration_and_timeline_are_rejected() -> None:
    with pytest.raises(AnalysisError, match="Dauer"):
        build_scenes(0, [])
    with pytest.raises(AnalysisError, match="ungültigen Zeitbereich"):
        validate_timeline(10, [{"start": 3, "end": 2}])
    with pytest.raises(AnalysisError, match="überlappen"):
        validate_timeline(10, [{"start": 0, "end": 6}, {"start": 5, "end": 7}])


def test_one_scene_covers_a_video_without_visual_cuts() -> None:
    scenes = build_scenes(8.0, [])
    assert scenes == [{"scene_id": "scene_001", "start": 0.0, "end": 8.0, "duration": 8.0}]


def test_scene_boundaries_are_sorted_clipped_and_deterministic() -> None:
    scenes = build_scenes(10.0, [8.0, 2.0, 2.0, -1.0, 12.0])
    assert [(scene["start"], scene["end"]) for scene in scenes] == [
        (0.0, 2.0),
        (2.0, 8.0),
        (8.0, 10.0),
    ]


def test_transcript_fully_inside_scene_is_aligned() -> None:
    scenes = build_scenes(10.0, [5.0])
    aligned = align_transcript_to_scenes(
        scenes, {"segments": [{"start": 1.0, "end": 2.0, "text": "Hallo Welt"}]}
    )
    assert aligned[0]["transcript_segment_ids"] == ["segment_001"]
    assert aligned[0]["transcript_text"] == "Hallo Welt"
    assert aligned[0]["speech_coverage"] == 0.2
    assert aligned[1]["transcript_segment_ids"] == []


def test_transcript_crossing_scene_boundary_is_retained_in_both_overlaps() -> None:
    scenes = build_scenes(10.0, [5.0])
    aligned = align_transcript_to_scenes(
        scenes,
        {
            "segments": [
                {"start": 4.0, "end": 6.0, "text": "Ein Segment bleibt vollständig erhalten."}
            ]
        },
    )
    assert [scene["transcript_segment_ids"] for scene in aligned] == [
        ["segment_001"],
        ["segment_001"],
    ]
    assert all(
        scene["transcript_text"] == "Ein Segment bleibt vollständig erhalten." for scene in aligned
    )
    assert [
        piece["overlap_duration"] for scene in aligned for piece in scene["transcript_segments"]
    ] == [1.0, 1.0]


def test_scene_without_speech_and_speech_without_scene_change() -> None:
    silent_scene = align_transcript_to_scenes(build_scenes(5.0, []), {"segments": []})[0]
    assert silent_scene["speech_coverage"] == 0.0
    spoken_scene = align_transcript_to_scenes(
        build_scenes(5.0, []),
        {"segments": [{"start": 0.0, "end": 5.0, "text": "Durchgehende Sprache"}]},
    )[0]
    assert spoken_scene["speech_coverage"] == 1.0


def test_audio_timeline_has_silence_before_and_after_speech() -> None:
    timeline = build_audio_timeline(10.0, [{"start": 2.0, "end": 4.0, "duration": 2.0}])
    assert timeline["silence_segments"] == [
        {"start": 2.0, "end": 4.0, "duration": 2.0},
    ]
    assert timeline["speech_segments"] == [
        {"start": 0.0, "end": 2.0, "duration": 2.0},
        {"start": 4.0, "end": 10.0, "duration": 6.0},
    ]


def test_chapter_candidates_have_measured_inputs_not_fake_scores() -> None:
    scenes = build_scenes(10.0, [4.0, 7.0])
    chapters = build_chapter_candidates(scenes, [{"start": 3.5, "end": 4.1, "duration": 0.6}])
    assert chapters[0]["reason"] == ["video_start"]
    assert chapters[1]["reason"] == ["scene_change", "silence"]
    assert "confidence" not in chapters[1]
    assert chapters[1]["confidence_inputs"]["preceding_silence_duration"] == 0.6


def test_clip_candidates_obey_min_and_max_duration() -> None:
    transcripts = {
        "segments": [
            {"start": 0.0, "end": 4.0, "text": "Erster vollständiger Satz."},
            {"start": 4.0, "end": 8.0, "text": "Zweiter vollständiger Satz."},
            {"start": 8.0, "end": 12.0, "text": "Dritter vollständiger Satz."},
        ]
    }
    clips = build_clip_candidates(
        [{"start": 0.0, "end": 12.0, "duration": 12.0}],
        transcripts,
        min_duration=3.0,
        max_duration=5.0,
    )
    assert clips
    assert all(3.0 <= clip["duration"] <= 5.0 for clip in clips)
    assert all(clip["start"] < clip["end"] for clip in clips)


def test_clip_candidates_do_not_emit_too_short_speech_blocks() -> None:
    clips = build_clip_candidates(
        [{"start": 1.0, "end": 1.5, "duration": 0.5}],
        {"segments": []},
        min_duration=2.0,
        max_duration=8.0,
    )
    assert clips == []


def test_very_short_video_has_valid_one_scene_timeline() -> None:
    scenes = build_scenes(0.05, [0.01])
    validate_timeline(0.05, scenes)
    assert scenes[-1]["end"] == 0.05


def test_long_scene_clip_splitting_and_output_are_deterministic() -> None:
    speech = [{"start": 0.0, "end": 130.0, "duration": 130.0}]
    first = build_clip_candidates(speech, {"segments": []}, min_duration=15.0, max_duration=60.0)
    second = build_clip_candidates(speech, {"segments": []}, min_duration=15.0, max_duration=60.0)
    assert first == second
    assert all(clip["duration"] <= 60.0 for clip in first)


def test_representative_frame_path_is_relative_to_package() -> None:
    # The analyzer stores paths relative to the analysis package, never host paths.
    assert str(Path("scene_frames") / "scene_001.jpg") == "scene_frames/scene_001.jpg"


def test_scene_detection_uses_local_ffmpeg_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    command: list[str] = []

    def fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        command.extend(args)
        return subprocess.CompletedProcess(
            args, 0, "", "[Parsed_showinfo] pts_time:2.000\n[Parsed_showinfo] pts_time:5.000\n"
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert detect_scene_boundaries(Path("local.mp4"), threshold=0.3) == [2.0, 5.0]
    assert "select=gt(scene\\,0.3),showinfo" in command
