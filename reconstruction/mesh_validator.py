"""
Mesh Validator
==============
Post-deformation sanity checks on the generated mesh.
Verifies geometry is well-formed before export.

Runs INSIDE Blender (uses bpy, bmesh).

Author: Body Reconstruction Engine
Version: 0.1.0
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List

logger = logging.getLogger(__name__)


@dataclass
class MeshValidationResult:
    """Result of mesh validation checks."""
    passed: bool
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return (
            f"MeshValidation: {status} | "
            f"{len(self.warnings)} warnings | {len(self.errors)} errors"
        )


class MeshValidator:
    """
    Checks that the deformed mesh is geometrically valid for export.

    Checks:
    1. Mesh is non-empty (has vertices and faces).
    2. No NaN or Inf vertex coordinates.
    3. Bounding box is plausible (not collapsed, not astronomically large).
    4. No isolated vertices (vertices not connected to any edge).
    5. Face count is within expected range.
    """

    MIN_HEIGHT_M = 0.5
    MAX_HEIGHT_M = 2.5
    MIN_VERTICES = 1000
    MIN_FACES = 500

    def validate(self, obj) -> MeshValidationResult:
        """Run all validation checks on the Blender mesh object."""
        import bpy, mathutils
        import math

        result = MeshValidationResult(passed=True)
        mesh = obj.data

        # 1. Non-empty
        if len(mesh.vertices) < self.MIN_VERTICES:
            result.errors.append(
                f"Too few vertices: {len(mesh.vertices)} (min: {self.MIN_VERTICES})"
            )
            result.passed = False

        if len(mesh.polygons) < self.MIN_FACES:
            result.errors.append(
                f"Too few faces: {len(mesh.polygons)} (min: {self.MIN_FACES})"
            )
            result.passed = False

        # 2. NaN / Inf check
        nan_count = 0
        for v in mesh.vertices:
            for c in v.co:
                if not math.isfinite(c):
                    nan_count += 1

        if nan_count > 0:
            result.errors.append(f"Found {nan_count} non-finite (NaN/Inf) vertex coordinates")
            result.passed = False

        # 3. Bounding box plausibility
        mat = obj.matrix_world
        bbox_world = [mat @ mathutils.Vector(c) for c in obj.bound_box]
        zs = [v.z for v in bbox_world]
        xs = [v.x for v in bbox_world]
        ys = [v.y for v in bbox_world]

        height = max(zs) - min(zs)
        width = max(xs) - min(xs)
        depth = max(ys) - min(ys)

        if height < self.MIN_HEIGHT_M:
            result.errors.append(
                f"Mesh height too small: {height*100:.1f} cm (min: {self.MIN_HEIGHT_M*100:.0f} cm)"
            )
            result.passed = False

        if height > self.MAX_HEIGHT_M:
            result.warnings.append(
                f"Mesh height unusually large: {height*100:.1f} cm"
            )

        if width < 0.05:
            result.errors.append(f"Mesh width collapsed: {width*100:.1f} cm")
            result.passed = False

        if depth < 0.05:
            result.errors.append(f"Mesh depth collapsed: {depth*100:.1f} cm")
            result.passed = False

        # 4. Isolated vertices (expensive, skip if too many vertices)
        if len(mesh.vertices) < 50000:
            connected = set()
            for edge in mesh.edges:
                connected.update(edge.vertices)
            isolated = len(mesh.vertices) - len(connected)
            if isolated > 100:
                result.warnings.append(f"Found {isolated} isolated vertices (not connected to any edge)")

        logger.info(result.summary())
        if result.warnings:
            for w in result.warnings:
                logger.warning(f"  {w}")
        if result.errors:
            for e in result.errors:
                logger.error(f"  {e}")

        return result

