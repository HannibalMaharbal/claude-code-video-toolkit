"""Shared Blender scene operations used by UI operators and scripts."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

import bpy
from mathutils import Vector


SUPPORTED = {".blend", ".fbx", ".glb", ".gltf", ".obj", ".stl", ".zip"}
MAX_ARCHIVE_GLB_BYTES = 1024 * 1024 * 1024


def _import_gltf(filepath: str) -> None:
    bpy.ops.import_scene.gltf(filepath=filepath)


def _import_meshy_zip(filepath: str) -> None:
    try:
        archive = zipfile.ZipFile(filepath)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"Ungültiges Meshy-ZIP-Archiv: {exc}") from exc
    with archive:
        members = [
            item for item in archive.infolist()
            if not item.is_dir() and Path(item.filename).suffix.lower() == ".glb"
        ]
        if len(members) != 1:
            raise ValueError(
                f"Meshy-ZIP muss genau eine GLB-Datei enthalten; gefunden: {len(members)}"
            )
        member = members[0]
        if member.flag_bits & 0x1:
            raise ValueError("Verschlüsselte Meshy-ZIP-Archive werden nicht unterstützt")
        if member.file_size > MAX_ARCHIVE_GLB_BYTES:
            raise ValueError("GLB im ZIP überschreitet die erlaubte Größe von 1 GiB")
        if member.compress_size and member.file_size / member.compress_size > 1000:
            raise ValueError("Verdächtiges Kompressionsverhältnis im Meshy-ZIP")

        # Write only to a generated temporary filename, never to an archive path.
        with tempfile.TemporaryDirectory(prefix="hannibal-meshy-") as temp_dir:
            extracted = Path(temp_dir) / "asset.glb"
            total = 0
            with archive.open(member) as source, extracted.open("wb") as target:
                while block := source.read(1024 * 1024):
                    total += len(block)
                    if total > MAX_ARCHIVE_GLB_BYTES:
                        raise ValueError("Entpackte GLB überschreitet die erlaubte Größe von 1 GiB")
                    target.write(block)
            _import_gltf(str(extracted))


def import_asset(filepath: str) -> list[bpy.types.Object]:
    path = Path(bpy.path.abspath(filepath)).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"Datei nicht gefunden: {path}")
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED:
        raise ValueError(f"Nicht unterstütztes Format: {suffix}")
    before = {obj.as_pointer() for obj in bpy.context.scene.objects}
    if suffix == ".blend":
        with bpy.data.libraries.load(str(path), link=False) as (source, target):
            target.objects = list(source.objects)
        for obj in target.objects:
            if obj is not None:
                bpy.context.scene.collection.objects.link(obj)
    elif suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(path))
    elif suffix in {".glb", ".gltf"}:
        _import_gltf(str(path))
    elif suffix == ".zip":
        _import_meshy_zip(str(path))
    elif suffix == ".obj":
        bpy.ops.wm.obj_import(filepath=str(path))
    elif suffix == ".stl":
        bpy.ops.wm.stl_import(filepath=str(path))
    return [obj for obj in bpy.context.scene.objects if obj.as_pointer() not in before]


def validate_scene(
    scene: bpy.types.Scene,
    width: int | None = None,
    height: int | None = None,
) -> list[str]:
    meshes = [obj for obj in scene.objects if obj.type == "MESH"]
    if not meshes:
        raise ValueError("Keine Mesh-Objekte in der Szene")
    if scene.camera is None:
        raise ValueError("Keine aktive Kamera in der Szene")
    resolution_x = scene.render.resolution_x if width is None else width
    resolution_y = scene.render.resolution_y if height is None else height
    if resolution_x < 16 or resolution_y < 16:
        raise ValueError("Renderauflösung muss mindestens 16×16 Pixel betragen")
    if scene.frame_end < scene.frame_start:
        raise ValueError("Frame-Ende liegt vor Frame-Start")
    return [
        f"{len(meshes)} Mesh(es)",
        f"Kamera: {scene.camera.name}",
        f"{resolution_x}×{resolution_y}",
    ]


def audit_mesh_geometry(scene: bpy.types.Scene, recalculate_normals: bool = True) -> dict:
    """Performs deep mechanical and geometric audit of all scene meshes.
    
    Verifies manifoldness (watertightness for CAD / 3D printing), loose vertices,
    and bounding dimensions. Optionally normalizes face normals to point outside.
    """
    import bmesh

    meshes = [obj for obj in scene.objects if obj.type == "MESH"]
    if not meshes:
        return {"status": "empty", "total_meshes": 0, "is_watertight_for_cad": False}

    total_vertices = 0
    total_edges = 0
    total_faces = 0
    non_manifold_count = 0
    loose_vertices_count = 0
    mesh_details = []

    for obj in meshes:
        mesh = obj.data
        bm = bmesh.new()
        bm.from_mesh(mesh)

        nm_edges = sum(1 for e in bm.edges if not e.is_manifold)
        loose_v = sum(1 for v in bm.verts if not v.link_edges)

        if recalculate_normals and len(bm.faces) > 0:
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            bm.to_mesh(mesh)
            mesh.update()

        dims = obj.dimensions
        mesh_details.append({
            "name": obj.name,
            "vertices": len(bm.verts),
            "edges": len(bm.edges),
            "faces": len(bm.faces),
            "non_manifold_edges": nm_edges,
            "loose_vertices": loose_v,
            "dimensions_meters": [round(dims.x, 4), round(dims.y, 4), round(dims.z, 4)],
            "is_watertight": nm_edges == 0,
        })
        total_vertices += len(bm.verts)
        total_edges += len(bm.edges)
        total_faces += len(bm.faces)
        non_manifold_count += nm_edges
        loose_vertices_count += loose_v
        bm.free()

    is_watertight = non_manifold_count == 0
    return {
        "status": "ok",
        "total_meshes": len(meshes),
        "total_vertices": total_vertices,
        "total_edges": total_edges,
        "total_faces": total_faces,
        "non_manifold_edges": non_manifold_count,
        "loose_vertices": loose_vertices_count,
        "is_watertight_for_cad": is_watertight,
        "meshes": mesh_details,
    }


def export_clean_geometry(filepath: str, format_type: str = "glb") -> str:
    """Exports clean geometry directly to GLB (Web/AR) or STL (Fusion 360 / CAD / 3D Druck)."""
    dest = Path(filepath).expanduser().resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    fmt = format_type.lower()
    if fmt == "stl":
        bpy.ops.wm.stl_export(filepath=str(dest))
    elif fmt in {"glb", "gltf"}:
        bpy.ops.export_scene.gltf(filepath=str(dest), export_format="GLB")
    else:
        raise ValueError(f"Nicht unterstütztes Export-Format: {format_type}")
    return str(dest)


def prepare_scene(scene: bpy.types.Scene) -> None:
    meshes = [obj for obj in scene.objects if obj.type == "MESH"]
    if not meshes:
        return
    points = [obj.matrix_world @ Vector(corner) for obj in meshes for corner in obj.bound_box]
    low = Vector(tuple(min(point[i] for point in points) for i in range(3)))
    high = Vector(tuple(max(point[i] for point in points) for i in range(3)))
    center = (low + high) * 0.5
    radius = max((high - low).length * 0.5, 0.5)
    camera = scene.camera
    if camera is None:
        camera_data = bpy.data.cameras.new("Toolkit Camera")
        camera = bpy.data.objects.new("Toolkit Camera", camera_data)
        scene.collection.objects.link(camera)
        scene.camera = camera
    camera.location = center + Vector((radius * 3.2, -radius * 3.2, radius * 2.2))
    camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.clip_end = max(radius * 100, 1000)
    for name, offset, energy, size in (
        ("Toolkit Key", (1.5, -2, 2.5), 1400, 2.5),
        ("Toolkit Fill", (-2, -1, 0.7), 800, 3.0),
        ("Toolkit Rim", (0.5, 2, 1.8), 1800, 2.0),
    ):
        light = scene.objects.get(name)
        if light is None or light.type != "LIGHT":
            light_data = bpy.data.lights.new(name, "AREA")
            light = bpy.data.objects.new(name, light_data)
            scene.collection.objects.link(light)
        elif light.data.type != "AREA":
            light.data = bpy.data.lights.new(f"{name} Area", "AREA")
        light.data.energy = energy
        light.data.shape = "DISK"
        light.data.size = max(radius * size, 0.1)
        light.location = center + Vector(offset) * radius
        light.rotation_euler = (center - light.location).to_track_quat("-Z", "Y").to_euler()


def unique_output_path(directory: str, stem: str, suffix: str) -> str:
    root = Path(directory).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = root / f"{stem}-{stamp}{suffix}"
    counter = 1
    while candidate.exists():
        candidate = root / f"{stem}-{stamp}-{counter:02d}{suffix}"
        counter += 1
    return str(candidate)


def configure_frames(scene: bpy.types.Scene, settings) -> str:
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = settings.width
    scene.render.resolution_y = settings.height
    scene.render.resolution_percentage = 100
    scene.render.fps = settings.fps
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.frame_start = 1
    scene.frame_end = settings.frames
    directory = bpy.path.abspath(settings.output_dir)
    frame_dir = unique_output_path(directory, "blender-frames", ".frames")
    Path(frame_dir).mkdir(parents=True)
    scene.render.filepath = str(Path(frame_dir) / "frame_")
    scene.render.use_file_extension = True
    return frame_dir


def export_mp4(
    frame_dir: str,
    directory: str,
    settings,
    start_frame: int = 1,
    destination: str | None = None,
) -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg ist nicht im PATH; MP4-Export ist nicht verfügbar")
    source_dir = Path(frame_dir).expanduser().resolve()
    frames = sorted(source_dir.glob("frame_*.png"))
    expected = [source_dir / f"frame_{frame:04d}.png" for frame in range(start_frame, start_frame + settings.frames)]
    missing = [frame.name for frame in expected if not frame.is_file()]
    if missing:
        preview = ", ".join(missing[:5])
        suffix = " …" if len(missing) > 5 else ""
        raise RuntimeError(f"Fehlende Render-Frames ({len(missing)}): {preview}{suffix}")
    if destination:
        output_path = Path(destination).expanduser().resolve()
        if output_path.suffix.lower() != ".mp4":
            raise ValueError("MP4 output path must end in .mp4")
        if output_path.exists():
            raise FileExistsError(f"Refusing to overwrite existing clip: {output_path}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output = str(output_path)
    else:
        output = unique_output_path(directory, "blender-clip", ".mp4")
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-n",
        "-framerate", str(settings.fps), "-start_number", str(start_frame),
        "-i", str(source_dir / "frame_%04d.png"), "-frames:v", str(settings.frames),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", output,
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(f"ffmpeg-Export fehlgeschlagen: {result.stderr.strip()}")
    if not Path(output).is_file() or Path(output).stat().st_size == 0:
        raise RuntimeError(f"ffmpeg lieferte keine MP4-Datei: {output}")
    return output


def export_scene(directory: str) -> str:
    path = unique_output_path(bpy.path.abspath(directory), "scene", ".blend")
    bpy.ops.wm.save_as_mainfile(filepath=path, check_existing=False)
    return path
