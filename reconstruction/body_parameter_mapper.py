"""
Body Parameter Mapper
=====================
Maps parsed JSON measurements to internal deformation parameters.
Produces a structured DeformationPlan that body_deformer.py consumes.

Handles:
- Unit conversion (all values stored in metres, Blender's native unit)
- Missing measurement fallback with 'inferred' flag
- Gender-based defaults
- Cross-section geometry targets

Author: Body Reconstruction Engine
Version: 0.1.0
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from reconstruction.json_parser import ParsedMeasurements

logger = logging.getLogger(__name__)


@dataclass
class RegionTarget:
    """Deformation target for a single anatomical region."""
    label: str
    # Circumference targets (metres)
    circumference_m: Optional[float] = None
    # Width and depth targets (metres) — ellipse model
    width_m: Optional[float] = None
    depth_m: Optional[float] = None
    # Z height in Blender space (metres) where this region is measured
    z_height_m: Optional[float] = None
    # Reliability weight (0–1) from measurement confidence
    weight: float = 1.0
    # Whether this value came directly from JSON or was inferred
    source: str = "measured"  # 'measured', 'inferred', 'default'
    # Confidence from original measurement
    confidence: Optional[float] = None


@dataclass
class ShapeKeySettings:
    """MPFB shape key values to set for gender/ethnicity blending."""
    # Keys: shape key name → blend value (0.0–1.0)
    values: Dict[str, float] = field(default_factory=dict)


@dataclass
class LandmarkZHeights:
    """
    Vertical (Z in Blender) heights of key anatomical landmarks (metres).
    Derived from landmarks_3d or estimated from height proportions.
    """
    head_top: float = 1.70
    chin: float = 1.50
    neck_base: float = 1.41
    shoulder: float = 1.39
    upper_chest: float = 1.22
    chest: float = 1.20
    underbust: float = 1.14
    waist: float = 1.02
    abdomen: float = 0.98
    high_hip: float = 0.94
    hip: float = 0.88
    crotch: float = 0.82
    knee: float = 0.48
    ankle: float = 0.09
    ground: float = 0.00


@dataclass
class DeformationPlan:
    """
    Complete parameterised plan for body reconstruction.
    Passed to body_deformer.py which applies the actual vertex displacements.
    """
    # Source info
    session_id: str
    gender: str  # 'female', 'male', 'unknown'

    # Height target (metres)
    target_height_m: float = 1.70

    # Anatomical Z heights for measurement planes (metres)
    landmark_heights: LandmarkZHeights = field(default_factory=LandmarkZHeights)

    # Per-region deformation targets
    regions: Dict[str, RegionTarget] = field(default_factory=dict)

    # Shoulder breadth (distance between left and right acromion, metres)
    shoulder_breadth_m: Optional[float] = None
    shoulder_breadth_source: str = "default"

    # Shape key settings
    shape_keys: ShapeKeySettings = field(default_factory=ShapeKeySettings)

    # Tolerances for optimisation (cm)
    tolerances: Dict[str, float] = field(default_factory=lambda: {
        "chest_circumference_cm":  1.0,
        "waist_circumference_cm":  1.0,
        "hip_circumference_cm":    1.0,
        "height_cm":               0.5,
        "shoulder_breadth_cm":     1.0,
    })

    def summary(self) -> str:
        lines = [f"DeformationPlan [{self.session_id}] gender={self.gender}"]
        lines.append(f"  height: {self.target_height_m*100:.1f} cm")
        for name, r in self.regions.items():
            circ = f"{r.circumference_m*100:.1f}cm" if r.circumference_m else "—"
            w = f"{r.width_m*100:.1f}cm" if r.width_m else "—"
            d = f"{r.depth_m*100:.1f}cm" if r.depth_m else "—"
            lines.append(f"  {name}: circ={circ}, w={w}, d={d} [{r.source}]")
        return "\n".join(lines)


class BodyParameterMapper:
    """
    Converts a ParsedMeasurements object into a DeformationPlan.

    Fallback strategy for missing measurements:
    - Use the base MPFB model's proportions relative to height.
    - Mark these as source='inferred'.
    - Never silently pass inferred values as measured.
    """

    # MPFB base model reference proportions (relative to 165.94 cm height)
    # These are the base model's actual measurements at scale 1.0
    BASE_HEIGHT_CM = 165.94
    BASE_PROPORTIONS = {
        # region: (circ_ratio, width_ratio, depth_ratio)
        # ratios are fraction of height
        "chest":      (0.87, 0.35, 0.23),  # ~86 cm circ, ~35 cm wide, ~23 cm deep at 165 cm height
        "waist":      (0.75, 0.29, 0.19),
        "high_hip":   (0.82, 0.32, 0.20),
        "hip":        (0.93, 0.35, 0.23),
        "neck":       (0.22, 0.08, 0.08),
        "upper_chest":(0.88, 0.36, 0.23),
        "underbust":  (0.80, 0.33, 0.21),
        "abdomen":    (0.76, 0.30, 0.19),
    }

    def map(self, parsed: ParsedMeasurements) -> DeformationPlan:
        """Build a DeformationPlan from a ParsedMeasurements object."""

        height_cm = parsed.get_value("height_cm") or self.BASE_HEIGHT_CM
        height_m = height_cm / 100.0
        gender = parsed.gender.final_gender if parsed.gender else "unknown"

        plan = DeformationPlan(
            session_id=parsed.session_id,
            gender=gender,
            target_height_m=height_m,
        )

        # Build landmark heights from landmarks_3d or estimate from proportions
        plan.landmark_heights = self._build_landmark_heights(parsed, height_m)

        # Map each anatomical region
        plan.regions["chest"] = self._map_region(
            parsed, "chest",
            circ_key="chest_circumference_cm",
            width_key="chest_width_cm",
            depth_key="chest_depth_cm",
            cross_section_key="chest",
            z_m=plan.landmark_heights.upper_chest,
        )

        plan.regions["upper_chest"] = self._map_region(
            parsed, "upper_chest",
            circ_key="upper_chest_circumference_cm",
            width_key=None,
            depth_key=None,
            cross_section_key="chest",  # use chest cross-section as proxy
            z_m=plan.landmark_heights.upper_chest,
        )

        plan.regions["underbust"] = self._map_region(
            parsed, "underbust",
            circ_key="underbust_circumference_cm",
            width_key=None,
            depth_key=None,
            cross_section_key=None,
            z_m=plan.landmark_heights.underbust,
        )

        plan.regions["waist"] = self._map_region(
            parsed, "waist",
            circ_key="waist_circumference_cm",
            width_key="waist_width_cm",
            depth_key="waist_depth_cm",
            cross_section_key="waist",
            z_m=plan.landmark_heights.waist,
        )

        plan.regions["abdomen"] = self._map_region(
            parsed, "abdomen",
            circ_key="abdomen_circumference_cm",
            width_key=None,
            depth_key=None,
            cross_section_key=None,
            z_m=plan.landmark_heights.abdomen,
        )

        plan.regions["high_hip"] = self._map_region(
            parsed, "high_hip",
            circ_key="high_hip_circumference_cm",
            width_key=None,
            depth_key=None,
            cross_section_key=None,
            z_m=plan.landmark_heights.high_hip,
        )

        plan.regions["hip"] = self._map_region(
            parsed, "hip",
            circ_key="hip_circumference_cm",
            width_key="hip_breadth_cm",
            depth_key="hip_depth_cm",
            cross_section_key="hip",
            z_m=plan.landmark_heights.hip,
        )

        plan.regions["neck"] = self._map_region(
            parsed, "neck",
            circ_key="neck_circumference_cm",
            width_key=None,
            depth_key=None,
            cross_section_key="neck",
            z_m=plan.landmark_heights.neck_base,
        )

        # Shoulder breadth
        sb = parsed.get_value("shoulder_breadth_cm")
        sb_entry = parsed.get_entry("shoulder_breadth_cm")
        if sb is not None:
            plan.shoulder_breadth_m = sb / 100.0
            plan.shoulder_breadth_source = "measured"
        else:
            # Estimate: shoulder breadth ≈ 24% of height for females, 26% for males
            ratio = 0.24 if gender == "female" else 0.26
            plan.shoulder_breadth_m = height_m * ratio
            plan.shoulder_breadth_source = "inferred"
            logger.warning(f"shoulder_breadth_cm missing — inferred as {plan.shoulder_breadth_m*100:.1f} cm")

        # Shape key values based on gender
        plan.shape_keys = self._build_shape_keys(parsed)

        logger.info(plan.summary())
        return plan

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _map_region(
        self,
        parsed: ParsedMeasurements,
        label: str,
        circ_key: Optional[str],
        width_key: Optional[str],
        depth_key: Optional[str],
        cross_section_key: Optional[str],
        z_m: float,
        height_m: Optional[float] = None,
    ) -> RegionTarget:
        """Build a RegionTarget for one anatomical region."""
        if height_m is None:
            height_m = parsed.get_value("height_cm") or self.BASE_HEIGHT_CM
            height_m /= 100.0

        # 1. Direct measurements
        circ_val = parsed.get_value(circ_key) if circ_key else None
        width_val = parsed.get_value(width_key) if width_key else None
        depth_val = parsed.get_value(depth_key) if depth_key else None

        # 2. Try cross-section data for width/depth if not in direct measurements
        if (width_val is None or depth_val is None) and cross_section_key and parsed.cross_sections:
            cs = parsed.cross_sections.get(cross_section_key)
            if cs:
                if width_val is None:
                    width_val = cs.width_cm
                if depth_val is None:
                    depth_val = cs.depth_cm

        # 3. Determine source and apply fallbacks
        sources = []
        if circ_val is not None:
            sources.append("measured")
        if width_val is not None and depth_val is not None:
            sources.append("measured")

        if circ_val is None and (width_val is not None and depth_val is not None):
            # Estimate circumference from width + depth (ellipse)
            a, b = width_val / 2, depth_val / 2
            h = ((a - b) ** 2) / ((a + b) ** 2)
            circ_val = math.pi * (a + b) * (1 + (3 * h) / (10 + math.sqrt(max(0, 4 - 3 * h))))
            sources.append("computed")
            logger.debug(f"{label}: circumference inferred from width/depth = {circ_val:.1f} cm")

        if circ_val is None:
            # Use base model proportion
            prop = self.BASE_PROPORTIONS.get(label)
            if prop:
                circ_val = prop[0] * height_m * 100
                width_val = prop[1] * height_m * 100
                depth_val = prop[2] * height_m * 100
                sources = ["inferred"]
                logger.warning(f"{label}: all measurements missing — using proportional defaults")

        # Get weight from the primary measurement entry
        entry = parsed.get_entry(circ_key) if circ_key else None
        weight = entry.weight if entry and entry.is_valid else 0.5
        confidence = entry.confidence if entry else None

        source_str = "measured" if sources and sources[0] == "measured" else (
            "computed" if sources and sources[0] == "computed" else "inferred"
        )

        return RegionTarget(
            label=label,
            circumference_m=circ_val / 100.0 if circ_val is not None else None,
            width_m=width_val / 100.0 if width_val is not None else None,
            depth_m=depth_val / 100.0 if depth_val is not None else None,
            z_height_m=z_m,
            weight=weight,
            source=source_str,
            confidence=confidence,
        )

    def _build_landmark_heights(
        self, parsed: ParsedMeasurements, height_m: float
    ) -> LandmarkZHeights:
        """
        Build Z heights for anatomical landmarks.
        Prefer landmarks_3d. Fall back to proportional estimates.
        """
        lm = parsed.landmarks

        def lm_z(name: str) -> Optional[float]:
            """Get Blender Z (metres) for a landmark by name."""
            pt = lm.get(name)
            if pt:
                bx, by, bz = pt.to_blender()
                return bz  # Blender Z = JSON Y / 100
            return None

        def prop(ratio: float) -> float:
            return height_m * ratio

        heights = LandmarkZHeights()

        heights.head_top   = lm_z("head_top") or lm_z("crown") or height_m
        heights.chin       = lm_z("chin") or prop(0.88)
        heights.neck_base  = lm_z("neck_base") or prop(0.83)
        heights.shoulder   = lm_z("left_shoulder_joint") or lm_z("right_shoulder_joint") or prop(0.82)
        heights.upper_chest= lm_z("upper_chest") or lm_z("sternum") or prop(0.72)
        heights.chest      = lm_z("upper_chest") or prop(0.71)
        heights.underbust  = prop(0.67)  # typically not a landmark; estimated
        heights.waist      = lm_z("waist_center") or lm_z("navel") or prop(0.60)
        heights.abdomen    = prop(0.58)
        heights.high_hip   = prop(0.55)
        heights.hip        = lm_z("pelvis_center") or prop(0.52)
        heights.crotch     = lm_z("crotch") or prop(0.48)
        heights.knee       = lm_z("left_knee") or lm_z("right_knee") or prop(0.28)
        heights.ankle      = lm_z("left_ankle") or lm_z("right_ankle") or prop(0.05)
        heights.ground     = 0.0

        # Log any inferred heights
        for attr, value in heights.__dict__.items():
            landmark_name = {
                "head_top": "head_top", "chin": "chin", "neck_base": "neck_base",
                "shoulder": "left_shoulder_joint", "upper_chest": "upper_chest",
                "waist": "waist_center", "hip": "pelvis_center",
                "crotch": "crotch", "knee": "left_knee", "ankle": "left_ankle",
            }.get(attr)
            if landmark_name and not lm.get(landmark_name):
                logger.debug(f"Landmark '{attr}' inferred from proportion: {value*100:.1f} cm")

        return heights

    def _build_shape_keys(self, parsed: ParsedMeasurements) -> ShapeKeySettings:
        """
        Set MPFB macro-detail shape key values.
        These control ethnicity/gender blending, NOT body dimensions.
        """
        gender = parsed.gender.final_gender if parsed.gender else "unknown"
        gender_conf = parsed.gender.confidence if parsed.gender else 0.5

        # The shape keys blend between female and male presentations.
        # We use gender confidence to weight the blend.
        # All ethnicity keys are set to equal blend (no ethnicity data in JSON).

        ETHNIC_KEYS = ["$md-$as", "$md-$ca", "$md-$af"]
        ethnic_val = 1.0 / 3.0  # equal blend across three groups

        # Gender blend: high female confidence → higher female key values
        if gender == "female":
            female_val = min(0.8, max(0.3, gender_conf))
            male_val = 1.0 - female_val
        elif gender == "male":
            male_val = min(0.8, max(0.3, gender_conf))
            female_val = 1.0 - male_val
        else:
            female_val = 0.5
            male_val = 0.5

        values = {
            "$md-$as-$fe-$yn": ethnic_val * female_val * 3,  # scale to keep total reasonable
            "$md-$as-$ma-$yn": ethnic_val * male_val * 3,
            "$md-$ca-$fe-$yn": ethnic_val * female_val * 3,
            "$md-$ca-$ma-$yn": ethnic_val * male_val * 3,
            "$md-$af-$fe-$yn": ethnic_val * female_val * 3,
            "$md-$af-$ma-$yn": ethnic_val * male_val * 3,
            "$md-universal-$fe-$yn-$av$mu-$av$wg": female_val,
            "$md-universal-$ma-$yn-$av$mu-$av$wg": male_val,
        }

        return ShapeKeySettings(values=values)

