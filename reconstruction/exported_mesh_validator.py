"""Independent measurements of a GLB re-imported after export.

This module intentionally does not use CrossSectionAnalyzer or
MeshMeasurementCalculator. It intersects triangles from the imported GLB with
anatomical horizontal planes and measures the resulting connected contours.
Run inside Blender so the GLB is interpreted using Blender's glTF importer.
"""

from __future__ import annotations

import math
from collections import defaultdict, deque
from typing import Optional


def _slice_components(objects, z_m: float):
    """Return connected slice contours as lists of 2D (x,y) segments."""
    segments = []
    eps = 1e-8
    for obj in objects:
        if obj.type != "MESH":
            continue
        mesh = obj.data
        matrix = obj.matrix_world
        coords = [matrix @ v.co for v in mesh.vertices]
        for face in mesh.polygons:
            ids = list(face.vertices)
            if len(ids) < 3:
                continue
            # GLB faces are triangulated at import/export boundaries, but fan
            # triangulation here also supports any polygon that survives import.
            for index in range(1, len(ids) - 1):
                tri = [coords[ids[0]], coords[ids[index]], coords[ids[index + 1]]]
                hits = []
                for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
                    da, db = a.z - z_m, b.z - z_m
                    if abs(da) <= eps and abs(db) <= eps:
                        continue
                    if (da <= eps and db > eps) or (db <= eps and da > eps):
                        t = da / (da - db)
                        point = (round(a.x + (b.x - a.x) * t, 6),
                                 round(a.y + (b.y - a.y) * t, 6))
                        if point not in hits:
                            hits.append(point)
                if len(hits) == 2 and hits[0] != hits[1]:
                    segments.append((hits[0], hits[1]))

    adjacency = defaultdict(list)
    for index, (a, b) in enumerate(segments):
        adjacency[a].append((index, b))
        adjacency[b].append((index, a))
    visited = set()
    components = []
    for start in range(len(segments)):
        if start in visited:
            continue
        todo = [start]
        component_segments = []
        points = set()
        while todo:
            current = todo.pop()
            if current in visited:
                continue
            visited.add(current)
            a, b = segments[current]
            points.update((a, b))
            component_segments.append((a, b))
            for point in (a, b):
                todo.extend(i for i, _ in adjacency[point] if i not in visited)
        if len(points) >= 3:
            components.append((component_segments, points))
    return components


def _section_measure(objects, z_m: Optional[float], center_x_m: Optional[float] = None):
    if z_m is None:
        return None
    components = _slice_components(objects, z_m)
    candidates = []
    for segments, points in components:
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        cx = (min(xs) + max(xs)) / 2
        perimeter = sum(math.dist(a, b) for a, b in segments) * 100
        if center_x_m is not None and abs(cx - center_x_m) > 0.16:
            continue
        if center_x_m is None and abs(cx) > 0.14:
            continue
        candidates.append({
            "circumference_cm": perimeter,
            "width_cm": (max(xs) - min(xs)) * 100,
            "depth_cm": (max(ys) - min(ys)) * 100,
            "center_x_m": cx,
        })
    if not candidates:
        return None
    return max(candidates, key=lambda item: item["circumference_cm"])


def _target(parsed, key: str):
    entry = parsed.get_entry(key)
    if entry is None:
        return None, "missing"
    if entry.value is not None:
        return entry.value, entry.method or "scalar field metadata unavailable"
    values = [side.value for side in entry.sides.values() if side.value is not None]
    if not values:
        return None, "null or unavailable"
    methods = sorted({side.method for side in entry.sides.values() if side.value is not None and side.method})
    return sum(values) / len(values), "arithmetic mean of populated bilateral values" + (f"; source method(s): {', '.join(methods)}" if methods else "")


def _record(target, generated, method, tolerance_cm=1.0, target_method=None):
    if target is None or generated is None:
        return {
            "target_cm": target,
            "generated_cm": generated,
            "absolute_error_cm": None,
            "percentage_error": None,
            "pass": False,
            "status": "unsupported" if generated is None else "target_unavailable",
            "measurement_method": method,
            "target_method": target_method,
        }
    error = abs(generated - target)
    return {
        "target_cm": round(target, 3),
        "generated_cm": round(generated, 3),
        "absolute_error_cm": round(error, 3),
        "percentage_error": round(error / abs(target) * 100, 3) if target else None,
        "pass": error <= tolerance_cm,
        "status": "pass" if error <= tolerance_cm else "fail",
        "measurement_method": method,
        "target_method": target_method,
        "tolerance_cm": tolerance_cm,
    }


