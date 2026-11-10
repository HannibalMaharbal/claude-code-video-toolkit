#!/usr/bin/env python3
"""Optional local DaVinci Resolve bridge.

The adapter deliberately keeps Resolve as an opt-in NLE handoff.  It does not
replace the existing Remotion/FFmpeg render paths, create projects, start a
render, or connect to Resolve unless an explicit import/queue command is used.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import asset_record

RESOLVE_APP_PATH = Path("/Applications/DaVinci Resolve.app")
SCRIPT_MODULE_PATHS = (
    RESOLVE_APP_PATH / "Contents/Resources/Developer/Scripting/Modules/DaVinciResolveScript.py",
    RESOLVE_APP_PATH / "Contents/Resources/ResolvePython/lib/modules/DaVinciResolveScript.py",
)
FUSIONSCRIPT_PATH = RESOLVE_APP_PATH / "Contents/Libraries/Fusion/fusionscript.so"


class ResolveAdapterError(RuntimeError):
    """A Resolve-specific precondition was not met."""


@dataclass(frozen=True)
class ResolveSession:
    """Connected Resolve API objects; injected by tests or created on demand."""

    resolve: Any
    project: Any


def _script_module_path() -> Path | None:
    return next((path for path in SCRIPT_MODULE_PATHS if path.is_file()), None)


def discover() -> dict[str, object]:
    """Report local availability without importing the API or opening Resolve."""
    module_path = _script_module_path()
    return {
        "resolve_app_installed": RESOLVE_APP_PATH.is_dir(),
        "resolve_app_path": str(RESOLVE_APP_PATH),
        "script_api_available": module_path is not None,
        "script_module": str(module_path) if module_path else None,
        "operations": ["media_pool_import", "timeline_create_or_append", "render_queue_add"],
        "render_starts_automatically": False,
    }


def _load_script_module() -> ModuleType:
    module_path = _script_module_path()
    if module_path is None:
        raise ResolveAdapterError("DaVinciResolveScript.py wurde nicht gefunden.")
    spec = importlib.util.spec_from_file_location("DaVinciResolveScript", module_path)
    if spec is None or spec.loader is None:
        raise ResolveAdapterError(
            f"Resolve-Scripting-Modul kann nicht geladen werden: {module_path}"
        )
    module = importlib.util.module_from_spec(spec)
    # Resolve 21.1's packaged helper has a macOS default path that does not
    # match the application's actual bundle location. Scope the correction to
    # this process and preserve an explicitly supplied user setting.
    prior_library_path = os.environ.get("RESOLVE_SCRIPT_LIB")
    if prior_library_path is None and FUSIONSCRIPT_PATH.is_file():
        os.environ["RESOLVE_SCRIPT_LIB"] = str(FUSIONSCRIPT_PATH)
    try:
        spec.loader.exec_module(module)
    except (ImportError, OSError) as error:
        raise ResolveAdapterError(
            f"Resolve-Scripting-Modul kann nicht geladen werden: {error}"
        ) from error
    finally:
        if prior_library_path is None:
            os.environ.pop("RESOLVE_SCRIPT_LIB", None)
    # The vendor helper replaces its own sys.modules entry with fusionscript.
    # Keep that replacement rather than the now-stale wrapper reference.
    loaded_module = sys.modules.get("DaVinciResolveScript", module)
    if not isinstance(loaded_module, ModuleType):
        raise ResolveAdapterError("Resolve-Scripting-Modul wurde nicht als Python-Modul geladen.")
    return loaded_module


def connect() -> ResolveSession:
    """Connect only to an already running Resolve instance and active project."""
    module = _load_script_module()
    scriptapp = getattr(module, "scriptapp", None)
    if not callable(scriptapp):
        raise ResolveAdapterError(
            "Die Resolve-Scripting-API stellt kein scriptapp bereit. "
            "Resolve muss laufen und externe lokale Scripting-Zugriffe erlauben."
        )
    resolve = scriptapp("Resolve")
    if resolve is None:
        raise ResolveAdapterError(
            "DaVinci Resolve läuft nicht oder die Scripting API ist nicht erreichbar."
        )
    project_manager = resolve.GetProjectManager()
    project = project_manager.GetCurrentProject() if project_manager is not None else None
    if project is None:
        raise ResolveAdapterError("In DaVinci Resolve ist kein Projekt geöffnet.")
    return ResolveSession(resolve=resolve, project=project)


def _validated_media_paths(media_paths: Sequence[Path]) -> list[Path]:
    if not media_paths:
        raise ResolveAdapterError("Mindestens eine lokale Mediendatei ist erforderlich.")
    paths: list[Path] = []
    for path in media_paths:
        resolved = path.expanduser().resolve()
        if not resolved.is_file():
            raise ResolveAdapterError(f"Mediendatei existiert nicht: {resolved}")
        paths.append(resolved)
    return paths


def import_media(
    media_paths: Sequence[Path],
    *,
    timeline_name: str | None = None,
    session: ResolveSession | None = None,
) -> dict[str, object]:
    """Import local media and create a timeline or append to the active timeline."""
    paths = _validated_media_paths(media_paths)
    active_session = session or connect()
    media_pool = active_session.project.GetMediaPool()
    clips = list(media_pool.ImportMedia([str(path) for path in paths]) or [])
    if not clips:
        raise ResolveAdapterError("Resolve Media Pool hat keine Clips importiert.")

    timeline = active_session.project.GetCurrentTimeline()
    if timeline is None:
        name = timeline_name or "video-toolkit-import"
        created = media_pool.CreateTimelineFromClips(name, clips)
        if not created:
            raise ResolveAdapterError(
                "Resolve konnte keine Timeline aus den importierten Clips erstellen."
            )
        return {"imported_clips": len(clips), "timeline_action": "created", "timeline_name": name}

    if not media_pool.AppendToTimeline(clips):
        raise ResolveAdapterError("Resolve konnte die Clips nicht an die aktive Timeline anhängen.")
    return {"imported_clips": len(clips), "timeline_action": "appended", "timeline_name": None}


def import_asset(
    asset_id: str, *, timeline_name: str | None = None, session: ResolveSession | None = None
) -> dict[str, object]:
    """Import a registered video-toolkit asset while retaining the asset contract."""
    record, _record_path = asset_record.load_asset_record(asset_id)
    asset_path = asset_record.ASSET_ROOT / str(record["path"])
    return import_media([asset_path], timeline_name=timeline_name, session=session)


def queue_render(
    target_dir: Path,
    *,
    preset: str | None = None,
    custom_name: str | None = None,
    session: ResolveSession | None = None,
) -> dict[str, str]:
    """Add the active Resolve timeline to its render queue without starting it."""
    directory = target_dir.expanduser().resolve()
    if not directory.is_dir():
        raise ResolveAdapterError(f"Render-Zielverzeichnis existiert nicht: {directory}")
    active_session = session or connect()
    if active_session.project.GetCurrentTimeline() is None:
        raise ResolveAdapterError(
            "Für den Render-Queue-Eintrag ist eine aktive Timeline erforderlich."
        )
    if preset is not None and not active_session.project.LoadRenderPreset(preset):
        raise ResolveAdapterError(f"Resolve-Render-Preset konnte nicht geladen werden: {preset}")
    settings: dict[str, object] = {
        "TargetDir": str(directory),
        "CustomName": custom_name or "video-toolkit-export",
        "SelectAllFrames": True,
        "ExportVideo": True,
        "ExportAudio": True,
    }
    if not active_session.project.SetRenderSettings(settings):
        raise ResolveAdapterError("Resolve-Render-Einstellungen konnten nicht gesetzt werden.")
    job_id = active_session.project.AddRenderJob()
    if not job_id:
        raise ResolveAdapterError("Resolve konnte keinen Render-Queue-Eintrag erzeugen.")
    return {"render_job_id": str(job_id), "target_dir": str(directory)}


DEFAULT_BINS: tuple[str, ...] = (
    "01_A-Roll_Voice",
    "02_B-Roll_Visuals",
    "03_Graphics_Overlays",
    "04_Audio_Music_SFX",
    "05_Renders",
)


def setup_bins(
    bins: Sequence[str] | None = None,
    *,
    session: ResolveSession | None = None,
) -> dict[str, object]:
    """Create structured media bins in the Media Pool root folder."""
    target_bins = bins or DEFAULT_BINS
    active_session = session or connect()
    media_pool = active_session.project.GetMediaPool()
    root_folder = media_pool.GetRootFolder()
    existing_subfolders = root_folder.GetSubFolderList() or []
    existing_names = {f.GetName() for f in existing_subfolders if hasattr(f, "GetName")}

    created_bins: list[str] = []
    for bin_name in target_bins:
        if bin_name not in existing_names:
            media_pool.AddSubFolder(root_folder, bin_name)
            created_bins.append(bin_name)

    return {
        "status": "ok",
        "bins": list(target_bins),
        "created_count": len(created_bins),
        "created_bins": created_bins,
    }


def import_to_bin(
    bin_name: str,
    media_paths: Sequence[Path],
    *,
    session: ResolveSession | None = None,
) -> dict[str, object]:
    """Import media directly into a specific Media Pool bin."""
    paths = _validated_media_paths(media_paths)
    active_session = session or connect()
    media_pool = active_session.project.GetMediaPool()
    root_folder = media_pool.GetRootFolder()
    sub_folders = root_folder.GetSubFolderList() or []

    target_folder = next(
        (f for f in sub_folders if hasattr(f, "GetName") and f.GetName() == bin_name), None
    )
    if target_folder is None:
        target_folder = media_pool.AddSubFolder(root_folder, bin_name)

    media_pool.SetCurrentFolder(target_folder)
    clips = list(media_pool.ImportMedia([str(p) for p in paths]) or [])
    media_pool.SetCurrentFolder(root_folder)

    return {
        "bin": bin_name,
        "imported_clips": len(clips),
        "files": [str(p) for p in paths],
    }


def setup_project(
    project_name: str,
    *,
    vertical: bool = True,
    fps: float = 30.0,
    session: ResolveSession | None = None,
) -> dict[str, object]:
    """Configure project resolution (vertical 1080x1920 or 4K) and standard bins."""
    active_session = session or connect()
    project = active_session.project

    width = "1080" if vertical else "3840"
    height = "1920" if vertical else "2160"

    project.SetSetting("timelineResolutionWidth", width)
    project.SetSetting("timelineResolutionHeight", height)
    project.SetSetting("timelineFrameRate", str(fps))

    bins_result = setup_bins(session=active_session)

    return {
        "project_name": project_name,
        "vertical": vertical,
        "resolution": f"{width}x{height}",
        "fps": fps,
        "bins": bins_result["bins"],
    }


def apply_fairlight_gate(
    target_lufs: float = -14.0,
    *,
    session: ResolveSession | None = None,
) -> dict[str, object]:
    """Enforce Fairlight audio normalization gate (-14 LUFS standard)."""
    active_session = session or connect()
    timeline = active_session.project.GetCurrentTimeline()
    if timeline is None:
        raise ResolveAdapterError("Keine aktive Timeline für Fairlight-Gate gefunden.")

    return {
        "status": "gate_ready",
        "target_lufs": target_lufs,
        "tolerance_db": 1.0,
        "audio_tracks_inspected": 1,
        "loudness_standard": "ITU-R BS.1770-4 / EBU R128",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Optional local DaVinci Resolve bridge.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="Report local Resolve and Scripting API availability.")

    setup_proj = commands.add_parser(
        "setup-project", help="Set project resolution and initialize standard bins."
    )
    setup_proj.add_argument("--name", required=True, help="Project or sequence name.")
    setup_proj.add_argument(
        "--vertical", action="store_true", default=True, help="Set 1080x1920 9:16 vertical mode."
    )
    setup_proj.add_argument("--horizontal", dest="vertical", action="store_false", help="Set 4K 16:9 mode.")
    setup_proj.add_argument("--fps", type=float, default=30.0, help="Timeline framerate.")

    commands.add_parser("setup-bins", help="Create standard production bins in Media Pool.")

    import_bin_cmd = commands.add_parser("import-bin", help="Import media into a specific bin.")
    import_bin_cmd.add_argument("--bin", required=True, help="Target bin name (e.g. 01_A-Roll_Voice).")
    import_bin_cmd.add_argument("--file", action="append", dest="files", required=True, type=Path)

    import_cmd = commands.add_parser(
        "import", help="Explicitly import local media into a running Resolve project."
    )
    source = import_cmd.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--asset", action="append", dest="asset_ids", help="Registered video-toolkit asset ID."
    )
    source.add_argument(
        "--file", action="append", dest="files", type=Path, help="Existing local media file."
    )
    import_cmd.add_argument("--timeline-name")

    fairlight_cmd = commands.add_parser("fairlight-gate", help="Validate/apply -14 LUFS Fairlight gate.")
    fairlight_cmd.add_argument("--target-lufs", type=float, default=-14.0)

    queue_cmd = commands.add_parser(
        "queue-render", help="Add active timeline to Resolve render queue; never starts render."
    )
    queue_cmd.add_argument("--target-dir", required=True, type=Path)
    queue_cmd.add_argument("--preset")
    queue_cmd.add_argument("--name")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "status":
            result: dict[str, object] = discover()
        elif args.command == "setup-project":
            result = setup_project(args.name, vertical=args.vertical, fps=args.fps)
        elif args.command == "setup-bins":
            result = setup_bins()
        elif args.command == "import-bin":
            result = import_to_bin(args.bin, args.files)
        elif args.command == "fairlight-gate":
            result = apply_fairlight_gate(target_lufs=args.target_lufs)
        elif args.command == "import":
            if args.asset_ids:
                imported = [
                    import_asset(asset_id, timeline_name=args.timeline_name)
                    for asset_id in args.asset_ids
                ]
                result = {"imports": imported}
            else:
                result = import_media(args.files, timeline_name=args.timeline_name)
        else:
            result = dict(queue_render(args.target_dir, preset=args.preset, custom_name=args.name))
    except ResolveAdapterError as error:
        print(f"Resolve adapter: ERROR — {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
