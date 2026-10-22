"""Import an asset, validate the Blender scene, and render an MP4 clip.

Run with Blender, not system Python:
    blender -b -noaudio -P tools/blender_cli/render_clip.py -- \
      --input path/to/model.glb --output projects/blender-prototype/model.mp4
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


SUPPORTED = {".blend", ".fbx", ".glb", ".gltf", ".obj", ".stl"}


def parse_args() -> argparse.Namespace:
    argv = sys.argv
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Source .blend/.fbx/.glb/.gltf/.obj/.stl")
    parser.add_argument("--output", required=True, type=Path, help="Destination MP4 file")
    parser.add_argument("--frames", type=int, default=72, help="Clip length in frames (default: 72)")
    parser.add_argument("--fps", type=int, default=24, help="Frame rate (default: 24)")
    parser.add_argument("--width", type=int, default=1280, help="Render width (default: 1280)")
    parser.add_argument("--height", type=int, default=720, help="Render height (default: 720)")
    parser.add_argument("--samples", type=int, default=32, help="Cycles samples (default: 32)")
    parser.add_argument("--engine", choices=("BLENDER_EEVEE_NEXT", "CYCLES"), default="BLENDER_EEVEE_NEXT")
    parser.add_argument("--turntable", action="store_true", help="Rotate imported mesh objects through one turn")
    args = parser.parse_args(argv)
    args.input = args.input.expanduser().resolve()
    args.output = args.output.expanduser().resolve()
    if not args.input.is_file():
        parser.error(f"input file does not exist: {args.input}")
    if args.input.suffix.lower() not in SUPPORTED:
        parser.error(f"unsupported input extension {args.input.suffix!r}; supported: {', '.join(sorted(SUPPORTED))}")
    for name in ("frames", "fps", "width", "height", "samples"):
        if getattr(args, name) < 1:
            parser.error(f"--{name} must be greater than zero")
    if args.output.suffix.lower() != ".mp4":
        parser.error("--output must end in .mp4")
    if args.input == args.output:
        parser.error("input and output paths must differ")
    return args


def import_asset(path: Path) -> None:
    suffix = path.suffix.lower()
    if suffix == ".blend":
        with bpy.data.libraries.load(str(path), link=False) as (source, target):
            target.objects = list(source.objects)
        for obj in target.objects:
            if obj is not None:
                bpy.context.scene.collection.objects.link(obj)
    elif suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(path))
    elif suffix in {".glb", ".gltf"}:
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif suffix == ".obj":
        bpy.ops.wm.obj_import(filepath=str(path))
    elif suffix == ".stl":
        bpy.ops.wm.stl_import(filepath=str(path))


def scene_meshes() -> list[bpy.types.Object]:
    return [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]


def bounds(meshes: list[bpy.types.Object]) -> tuple[Vector, float]:
    points = [obj.matrix_world @ Vector(corner) for obj in meshes for corner in obj.bound_box]
    low = Vector(tuple(min(point[i] for point in points) for i in range(3)))
    high = Vector(tuple(max(point[i] for point in points) for point in points))
    center = (low + high) * 0.5
    radius = max((high - low).length * 0.5, 0.5)
    return center, radius


def aim(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def make_camera_and_lights(center: Vector, radius: float) -> None:
    scene = bpy.context.scene
    distance = radius * 3.2
    camera_data = bpy.data.cameras.new("Toolkit Camera")
    camera = bpy.data.objects.new("Toolkit Camera", camera_data)
    scene.collection.objects.link(camera)
    camera.location = center + Vector((distance, -distance, distance * 0.7))
    camera_data.lens = 50
    camera_data.clip_end = max(distance * 20, 1000)
    aim(camera, center)
    scene.camera = camera
    for name, offset, power, size in (
        ("Key", (1.5, -2, 2.5), 1400, radius * 2.5),
        ("Fill", (-2, -1, 0.7), 800, radius * 3),
        ("Rim", (0.5, 2, 1.8), 1800, radius * 2),
    ):
        data = bpy.data.lights.new(name, "AREA")
        data.energy = power
        data.shape = "DISK"
        data.size = max(size, 0.1)
        light = bpy.data.objects.new(name, data)
        scene.collection.objects.link(light)
        light.location = center + Vector(offset) * radius
        aim(light, center)


def validate_scene(meshes: list[bpy.types.Object]) -> None:
    scene = bpy.context.scene
    if not meshes:
        raise RuntimeError("Scene check failed: imported scene contains no mesh objects")
    if scene.camera is None:
        raise RuntimeError("Scene check failed: no camera is available")
    if scene.render.resolution_x < 1 or scene.render.resolution_y < 1:
        raise RuntimeError("Scene check failed: render resolution is invalid")
    for obj in meshes:
        if any(not math.isfinite(value) for value in obj.dimensions):
            raise RuntimeError(f"Scene check failed: {obj.name!r} has non-finite dimensions")
    print(f"SCENE_OK meshes={len(meshes)} camera={scene.camera.name!r} resolution={scene.render.resolution_x}x{scene.render.resolution_y}", flush=True)


def configure_and_render(args: argparse.Namespace, meshes: list[bpy.types.Object]) -> None:
    scene = bpy.context.scene
    scene.render.engine = args.engine
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    scene.render.resolution_percentage = 100
    scene.render.fps = args.fps
    scene.frame_start = 1
    scene.frame_end = args.frames
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
    scene.render.ffmpeg.ffmpeg_preset = "GOOD"
    scene.render.filepath = str(args.output)
    scene.render.use_file_extension = True
    if args.engine == "CYCLES":
        scene.cycles.samples = args.samples
    if args.turntable:
        for obj in meshes:
            obj.rotation_mode = "XYZ"
            obj.rotation_euler.z -= math.tau
            obj.keyframe_insert(data_path="rotation_euler", index=2, frame=1)
            obj.rotation_euler.z += math.tau
            obj.keyframe_insert(data_path="rotation_euler", index=2, frame=args.frames)
    scene.frame_set(1)
    scene.render.image_settings.color_mode = "RGB"
    scene.view_settings.view_transform = "AgX"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.render.render(animation=True)
    if not args.output.is_file() or args.output.stat().st_size == 0:
        raise RuntimeError(f"Render finished without a non-empty MP4 at {args.output}")
    print(f"EXPORT_OK file={args.output} bytes={args.output.stat().st_size}", flush=True)


def main() -> None:
    args = parse_args()
    if args.input.suffix.lower() != ".blend":
        bpy.ops.wm.read_factory_settings(use_empty=True)
    import_asset(args.input)
    meshes = scene_meshes()
    if not meshes:
        raise RuntimeError("Import completed but produced no mesh objects")
    center, radius = bounds(meshes)
    make_camera_and_lights(center, radius)
    validate_scene(meshes)
    configure_and_render(args, meshes)


if __name__ == "__main__":
    main()
