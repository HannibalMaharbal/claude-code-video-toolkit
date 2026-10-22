"""Hannibal Blender Toolkit: compact UI and CLI-shared scene actions."""

bl_info = {
    "name": "Hannibal Blender Toolkit",
    "author": "Hannibal Workspace",
    "version": (0, 1, 0),
    "blender": (5, 2, 0),
    "location": "View3D > Sidebar > Toolkit",
    "description": "Import, validate, render, and export video-toolkit clips",
    "category": "3D View",
}

import bpy
from pathlib import Path

from . import pipeline

_DEFAULT_OUTPUT = str(Path(__file__).resolve().parents[3] / "projects" / "blender-prototype")


class HannibalToolkitSettings(bpy.types.PropertyGroup):
    asset_path: bpy.props.StringProperty(name="Asset", subtype="FILE_PATH")
    output_dir: bpy.props.StringProperty(
        name="Ausgabeordner", subtype="DIR_PATH",
        default=_DEFAULT_OUTPUT,
    )
    width: bpy.props.IntProperty(name="Breite", default=1280, min=16)
    height: bpy.props.IntProperty(name="Höhe", default=720, min=16)
    fps: bpy.props.IntProperty(name="FPS", default=24, min=1, max=120)
    frames: bpy.props.IntProperty(name="Frames", default=72, min=1)
    last_render_dir: bpy.props.StringProperty(name="Letzter Render", subtype="DIR_PATH", options={"HIDDEN"})
    last_export_path: bpy.props.StringProperty(name="Letzter MP4-Export", subtype="FILE_PATH", options={"HIDDEN"})
    last_render_fps: bpy.props.IntProperty(default=24, min=1, options={"HIDDEN"})
    last_render_frames: bpy.props.IntProperty(default=72, min=1, options={"HIDDEN"})
    last_render_start: bpy.props.IntProperty(default=1, min=1, options={"HIDDEN"})


class HANNIBAL_OT_import_asset(bpy.types.Operator):
    bl_idname = "hannibal_toolkit.import_asset"
    bl_label = "Asset importieren"
    bl_description = "Importiert ein unterstütztes 3D-Asset in die Szene"
    bl_options = {"REGISTER", "UNDO"}

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    filter_glob: bpy.props.StringProperty(
        default="*.blend;*.fbx;*.glb;*.gltf;*.obj;*.stl;*.zip",
        options={"HIDDEN"},
    )

    def invoke(self, context, _event):
        settings = context.scene.hannibal_toolkit
        if settings.asset_path:
            self.filepath = bpy.path.abspath(settings.asset_path)
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        try:
            imported = pipeline.import_asset(self.filepath)
            pipeline.prepare_scene(context.scene)
            context.scene.hannibal_toolkit.asset_path = self.filepath
            self.report({"INFO"}, f"Importiert: {len(imported)} Objekte")
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class HANNIBAL_OT_validate_scene(bpy.types.Operator):
    bl_idname = "hannibal_toolkit.validate_scene"
    bl_label = "Szene prüfen"
    bl_description = "Prüft Meshes, Kamera, Bildgröße und Renderpfad"

    def execute(self, context):
        try:
            settings = context.scene.hannibal_toolkit
            messages = pipeline.validate_scene(context.scene, settings.width, settings.height)
            self.report({"INFO"}, "; ".join(messages))
            return {"FINISHED"}
        except ValueError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class HANNIBAL_OT_render_clip(bpy.types.Operator):
    bl_idname = "hannibal_toolkit.render_clip"
    bl_label = "Rendern"
    bl_description = "Rendert die Animation als H.264-MP4"

    def execute(self, context):
        scene = context.scene
        settings = scene.hannibal_toolkit
        try:
            messages = pipeline.validate_scene(scene, settings.width, settings.height)
            path = pipeline.configure_frames(scene, settings)
            bpy.ops.render.render(animation=True)
            settings.last_render_dir = path
            settings.last_render_fps = settings.fps
            settings.last_render_frames = settings.frames
            settings.last_render_start = scene.frame_start
            self.report({"INFO"}, f"Frames gerendert: {path}; " + "; ".join(messages))
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class HANNIBAL_OT_export_mp4(bpy.types.Operator):
    bl_idname = "hannibal_toolkit.export_mp4"
    bl_label = "MP4 exportieren"
    bl_description = "Setzt die gerenderten Einzelbilder mit FFmpeg zu einem MP4-Clip zusammen"

    def execute(self, context):
        settings = context.scene.hannibal_toolkit
        try:
            if not settings.last_render_dir:
                raise ValueError("Bitte zuerst die Szene rendern")
            render_settings = type("ExportSettings", (), {
                "fps": settings.last_render_fps,
                "frames": settings.last_render_frames,
            })()
            path = pipeline.export_mp4(
                settings.last_render_dir, settings.output_dir, render_settings, settings.last_render_start
            )
            settings.last_export_path = path
            self.report({"INFO"}, f"MP4 exportiert: {path}")
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class HANNIBAL_OT_save_scene(bpy.types.Operator):
    bl_idname = "hannibal_toolkit.save_scene"
    bl_label = "Szene als .blend sichern"
    bl_description = "Speichert eine neue .blend-Kopie im Ausgabeordner, ohne vorhandene Dateien zu ersetzen"
    bl_options = {"REGISTER"}

    def execute(self, context):
        settings = context.scene.hannibal_toolkit
        try:
            path = pipeline.export_scene(settings.output_dir)
            self.report({"INFO"}, f"Szene gesichert: {path}")
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class HANNIBAL_PT_toolkit(bpy.types.Panel):
    bl_label = "Video Toolkit"
    bl_idname = "HANNIBAL_PT_video_toolkit"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Toolkit"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.hannibal_toolkit
        layout.label(text="3D-Asset → Video-Clip", icon="WORKSPACE")
        layout.prop(settings, "asset_path")
        layout.operator("hannibal_toolkit.import_asset", icon="IMPORT", text="Asset laden (GLB / ZIP / 3D)")
        layout.separator()
        layout.operator("hannibal_toolkit.validate_scene", icon="CHECKMARK", text="Szene prüfen")
        layout.separator()
        layout.prop(settings, "output_dir")
        row = layout.row(align=True)
        row.prop(settings, "width")
        row.prop(settings, "height")
        row.prop(settings, "fps")
        layout.prop(settings, "frames")
        layout.operator("hannibal_toolkit.render_clip", icon="RENDER_ANIMATION", text="Frames rendern")
        layout.operator("hannibal_toolkit.export_mp4", icon="FILE_MOVIE", text="MP4 exportieren")
        layout.operator("hannibal_toolkit.save_scene", icon="FILE_BLEND", text="Szene als .blend sichern")
        if settings.last_export_path:
            layout.label(text=bpy.path.abspath(settings.last_export_path), icon="FILE_MOVIE")


CLASSES = (
    HannibalToolkitSettings,
    HANNIBAL_OT_import_asset,
    HANNIBAL_OT_validate_scene,
    HANNIBAL_OT_render_clip,
    HANNIBAL_OT_export_mp4,
    HANNIBAL_OT_save_scene,
    HANNIBAL_PT_toolkit,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.hannibal_toolkit = bpy.props.PointerProperty(type=HannibalToolkitSettings)


def unregister():
    del bpy.types.Scene.hannibal_toolkit
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
