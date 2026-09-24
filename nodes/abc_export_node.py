"""
GLBToAlembic Node - Convert an animated GLB from SMPL to GLB Animation into Alembic using bpy.
"""

import json
import logging
import struct
from pathlib import Path

import numpy as np
import folder_paths

from comfy_api.latest import io

log = logging.getLogger("motioncapture")


def _read_glb_json(path):
    with open(path, "rb") as f:
        magic, _, _ = struct.unpack("<4sII", f.read(12))
        if magic != b"glTF":
            raise ValueError(f"Not a GLB file: {path}")
        length, _ = struct.unpack("<II", f.read(8))
        return json.loads(f.read(length))


class GLBToAlembic(io.ComfyNode):
    """
    Bake the skinned body and camera of an SMPL to GLB Animation file into Alembic.
    fps and frame range come from the GLB's keys.
    """

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="GLBToAlembic",
            display_name="GLB to Alembic",
            category="MotionCapture/GVHMR",
            is_output_node=True,
            inputs=[
                io.String.Input("glb_path", default="", multiline=False,
                                tooltip="GLB from SMPL to GLB Animation"),
                io.String.Input("output_path", default="", multiline=False, optional=True,
                                tooltip="Where to write the .abc. Relative paths are inside the ComfyUI output folder. Empty = next to the GLB"),
                io.Custom("CAMERA_TRACK").Input("camera_track", optional=True,
                    tooltip="The camera_track given to SMPL to GLB Animation. Writes its haperture and per-frame focal length so the camera comes back into Nuke unchanged. Without it the camera gets a 36mm haperture with the GLB's field of view."),
            ],
            outputs=[
                io.String.Output(display_name="abc_path"),
            ],
        )

    @classmethod
    def execute(cls, glb_path, output_path="", camera_track=None):
        import bpy

        glb_file = Path(glb_path.strip())
        if not glb_file.exists():
            raise FileNotFoundError(f"GLB not found: {glb_file}")
        if output_path.strip():
            abc_file = Path(folder_paths.get_output_directory()) / output_path.strip()  # absolute paths replace output dir
            if abc_file.suffix.lower() != ".abc":
                abc_file = abc_file.with_name(abc_file.name + ".abc")
            abc_file.parent.mkdir(parents=True, exist_ok=True)
        else:
            abc_file = glb_file.with_suffix(".abc")

        gltf = _read_glb_json(glb_file)
        times = gltf["accessors"][gltf["animations"][0]["samplers"][0]["input"]]
        num_frames = times["count"]
        fps = round((num_frames - 1) / (times["max"][0] - times["min"][0])) if num_frames > 1 else 30
        start = round(times["min"][0] * fps)
        end = start + num_frames - 1

        bpy.ops.wm.read_homefile(use_empty=True)
        scene = bpy.context.scene
        # the glTF importer turns key times into frames with the scene fps
        scene.render.fps = fps
        scene.render.fps_base = 1.0
        bpy.ops.import_scene.gltf(filepath=str(glb_file))
        scene.frame_start, scene.frame_end = start, end

        bpy.ops.object.select_all(action='DESELECT')
        bpy.data.objects["SMPLMesh"].select_set(True)
        cam_obj = bpy.data.objects.get("Camera")
        if cam_obj is not None:
            # Alembic stores sensor width/height as the apertures, and the importer
            # leaves Blender's 36x24 default, so size the sensor to the plate aspect
            cam_gltf = gltf["cameras"][0]["perspective"]
            cam = cam_obj.data
            cam.lens_unit = 'MILLIMETERS'
            cam.sensor_fit = 'HORIZONTAL'
            cam.sensor_width = camera_track["haperture"] if camera_track is not None else 36.0
            cam.sensor_height = cam.sensor_width / cam_gltf["aspectRatio"]
            if camera_track is not None:
                if len(camera_track["focal_mm"]) < num_frames:
                    raise ValueError(f"camera_track has {len(camera_track['focal_mm'])} frames but the GLB has {num_frames}")
                for i, focal in enumerate(camera_track["focal_mm"][:num_frames].tolist()):
                    cam.lens = focal
                    cam.keyframe_insert("lens", frame=start + i)
            else:
                cam.lens = (cam.sensor_height / 2) / np.tan(cam_gltf["yfov"] / 2)
            cam_obj.select_set(True)

        bpy.ops.wm.alembic_export(filepath=str(abc_file), start=start, end=end,
                                  selected=True, flatten=True, uvs=False)

        log.info("[GLBToAlembic] Wrote %s -- frames %d-%d at %d fps%s", abc_file, start, end, fps,
                 "" if cam_obj is not None else ", no camera")
        return io.NodeOutput(str(abc_file), ui={})


NODE_CLASS_MAPPINGS = {
    "GLBToAlembic": GLBToAlembic,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GLBToAlembic": "GLB to Alembic",
}
