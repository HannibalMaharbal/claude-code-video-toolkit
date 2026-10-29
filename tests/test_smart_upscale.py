"""Tests for Smart Upscale (Calvin Hollywood Trick) & ByteDance Video Upscaler."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools import video_generate, higgsfield_video


def test_bytedance_upscale_tier_mapping() -> None:
    assert "bytedance_video_upscale" in video_generate.MODEL_TO_TIER
    assert video_generate.MODEL_TO_TIER["bytedance_video_upscale"] == "upscale"
    assert "bytedance_video_upscale" not in video_generate.MODEL_RATES


def test_run_bytedance_upscale_command(tmp_path: Path) -> None:
    input_file = tmp_path / "draft.mp4"
    output_file = tmp_path / "crisp.mp4"
    input_file.write_bytes(b"data")

    with patch.object(video_generate.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run_mock:
        rc = video_generate._run_bytedance_upscale(
            str(input_file),
            str(output_file),
            resolution="1080p",
            preset="aigc",
            confirm=True,
        )

    assert rc == 0
    cmd = run_mock.call_args.args[0]
    assert "--model" in cmd
    assert cmd[cmd.index("--model") + 1] == "bytedance_video_upscale"
    assert "--video" in cmd
    assert cmd[cmd.index("--video") + 1] == str(input_file)
    assert "--resolution" in cmd
    assert cmd[cmd.index("--resolution") + 1] == "1080p"
    assert "--preset" in cmd
    assert cmd[cmd.index("--preset") + 1] == "aigc"
    assert "--confirm" in cmd


def test_run_cloud_generation_passes_smart_upscale_flag(tmp_path: Path) -> None:
    output_file = tmp_path / "output.mp4"

    with patch.object(video_generate.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run_mock:
        rc = video_generate._run_cloud_generation(
            model="seedance_2_5",
            prompt="cinematic test",
            output_path=str(output_file),
            provider="higgsfield",
            duration=10,
            smart_upscale=True,
            confirm=True,
        )

    assert rc == 0
    cmd = run_mock.call_args.args[0]
    assert "--smart-upscale" in cmd
    assert "--confirm" in cmd


def test_upscale_cost_failure_is_not_invented() -> None:
    with patch.object(higgsfield_video, '_get_higgsfield_bin', return_value='higgsfield'), patch.object(higgsfield_video, '_run_json', side_effect=RuntimeError('quote unavailable')):
        import pytest
        with pytest.raises(RuntimeError, match='quote unavailable'):
            higgsfield_video.estimate_cost('bytedance_video_upscale', video='clip.mp4')


def test_smart_upscale_does_not_spend_without_full_quote(monkeypatch, tmp_path, capsys) -> None:
    import sys
    import pytest
    monkeypatch.setattr(sys, 'argv', ['higgsfield_video.py', '--model', 'seedance_2_5', '--prompt', 'test', '--output', str(tmp_path / 'out.mp4'), '--smart-upscale', '--confirm'])
    monkeypatch.setattr(higgsfield_video, 'get_balance', lambda: {'credits': 100, 'raw': '100 credits'})
    monkeypatch.setattr(higgsfield_video, 'estimate_cost', lambda *a, **kw: {'credits': 30})
    with patch.object(higgsfield_video, 'create_video') as create:
        with pytest.raises(SystemExit):
            higgsfield_video.main()
        create.assert_not_called()
    assert 'unbekannt' in capsys.readouterr().err.lower()


def test_media_quote_requires_upload_permission(monkeypatch, tmp_path):
    import sys
    import pytest
    monkeypatch.setattr(sys, 'argv', ['higgsfield_video.py', '--model', 'bytedance_video_upscale', '--video', str(tmp_path / 'input.mp4'), '--output', str(tmp_path / 'out.mp4')])
    with patch.object(higgsfield_video, 'estimate_cost') as quote:
        with pytest.raises(SystemExit):
            higgsfield_video.main()
        quote.assert_not_called()


def test_confirm_requires_price_ceiling(monkeypatch, tmp_path):
    import sys
    import pytest
    monkeypatch.setattr(sys, 'argv', ['higgsfield_video.py', '--prompt', 'test', '--output', str(tmp_path / 'out.mp4'), '--confirm'])
    monkeypatch.setattr(higgsfield_video, 'get_balance', lambda: {'credits': 100, 'raw': '100 credits'})
    monkeypatch.setattr(higgsfield_video, 'estimate_cost', lambda *a, **kw: {'credits': 30})
    with patch.object(higgsfield_video, 'create_video') as create:
        with pytest.raises(SystemExit):
            higgsfield_video.main()
        create.assert_not_called()


def test_changed_or_invalid_quote_never_creates_job(monkeypatch, tmp_path):
    import sys
    import pytest
    for quote in (31, float('nan'), float('inf')):
        monkeypatch.setattr(sys, 'argv', ['higgsfield_video.py', '--prompt', 'test', '--output', str(tmp_path / 'out.mp4'), '--confirm', '--max-credits', '30'])
        monkeypatch.setattr(higgsfield_video, 'get_balance', lambda: {'credits': 100, 'raw': '100 credits'})
        monkeypatch.setattr(higgsfield_video, 'estimate_cost', lambda *a, **kw: {'credits': quote})
        with patch.object(higgsfield_video, 'create_video') as create:
            with pytest.raises(SystemExit):
                higgsfield_video.main()
            create.assert_not_called()


def test_same_input_and_output_is_rejected(monkeypatch, tmp_path):
    import sys
    import pytest
    video = str(tmp_path / 'clip.mp4')
    monkeypatch.setattr(sys, 'argv', ['higgsfield_video.py', '--model', 'bytedance_video_upscale', '--video', video, '--output', video, '--allow-upload'])
    with patch.object(higgsfield_video, 'estimate_cost') as quote:
        with pytest.raises(SystemExit):
            higgsfield_video.main()
        quote.assert_not_called()


def test_topaz_forwards_price_and_upload_approval(tmp_path):
    with patch.object(video_generate.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as run:
        assert video_generate._run_topaz_upscale(str(tmp_path / 'in.mp4'), str(tmp_path / 'out.mp4'), confirm=True, max_credits=12, allow_upload=True) == 0
    cmd = run.call_args.args[0]
    assert '--allow-upload' in cmd
    assert cmd[cmd.index('--max-credits') + 1] == '12'
    assert '--confirm' in cmd
