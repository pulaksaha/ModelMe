"""
Measurement Validator
=====================
Validates parsed measurement data for completeness, plausible ranges,
unit correctness, and internal consistency.

Does NOT invent missing measurements — it flags them.
Logs warnings but does not raise exceptions for recoverable issues.

Author: Body Reconstruction Engine
Version: 0.1.0
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from reconstruction.json_parser import ParsedMeasurements, MeasurementEntry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Validation result types
# ---------------------------------------------------------------------------

@dataclass
class FieldValidationResult:
    """Validation outcome for a single measurement field."""
    name: str
    status: str          # 'ok', 'missing', 'out_of_range', 'low_confidence', 'unit_suspect'
    value: Optional[float]
    message: str
    is_critical: bool    # True = reconstruction cannot proceed without this field


@dataclass
class ValidationReport:
    """Complete validation report for a measurement file."""
    session_id: str
    overall_status: str    # 'pass', 'warn', 'fail'
    field_results: List[FieldValidationResult] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return self.overall_status != 'fail'

    def passed_fields(self) -> List[str]:
        return [r.name for r in self.field_results if r.status == 'ok']

    def missing_critical(self) -> List[str]:
        return [r.name for r in self.field_results
                if r.is_critical and r.status == 'missing']

    def out_of_range_fields(self) -> List[str]:
        return [r.name for r in self.field_results if r.status == 'out_of_range']

    def summary(self) -> str:
        return (
            f"Session {self.session_id}: {self.overall_status.upper()} | "
            f"{len(self.passed_fields())} passed | "
            f"{len(self.missing_critical())} critical missing | "
            f"{len(self.warnings)} warnings | "
            f"{len(self.errors)} errors"
        )


# ---------------------------------------------------------------------------
# Plausible anthropometric ranges (cm) for adult humans
# Very wide to avoid false rejections on atypical body types
# ---------------------------------------------------------------------------

MEASUREMENT_RANGES: Dict[str, Tuple[float, float]] = {
    "height_cm":                     (120.0, 230.0),
    "neck_circumference_cm":         (25.0, 65.0),
    "neck_base_circumference_cm":    (25.0, 65.0),
    "neck_length_cm":                (3.0,  20.0),
    "head_circumference_cm":         (46.0, 70.0),
    "chest_circumference_cm":        (60.0, 170.0),
    "upper_chest_circumference_cm":  (60.0, 180.0),
    "underbust_circumference_cm":    (55.0, 160.0),
    "waist_circumference_cm":        (50.0, 180.0),
    "abdomen_circumference_cm":      (50.0, 180.0),
    "high_hip_circumference_cm":     (60.0, 180.0),
    "hip_circumference_cm":          (60.0, 180.0),
    "shoulder_breadth_cm":           (25.0, 65.0),
    "shoulder_slope_deg":            (0.0,  40.0),
    "chest_width_cm":                (20.0, 70.0),
    "chest_depth_cm":                (12.0, 45.0),
    "waist_width_cm":                (15.0, 65.0),
    "waist_depth_cm":                (10.0, 45.0),
    "waist_height_cm":               (60.0, 130.0),
    "waist_to_hip_cm":               (5.0,  30.0),
    "torso_length_cm":               (25.0, 65.0),
    "shoulder_to_crotch_cm":         (40.0, 90.0),
    "hip_breadth_cm":                (20.0, 65.0),
    "hip_depth_cm":                  (15.0, 50.0),
    "upper_arm_circumference_cm":    (18.0, 65.0),
    "biceps_circumference_cm":       (18.0, 65.0),
    "forearm_circumference_cm":      (15.0, 50.0),
    "wrist_circumference_cm":        (12.0, 30.0),
    "thigh_circumference_cm":        (30.0, 90.0),
    "knee_circumference_cm":         (25.0, 70.0),
    "calf_circumference_cm":         (25.0, 70.0),
    "ankle_circumference_cm":        (15.0, 50.0),
    "inseam_cm":                     (50.0, 100.0),
    "arm_span_cm":                   (120.0, 230.0),
}

# These fields are required for the reconstruction to work at all
CRITICAL_FIELDS = {"height_cm", "chest_circumference_cm", "waist_circumference_cm", "hip_circumference_cm"}

# Fields that strongly improve reconstruction quality
IMPORTANT_FIELDS = {
    "shoulder_breadth_cm", "chest_width_cm", "chest_depth_cm",
    "waist_width_cm", "waist_depth_cm", "hip_breadth_cm", "hip_depth_cm",
    "neck_circumference_cm", "waist_height_cm",
}


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

class MeasurementValidator:
    """
    Validates a ParsedMeasurements object.

    Rules:
    1. Critical fields must be present and in range.
    2. All present values must be within plausible anthropometric ranges.
    3. Unit must be 'cm' (other units not supported without conversion).
    4. Internal consistency checks (e.g. waist < hip, waist < chest).
    5. Landmarks must have a known coordinate frame.
    6. Low-confidence measurements are flagged but not rejected.
    """

    def validate(self, parsed: ParsedMeasurements) -> ValidationReport:
        """Run all validation checks. Returns a ValidationReport."""
        report = ValidationReport(
            session_id=parsed.session_id,
            overall_status="pass",
        )

        # 1. Unit check
        self._check_unit(parsed, report)

        # 2. Per-field range and presence checks
        for name in set(CRITICAL_FIELDS) | set(IMPORTANT_FIELDS) | set(parsed.measurements.keys()):
            entry = parsed.measurements.get(name)
            result = self._validate_field(name, entry)
            report.field_results.append(result)
            if result.status == 'out_of_range':
                report.errors.append(f"{name}: {result.message}")
            elif result.status in ('missing', 'low_confidence', 'unit_suspect'):
                report.warnings.append(f"{name}: {result.message}")

        # 3. Internal consistency
        self._check_consistency(parsed, report)

        # 4. Landmark frame
        self._check_landmarks(parsed, report)

        # 5. Determine overall status
        critical_missing = report.missing_critical()
        if critical_missing or report.out_of_range_fields():
            report.overall_status = "fail"
            report.errors.insert(0, f"Critical fields missing or invalid: {critical_missing}")
        elif report.warnings:
            report.overall_status = "warn"

        logger.info(report.summary())
        return report

    # -----------------------------------------------------------------------
    # Private validators
    # -----------------------------------------------------------------------

    def _check_unit(self, parsed: ParsedMeasurements, report: ValidationReport) -> None:
        if parsed.unit.lower() != "cm":
            report.warnings.append(
                f"Unit is '{parsed.unit}', expected 'cm'. "
                f"Values will be treated as cm — verify correctness."
            )

    def _validate_field(
        self,
        name: str,
        entry: Optional[MeasurementEntry],
    ) -> FieldValidationResult:
        is_critical = name in CRITICAL_FIELDS

        # Missing entirely from JSON
        if entry is None:
            return FieldValidationResult(
                name=name, status="missing", value=None,
                message=f"Field '{name}' not found in JSON",
                is_critical=is_critical,
            )

        # Null value
        if not entry.is_valid:
            return FieldValidationResult(
                name=name, status="missing", value=None,
                message=f"'{name}' is null (status: {entry.status})",
                is_critical=is_critical,
            )

        value = entry.value
        # Range check
        if name in MEASUREMENT_RANGES:
            lo, hi = MEASUREMENT_RANGES[name]
            if not (lo <= value <= hi):
                return FieldValidationResult(
                    name=name, status="out_of_range", value=value,
                    message=f"'{name}'={value:.2f} is outside plausible range [{lo}, {hi}]",
                    is_critical=is_critical,
                )

        # Low confidence warning
        if entry.confidence is not None and entry.confidence < 0.5:
            return FieldValidationResult(
                name=name, status="low_confidence", value=value,
                message=f"'{name}' has low confidence: {entry.confidence:.2f}",
                is_critical=is_critical,
            )

        return FieldValidationResult(
            name=name, status="ok", value=value,
            message="ok",
            is_critical=is_critical,
        )

    def _check_consistency(self, parsed: ParsedMeasurements, report: ValidationReport) -> None:
        """Check that body measurements are internally consistent."""
        def get(name: str) -> Optional[float]:
            return parsed.get_value(name)

        waist = get("waist_circumference_cm")
        chest = get("chest_circumference_cm")
        hip = get("hip_circumference_cm")
        height = get("height_cm")

        if waist and chest and waist > chest * 1.3:
            report.warnings.append(
                f"Unusual: waist ({waist:.1f}) > 1.3× chest ({chest:.1f})"
            )

        if waist and hip and waist > hip * 1.2:
            report.warnings.append(
                f"Unusual: waist ({waist:.1f}) > 1.2× hip ({hip:.1f})"
            )

        if height and chest:
            # Chest / height ratio typically 0.45–0.65
            ratio = chest / height
            if not (0.4 <= ratio <= 0.8):
                report.warnings.append(
                    f"Unusual chest/height ratio: {ratio:.3f} (expected 0.40–0.80)"
                )

        # Width + depth geometry should be consistent with circumference
        chest_w = get("chest_width_cm")
        chest_d = get("chest_depth_cm")
        chest_circ = get("chest_circumference_cm")
        if chest_w and chest_d and chest_circ:
            import math
            a, b = chest_w / 2, chest_d / 2
            h_ram = ((a - b) ** 2) / ((a + b) ** 2)
            est = math.pi * (a + b) * (1 + (3 * h_ram) / (10 + math.sqrt(4 - 3 * h_ram)))
            diff = abs(est - chest_circ)
            if diff > 8.0:
                report.warnings.append(
                    f"Chest width/depth ({chest_w}×{chest_d} cm) gives estimated circumference "
                    f"{est:.1f} cm, but JSON says {chest_circ:.1f} cm (diff={diff:.1f} cm). "
                    f"Using JSON circumference as authoritative."
                )

    def _check_landmarks(self, parsed: ParsedMeasurements, report: ValidationReport) -> None:
        if not parsed.landmarks:
            report.warnings.append("No landmarks_3d data found — landmark-based positioning disabled")
            return

        if parsed.landmark_coordinate_frame != "world_y_up":
            report.warnings.append(
                f"Unexpected landmark coordinate frame: '{parsed.landmark_coordinate_frame}'. "
                f"Expected 'world_y_up'. Conversion may be incorrect."
            )

        # Check head_top landmark height matches height_cm
        head_top = parsed.landmarks.get("head_top")
        height = parsed.get_value("height_cm")
        if head_top and height:
            diff = abs(head_top.y_cm - height)
            if diff > 3.0:
                report.warnings.append(
                    f"head_top landmark Y ({head_top.y_cm} cm) differs from "
                    f"height_cm ({height} cm) by {diff:.1f} cm"
                )

