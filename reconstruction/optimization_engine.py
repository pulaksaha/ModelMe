"""
Optimisation Engine
===================
Iteratively refines body deformation parameters to minimise measurement error.

Algorithm:
1. Measure current mesh with CrossSectionAnalyzer.
2. Compare against target measurements.
3. Compute per-region error and check tolerance.
4. If out of tolerance, apply damped proportional corrections.
5. Stop when all tolerances are met or max_iterations reached.

Runs INSIDE Blender (uses bpy).

Author: Body Reconstruction Engine
Version: 0.2.0
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class MeasurementComparison:
    """Comparison between target and generated measurement."""
    name: str
    target_cm: float
    generated_cm: float
    tolerance_cm: float
    weight: float = 1.0

    @property
    def difference_cm(self) -> float:
        return self.generated_cm - self.target_cm

    @property
    def absolute_error_cm(self) -> float:
        return abs(self.difference_cm)

    @property
    def percentage_error(self) -> float:
        if self.target_cm == 0:
            return 0.0
        return (self.difference_cm / self.target_cm) * 100.0

    @property
    def within_tolerance(self) -> bool:
        return self.absolute_error_cm <= self.tolerance_cm

    @property
    def status(self) -> str:
        if self.within_tolerance:
            return "within_tolerance"
        elif self.absolute_error_cm <= self.tolerance_cm * 2.0:
            return "near_tolerance"
        else:
            return "out_of_tolerance"


@dataclass
class IterationResult:
    """Result of one optimisation iteration."""
    iteration: int
    comparisons: Dict[str, MeasurementComparison]
    total_weighted_error: float
    converged: bool


@dataclass
class OptimisationReport:
    """Final report from the full optimisation run."""
    session_id: str
    iterations_run: int
    converged: bool
    final_comparisons: Dict[str, MeasurementComparison]
    history: List[IterationResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        result = {
            "session_id": self.session_id,
            "iterations_run": self.iterations_run,
            "converged": self.converged,
            "measurements": {}
        }
        for name, c in self.final_comparisons.items():
            result["measurements"][name] = {
                "target_cm": round(c.target_cm, 2),
                "generated_cm": round(c.generated_cm, 2),
                "difference_cm": round(c.difference_cm, 2),
                "percentage_error": round(c.percentage_error, 2),
                "tolerance_cm": c.tolerance_cm,
                "status": c.status,
                "weight": c.weight,
            }
        return result


class OptimisationEngine:
    """
    Iterative measurement-driven refinement.
    """

    DAMPING = 0.65  # Damping factor to prevent oscillation

    def __init__(self, max_iterations: int = 8, convergence_threshold: float = 0.8):
        self.max_iterations = max_iterations
        self.convergence_threshold = convergence_threshold

    def run(self, obj, plan, calculator, parsed_measurements) -> OptimisationReport:
        from reconstruction.body_deformer import BodyDeformer, REGION_SIGMA

        report = OptimisationReport(
            session_id=plan.session_id,
            iterations_run=0,
            converged=False,
            final_comparisons={},
        )

        TARGET_FIELDS = {
            "chest_circumference_cm":     plan.tolerances.get("chest_circumference_cm", 1.0),
            "waist_circumference_cm":     plan.tolerances.get("waist_circumference_cm", 1.0),
            "hip_circumference_cm":       plan.tolerances.get("hip_circumference_cm", 1.0),
            "underbust_circumference_cm": 1.5,
            "abdomen_circumference_cm":   1.5,
            "high_hip_circumference_cm":  1.5,
        }

        REGION_MAP = {
            "chest_circumference_cm":     ("chest", plan.landmark_heights.chest, REGION_SIGMA["chest"]),
            "underbust_circumference_cm": ("underbust", plan.landmark_heights.underbust, REGION_SIGMA["underbust"]),
            "waist_circumference_cm":     ("waist", plan.landmark_heights.waist, REGION_SIGMA["waist"]),
            "abdomen_circumference_cm":   ("abdomen", plan.landmark_heights.abdomen, REGION_SIGMA["abdomen"]),
            "high_hip_circumference_cm":  ("high_hip", plan.landmark_heights.high_hip, REGION_SIGMA["high_hip"]),
            "hip_circumference_cm":       ("hip", plan.landmark_heights.hip, REGION_SIGMA["hip"]),
        }

        deformer = BodyDeformer(obj, plan)

        for iteration in range(1, self.max_iterations + 1):
            report.iterations_run = iteration

            # Measure current mesh
            mesh_report = calculator.compute(obj, plan)

            comparisons: Dict[str, MeasurementComparison] = {}
            for field_name, tolerance in TARGET_FIELDS.items():
                target = parsed_measurements.get_value(field_name)
                generated = mesh_report.get_value(field_name)
                if target is None or generated is None:
                    continue

                entry = parsed_measurements.get_entry(field_name)
                weight = entry.weight if entry else 0.5
                comparisons[field_name] = MeasurementComparison(
                    name=field_name,
                    target_cm=target,
                    generated_cm=generated,
                    tolerance_cm=tolerance,
                    weight=weight,
                )

            # Check convergence
            all_within = bool(comparisons) and all(c.within_tolerance for c in comparisons.values())
            weighted_err = sum(c.absolute_error_cm * c.weight for c in comparisons.values()) / max(1, sum(c.weight for c in comparisons.values()))

            iter_res = IterationResult(
                iteration=iteration,
                comparisons=comparisons,
                total_weighted_error=weighted_err,
                converged=all_within,
            )
            report.history.append(iter_res)
            logger.info(f"Iteration {iteration}: weighted error = {weighted_err:.2f} cm, converged={all_within}")

            # The weighted average is useful for tracking progress, but it must
            # not mask a badly missed high-priority measurement. Convergence
            # means every available target is inside its own tolerance.
            if all_within:
                report.converged = True
                break

            # Apply corrections for regions out of tolerance
            corrections_applied = 0
            for field_name, c in comparisons.items():
                if c.within_tolerance or field_name not in REGION_MAP:
                    continue

                reg_name, z_m, sigma = REGION_MAP[field_name]
                ratio = c.target_cm / c.generated_cm if c.generated_cm > 1.0 else 1.0
                # Damped correction factor
                correction = 1.0 + (ratio - 1.0) * self.DAMPING
                correction = max(0.85, min(1.15, correction))

                deformer._apply_smooth_scale(
                    z_center=z_m,
                    sigma=sigma,
                    scale_x=correction,
                    scale_y=correction,
                    center_y_m=0.0,
                    torso_half_w_m=0.20,
                )
                corrections_applied += 1

            if corrections_applied == 0:
                break

            obj.data.update()

        # Final evaluation
        final_mesh_report = calculator.compute(obj, plan)
        for field_name, tolerance in TARGET_FIELDS.items():
            target = parsed_measurements.get_value(field_name)
            generated = final_mesh_report.get_value(field_name)
            if target is not None and generated is not None:
                entry = parsed_measurements.get_entry(field_name)
                weight = entry.weight if entry else 0.5
                report.final_comparisons[field_name] = MeasurementComparison(
                    name=field_name,
                    target_cm=target,
                    generated_cm=generated,
                    tolerance_cm=tolerance,
                    weight=weight,
                )

        return report
