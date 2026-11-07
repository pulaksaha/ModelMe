"""
Body Deformer
=============
Applies anatomically-controlled vertex-level deformations to match a DeformationPlan.

Runs INSIDE Blender (uses bpy, bmesh, mathutils).

Deformation strategy:
- Bakes gender/ethnicity shape keys into base mesh geometry.
- Scales vertex Z coordinates to match exact target height (grounded at Z=0).
- Deforms shoulder breadth laterally with smooth falloff.
- Deforms torso cross-sections (chest, underbust, waist, abdomen, hip, neck)
  using smooth Gaussian radial and directional displacement fields.
- Preserves smooth human anatomy without pinching or unnatural spikes.

Author: Body Reconstruction Engine
Version: 0.2.0
"""

from __future__ import annotations

import math
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def gaussian_weight(z: float, z_center: float, sigma: float) -> float:
    """Smooth Gaussian weight in [0, 1]."""
    return math.exp(-0.5 * ((z - z_center) / sigma) ** 2)


# Influence zone standard deviations (in metres)
REGION_SIGMA = {
    "head":        0.04,
    "neck":        0.035,
    "upper_chest": 0.065,
    "chest":       0.075,
    "underbust":   0.055,
    "waist":       0.055,
    "abdomen":     0.050,
    "high_hip":    0.055,
    "hip":         0.075,
}


