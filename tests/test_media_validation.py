import json
import subprocess
from pathlib import Path

import pytest

from tools.media_validation import MediaValidationError, validate_audio, validate_video


def completed(stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], 0, stdout=stdout, stderr=stderr)


def test_audio_metadata_loudness_and_silence(monkeypatch: pytest.MonkeyPatch) -> None:
    probe = {
        "format": {"duration": "2.5"},
        "streams": [
            {"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000", "channels": 2}
        ],
    }
    results = iter(
        [completed(json.dumps(probe)), completed(stderr="I: -16.0 LUFS\nsilence_duration: 0.7")]
    )
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: next(results))
    report = validate_audio(Path("sample.m4a"))
    assert report.duration == 2.5
    assert report.details["loudnessLufs"] == -16.0


def test_audio_rejects_excessive_silence(monkeypatch: pytest.MonkeyPatch) -> None:
    probe = {
        "format": {"duration": "10"},
        "streams": [
            {
                "codec_type": "audio",
                "codec_name": "pcm_s16le",
                "sample_rate": "24000",
                "channels": 1,
            }
        ],
    }
    results = iter(
        [completed(json.dumps(probe)), completed(stderr="I: -18.0 LUFS\nsilence_duration: 7.0")]
    )
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: next(results))
    with pytest.raises(MediaValidationError, match="Stille"):
        validate_audio(Path("sample.wav"))


def test_video_metadata_and_decode(monkeypatch: pytest.MonkeyPatch) -> None:
    probe = {
        "format": {"duration": "1.0", "format_name": "mov,mp4"},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "avg_frame_rate": "30/1",
            }
        ],
    }
    results = iter([completed(json.dumps(probe)), completed(), completed(), completed()])
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: next(results))
    report = validate_video(Path("sample.mp4"))
    assert report.details == {
        "container": "mov,mp4",
        "width": 1920,
        "height": 1080,
        "frameRate": 30.0,
    }
