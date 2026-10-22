"""Run inside Blender's UI to enable the add-on and save the startup workspace."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import addon_utils
import bpy


def main() -> None:
    config_dir = Path(bpy.utils.user_resource("CONFIG"))
    startup = config_dir / "startup.blend"
    addon_target = config_dir.parent / "scripts" / "addons" / "hannibal_blender_toolkit"
    expected_addon = Path(__file__).resolve().parent / "blender_toolkit_addon"
    if not addon_target.is_symlink() or addon_target.resolve() != expected_addon.resolve():
        raise RuntimeError(f"Expected project add-on link is missing or unrelated: {addon_target}")
    if startup.exists():
        raise RuntimeError(f"Refusing to replace existing startup file: {startup}")

    addon_utils.enable("hannibal_blender_toolkit", default_set=True, persistent=True)
    bpy.ops.wm.save_userpref()
    setup_path = Path(__file__).resolve().with_name("setup_startup.py")
    spec = importlib.util.spec_from_file_location("hannibal_setup_startup", setup_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load startup setup script: {setup_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.create_startup(startup)
    print("ADDON_ENABLED hannibal_blender_toolkit; STARTUP_SETUP_SCHEDULED", flush=True)


main()
