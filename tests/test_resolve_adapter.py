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
        self.import_returns: list[object] | None = ["clip"]
        self.import_raises: Exception | None = None

    def GetRootFolder(self) -> FakeFolder:  # noqa: N802
        return self.root_folder

    def GetCurrentFolder(self) -> FakeFolder:  # noqa: N802
        return self.current_folder

    def AddSubFolder(self, parent: FakeFolder, name: str) -> FakeFolder:  # noqa: N802
        new_folder = FakeFolder(name)
        parent.subfolders.append(new_folder)
        return new_folder

    def SetCurrentFolder(self, folder: FakeFolder) -> bool:  # noqa: N802
        self.current_folder = folder
        return True

    def ImportMedia(self, paths: list[str]) -> list[object] | None:  # noqa: N802 - Resolve API spelling
        if self.import_raises is not None:
            raise self.import_raises
        self.imported = paths
        return self.import_returns

    def CreateTimelineFromClips(self, name: str, clips: list[object]) -> str:  # noqa: N802
        self.created = (name, clips)
        return name

    def AppendToTimeline(self, clips: list[object]) -> bool:  # noqa: N802
        self.appended = clips
        return True


class FakeProject:
    def __init__(self, media_pool: FakeMediaPool, timeline: object | None = None, name: str = "Untitled Project") -> None:
        self.name = name
        self.media_pool = media_pool
        self.timeline = timeline
        self.settings: dict[str, object] | None = None
        self.project_settings: dict[str, str] = {}
        self.loaded_preset: str | None = None

    def GetName(self) -> str:  # noqa: N802
        return self.name

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


class FakeProjectManager:
    def __init__(self, current_project: FakeProject | None = None) -> None:
        self.current_project = current_project
        self.created_projects: list[str] = []
        self.loaded_projects: list[str] = []
        self.fail_create: bool = False
        self.fail_load: bool = False

    def GetCurrentProject(self) -> FakeProject | None:  # noqa: N802
        return self.current_project

    def CreateProject(self, name: str) -> FakeProject | None:  # noqa: N802
        self.created_projects.append(name)
        if self.fail_create:
            return None
        proj = self.current_project or FakeProject(FakeMediaPool(), name=name)
        proj.name = name
        self.current_project = proj
        return proj

    def LoadProject(self, name: str) -> FakeProject | None:  # noqa: N802
        self.loaded_projects.append(name)
        if self.fail_load:
            return None
        proj = self.current_project or FakeProject(FakeMediaPool(), name=name)
        proj.name = name
        self.current_project = proj
        return proj


class FakeResolve:
    def __init__(self, project_manager: FakeProjectManager | None = None) -> None:
        self.project_manager = project_manager or FakeProjectManager()

    def GetProjectManager(self) -> FakeProjectManager:  # noqa: N802
        return self.project_manager


def _session(
    project: FakeProject, project_manager: FakeProjectManager | None = None
) -> resolve_adapter.ResolveSession:
    pm = project_manager or FakeProjectManager(current_project=project)
    return resolve_adapter.ResolveSession(resolve=FakeResolve(project_manager=pm), project=project)


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


def test_import_to_bin_empty_response_raises_and_restores_folder(tmp_path: Path) -> None:
    media = tmp_path / "empty_import.mp4"
    media.write_bytes(b"video content")
    media_pool = FakeMediaPool()
    media_pool.import_returns = []
    project = FakeProject(media_pool)
    session = _session(project)

    with pytest.raises(resolve_adapter.ResolveAdapterError, match="keine Clips importiert"):
        resolve_adapter.import_to_bin("02_B-Roll_Visuals", [media], session=session)

    assert media_pool.current_folder == media_pool.root_folder


def test_import_to_bin_exception_restores_folder(tmp_path: Path) -> None:
    media = tmp_path / "crash_import.mp4"
    media.write_bytes(b"video content")
    media_pool = FakeMediaPool()
    media_pool.import_raises = RuntimeError("Import crashed abruptly")
    project = FakeProject(media_pool)
    session = _session(project)

    with pytest.raises(RuntimeError, match="Import crashed abruptly"):
        resolve_adapter.import_to_bin("02_B-Roll_Visuals", [media], session=session)

    assert media_pool.current_folder == media_pool.root_folder


