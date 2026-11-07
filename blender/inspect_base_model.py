"""
Blender Model Inspection Script
================================
Reads a .blend file and prints a comprehensive report about all mesh objects,
shape keys, vertex groups, modifiers, and mesh dimensions.

Usage (inside Blender background mode):
    /Applications/Blender.app/Contents/MacOS/Blender \
        --background /path/to/file.blend \
        --python blender/inspect_base_model.py \
        -- --output /path/to/report.json

Author: Body Reconstruction Engine
Version: 0.1.0
"""

import sys
import os
import argparse
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("inspect")


def parse_args():
    if "--" in sys.argv:
        argv = sys.argv[sys.argv.index("--") + 1:]
    else:
        argv = []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=None, help="Path to save JSON report")
    return parser.parse_args(argv)


def main():
    args = parse_args()
    import bpy
    import mathutils

    report = {
        "blender_version": bpy.app.version_string,
        "objects": [],
    }

    for obj in bpy.data.objects:
        obj_data = {
            "name": obj.name,
            "type": obj.type,
            "location_m": list(obj.location),
            "scale": list(obj.scale),
            "rotation_euler": list(obj.rotation_euler),
        }

        if obj.type == "MESH":
            mesh = obj.data
            obj_data["vertex_count"] = len(mesh.vertices)
            obj_data["face_count"] = len(mesh.polygons)
            obj_data["edge_count"] = len(mesh.edges)

            # Bounding box in world space (cm)
            bbox = [obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box]
            min_x = min(v.x for v in bbox) * 100
            max_x = max(v.x for v in bbox) * 100
            min_y = min(v.y for v in bbox) * 100
            max_y = max(v.y for v in bbox) * 100
            min_z = min(v.z for v in bbox) * 100
            max_z = max(v.z for v in bbox) * 100

            obj_data["bbox_cm"] = {
                "x": [round(min_x, 2), round(max_x, 2)],
                "y": [round(min_y, 2), round(max_y, 2)],
                "z": [round(min_z, 2), round(max_z, 2)],
                "width": round(max_x - min_x, 2),
                "depth": round(max_y - min_y, 2),
                "height": round(max_z - min_z, 2),
            }

            # Shape keys
            if mesh.shape_keys:
                obj_data["shape_keys"] = [
                    {
                        "name": k.name,
                        "value": round(k.value, 4),
                        "min": round(k.slider_min, 4),
                        "max": round(k.slider_max, 4),
                    }
                    for k in mesh.shape_keys.key_blocks
                ]
            else:
                obj_data["shape_keys"] = []

            # Modifiers
            obj_data["modifiers"] = [
                {"name": m.name, "type": m.type}
                for m in obj.modifiers
            ]

            # Vertex groups
            obj_data["vertex_groups"] = [vg.name for vg in obj.vertex_groups]

            # Custom properties
            obj_data["custom_props"] = list(obj.keys())
            obj_data["mesh_custom_props"] = list(mesh.keys())

        report["objects"].append(obj_data)

    report_str = json.dumps(report, indent=2)
    logger.info(report_str)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report_str)
        logger.info(f"\nReport saved to: {args.output}")


if __name__ == "__main__":
    main()

