"""Create and export a standalone cube to verify background Blender + GLB support.

Run with:
  "$BLENDER_EXECUTABLE" --background --python blender/blender_smoke.py -- \
    --output output/blender_smoke_test.glb
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

import bpy


def output_path_from_args() -> Path:
    blender_args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="output/blender_smoke_test.glb")
    args = parser.parse_args(blender_args)
    return Path(args.output).expanduser().resolve()


def main() -> None:
    output_path = output_path_from_args()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0.0, 0.0, 0.0))
    cube = bpy.context.object
    cube.name = "ModelMeSmokeTestCube"
    bpy.ops.export_scene.gltf(filepath=str(output_path), export_format="GLB")

    data = output_path.read_bytes()
    if len(data) < 20:
        raise RuntimeError(f"GLB is unexpectedly small: {len(data)} bytes")
    magic, _version, declared_length = struct.unpack_from("<4sII", data)
    if magic != b"glTF" or declared_length != len(data):
        raise RuntimeError("Exported file does not have a valid GLB header/length")

    print(json.dumps({
        "status": "ok",
        "blender_version": bpy.app.version_string,
        "bpy_accessible": True,
        "object": cube.name,
        "glb_path": str(output_path),
        "glb_bytes": len(data),
        "glb_magic": magic.decode("ascii"),
    }))


if __name__ == "__main__":
    main()