def test_import_to_bin_set_current_folder_failure_raises_and_restores_folder(tmp_path: Path) -> None:
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"video content")
    media_pool = FakeMediaPool()

    calls: list[FakeFolder] = []

    def fake_set_current_folder(folder: FakeFolder) -> bool:
        calls.append(folder)
        if folder.GetName() == "02_B-Roll_Visuals":
            return False
        media_pool.current_folder = folder
        return True

    media_pool.SetCurrentFolder = fake_set_current_folder  # type: ignore[assignment]
    project = FakeProject(media_pool)
    session = _session(project)

    with pytest.raises(
        resolve_adapter.ResolveAdapterError,
        match="nicht in Bin '02_B-Roll_Visuals' wechseln",
    ):
        resolve_adapter.import_to_bin("02_B-Roll_Visuals", [media], session=session)

    assert len(calls) == 2
    assert calls[0].GetName() == "02_B-Roll_Visuals"
    assert calls[1] == media_pool.root_folder
    assert media_pool.current_folder == media_pool.root_folder


def test_setup_project_configures_vertical_resolution() -> None:
    media_pool = FakeMediaPool()
    project = FakeProject(media_pool)
    pm = FakeProjectManager(current_project=project)

    res = resolve_adapter.setup_project(
        "Licbarska_Reel", vertical=True, fps=30.0, session=_session(project, project_manager=pm)
    )

    assert res["project_name"] == "Licbarska_Reel"
    assert res["vertical"] is True
    assert project.project_settings["timelineResolutionWidth"] == "1080"
    assert project.project_settings["timelineResolutionHeight"] == "1920"
    assert project.project_settings["timelineFrameRate"] == "30.0"
    assert pm.created_projects == ["Licbarska_Reel"]


def test_setup_project_falls_back_to_load_project_if_create_fails() -> None:
    media_pool = FakeMediaPool()
    project = FakeProject(media_pool)
    pm = FakeProjectManager(current_project=project)
    pm.fail_create = True

    res = resolve_adapter.setup_project(
        "Existing_Project", vertical=False, fps=25.0, session=_session(project, project_manager=pm)
    )

    assert res["project_name"] == "Existing_Project"
    assert pm.created_projects == ["Existing_Project"]
    assert pm.loaded_projects == ["Existing_Project"]
    assert project.project_settings["timelineResolutionWidth"] == "3840"
    assert project.project_settings["timelineResolutionHeight"] == "2160"


def test_setup_project_raises_when_create_and_load_both_fail() -> None:
    media_pool = FakeMediaPool()
    project = FakeProject(media_pool)
    pm = FakeProjectManager(current_project=project)
    pm.fail_create = True
    pm.fail_load = True

    with pytest.raises(resolve_adapter.ResolveAdapterError, match="weder erstellt noch geladen"):
        resolve_adapter.setup_project(
            "Failing_Project", session=_session(project, project_manager=pm)
        )


def test_setup_project_raises_when_project_manager_is_missing() -> None:
    media_pool = FakeMediaPool()
    project = FakeProject(media_pool)
    # Session where resolve has no GetProjectManager
    session = resolve_adapter.ResolveSession(resolve=SimpleNamespace(), project=project)

    with pytest.raises(resolve_adapter.ResolveAdapterError, match="ProjectManager"):
        resolve_adapter.setup_project("No_PM_Project", session=session)


def test_connect_require_project_false_allows_none_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeScriptAppResolve:
        def __init__(self, pm: FakeProjectManager) -> None:
            self._pm = pm

        def GetProjectManager(self) -> FakeProjectManager:
            return self._pm

    pm = FakeProjectManager(current_project=None)
    fake_mod = SimpleNamespace(scriptapp=lambda name: FakeScriptAppResolve(pm))
    monkeypatch.setattr(resolve_adapter, "_load_script_module", lambda: fake_mod)

    # When require_project=False, connection succeeds even without an open project
    session = resolve_adapter.connect(require_project=False)
    assert session.resolve is not None
    assert session.project is None

    # When require_project=True (default), connection fails
    with pytest.raises(resolve_adapter.ResolveAdapterError, match="kein Projekt geöffnet"):
        resolve_adapter.connect()


def test_setup_project_creates_project_when_no_project_is_currently_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeScriptAppResolve:
        def __init__(self, pm: FakeProjectManager) -> None:
            self._pm = pm

        def GetProjectManager(self) -> FakeProjectManager:
            return self._pm

    pm = FakeProjectManager(current_project=None)
    fake_mod = SimpleNamespace(scriptapp=lambda name: FakeScriptAppResolve(pm))
    monkeypatch.setattr(resolve_adapter, "_load_script_module", lambda: fake_mod)

    # Calling setup_project without session when no project is currently open in Resolve
    res = resolve_adapter.setup_project("FirstEverProject", vertical=True, fps=30.0)

    assert res["project_name"] == "FirstEverProject"
    assert "FirstEverProject" in pm.created_projects
    assert pm.current_project is not None
    assert pm.current_project.project_settings["timelineResolutionWidth"] == "1080"



def test_fairlight_gate_requires_active_timeline() -> None:
    media_pool = FakeMediaPool()
    project = FakeProject(media_pool, timeline=None)

    with pytest.raises(resolve_adapter.ResolveAdapterError, match="Keine aktive Timeline"):
        resolve_adapter.apply_fairlight_gate(session=_session(project))