def validate_exported_glb(glb_path, parsed, plan):
    """Import and measure the exported GLB; return JSON-serializable report."""
    import bpy

    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(glb_path))
    imported = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    if not imported:
        raise RuntimeError("Re-imported GLB contains no mesh objects")

    world_vertices = [o.matrix_world @ v.co for o in imported for v in o.data.vertices]
    if not world_vertices:
        raise RuntimeError("Re-imported GLB mesh has no vertices")
    height = (max(v.z for v in world_vertices) - min(v.z for v in world_vertices)) * 100
    dimensions = {
        "width_cm": round((max(v.x for v in world_vertices) - min(v.x for v in world_vertices)) * 100, 3),
        "depth_cm": round((max(v.y for v in world_vertices) - min(v.y for v in world_vertices)) * 100, 3),
        "height_cm": round(height, 3),
    }
    arm_span = (max(v.x for v in world_vertices) - min(v.x for v in world_vertices)) * 100

    planes = {
        "chest": plan.landmark_heights.chest,
        "waist": plan.landmark_heights.waist,
        "hip": plan.landmark_heights.hip,
    }
    sections = {name: _section_measure(imported, z) for name, z in planes.items()}
    results = {}

    shoulder_target, shoulder_source = _target(parsed, "shoulder_breadth_cm")
    shoulder_z = plan.landmark_heights.shoulder
    shoulder_band = [v for v in world_vertices if abs(v.z - shoulder_z) <= 0.03]
    shoulder_breadth = ((max(v.x for v in shoulder_band) - min(v.x for v in shoulder_band)) * 100
                        if shoulder_band else None)
    results["shoulder_breadth_cm"] = _record(
        shoulder_target, shoulder_breadth,
        "GLB vertex lateral extent in a +/-3 cm shoulder-height band",
        target_method=shoulder_source,
    )

    for key, generated_key, method, section, component in (
        ("chest_circumference_cm", "circumference_cm", "GLB triangle-plane intersection perimeter", "chest", None),
        ("waist_circumference_cm", "circumference_cm", "GLB triangle-plane intersection perimeter", "waist", None),
        ("hip_circumference_cm", "circumference_cm", "GLB triangle-plane intersection perimeter", "hip", None),
        ("chest_width_cm", "width_cm", "GLB slice lateral extent", "chest", None),
        ("chest_depth_cm", "depth_cm", "GLB slice anterior-posterior extent", "chest", None),
        ("waist_width_cm", "width_cm", "GLB slice lateral extent", "waist", None),
        ("waist_depth_cm", "depth_cm", "GLB slice anterior-posterior extent", "waist", None),
        ("hip_breadth_cm", "width_cm", "GLB slice lateral extent", "hip", None),
        ("hip_depth_cm", "depth_cm", "GLB slice anterior-posterior extent", "hip", None),
    ):
        target, target_method = _target(parsed, key)
        generated = sections.get(section)
        results[key] = _record(target, generated.get(generated_key) if generated else None,
                               method, target_method=target_method)

    for key in ("height_cm", "arm_span_cm"):
        target, target_method = _target(parsed, key)
        generated = height if key == "height_cm" else arm_span
        results[key] = _record(target, generated,
                               "GLB world-coordinate vertex extent; arm span is lateral bbox proxy" if key == "arm_span_cm" else "GLB world-coordinate vertical vertex extent",
                               target_method=target_method)

    # The mesh currently has no independently detectable crotch/leg stations.
    # Do not borrow target landmark positions to create apparently measured
    # inseam/thigh/calf results; surface segmentation is not yet calibrated.
    for key in ("inseam_cm", "thigh_circumference_cm", "calf_circumference_cm"):
        target, target_method = _target(parsed, key)
        results[key] = _record(target, None,
                               "unsupported: generated GLB has no calibrated crotch/limb section locator",
                               target_method=target_method)

    for obj in imported:
        bpy.data.objects.remove(obj, do_unlink=True)
    return {
        "validation_type": "independent_reimported_glb",
        "source_glb": str(glb_path),
        "mesh_dimensions_cm": dimensions,
        "passed": all(item["pass"] for item in results.values()),
        "measurements": results,
    }
