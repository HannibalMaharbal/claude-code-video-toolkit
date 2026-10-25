"""Headless entry point sharing import, validation, and render actions with the add-on.

    blender -b --gpu-backend metal --python-exit-code 1 -noaudio \
      -P tools/blender_cli/run_pipeline.py -- \
      --input /path/to/model.glb --output-dir projects/blender-prototype
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blender_toolkit_addon import pipeline


def run() -> dict:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("projects/blender-prototype"))
    parser.add_argument("--frames", type=int, default=72)
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--save-scene", action="store_true", help="Also export a dated .blend copy")
    parser.add_argument("--audit-mesh", action="store_true", help="Run geometric and CAD watertightness audit")
    parser.add_argument("--audit-only", action="store_true", help="Only run audit, skip rendering")
    parser.add_argument("--export-glb", type=Path, default=None, help="Export normalized clean GLB")
    parser.add_argument("--export-stl", type=Path, default=None, help="Export normalized clean STL for CAD/3D printing")
    args = parser.parse_args(argv)
    source = args.input.expanduser().resolve()
    if not source.is_file():
        parser.error(f"input file does not exist: {source}")
    if not args.audit_only and (args.frames < 1 or args.fps < 1 or min(args.width, args.height) < 16):
        parser.error("frames and fps must be positive; width and height must be at least 16")
    if source.suffix.lower() != ".blend":
        bpy.ops.wm.read_factory_settings(use_empty=True)
    imported = pipeline.import_asset(str(source))
    pipeline.prepare_scene(bpy.context.scene)
    output_dir = args.output_dir.expanduser().resolve()
    messages = pipeline.validate_scene(bpy.context.scene, args.width, args.height)

    audit_result = None
    if args.audit_mesh or args.audit_only:
        audit_result = pipeline.audit_mesh_geometry(bpy.context.scene, recalculate_normals=True)
        print(f"AUDIT_OK watertight={audit_result['is_watertight_for_cad']} vertices={audit_result['total_vertices']} non_manifold={audit_result['non_manifold_edges']}", flush=True)

    exported_clean = {}
    if args.export_glb:
        exported_clean["glb"] = pipeline.export_clean_geometry(str(args.export_glb), "glb")
        print(f"CLEAN_GLB_OK file={exported_clean['glb']}", flush=True)
    if args.export_stl:
        exported_clean["stl"] = pipeline.export_clean_geometry(str(args.export_stl), "stl")
        print(f"CLEAN_STL_OK file={exported_clean['stl']}", flush=True)

    if args.audit_only:
        return {
            "schema_version": 1,
            "status": "ok",
            "audit_only": True,
            "input": str(source),
            "imported_objects": len(imported),
            "validation": messages,
            "mesh_audit": audit_result,
            "exported_clean": exported_clean,
        }

    settings = type("RenderSettings", (), {
        "width": args.width, "height": args.height, "fps": args.fps,
        "frames": args.frames, "output_dir": str(output_dir),
    })()
    frame_dir = pipeline.configure_frames(bpy.context.scene, settings)
    print(f"SCENE_OK imported={len(imported)} " + "; ".join(messages), flush=True)
    bpy.ops.render.render(animation=True)
    print(f"RENDER_OK frames={frame_dir}", flush=True)
    output = Path(pipeline.export_mp4(frame_dir, str(output_dir), settings, bpy.context.scene.frame_start))
    print(f"EXPORT_OK file={output} bytes={output.stat().st_size}", flush=True)
    scene_path = None
    if args.save_scene:
        scene_path = pipeline.export_scene(str(output_dir))
        print(f"SCENE_EXPORT_OK file={scene_path}", flush=True)
    return {
        "schema_version": 1,
        "status": "ok",
        "input": str(source),
        "imported_objects": len(imported),
        "validation": messages,
        "mesh_audit": audit_result,
        "exported_clean": exported_clean,
        "render": {
            "frames_dir": frame_dir,
            "frame_count": args.frames,
            "fps": args.fps,
            "width": args.width,
            "height": args.height,
        },
        "video": str(output),
        "scene": scene_path,
    }


def main() -> None:
    try:
        result = run()
    except Exception as exc:
        print("PIPELINE_ERROR " + json.dumps({
            "schema_version": 1,
            "status": "error",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }, ensure_ascii=False, separators=(",", ":")), file=sys.stderr, flush=True)
        raise SystemExit(1) from None
    print("PIPELINE_RESULT " + json.dumps(result, ensure_ascii=False, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    main()