def test_fairlight_gate_timeline_returns_not_measured() -> None:
    media_pool = FakeMediaPool()
    project = FakeProject(media_pool, timeline=object())

    res = resolve_adapter.apply_fairlight_gate(target_lufs=-14.0, session=_session(project))

    assert res["status"] == "not_measured"
    assert "audio_tracks_inspected" not in res
    assert "note" in res
    assert "ffmpeg" in str(res["note"]).lower()


def test_resolve_mcp_fairlight_gate_timeline_returns_not_measured(monkeypatch: pytest.MonkeyPatch) -> None:
    from tools import resolve_mcp

    media_pool = FakeMediaPool()
    project = FakeProject(media_pool, timeline=object())
    monkeypatch.setattr(resolve_adapter, "connect", lambda: _session(project))

    res = resolve_mcp.handle_tool_call("resolve_fairlight_gate", {})
    assert res["status"] == "not_measured"
    assert "audio_tracks_inspected" not in res
    assert "note" in res
    assert "ffmpeg" in str(res["note"]).lower()


def test_resolve_mcp_setup_project(monkeypatch: pytest.MonkeyPatch) -> None:
    from tools import resolve_mcp

    media_pool = FakeMediaPool()
    project = FakeProject(media_pool)
    pm = FakeProjectManager(current_project=project)
    monkeypatch.setattr(resolve_adapter, "connect", lambda *a, **kw: _session(project, project_manager=pm))

    res = resolve_mcp.handle_tool_call(
        "resolve_setup_project", {"project_name": "MCP_Project", "vertical": True, "fps": 30.0}
    )
    assert res["project_name"] == "MCP_Project"
    assert res["vertical"] is True
    assert pm.created_projects == ["MCP_Project"]


def test_discover_reports_free_edition_as_inactive_until_studio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_dir = tmp_path / "DaVinci Resolve.app"
    app_dir.mkdir()
    script = tmp_path / "DaVinciResolveScript.py"
    script.write_text("# script module", encoding="utf-8")
    monkeypatch.setattr(resolve_adapter, "RESOLVE_APP_PATH", app_dir)
    monkeypatch.setattr(resolve_adapter, "SCRIPT_MODULE_PATHS", (script,))

    status = resolve_adapter.discover()
    assert status["is_studio"] is False
    assert status["active"] is False
    assert status["status"] == "inactive"
    assert status["edition"] == "free"
    assert "Resolve Studio" in status["note"]


def test_discover_recognizes_studio_edition_at_applications_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    studio_dir = tmp_path / "DaVinci Resolve Studio.app"
    studio_dir.mkdir()
    script = tmp_path / "DaVinciResolveScript.py"
    script.write_text("# script", encoding="utf-8")

    monkeypatch.setattr(resolve_adapter, "STUDIO_APP_PATHS", (studio_dir,))
    monkeypatch.setattr(resolve_adapter, "FREE_APP_PATHS", (tmp_path / "Nonexistent.app",))
    monkeypatch.setattr(resolve_adapter, "RESOLVE_APP_PATH", tmp_path / "Nonexistent.app")
    monkeypatch.setattr(resolve_adapter, "SCRIPT_MODULE_PATHS", (script,))

    status = resolve_adapter.discover()
    assert status["resolve_app_installed"] is True
    assert status["is_studio"] is True
    assert status["edition"] == "studio"
    assert status["active"] is True
    assert status["status"] == "active"
    assert status["resolve_app_path"] == str(studio_dir)


def test_discover_recognizes_studio_edition_in_subfolder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    studio_sub_dir = tmp_path / "DaVinci Resolve" / "DaVinci Resolve Studio.app"
    studio_sub_dir.parent.mkdir()
    studio_sub_dir.mkdir()
    script = tmp_path / "DaVinciResolveScript.py"
    script.write_text("# script", encoding="utf-8")

    monkeypatch.setattr(resolve_adapter, "STUDIO_APP_PATHS", (studio_sub_dir,))
    monkeypatch.setattr(resolve_adapter, "FREE_APP_PATHS", (tmp_path / "Nonexistent.app",))
    monkeypatch.setattr(resolve_adapter, "RESOLVE_APP_PATH", tmp_path / "Nonexistent.app")
    monkeypatch.setattr(resolve_adapter, "SCRIPT_MODULE_PATHS", (script,))

    status = resolve_adapter.discover()
    assert status["resolve_app_installed"] is True
    assert status["is_studio"] is True
    assert status["edition"] == "studio"
    assert status["resolve_app_path"] == str(studio_sub_dir)


