from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import resolve_adapter


class FakeFolder:
    def __init__(self, name: str) -> None:
        self.name = name
        self.subfolders: list[FakeFolder] = []

    def GetName(self) -> str:  # noqa: N802
        return self.name

    def GetSubFolderList(self) -> list[FakeFolder]:  # noqa: N802
        return self.subfolders


class FakeMediaPool:
    def __init__(self) -> None:
        self.imported: list[str] = []
        self.created: tuple[str, list[object]] | None = None
        self.appended: list[object] | None = None
        self.root_folder = FakeFolder("Master")
        self.current_folder = self.root_folder

    def GetRootFolder(self) -> FakeFolder:  # noqa: N802
        return self.root_folder

    def AddSubFolder(self, parent: FakeFolder, name: str) -> FakeFolder:  # noqa: N802
        new_folder = FakeFolder(name)
        parent.subfolders.append(new_folder)
        return new_folder

    def SetCurrentFolder(self, folder: FakeFolder) -> bool:  # noqa: N802
        self.current_folder = folder
        return True

    def ImportMedia(self, paths: list[str]) -> list[object]:  # noqa: N802 - Resolve API spelling
        self.imported = paths
        return ["clip"]

    def CreateTimelineFromClips(self, name: str, clips: list[object]) -> str:  # noqa: N802
        self.created = (name, clips)
        return name

    def AppendToTimeline(self, clips: list[object]) -> bool:  # noqa: N802
        self.appended = clips
        return True


class FakeProject:
    def __init__(self, media_pool: FakeMediaPool, timeline: object | None = None) -> None:
        self.media_pool = media_pool
        self.timeline = timeline
        self.settings: dict[str, object] | None = None
        self.project_settings: dict[str, str] = {}
        self.loaded_preset: str | None = None

    def GetMediaPool(self) -> FakeMediaPool:  # noqa: N802
        return self.media_pool

    def GetCurrentTimeline(self) -> object | None:  # noqa: N802
        return self.timeline

    def SetSetting(self, key: str, value: str) -> bool:  # noqa: N802
        self.project_settings[key] = value
        return True

    def LoadRenderPreset(self, preset: str) -> bool:  # noqa: N802
        self.loaded_preset = preset
        return True

    def SetRenderSettings(self, settings: dict[str, object]) -> bool:  # noqa: N802
        self.settings = settings
        return True

    def AddRenderJob(self) -> str:  # noqa: N802
        return "render-job-1"


def _session(project: FakeProject) -> resolve_adapter.ResolveSession:
    return resolve_adapter.ResolveSession(resolve=SimpleNamespace(), project=project)


def test_discover_reports_locally_present_script_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = tmp_path / "DaVinciResolveScript.py"
    script.write_text("# fake", encoding="utf-8")
    monkeypatch.setattr(resolve_adapter, "SCRIPT_MODULE_PATHS", (script,))
    monkeypatch.setattr(resolve_adapter, "RESOLVE_APP_PATH", tmp_path / "DaVinci Resolve.app")

    status = resolve_adapter.discover()

    assert status["script_api_available"] is True
    assert status["script_module"] == str(script)
    assert status["resolve_app_installed"] is False


def test_fusion_library_path_matches_the_local_resolve_bundle() -> None:
    assert resolve_adapter.FUSIONSCRIPT_PATH == (
        resolve_adapter.RESOLVE_APP_PATH / "Contents/Libraries/Fusion/fusionscript.so"
    )


def test_connect_reports_missing_scriptapp_as_an_adapter_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(resolve_adapter, "_load_script_module", lambda: SimpleNamespace())

    with pytest.raises(resolve_adapter.ResolveAdapterError, match="scriptapp"):
        resolve_adapter.connect()


def test_import_creates_a_named_timeline_when_none_is_active(tmp_path: Path) -> None:
    media = tmp_path / "master.mp4"
    media.write_bytes(b"video")
    media_pool = FakeMediaPool()

    result = resolve_adapter.import_media(
        [media], timeline_name="AI future", session=_session(FakeProject(media_pool))
    )

    assert result == {
        "imported_clips": 1,
        "timeline_action": "created",
        "timeline_name": "AI future",
    }
    assert media_pool.imported == [str(media.resolve())]
    assert media_pool.created == ("AI future", ["clip"])


