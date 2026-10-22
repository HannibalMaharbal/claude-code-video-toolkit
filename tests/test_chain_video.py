import importlib.util
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).parents[1] / "tools" / "chain_video.py"
SPEC = importlib.util.spec_from_file_location("chain_video", MODULE_PATH)
chain = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(chain)


def _completed():
    return type("Result", (), {"returncode": 0, "stdout": b"", "stderr": b""})()


def test_first_scene_uses_reference_image(tmp_path):
    output = tmp_path / "clip.mp4"

    def run(cmd, **kwargs):
        output.write_bytes(b"video")
        return _completed()

    with patch.object(chain.subprocess, "run", side_effect=run) as mocked:
        chain.generate_scene("start.png", None, "Begin.", str(output), ["--seed", "4"])

    cmd = mocked.call_args.args[0]
    assert cmd[1].endswith("tools/ltx25_mlx_adapter.py")
    assert cmd[cmd.index("--image") + 1] == "start.png"
    assert "--continue-from" not in cmd


def test_followup_scene_delegates_continuation_to_local_adapter(tmp_path):
    output = tmp_path / "clip-02.mp4"

    def run(cmd, **kwargs):
        output.write_bytes(b"video")
        return _completed()

    with patch.object(chain.subprocess, "run", side_effect=run) as mocked:
        chain.generate_scene(None, "clip-01.mp4", "Continue.", str(output), [])

    cmd = mocked.call_args.args[0]
    assert cmd[cmd.index("--continue-from") + 1] == "clip-01.mp4"
    assert "--image" not in cmd
    assert "--cloud" not in cmd
