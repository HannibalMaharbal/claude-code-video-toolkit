#!/usr/bin/env python3
"""Optional local DaVinci Resolve bridge.

The adapter deliberately keeps Resolve as an opt-in NLE handoff.  It does not
replace the existing Remotion/FFmpeg render paths, create projects, start a
render, or connect to Resolve unless an explicit import/queue command is used.

Status: Inaktiv bis DaVinci Resolve Studio vorhanden ist. Die installierte
DaVinci Resolve Free 21.1 Edition unterstützt keine externe Python-Scripting-API.
Das Fairlight-Lautheits-Gate (--file) verwendet ffmpeg loudnorm für echte
Lautheitsmessungen (-14 LUFS ±1, True Peak <= -1 dBTP).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import asset_record

DEFAULT_RESOLVE_APP_PATH = Path("/Applications/DaVinci Resolve.app")
RESOLVE_APP_PATH = DEFAULT_RESOLVE_APP_PATH
STUDIO_APP_PATHS = (
    Path("/Applications/DaVinci Resolve Studio.app"),
    Path("/Applications/DaVinci Resolve/DaVinci Resolve Studio.app"),
)
FREE_APP_PATHS = (
    Path("/Applications/DaVinci Resolve.app"),
    Path("/Applications/DaVinci Resolve/DaVinci Resolve.app"),
)
DEFAULT_STUDIO_APP_PATHS = STUDIO_APP_PATHS
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


SCRIPT_MODULE_SUBPATHS = (
    "Contents/Resources/Developer/Scripting/Modules/DaVinciResolveScript.py",
    "Contents/Resources/ResolvePython/lib/modules/DaVinciResolveScript.py",
)


def get_script_module_paths(app_path: Path | None = None) -> list[Path]:
    """Return an ordered list of candidate script module paths across all candidate Resolve installations.

    Includes explicit SCRIPT_MODULE_PATHS, candidate subpaths under app_path (if provided),
    STUDIO_APP_PATHS, FREE_APP_PATHS, and RESOLVE_APP_PATH.
    """
    candidates: list[Path] = list(SCRIPT_MODULE_PATHS)

    app_candidates: list[Path] = []
    if app_path is not None:
        app_candidates.append(app_path)
    for p in STUDIO_APP_PATHS:
        if p not in app_candidates:
            app_candidates.append(p)
    for p in FREE_APP_PATHS:
        if p not in app_candidates:
            app_candidates.append(p)
    if RESOLVE_APP_PATH not in app_candidates:
        app_candidates.append(RESOLVE_APP_PATH)

    for app in app_candidates:
        for sub in SCRIPT_MODULE_SUBPATHS:
            cand = app / sub
            if cand not in candidates:
                candidates.append(cand)
    return candidates


def _script_module_path(app_path: Path | None = None) -> Path | None:
    for path in get_script_module_paths(app_path):
        if path.is_file():
            return path
    return None


def discover() -> dict[str, object]:
    """Report local availability without importing the API or opening Resolve."""
    detected_path: Path | None = None
    is_studio = False
    edition: str | None = None

    # Handle explicit monkeypatching/override of RESOLVE_APP_PATH in unit tests
    if RESOLVE_APP_PATH != DEFAULT_RESOLVE_APP_PATH and STUDIO_APP_PATHS == DEFAULT_STUDIO_APP_PATHS:
        if RESOLVE_APP_PATH.is_dir():
            detected_path = RESOLVE_APP_PATH
            is_studio = "studio" in str(RESOLVE_APP_PATH).lower()
            edition = "studio" if is_studio else "free"
    else:
        # 1. Check Studio installation candidates
        studio_candidates = list(STUDIO_APP_PATHS)
        if RESOLVE_APP_PATH.is_dir() and "studio" in str(RESOLVE_APP_PATH).lower():
            studio_candidates.insert(0, RESOLVE_APP_PATH)

        for path in studio_candidates:
            if path.is_dir():
                detected_path = path
                is_studio = True
                edition = "studio"
                break

        # 2. Check Free installation candidates if Studio not present
        if detected_path is None:
            free_candidates = list(FREE_APP_PATHS)
            if RESOLVE_APP_PATH.is_dir() and "studio" not in str(RESOLVE_APP_PATH).lower():
                free_candidates.insert(0, RESOLVE_APP_PATH)

            for path in free_candidates:
                if path.is_dir():
                    detected_path = path
                    is_studio = False
                    edition = "free"
                    break

    app_installed = detected_path is not None
    app_path = detected_path if detected_path is not None else RESOLVE_APP_PATH
    module_path = _script_module_path(app_path if app_installed else None)

    status_str = "active" if (app_installed and is_studio and module_path is not None) else "inactive"
    return {
        "status": status_str,
        "active": status_str == "active",
        "resolve_app_installed": app_installed,
        "resolve_app_path": str(app_path),
        "script_api_available": module_path is not None,
        "script_module": str(module_path) if module_path else None,
        "is_studio": is_studio,
        "edition": edition,
        "note": (
            "Inaktiv bis Resolve Studio vorhanden (DaVinci Resolve Free bietet keine externe Scripting-API)."
            if status_str == "inactive"
            else "DaVinci Resolve Studio API betriebsbereit."
        ),
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
    fusionscript_path = FUSIONSCRIPT_PATH
    if not fusionscript_path.is_file() and module_path is not None:
        for parent in module_path.parents:
            cand = parent / "Libraries" / "Fusion" / "fusionscript.so"
            if cand.is_file():
                fusionscript_path = cand
                break
    if prior_library_path is None and fusionscript_path.is_file():
        os.environ["RESOLVE_SCRIPT_LIB"] = str(fusionscript_path)
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


def connect(require_project: bool = True) -> ResolveSession:
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
    if require_project and project is None:
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

    previous_folder = (
        media_pool.GetCurrentFolder()
        if hasattr(media_pool, "GetCurrentFolder") and callable(media_pool.GetCurrentFolder)
        else root_folder
    )
    if previous_folder is None:
        previous_folder = root_folder

    try:
        if not media_pool.SetCurrentFolder(target_folder):
            raise ResolveAdapterError(
                f"Resolve Media Pool konnte nicht in Bin '{bin_name}' wechseln."
            )
        raw_clips = media_pool.ImportMedia([str(p) for p in paths])
        clips = list(raw_clips or [])
        if not clips and paths:
            raise ResolveAdapterError(
                f"Resolve Media Pool konnte die Dateien nicht in Bin '{bin_name}' importieren (keine Clips importiert)."
            )
    finally:
        media_pool.SetCurrentFolder(previous_folder)

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
    active_session = session or connect(require_project=False)
    if active_session.resolve is None or not hasattr(active_session.resolve, "GetProjectManager"):
        raise ResolveAdapterError("Resolve ProjectManager ist nicht verfügbar.")
    project_manager = active_session.resolve.GetProjectManager()
    if project_manager is None:
        raise ResolveAdapterError("Resolve ProjectManager ist nicht verfügbar.")

    project = None
    if hasattr(project_manager, "CreateProject") and callable(project_manager.CreateProject):
        project = project_manager.CreateProject(project_name)
    if project is None and hasattr(project_manager, "LoadProject") and callable(project_manager.LoadProject):
        project = project_manager.LoadProject(project_name)
    if project is None:
        raise ResolveAdapterError(
            f"Resolve-Projekt '{project_name}' konnte weder erstellt noch geladen werden."
        )

    active_session = ResolveSession(resolve=active_session.resolve, project=project)

    width = "1080" if vertical else "3840"
    height = "1920" if vertical else "2160"

    settings = {
        "timelineResolutionWidth": width,
        "timelineResolutionHeight": height,
        "timelineFrameRate": str(fps),
    }
    for setting_name, value in settings.items():
        if not project.SetSetting(setting_name, value):
            raise ResolveAdapterError(
                f"Konnte DaVinci Resolve Projekteinstellung '{setting_name}' nicht auf {value!r} setzen."
            )

    bins_result = setup_bins(session=active_session)

    return {
        "project_name": project_name,
        "vertical": vertical,
        "resolution": f"{width}x{height}",
        "fps": fps,
        "bins": bins_result["bins"],
    }


def measure_audio_loudness(file_path: Path) -> dict[str, float]:
    """Measure integrated loudness (LUFS) and true peak (dBTP) using ffmpeg loudnorm."""
    path = Path(file_path)
    if not path.is_file():
        raise ResolveAdapterError(f"Exportdatei zur Lautheitsmessung existiert nicht: {path}")

    cmd = [
        "ffmpeg", "-hide_banner",
        "-i", str(path),
        "-af", "loudnorm=print_format=json",
        "-f", "null", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    output = proc.stderr + "\n" + proc.stdout
    match = re.search(
        r"\{\s*\"input_i\"\s*:\s*\"([^\"]+)\",.*?\"input_tp\"\s*:\s*\"([^\"]+)\".*?\}",
        output,
        re.DOTALL,
    )
    if not match:
        raise ResolveAdapterError(f"FFmpeg loudnorm konnte keine Lautheitsmessung erzeugen: {output}")
    try:
        data = json.loads(match.group(0))
        return {
            "input_i": float(data["input_i"]),
            "input_tp": float(data["input_tp"]),
            "input_lra": float(data.get("input_lra", 0.0)),
            "input_thresh": float(data.get("input_thresh", 0.0)),
        }
    except (KeyError, ValueError, json.JSONDecodeError) as err:
        raise ResolveAdapterError(f"Fehler beim Parsen der Lautheitsdaten: {err}")


def apply_fairlight_gate(
    target_lufs: float = -14.0,
    *,
    file_path: Path | None = None,
    tolerance_db: float = 1.0,
    max_true_peak: float = -1.0,
    session: ResolveSession | None = None,
) -> dict[str, object]:
    """Enforce Fairlight audio normalization gate (-14 LUFS standard) with true ffmpeg measurement."""
    if file_path is not None:
        metrics = measure_audio_loudness(Path(file_path))
        input_i = metrics["input_i"]
        input_tp = metrics["input_tp"]

        min_lufs = target_lufs - tolerance_db
        max_lufs = target_lufs + tolerance_db
        lufs_ok = min_lufs <= input_i <= max_lufs
        tp_ok = input_tp <= max_true_peak
        passed = lufs_ok and tp_ok

        return {
            "status": "pass" if passed else "fail",
            "passed": passed,
            "measured_lufs": input_i,
            "measured_tp": input_tp,
            "target_lufs": target_lufs,
            "tolerance_db": tolerance_db,
            "max_true_peak_dbtp": max_true_peak,
            "loudness_standard": "ITU-R BS.1770-4 / EBU R128",
            "reason": None if passed else (
                f"Integrierte Lautheit ({input_i} LUFS) weicht vom Ziel ({target_lufs} ±{tolerance_db} LUFS) ab."
                if not lufs_ok else
                f"True Peak ({input_tp} dBTP) überschreitet Grenzwert ({max_true_peak} dBTP)."
            ),
        }

    active_session = session or connect()
    timeline = active_session.project.GetCurrentTimeline()
    if timeline is None:
        raise ResolveAdapterError("Keine aktive Timeline für Fairlight-Gate gefunden.")

    return {
        "status": "not_measured",
        "passed": False,
        "target_lufs": target_lufs,
        "tolerance_db": tolerance_db,
        "loudness_standard": "ITU-R BS.1770-4 / EBU R128",
        "note": "Lautheit wurde nicht gemessen. Bitte file_path/--file angeben, um eine echte ffmpeg loudnorm-Messung durchzuführen.",
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
    fairlight_cmd.add_argument("--file", type=Path, help="Exported media file to measure and validate.")

    queue_cmd = commands.add_parser(
        "queue-render", help="Add active timeline to Resolve render queue; never starts render."
    )
    queue_cmd.add_argument("--target-dir", required=True, type=Path)
    queue_cmd.add_argument("--preset")
    queue_cmd.add_argument("--name")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
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
            result = apply_fairlight_gate(target_lufs=args.target_lufs, file_path=args.file)
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
    if args.command == "fairlight-gate":
        status = result.get("status")
        if status == "pass":
            return 0
        if status == "not_measured":
            return 3
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