def test_discover_reports_edition_none_when_neither_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(resolve_adapter, "STUDIO_APP_PATHS", (tmp_path / "NoStudio.app",))
    monkeypatch.setattr(resolve_adapter, "FREE_APP_PATHS", (tmp_path / "NoFree.app",))
    monkeypatch.setattr(resolve_adapter, "RESOLVE_APP_PATH", tmp_path / "NoFree.app")
    monkeypatch.setattr(resolve_adapter, "SCRIPT_MODULE_PATHS", ())

    status = resolve_adapter.discover()
    assert status["resolve_app_installed"] is False
    assert status["is_studio"] is False
    assert status["edition"] is None
    assert status["active"] is False


def test_fairlight_gate_measurement_fails_on_quiet_audio(tmp_path: Path) -> None:
    quiet_file = tmp_path / "quiet.wav"
    import subprocess
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
        "-c:a", "pcm_s16le",
        str(quiet_file),
    ]
    subprocess.run(cmd, check=True, capture_output=True)

    res = resolve_adapter.apply_fairlight_gate(file_path=quiet_file, target_lufs=-14.0)

    assert res["status"] == "fail"
    assert res["passed"] is False
    assert res["measured_lufs"] < -15.0
    assert "measured_tp" in res
    assert res["target_lufs"] == -14.0


def test_fairlight_gate_measurement_passes_on_compliant_audio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio_file = tmp_path / "master.mp4"
    audio_file.write_bytes(b"dummy audio")

    monkeypatch.setattr(
        resolve_adapter,
        "measure_audio_loudness",
        lambda p: {"input_i": -14.1, "input_tp": -1.5, "input_lra": 3.0, "input_thresh": -24.0},
    )

    res = resolve_adapter.apply_fairlight_gate(file_path=audio_file, target_lufs=-14.0)

    assert res["status"] == "pass"
    assert res["passed"] is True
    assert res["measured_lufs"] == -14.1
    assert res["measured_tp"] == -1.5


def test_setup_project_raises_on_set_setting_failure() -> None:
    class FailingSetSettingProject(FakeProject):
        def SetSetting(self, key: str, value: str) -> bool:  # noqa: N802
            if key == "timelineResolutionHeight":
                return False
            return super().SetSetting(key, value)

    project = FailingSetSettingProject(media_pool=FakeMediaPool())
    session = _session(project)

    with pytest.raises(resolve_adapter.ResolveAdapterError, match="timelineResolutionHeight"):
        resolve_adapter.setup_project("TestProject", session=session)


def test_fairlight_gate_main_exit_codes_and_mcp_passed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = FakeProject(FakeMediaPool(), timeline=object())
    session = _session(project)
    unmeasured = resolve_adapter.apply_fairlight_gate(session=session)
    assert unmeasured["status"] == "not_measured"
    assert unmeasured["passed"] is False

    audio_file = tmp_path / "pass.mp4"
    audio_file.write_bytes(b"dummy")
    monkeypatch.setattr(
        resolve_adapter,
        "measure_audio_loudness",
        lambda p: {"input_i": -14.0, "input_tp": -1.5, "input_lra": 3.0, "input_thresh": -24.0},
    )
    assert resolve_adapter.main(["fairlight-gate", "--file", str(audio_file)]) == 0

    monkeypatch.setattr(
        resolve_adapter,
        "measure_audio_loudness",
        lambda p: {"input_i": -25.0, "input_tp": -1.5, "input_lra": 3.0, "input_thresh": -24.0},
    )
    assert resolve_adapter.main(["fairlight-gate", "--file", str(audio_file)]) == 1

    monkeypatch.setattr(resolve_adapter, "connect", lambda: session)
    assert resolve_adapter.main(["fairlight-gate"]) == 3


def test_discover_and_loader_find_same_studio_module_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_studio = tmp_path / "DaVinci Resolve Studio.app"
    script = (
        fake_studio
        / "Contents"
        / "Resources"
        / "Developer"
        / "Scripting"
        / "Modules"
        / "DaVinciResolveScript.py"
    )
    script.parent.mkdir(parents=True)
    script.write_text("# fake resolve script", encoding="utf-8")

    monkeypatch.setattr(resolve_adapter, "STUDIO_APP_PATHS", (fake_studio,))
    monkeypatch.setattr(resolve_adapter, "FREE_APP_PATHS", (tmp_path / "NonexistentFree.app",))
    monkeypatch.setattr(resolve_adapter, "RESOLVE_APP_PATH", tmp_path / "NonexistentApp.app")
    monkeypatch.setattr(resolve_adapter, "SCRIPT_MODULE_PATHS", ())

    discovered = resolve_adapter.discover()
    assert discovered["status"] == "active"
    assert discovered["script_module"] == str(script)

    loader_path = resolve_adapter._script_module_path()
    assert loader_path == script
    assert str(loader_path) == discovered["script_module"]





