"""
Cross-Section Analyzer
======================
Computes horizontal body cross-sections from an evaluated Blender mesh
using bmesh plane bisecting.

Key capability: isolates the TORSO contour by filtering out arms,
neck, and disconnected geometry using centroid proximity and contour area.

Runs INSIDE Blender (uses bpy and bmesh).

Author: Body Reconstruction Engine
Version: 0.2.0
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class Contour:
    """A single 2D cross-section contour at a given Z height."""
    vertices: List[Tuple[float, float]]  # (x, y) pairs in cm (Blender XY plane)
    circumference_cm: float
    width_cm: float
    depth_cm: float
    area_cm2: float
    center_x_cm: float
    center_y_cm: float
    is_closed: bool
    vertex_count: int


@dataclass
class CrossSection:
    """Result of a horizontal slice at a given Z height."""
    z_height_cm: float
    label: str
    torso_contour: Optional[Contour]
    all_contours: List[Contour]
    valid: bool
    notes: str = ""


class CrossSectionAnalyzer:
    """
    Computes horizontal cross-sections of a Blender mesh using bmesh.ops.bisect_plane.
    """

    def __init__(self, torso_center_max_x_cm: float = 6.0, min_torso_circ_cm: float = 30.0):
        """
        Args:
            torso_center_max_x_cm: Maximum allowed |center_x| (in cm) for the torso contour.
                                   Torso is centered at X ≈ 0, arms are at |X| > 15 cm.
            min_torso_circ_cm: Minimum plausible torso circumference in cm.
        """
        self.torso_center_max_x_cm = torso_center_max_x_cm
        self.min_torso_circ_cm = min_torso_circ_cm

    def analyze_at_height(
        self,
        obj,
        z_height_m: float,
        label: str = "section",
    ) -> CrossSection:
        """
        Compute horizontal cross-section at z_height_m (metres, Blender world coordinates).
        Returns CrossSection with torso_contour identified.
        """
        import bmesh
        import bpy
        import mathutils

        z_cm = z_height_m * 100.0

        # Get evaluated mesh with modifiers applied
        depsgraph = bpy.context.evaluated_depsgraph_get()
        obj_eval = obj.evaluated_get(depsgraph)
        eval_mesh = obj_eval.to_mesh()

        bm = bmesh.new()
        bm.from_mesh(eval_mesh)

        # Apply world transform if needed
        mat = obj_eval.matrix_world
        if mat != mathutils.Matrix.Identity(4):
            for v in bm.verts:
                v.co = mat @ v.co

        # Bisect plane at Z = z_height_m
        plane_co = (0.0, 0.0, z_height_m)
        plane_no = (0.0, 0.0, 1.0)

        res = bmesh.ops.bisect_plane(
            bm,
            geom=bm.faces[:] + bm.edges[:] + bm.verts[:],
            plane_co=plane_co,
            plane_no=plane_no,
            clear_inner=False,
            clear_outer=False,
        )

        # geom_cut contains the newly generated intersection edges
        cut_edges = [e for e in res.get("geom_cut", []) if isinstance(e, bmesh.types.BMEdge)]

        all_contours = self._trace_loops(cut_edges)
        bm.free()

        # Find primary torso contour
        torso = self._select_torso(all_contours)

        return CrossSection(
            z_height_cm=z_cm,
            label=label,
            torso_contour=torso,
            all_contours=all_contours,
            valid=torso is not None,
            notes="" if torso else f"No valid torso contour found at Z={z_cm:.1f}cm",
        )

    def _trace_loops(self, cut_edges) -> List[Contour]:
        """Trace continuous loops from cut edges."""
        import bmesh

        vert_map: Dict[bmesh.types.BMVert, List[bmesh.types.BMEdge]] = {}
        for e in cut_edges:
            for v in e.verts:
                vert_map.setdefault(v, []).append(e)

        visited_edges = set()
        contours: List[Contour] = []

        for start_edge in cut_edges:
            if start_edge in visited_edges:
                continue

            loop_points: List[Tuple[float, float]] = []
            cur_edge = start_edge
            cur_v = start_edge.verts[0]
            start_v = cur_v
            is_closed = False

            while True:
                visited_edges.add(cur_edge)
                loop_points.append((cur_v.co.x * 100.0, cur_v.co.y * 100.0))

                other_v = cur_edge.other_vert(cur_v)
                cur_v = other_v

                next_edge = None
                for cand in vert_map.get(cur_v, []):
                    if cand not in visited_edges:
                        next_edge = cand
                        break

                if next_edge is None:
                    if cur_v == start_v:
                        is_closed = True
                    break

                cur_edge = next_edge
                if cur_v == start_v:
                    is_closed = True
                    break

            if len(loop_points) >= 3:
                contour = self._make_contour(loop_points, is_closed)
                contours.append(contour)

        return contours

    def _make_contour(self, pts: List[Tuple[float, float]], is_closed: bool) -> Contour:
        n = len(pts)
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        w = max(xs) - min(xs)
        d = max(ys) - min(ys)
        cx = sum(xs) / n
        cy = sum(ys) / n

        # Perimeter
        circ = 0.0
        for i in range(n):
            j = (i + 1) % n if is_closed else min(i + 1, n - 1)
            if is_closed or i < n - 1:
                circ += math.hypot(pts[j][0] - pts[i][0], pts[j][1] - pts[i][1])

        # Shoelace formula for area
        area = 0.0
        if is_closed:
            for i in range(n):
                j = (i + 1) % n
                area += pts[i][0] * pts[j][1] - pts[j][0] * pts[i][1]
            area = abs(area) * 0.5

        return Contour(
            vertices=pts,
            circumference_cm=circ,
            width_cm=w,
            depth_cm=d,
            area_cm2=area,
            center_x_cm=cx,
            center_y_cm=cy,
            is_closed=is_closed,
            vertex_count=n,
        )

    def _select_torso(self, contours: List[Contour]) -> Optional[Contour]:
        """Pick the torso contour (centered at X ≈ 0, largest area/circ)."""
        candidates = [
            c for c in contours
            if abs(c.center_x_cm) <= self.torso_center_max_x_cm
            and c.circumference_cm >= self.min_torso_circ_cm
        ]

        if not candidates:
            # Fallback: widen center tolerance slightly
            candidates = [
                c for c in contours
                if abs(c.center_x_cm) <= self.torso_center_max_x_cm * 2.0
                and c.circumference_cm >= self.min_torso_circ_cm * 0.7
            ]

        if not candidates:
            return None

        # Prefer closed contours, then largest circumference
        candidates.sort(key=lambda c: (c.is_closed, c.circumference_cm), reverse=True)
        return candidates[0]
