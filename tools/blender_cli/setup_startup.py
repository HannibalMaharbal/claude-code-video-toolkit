"""Create the persistent compact Blender startup file inside Blender's UI."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import shutil
import sys
from pathlib import Path

import bpy


def request_workspace_cleanup(window, keep) -> None:
    if window.workspace != keep or bpy.context.workspace != keep:
        raise RuntimeError(
            f"The target workspace must be active before cleanup: "
            f"target={keep.name!r}, active={window.workspace.name!r}"
        )
    with bpy.context.temp_override(window=window, workspace=keep):
        if not bpy.ops.workspace.delete_all_others.poll():
            raise RuntimeError("Blender cannot delete the other workspaces in this window")
        result = bpy.ops.workspace.delete_all_others()
    print(f"WORKSPACE_DELETE_ALL_OTHERS result={sorted(result)}", flush=True)
    if "FINISHED" not in result:
        raise RuntimeError(f"Blender refused to delete the other workspaces: {result}")


def verify_only_workspace(keep) -> list[str]:
    remaining = list(bpy.data.workspaces)
    names = [workspace.name for workspace in remaining]
    if len(remaining) != 1 or remaining[0] != keep:
        raise RuntimeError(f"Workspace cleanup incomplete: {names}")
    return names


def create_startup(
    output: Path, *, replace_existing: bool = False, backup_dir: Path | None = None
) -> None:
    output = output.expanduser().resolve()
    if output.exists():
        if not replace_existing or backup_dir is None:
            raise FileExistsError(f"Refusing to overwrite existing startup file: {output}")
        backup_dir = backup_dir.expanduser().resolve()
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / f"startup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.blend"
        shutil.copy2(output, backup)
        digest = hashlib.sha256(backup.read_bytes()).hexdigest()
        backup.with_suffix(".blend.sha256").write_text(f"{digest}  {backup.name}\n")
    window = bpy.context.window
    if window is None:
        raise RuntimeError("Startup workspace setup requires Blender's interactive window")
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.length_unit = "METERS"
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.fps = 24
    scene.frame_start = 1
    scene.frame_end = 72
    toolkit_root = Path(__file__).resolve().parents[2]
    scene.render.filepath = str(toolkit_root / "projects" / "blender-prototype" / "blender-clip")
    scene.render.image_settings.file_format = "PNG"

    default_cube = bpy.data.objects.get("Cube")
    if default_cube is not None and default_cube.type == "MESH" and default_cube.data.name == "Cube":
        bpy.data.objects.remove(default_cube, do_unlink=True)

    keep = window.workspace
    request_workspace_cleanup(window, keep)

    def finish_after_ui_update():
        try:
            verify_only_workspace(keep)
            keep.name = "Video Studio"
            # Keep the 3D View, Outliner, Properties, timeline, and open Toolkit sidebar.
            screen = window.screen
            if screen:
                for area in screen.areas:
                    if area.type == "VIEW_3D":
                        area.spaces.active.show_region_ui = True
            output.parent.mkdir(parents=True, exist_ok=True)
            bpy.ops.wm.save_as_mainfile(filepath=str(output), check_existing=False)
            print(f"STARTUP_CREATED {output}", flush=True)
        except Exception as exc:
            print(f"STARTUP_ERROR {type(exc).__name__}: {exc}", flush=True)
        return None

    bpy.app.timers.register(finish_after_ui_update, first_interval=1.0)


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--replace-existing", action="store_true")
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--probe-delete", action="store_true", help="Try workspace removal in memory; do not save")
    parser.add_argument("--probe-operators", action="store_true", help="Print Blender workspace operator API and exit")
    args = parser.parse_args(argv)
    if args.probe_operators:
        try:
            print("WORKSPACE_OPERATORS", [name for name in dir(bpy.ops.workspace) if not name.startswith("_")], flush=True)
            for name in ("append_activate", "delete", "delete_all_others"):
                operator = getattr(bpy.ops.workspace, name, None)
                if operator is not None:
                    rna = operator.get_rna_type()
                    properties = [p.identifier for p in rna.properties if p.identifier != "rna_type"]
                    print(f"WORKSPACE_OPERATOR_API {name} properties={properties}", flush=True)
        finally:
            bpy.ops.wm.quit_blender()
        return
    if args.probe_delete:
        def probe_result(keep):
            try:
                names = verify_only_workspace(keep)
                print(f"WORKSPACE_PROBE_OK remaining={names}", flush=True)
            except Exception as exc:
                print(f"WORKSPACE_PROBE_ERROR {type(exc).__name__}: {exc}", flush=True)
            bpy.ops.wm.quit_blender()
            return None

        def probe_cleanup():
            window = bpy.context.window
            if window is None:
                print("WORKSPACE_PROBE_ERROR no interactive window", flush=True)
                bpy.ops.wm.quit_blender()
                return None
            keep = window.workspace
            try:
                request_workspace_cleanup(window, keep)
                bpy.app.timers.register(lambda: probe_result(keep), first_interval=1.0)
            except Exception as exc:
                print(f"WORKSPACE_PROBE_ERROR {type(exc).__name__}: {exc}", flush=True)
                bpy.ops.wm.quit_blender()
            return None

        bpy.app.timers.register(probe_cleanup, first_interval=1.0)
        return
    if args.output is None:
        parser.error("--output is required unless --probe-delete is used")
    create_startup(args.output, replace_existing=args.replace_existing, backup_dir=args.backup_dir)


if __name__ == "__main__":
    main()
