import subprocess
from pathlib import Path

from tools.audio_mix import mix


def _run_ffmpeg(*args: str) -> None:
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args],
        check=True,
        capture_output=True,
        text=True,
    )


def test_voiceover_only_mix_hits_release_loudness(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    voiceover = tmp_path / "voice.wav"
    output = tmp_path / "master.mp4"
    _run_ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=320x180:r=24:d=2",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(video),
    )
    _run_ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=48000:duration=2",
        "-filter:a",
        "volume=0.08",
        "-c:a",
        "pcm_s16le",
        str(voiceover),
    )

    result = mix(video, voiceover, output, target_lufs=-14.0)

    assert output.is_file()
    assert abs(float(result["audio_qc"]["loudnessLufs"]) - (-14.0)) <= 0.5
    assert float(result["audio_qc"]["truePeakDbfs"]) <= -1.5


def test_music_mix_keeps_voice_sidechain_connected(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    voiceover = tmp_path / "voice.wav"
    music = tmp_path / "music.wav"
    output = tmp_path / "master.mp4"
    _run_ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=320x180:r=24:d=2",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(video),
    )
    _run_ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=48000:duration=2",
        "-filter:a",
        "volume=0.08",
        str(voiceover),
    )
    _run_ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=220:sample_rate=48000:duration=2",
        "-filter:a",
        "volume=0.02",
        str(music),
    )

    result = mix(video, voiceover, output, music=music, target_lufs=-14.0)

    assert output.is_file()
    assert result["music_ducked"] is True
    assert abs(float(result["audio_qc"]["loudnessLufs"]) - (-14.0)) <= 0.5
    assert float(result["audio_qc"]["truePeakDbfs"]) <= -1.5