def test_import_appends_to_the_active_timeline(tmp_path: Path) -> None:
    media = tmp_path / "master.mp4"
    media.write_bytes(b"video")
    media_pool = FakeMediaPool()

    result = resolve_adapter.import_media(
        [media], session=_session(FakeProject(media_pool, timeline=object()))
    )

    assert result["timeline_action"] == "appended"
    assert media_pool.appended == ["clip"]


def test_import_rejects_missing_media_before_connecting(tmp_path: Path) -> None:
    with pytest.raises(resolve_adapter.ResolveAdapterError, match="existiert nicht"):
        resolve_adapter.import_media([tmp_path / "missing.mp4"], session=SimpleNamespace())


def test_queue_render_adds_job_but_never_starts_rendering(tmp_path: Path) -> None:
    media_pool = FakeMediaPool()
    project = FakeProject(media_pool, timeline=object())

    result = resolve_adapter.queue_render(
        tmp_path,
        preset="H.264 Master",
        custom_name="ai-future",
        session=_session(project),
    )

    assert result == {"render_job_id": "render-job-1", "target_dir": str(tmp_path.resolve())}
    assert project.loaded_preset == "H.264 Master"
    assert project.settings == {
        "TargetDir": str(tmp_path.resolve()),
        "CustomName": "ai-future",
        "SelectAllFrames": True,
        "ExportVideo": True,
        "ExportAudio": True,
    }


def test_queue_render_requires_existing_directory(tmp_path: Path) -> None:
    with pytest.raises(resolve_adapter.ResolveAdapterError, match="existiert nicht"):
        resolve_adapter.queue_render(tmp_path / "missing", session=SimpleNamespace())


def test_setup_bins_creates_default_bins() -> None:
    media_pool = FakeMediaPool()
    project = FakeProject(media_pool)

    res = resolve_adapter.setup_bins(session=_session(project))

    assert res["status"] == "ok"
    assert res["created_count"] == len(resolve_adapter.DEFAULT_BINS)
    subfolder_names = [f.GetName() for f in media_pool.root_folder.GetSubFolderList()]
    assert "01_A-Roll_Voice" in subfolder_names
    assert "05_Renders" in subfolder_names


def test_import_to_bin_switches_folder_and_imports(tmp_path: Path) -> None:
    media = tmp_path / "b_roll.mp4"
    media.write_bytes(b"sample")
    media_pool = FakeMediaPool()
    project = FakeProject(media_pool)

    res = resolve_adapter.import_to_bin("02_B-Roll_Visuals", [media], session=_session(project))

    assert res["bin"] == "02_B-Roll_Visuals"
    assert res["imported_clips"] == 1
    assert media_pool.imported == [str(media.resolve())]
    assert media_pool.current_folder == media_pool.root_folder


def test_setup_project_configures_vertical_resolution() -> None:
    media_pool = FakeMediaPool()
    project = FakeProject(media_pool)

    res = resolve_adapter.setup_project("Licbarska_Reel", vertical=True, fps=30.0, session=_session(project))

    assert res["project_name"] == "Licbarska_Reel"
    assert res["vertical"] is True
    assert project.project_settings["timelineResolutionWidth"] == "1080"
    assert project.project_settings["timelineResolutionHeight"] == "1920"
    assert project.project_settings["timelineFrameRate"] == "30.0"


def test_fairlight_gate_requires_active_timeline() -> None:
    media_pool = FakeMediaPool()
    project = FakeProject(media_pool, timeline=None)

    with pytest.raises(resolve_adapter.ResolveAdapterError, match="Keine aktive Timeline"):
        resolve_adapter.apply_fairlight_gate(session=_session(project))


def test_fairlight_gate_succeeds_with_timeline() -> None:
    media_pool = FakeMediaPool()
    project = FakeProject(media_pool, timeline=object())

    res = resolve_adapter.apply_fairlight_gate(target_lufs=-14.0, session=_session(project))

    assert res["status"] == "gate_ready"
    assert res["target_lufs"] == -14.0

