import subprocess

from tools.video_qa_audit import audit_video


def _make_clip(path, audio_source, video_source="testsrc2=size=320x180:rate=24:duration=4"):
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", video_source,
            "-f", "lavfi", "-i", audio_source,
            "-t", "4", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", str(path),
        ],
        check=True,
    )


def test_clean_clip_passes(tmp_path):
    clip = tmp_path / "clean.mp4"
    _make_clip(clip, "sine=frequency=1000:sample_rate=48000:duration=4")
    report = audit_video(str(clip))
    assert report["passed"] is True
    assert report["dead_air_count"] == 0
    assert report["black_frames"] == []
    assert report["freezes"] == []


def test_dead_air_fails(tmp_path):
    clip = tmp_path / "silent.mp4"
    _make_clip(clip, "anullsrc=r=48000:cl=stereo")
    report = audit_video(str(clip))
    assert report["passed"] is False
    assert report["dead_air_count"] >= 1


def test_black_frozen_video_fails(tmp_path):
    clip = tmp_path / "black.mp4"
    _make_clip(clip, "sine=frequency=1000:sample_rate=48000:duration=4", "color=black:size=320x180:rate=24:duration=4")
    report = audit_video(str(clip))
    assert report["passed"] is False
    assert report["black_frames"]
    assert report["freezes"]
