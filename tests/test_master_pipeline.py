from pathlib import Path
from unittest.mock import patch

from tools.master_pipeline import run_pipeline, run_voiceover


def test_run_voiceover_invokes_script(tmp_path: Path):
    out = tmp_path / "voice.wav"
    out.write_bytes(b"audio-data")

    def mock_run(cmd, **kwargs):
        return type("Result", (), {"returncode": 0})()

    with patch("tools.master_pipeline.subprocess.run", side_effect=mock_run):
        ok = run_voiceover("Test speech", out, mode="promote")

    assert ok is True


def test_run_pipeline_local_execution(tmp_path: Path):
    output = tmp_path / "master.mp4"

    def mock_generate(*args, **kwargs):
        Path(kwargs.get("output_path") or args[1]).write_bytes(b"video-data")
        return {"success": True, "output": kwargs.get("output_path") or args[1]}

    with patch("tools.master_pipeline.generate_video", side_effect=mock_generate):
        res = run_pipeline(
            prompt="A majestic sunrise over the mountains.",
            output_path=str(output),
            provider="local",
            duration=4,
            verbose=False,
        )

    assert res["success"] is True
    assert res["resolution"] == "1920x1080"
    assert res["provider"] == "local"
    assert res["cost_eur"] == 0.0
    assert output.exists()


def test_run_pipeline_with_audio_mix(tmp_path: Path):
    output = tmp_path / "master_with_audio.mp4"
    music = tmp_path / "beat.mp3"
    music.write_bytes(b"music-data")

    def mock_generate(*args, **kwargs):
        Path(kwargs.get("output_path") or args[1]).write_bytes(b"video-data")
        return {"success": True}

    def mock_mix(*args, **kwargs):
        Path(kwargs.get("output") or args[2]).write_bytes(b"mixed-video-audio")
        return {"success": True, "target_lufs": -14.0}

    with (
        patch("tools.master_pipeline.generate_video", side_effect=mock_generate),
        patch("tools.master_pipeline.run_voiceover", return_value=True),
        patch("tools.master_pipeline.mix", side_effect=mock_mix),
    ):
        res = run_pipeline(
            prompt="Luxury watch spinning in studio",
            output_path=str(output),
            voice_text="Exklusiv bei uns.",
            music=str(music),
            target_lufs=-14.0,
            verbose=False,
        )

    assert res["success"] is True
    assert res["audio_status"] == "mastered"
    assert res["target_lufs"] == -14.0
    assert output.exists()
