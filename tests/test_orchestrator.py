import asyncio
from pathlib import Path

import pytest

from tools import orchestrator
from tools.input_parser import InputType, ParsedInput
from tools.orchestrator import JobState, stable_job_id
from tools.scene_splitter import Scene, SceneType


def test_job_id_is_stable_and_sensitive_to_material_options() -> None:
    first = stable_job_id("Thema", None, "default", 60, "de")
    second = stable_job_id("Thema", None, "default", 60, "de")
    changed = stable_job_id("Thema", None, "licbarska", 60, "de")

    assert first == second
    assert first != changed
    assert len(first) == 16


def test_job_state_is_written_atomically(tmp_path: Path) -> None:
    state = JobState(tmp_path / "job.json", "abc123")

    state.write("running", step="assets")

    assert state.read() == {
        "job_id": "abc123",
        "status": "running",
        "step": "assets",
    }
    assert not (tmp_path / "job.json.tmp").exists()


def test_completed_job_is_reused_without_second_compose(tmp_path: Path, monkeypatch) -> None:
    parsed = ParsedInput(InputType.SCRIPT, "script.md", "demo", "Text")
    scenes = [Scene(0, SceneType.VOICEOVER, "Demo", "Text", 4.0)]
    compose_calls = 0

    monkeypatch.setattr(orchestrator, "parse_input", lambda **_kwargs: parsed)
    monkeypatch.setattr(orchestrator, "split_scenes", lambda *_args, **_kwargs: scenes)
    monkeypatch.setattr(orchestrator, "load_brand", lambda _brand: ({}, {}))

    def fake_compose(*_args) -> None:
        nonlocal compose_calls
        compose_calls += 1
        output = _args[4]
        output.write_bytes(b"video")

    monkeypatch.setattr(orchestrator, "compose_video", fake_compose)

    first = orchestrator.orchestrate(
        "",
        script_file="script.md",
        no_music=True,
        no_voiceover=True,
        output_dir=str(tmp_path),
    )
    second = orchestrator.orchestrate(
        "",
        script_file="script.md",
        no_music=True,
        no_voiceover=True,
        output_dir=str(tmp_path),
    )

    assert first == second
    assert compose_calls == 1


@pytest.mark.asyncio
async def test_asset_generation_keeps_success_when_one_scene_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenes = [
        Scene(0, SceneType.VOICEOVER, "One", "Text", 4.0),
        Scene(1, SceneType.VOICEOVER, "Two", "Text", 4.0),
    ]

    async def fake_voiceover(scene, _voice, _premium, out_dir):
        if scene.index == 1:
            raise RuntimeError("provider unavailable")
        output = out_dir / "vo_00.mp3"
        output.write_bytes(b"audio")
        return output

    monkeypatch.setattr(orchestrator, "generate_voiceover", fake_voiceover)

    assets = await orchestrator.generate_assets(scenes, {}, 8.0, False, True, tmp_path)

    assert set(assets["voiceovers"]) == {0}


@pytest.mark.asyncio
async def test_voiceover_timeout_kills_child_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class SlowProcess:
        returncode = None
        killed = False

        async def communicate(self):
            await asyncio.sleep(1)
            return b"", b""

        def kill(self) -> None:
            self.killed = True

        async def wait(self) -> int:
            self.returncode = -9
            return -9

    process = SlowProcess()

    async def fake_subprocess(*_args, **_kwargs):
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_subprocess)
    scene = Scene(0, SceneType.VOICEOVER, "Demo", "Text", 4.0)

    result = await orchestrator.generate_voiceover(scene, {}, False, tmp_path, timeout_s=0.01)

    assert result is None
    assert process.killed is True
