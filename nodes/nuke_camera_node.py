"""
LoadNukeCamera Node - Load a camera exported from Nuke as a .chan file.
"""

import logging
from pathlib import Path

import numpy as np
import torch
from scipy.spatial.transform import Rotation as R

from comfy_api.latest import io

import folder_paths

log = logging.getLogger("motioncapture")


class LoadNukeCamera(io.ComfyNode):
    """
    Read a Nuke Camera "export chan file" (frame tx ty tz rx ry rz vfov per line)
    into a CAMERA_TRACK for GVHMR Inference. Line 1 is the first video frame.
    """

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="LoadNukeCamera",
            display_name="Load Nuke Camera (.chan)",
            category="MotionCapture/GVHMR",
            inputs=[
                # A STRING, not a Combo: comfy_env freezes INPUT_TYPES at startup,
                # so a file list would reject anything uploaded afterwards.
                io.String.Input("chan_file", default="", multiline=False,
                                tooltip="Name of a .chan file in the ComfyUI input folder. Use the upload button to add one (Nuke Camera > File tab > export chan file)."),
                io.Combo.Input("rot_order", options=["ZXY", "XYZ", "XZY", "YXZ", "YZX", "ZYX"], default="ZXY",
                               tooltip="The Camera's rot_order knob"),
                io.Float.Input("haperture", default=36.0, min=0.1, max=1000.0, step=0.001,
                               tooltip="The Camera's haperture knob (mm). Nuke fits it to the plate width."),
                io.Float.Input("vaperture", default=24.0, min=0.1, max=1000.0, step=0.001,
                               tooltip="The Camera's vaperture knob (mm). Used to turn the .chan field of view back into focal length."),
            ],
            outputs=[
                io.Custom("CAMERA_TRACK").Output(display_name="camera_track"),
            ],
        )

    @staticmethod
    def _resolve(chan_file):
        input_dir = Path(folder_paths.get_input_directory()).resolve()
        path = (input_dir / chan_file).resolve()
        if path.parent != input_dir or path.suffix.lower() != ".chan" or not path.is_file():
            raise FileNotFoundError(f"Chan file not found in the input folder: {chan_file}")
        return path

    @classmethod
    def execute(cls, chan_file, rot_order="ZXY", haperture=36.0, vaperture=24.0):
        path = cls._resolve(chan_file)
        chan = np.loadtxt(str(path), ndmin=2)
        if chan.shape[1] != 8:
            raise ValueError(f"Expected 8 columns (frame tx ty tz rx ry rz vfov) in {path}, got {chan.shape[1]}. "
                             "Export with the Camera node's 'export chan file' button.")

        position = chan[:, 1:4]
        # Nuke rot_order ZXY applies Z first, which is scipy's extrinsic "zxy"
        axis = {"X": 4, "Y": 5, "Z": 6}
        angles = chan[:, [axis[a] for a in rot_order]]
        R_cam2world_gl = R.from_euler(rot_order.lower(), angles, degrees=True).as_matrix()
        # Nuke cameras look down -Z with +Y up; GVHMR uses OpenCV (+Z forward, +Y down)
        R_w2c = np.transpose(R_cam2world_gl @ np.diag([1.0, -1.0, -1.0]), (0, 2, 1))
        t_w2c = -np.einsum('fij,fj->fi', R_w2c, position)
        focal_mm = (vaperture / 2) / np.tan(np.radians(chan[:, 7]) / 2)

        log.info("[LoadNukeCamera] %d frames from %s, focal %.3f-%.3fmm", len(chan), path, focal_mm.min(), focal_mm.max())
        return io.NodeOutput({
            "R_w2c": torch.from_numpy(R_w2c).float(),
            "t_w2c": torch.from_numpy(t_w2c).float(),
            "focal_mm": torch.from_numpy(focal_mm).float(),
            "haperture": haperture,
        })


NODE_CLASS_MAPPINGS = {
    "LoadNukeCamera": LoadNukeCamera,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LoadNukeCamera": "Load Nuke Camera (.chan)",
}
