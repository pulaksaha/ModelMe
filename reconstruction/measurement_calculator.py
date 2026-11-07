"""
Measurement Calculator
======================
Computes anthropometric measurements from an evaluated Blender mesh object.
Uses CrossSectionAnalyzer for torso cross-sections.

Runs INSIDE Blender (uses bpy, bmesh).

Author: Body Reconstruction Engine
Version: 0.2.0
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from reconstruction.cross_section_analyzer import CrossSectionAnalyzer

logger = logging.getLogger(__name__)


@dataclass
class MeshMeasurement:
    """A single measurement computed from the 3D mesh."""
    name: str
    value_cm: float
    method: str
    z_height_cm: Optional[float] = None
    notes: str = ""


@dataclass
class MeshMeasurementReport:
    """Complete set of measurements extracted from a mesh."""
    object_name: str
    measurements: Dict[str, MeshMeasurement]

    def get_value(self, name: str) -> Optional[float]:
        m = self.measurements.get(name)
        return m.value_cm if m else None

    def summary(self) -> str:
        lines = [f"Mesh measurements for '{self.object_name}':"]
        for name, m in self.measurements.items():
            z_str = f" @Z={m.z_height_cm:.1f}cm" if m.z_height_cm else ""
            lines.append(f"  {name}: {m.value_cm:.2f} cm{z_str}")
        return "\n".join(lines)


class MeshMeasurementCalculator:
    """
    Computes body measurements from a Blender mesh object.
    """

    def __init__(self):
        self.analyzer = CrossSectionAnalyzer()

    def compute(self, obj, plan) -> MeshMeasurementReport:
        """
        Compute all measurements from the given Blender mesh object.
        """
        import bpy

        depsgraph = bpy.context.evaluated_depsgraph_get()
        obj_eval = obj.evaluated_get(depsgraph)
        mesh_eval = obj_eval.to_mesh()

        report = MeshMeasurementReport(
            object_name=obj.name,
            measurements={},
        )

        # 1. Height (vertex Z extent)
        body_z = [v.co.z * 100.0 for v in mesh_eval.vertices]
        if body_z:
            min_z = min(body_z)
            max_z = max(body_z)
            report.measurements["height_cm"] = MeshMeasurement(
                name="height_cm",
                value_cm=round(max_z - min_z, 2),
                method="vertex_extent",
                notes=f"Z: {min_z:.2f} to {max_z:.2f} cm",
            )

        # 2. Shoulder breadth (skin surface lateral breadth at shoulder height)
        shoulder_z = plan.landmark_heights.shoulder
        shoulder_band = [
            v.co for v in mesh_eval.vertices
            if abs(v.co.z - shoulder_z) <= 0.03
        ]
        if shoulder_band:
            left_xs = [v.x * 100.0 for v in shoulder_band if v.x > 0]
            right_xs = [v.x * 100.0 for v in shoulder_band if v.x < 0]
            if left_xs and right_xs:
                sb = max(left_xs) - min(right_xs)
                report.measurements["shoulder_breadth_cm"] = MeshMeasurement(
                    name="shoulder_breadth_cm",
                    value_cm=round(sb, 2),
                    method="lateral_acromion_extent",
                    z_height_cm=shoulder_z * 100.0,
                    notes=f"Left: {max(left_xs):.2f}cm, Right: {min(right_xs):.2f}cm",
                )

        # 3. Torso cross-sections
        landmark_map = {
            "upper_chest_circumference_cm": ("upper_chest", plan.landmark_heights.upper_chest),
            "chest_circumference_cm":       ("chest",       plan.landmark_heights.chest),
            "underbust_circumference_cm":   ("underbust",   plan.landmark_heights.underbust),
            "waist_circumference_cm":       ("waist",       plan.landmark_heights.waist),
            "abdomen_circumference_cm":     ("abdomen",     plan.landmark_heights.abdomen),
            "high_hip_circumference_cm":    ("high_hip",    plan.landmark_heights.high_hip),
            "hip_circumference_cm":         ("hip",         plan.landmark_heights.hip),
            "neck_circumference_cm":        ("neck",        plan.landmark_heights.neck_base),
        }

        # Slices to also extract width and depth
        slice_cache: Dict[str, any] = {}

        for meas_name, (region, z_m) in landmark_map.items():
            cs = self.analyzer.analyze_at_height(obj, z_m, label=region)
            slice_cache[region] = cs
            if cs.valid and cs.torso_contour:
                report.measurements[meas_name] = MeshMeasurement(
                    name=meas_name,
                    value_cm=round(cs.torso_contour.circumference_cm, 2),
                    method="mesh_cross_section_contour",
                    z_height_cm=round(cs.z_height_cm, 2),
                    notes=f"Closed: {cs.torso_contour.is_closed}, pts: {cs.torso_contour.vertex_count}",
                )

        # 4. Width and Depth
        region_width_depth = [
            ("chest", "chest_width_cm", "chest_depth_cm"),
            ("waist", "waist_width_cm", "waist_depth_cm"),
            ("hip", "hip_breadth_cm", "hip_depth_cm"),
        ]

        for reg, w_name, d_name in region_width_depth:
            cs = slice_cache.get(reg)
            if cs and cs.valid and cs.torso_contour:
                report.measurements[w_name] = MeshMeasurement(
                    name=w_name,
                    value_cm=round(cs.torso_contour.width_cm, 2),
                    method="cross_section_width",
                    z_height_cm=round(cs.z_height_cm, 2),
                )
                report.measurements[d_name] = MeshMeasurement(
                    name=d_name,
                    value_cm=round(cs.torso_contour.depth_cm, 2),
                    method="cross_section_depth",
                    z_height_cm=round(cs.z_height_cm, 2),
                )

        return report