class BodyDeformer:
    """
    Applies anatomically controlled vertex deformations to a Blender mesh object.
    """

    def __init__(self, obj, plan):
        self.obj = obj
        self.plan = plan

    def apply_all(self) -> None:
        """Apply all deformations in anatomically correct sequence."""
        # 1. Shape keys (gender/macro features) baked into geometry
        self._apply_and_bake_shape_keys()

        # 2. Height scaling (grounds mesh at Z=0)
        self._apply_height()

        # 3. Shoulder breadth
        self._apply_shoulder_breadth()

        # 4. Torso regional adjustments
        self._apply_torso_regions()

        self.obj.data.update()
        logger.info("All deformations successfully applied.")

    # -----------------------------------------------------------------------
    # Step 1: Shape keys
    # -----------------------------------------------------------------------

    def _apply_and_bake_shape_keys(self) -> None:
        """Set macro shape key weights and bake them into the mesh geometry."""
        import bpy

        mesh = self.obj.data
        if not mesh.shape_keys:
            return

        keys = mesh.shape_keys.key_blocks
        for key_name, val in self.plan.shape_keys.values.items():
            if key_name in keys:
                keys[key_name].value = max(0.0, min(1.0, float(val)))

        # Bake shape keys into base coordinates so direct vertex deformation works
        bpy.context.view_layer.objects.active = self.obj
        self.obj.select_set(True)
        bpy.ops.object.shape_key_remove(all=True, apply_mix=True)
        logger.info("Shape keys blended and baked into base mesh.")

    # -----------------------------------------------------------------------
    # Step 2: Height scaling
    # -----------------------------------------------------------------------

    def _apply_height(self) -> None:
        """
        Scale the entire mesh along Z to match the target height.
        Grounds the lowest point at Z = 0.00.
        """
        target_h = self.plan.target_height_m
        verts = self.obj.data.vertices
        zs = [v.co.z for v in verts]
        min_z = min(zs)
        max_z = max(zs)
        cur_h = max_z - min_z

        if cur_h < 0.1:
            logger.error("Invalid mesh height, skipping height scaling.")
            return

        scale_z = target_h / cur_h
        for v in verts:
            v.co.z = (v.co.z - min_z) * scale_z

        self.obj.data.update()
        logger.info(f"Height scaled: {cur_h*100:.2f} cm -> {target_h*100:.2f} cm (scale_z={scale_z:.4f})")

    # -----------------------------------------------------------------------
    # Step 3: Shoulder breadth
    # -----------------------------------------------------------------------

    def _apply_shoulder_breadth(self) -> None:
        """
        Adjust lateral extent at shoulder height to match target shoulder breadth.
        """
        if not self.plan.shoulder_breadth_m:
            return

        target_half = self.plan.shoulder_breadth_m / 2.0
        shoulder_z = self.plan.landmark_heights.shoulder
        verts = self.obj.data.vertices

        # Measure current outer lateral extent in shoulder band
        band = [v for v in verts if abs(v.co.z - shoulder_z) <= 0.035 and v.co.x > 0]
        if not band:
            return

        cur_half = max(v.co.x for v in band)
        delta_half = target_half - cur_half

        if abs(delta_half) < 0.001:
            return

        # Deform lateral shoulder and arms smoothly
        sigma = 0.08
        for v in verts:
            w = gaussian_weight(v.co.z, shoulder_z, sigma)
            if w > 0.005 and abs(v.co.x) > 0.10:
                sign = 1.0 if v.co.x > 0 else -1.0
                v.co.x += sign * delta_half * w

        self.obj.data.update()
        logger.info(f"Shoulder breadth adjusted: half {cur_half*100:.2f}cm -> {target_half*100:.2f}cm")

    # -----------------------------------------------------------------------
    # Step 4: Torso regional adjustments
    # -----------------------------------------------------------------------

    def _apply_torso_regions(self) -> None:
        """
        Deform torso sections using smooth Gaussian radial and axis adjustments.
        """
        from reconstruction.cross_section_analyzer import CrossSectionAnalyzer
        analyzer = CrossSectionAnalyzer()

        # Regions ordered from chest downwards
        regions_to_process = [
            ("chest",       self.plan.landmark_heights.chest,       REGION_SIGMA["chest"]),
            ("underbust",   self.plan.landmark_heights.underbust,   REGION_SIGMA["underbust"]),
            ("waist",       self.plan.landmark_heights.waist,       REGION_SIGMA["waist"]),
            ("abdomen",     self.plan.landmark_heights.abdomen,     REGION_SIGMA["abdomen"]),
            ("high_hip",    self.plan.landmark_heights.high_hip,    REGION_SIGMA["high_hip"]),
            ("hip",         self.plan.landmark_heights.hip,         REGION_SIGMA["hip"]),
            ("neck",        self.plan.landmark_heights.neck_base,   REGION_SIGMA["neck"]),
        ]

        for reg_name, z_m, sigma in regions_to_process:
            target = self.plan.regions.get(reg_name)
            if not target:
                continue

            cs = analyzer.analyze_at_height(self.obj, z_m, label=reg_name)
            if not cs.valid or not cs.torso_contour:
                continue

            cur_circ = cs.torso_contour.circumference_cm
            cur_w = cs.torso_contour.width_cm
            cur_d = cs.torso_contour.depth_cm

            target_circ = target.circumference_m * 100.0 if target.circumference_m else None
            target_w = target.width_m * 100.0 if target.width_m else None
            target_d = target.depth_m * 100.0 if target.depth_m else None

            # Calculate scaling factors
            scale_x = 1.0
            scale_y = 1.0

            if target_w and target_d and cur_w > 1.0 and cur_d > 1.0:
                scale_x = target_w / cur_w
                scale_y = target_d / cur_d
                # Fine-tune with circumference ratio
                if target_circ and cur_circ > 1.0:
                    circ_ratio = target_circ / cur_circ
                    scale_x = (scale_x + circ_ratio) * 0.5
                    scale_y = (scale_y + circ_ratio) * 0.5
            elif target_circ and cur_circ > 1.0:
                ratio = target_circ / cur_circ
                scale_x = ratio
                scale_y = ratio

            # Clamp scaling factor to prevent extreme distortion
            scale_x = max(0.70, min(1.30, scale_x))
            scale_y = max(0.70, min(1.30, scale_y))

            if abs(scale_x - 1.0) < 0.005 and abs(scale_y - 1.0) < 0.005:
                continue

            self._apply_smooth_scale(
                z_center=z_m,
                sigma=sigma,
                scale_x=scale_x,
                scale_y=scale_y,
                center_y_m=cs.torso_contour.center_y_cm / 100.0,
                torso_half_w_m=cur_w / 200.0,
            )

        self.obj.data.update()

    def _apply_smooth_scale(
        self,
        z_center: float,
        sigma: float,
        scale_x: float,
        scale_y: float,
        center_y_m: float,
        torso_half_w_m: float,
    ) -> None:
        """Apply smooth X/Y scaling around (0, center_y_m, z_center)."""
        verts = self.obj.data.vertices
        arm_margin = 0.04  # margin beyond torso width where arms begin

        for v in verts:
            w = gaussian_weight(v.co.z, z_center, sigma)
            if w <= 0.005:
                continue

            # Check if vertex is part of the torso
            if abs(v.co.x) <= torso_half_w_m + arm_margin:
                v.co.x += (scale_x - 1.0) * w * v.co.x
                v.co.y += (scale_y - 1.0) * w * (v.co.y - center_y_m)
            else:
                # If vertex is on the arm, offset laterally to prevent intersection
                sign = 1.0 if v.co.x > 0 else -1.0
                lateral_shift = (scale_x - 1.0) * torso_half_w_m * w
                v.co.x += sign * lateral_shift
