"""
Blender Reconstruction Script
==============================
Entry point for Blender background-mode reconstruction.

Usage:
    /Applications/Blender.app/Contents/MacOS/Blender \
        --background assets/base_human/base_human.blend \
        --python blender/reconstruct.py \
        -- \
        --json_path /path/to/measurements.json \
        --output_dir /path/to/output \
        --job_id some_unique_id

The script:
1. Opens the clean base human .blend file.
2. Duplicates the Human mesh (never modifies the original).
3. Reads and validates the measurement JSON.
4. Maps measurements to deformation parameters.
5. Applies body deformation.
6. Runs optimisation loop.
7. Validates the mesh.
8. Exports GLB.
9. Saves validation report JSON.
10. Prints STATUS:SUCCESS or STATUS:FAILED to stdout.

Exit codes:
    0 = success
    1 = failure

Author: Body Reconstruction Engine
Version: 0.1.0
"""

import sys
import os
import argparse
import json
import logging
import traceback
from pathlib import Path

# ---------------------------------------------------------------------------
# Configure logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("reconstruct")


def parse_args():
    """Parse arguments after the '--' separator Blender uses."""
    # Blender passes its own args before '--'; ours come after
    if "--" in sys.argv:
        argv = sys.argv[sys.argv.index("--") + 1:]
    else:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(description="Body Reconstruction Script")
    parser.add_argument("--json_path",   required=True, help="Path to measurements JSON file")
    parser.add_argument("--output_dir",  required=True, help="Output directory for GLB and report")
    parser.add_argument("--job_id",      required=True, help="Unique job identifier")
    parser.add_argument("--project_root", default=None, help="Project root directory (for imports)")
    parser.add_argument("--max_iterations", type=int, default=12, help="Max optimisation iterations")
    return parser.parse_args(argv)


def setup_import_path(project_root: str):
    """Add the project root to sys.path so reconstruction modules can be imported."""
    root = Path(project_root) if project_root else Path(__file__).parent.parent
    root_str = str(root.resolve())
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    logger.info(f"Import path: {root_str}")


def report_progress(stage: str, pct: int, job_id: str, output_dir: Path):
    """Write a progress file for the backend to read."""
    progress = {"stage": stage, "progress": pct, "job_id": job_id}
    progress_path = output_dir / f"{job_id}_progress.json"
    try:
        progress_path.write_text(json.dumps(progress))
    except Exception:
        pass
    logger.info(f"[{pct:3d}%] {stage}")


def main():
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    setup_import_path(args.project_root)

    # Import reconstruction modules (inside Blender Python context)
    from reconstruction.json_parser import load_measurements
    from reconstruction.measurement_validator import MeasurementValidator
    from reconstruction.body_parameter_mapper import BodyParameterMapper
    from reconstruction.body_deformer import BodyDeformer
    from reconstruction.measurement_calculator import MeshMeasurementCalculator
    from reconstruction.optimization_engine import OptimisationEngine
    from reconstruction.mesh_validator import MeshValidator
    from reconstruction.model_exporter import ModelExporter

    import bpy
    import mathutils

    job_id = args.job_id
    glb_path = output_dir / f"{job_id}.glb"
    report_path = output_dir / f"{job_id}_validation.json"
    result_path = output_dir / f"{job_id}_result.json"

    try:
        # -------------------------------------------------------------------
        # Stage 1: Parse and validate JSON
        # -------------------------------------------------------------------
        report_progress("Reading measurement JSON", 5, job_id, output_dir)
        parsed = load_measurements(args.json_path)

        report_progress("Validating measurements", 10, job_id, output_dir)
        validator = MeasurementValidator()
        val_report = validator.validate(parsed)

        if not val_report.is_valid:
            critical_missing = val_report.missing_critical()
            raise ValueError(f"Measurement validation failed. Critical fields missing: {critical_missing}")

        if val_report.warnings:
            for w in val_report.warnings:
                logger.warning(f"  Validation warning: {w}")

        # -------------------------------------------------------------------
        # Stage 2: Map measurements to deformation plan
        # -------------------------------------------------------------------
        report_progress("Preparing deformation plan", 15, job_id, output_dir)
        mapper = BodyParameterMapper()
        plan = mapper.map(parsed)
        plan.tolerances["chest_circumference_cm"] = 1.0
        plan.tolerances["waist_circumference_cm"] = 1.0
        plan.tolerances["hip_circumference_cm"] = 1.0

        # -------------------------------------------------------------------
        # Stage 3: Set up reconstruction mesh
        # -------------------------------------------------------------------
        report_progress("Preparing human template", 20, job_id, output_dir)

        # Find the Human base object (never modify it)
        base_obj = bpy.data.objects.get("Human")
        if base_obj is None:
            raise RuntimeError(
                "Object 'Human' not found in base_human.blend. "
                "Check that the correct .blend file was loaded."
            )

        # Remove any previous reconstruction object
        recon_name = "Human_Reconstruction"
        existing = bpy.data.objects.get(recon_name)
        if existing:
            bpy.data.objects.remove(existing, do_unlink=True)
            logger.info(f"Removed existing '{recon_name}' object")

        # Duplicate the base Human mesh
        recon_obj = base_obj.copy()
        recon_obj.data = base_obj.data.copy()
        recon_obj.name = recon_name
        recon_obj.data.name = f"{recon_name}_mesh"

        # Place it at origin, clear scale
        recon_obj.location = (0, 0, 0)
        # Do NOT apply scale here — we want world scale to be 1:1 in metres

        bpy.context.collection.objects.link(recon_obj)
        bpy.context.view_layer.objects.active = recon_obj
        recon_obj.select_set(True)

        # Apply object scale to mesh data so vertex positions are in world space
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        base_coordinates = [tuple(v.co) for v in recon_obj.data.vertices]
        base_bounds = {
            "width_cm": base_obj.dimensions.x * 100,
            "depth_cm": base_obj.dimensions.y * 100,
            "height_cm": base_obj.dimensions.z * 100,
        }

        logger.info(
            f"Reconstruction object created: '{recon_name}' "
            f"({len(recon_obj.data.vertices)} verts)"
        )

        # -------------------------------------------------------------------
        # Stage 4: Apply deformation
        # -------------------------------------------------------------------
        report_progress("Applying body deformation", 30, job_id, output_dir)
        deformer = BodyDeformer(recon_obj, plan)
        deformer.apply_all()
        changed_vertices = 0
        max_vertex_displacement_m = 0.0
        for before, vertex in zip(base_coordinates, recon_obj.data.vertices):
            displacement = (mathutils.Vector(before) - vertex.co).length
            if displacement > 1e-6:
                changed_vertices += 1
            max_vertex_displacement_m = max(max_vertex_displacement_m, displacement)

        # -------------------------------------------------------------------
        # Stage 5: Optimisation loop
        # -------------------------------------------------------------------
        report_progress("Optimising body dimensions", 50, job_id, output_dir)
        calculator = MeshMeasurementCalculator()
        engine = OptimisationEngine(max_iterations=args.max_iterations)
        opt_report = engine.run(recon_obj, plan, calculator, parsed)

        logger.info(f"Optimisation: {opt_report.iterations_run} iterations, converged={opt_report.converged}")

        # -------------------------------------------------------------------
        # Stage 6: Final measurement report
        # -------------------------------------------------------------------
        report_progress("Computing final measurements", 70, job_id, output_dir)
        final_mesh_report = calculator.compute(recon_obj, plan)

        # Build validation comparison report
        full_report = opt_report.to_dict()
        full_report["final_mesh_measurements"] = {
            k: {"value_cm": round(v.value_cm, 4), "method": v.method}
            for k, v in final_mesh_report.measurements.items()
        }
        full_report["shape_key_settings"] = plan.shape_keys.values
        full_report["deformation_sources"] = {
            r_name: r.source for r_name, r in plan.regions.items()
        }

        # -------------------------------------------------------------------
        # Stage 7: Mesh validation
        # -------------------------------------------------------------------
        report_progress("Validating mesh geometry", 80, job_id, output_dir)
        mesh_val = MeshValidator()
        mesh_val_result = mesh_val.validate(recon_obj)

        full_report["mesh_validation"] = {
            "passed": mesh_val_result.passed,
            "warnings": mesh_val_result.warnings,
            "errors": mesh_val_result.errors,
        }

        if not mesh_val_result.passed:
            raise RuntimeError(
                f"Mesh validation failed: {mesh_val_result.errors}"
            )

        # -------------------------------------------------------------------
        # Stage 8: Export GLB
        # -------------------------------------------------------------------
        report_progress("Exporting GLB", 90, job_id, output_dir)
        exporter = ModelExporter()
        export_result = exporter.export(recon_obj, glb_path)

        if not export_result.success:
            raise RuntimeError(f"GLB export failed: {export_result.error}")

        full_report["export"] = export_result.to_dict()
        full_report["geometry_change"] = {
            "source_vertex_count": len(base_coordinates),
            "changed_vertex_count": changed_vertices,
            "max_vertex_displacement_cm": round(max_vertex_displacement_m * 100, 4),
            "base_mesh_dimensions_cm": {k: round(v, 3) for k, v in base_bounds.items()},
            "comparison": "copied base Human mesh coordinates before deformation versus reconstructed mesh coordinates before export",
        }
        from reconstruction.exported_mesh_validator import validate_exported_glb
        full_report["independent_glb_validation"] = validate_exported_glb(
            glb_path, parsed, plan
        )
        full_report["geometry_change"]["exported_glb_dimensions_cm"] = full_report["independent_glb_validation"]["mesh_dimensions_cm"]

        # -------------------------------------------------------------------
        # Stage 9: Save reports
        # -------------------------------------------------------------------
        exporter.save_validation_report(full_report, report_path)

        # Write final result file
        result = {
            "status": "success",
            "job_id": job_id,
            "glb_path": str(glb_path),
            "report_path": str(report_path),
            "converged": opt_report.converged,
            "iterations": opt_report.iterations_run,
            "independent_validation_passed": full_report["independent_glb_validation"]["passed"],
            "geometry_change": full_report["geometry_change"],
            "measurements": {
                k: {
                    "target_cm": c.target_cm,
                    "generated_cm": c.generated_cm,
                    "difference_cm": round(c.difference_cm, 4),
                    "percentage_error": round(c.percentage_error, 2),
                    "status": c.status,
                }
                for k, c in opt_report.final_comparisons.items()
            }
        }
        result_path.write_text(json.dumps(result, indent=2))
        report_progress("Complete", 100, job_id, output_dir)

        print(f"STATUS:SUCCESS:{job_id}")
        logger.info(f"Reconstruction complete. GLB: {glb_path}")
        sys.exit(0)

    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"
        logger.error(f"Reconstruction FAILED: {error_msg}")
        logger.error(traceback.format_exc())

        # Write failure result
        result = {
            "status": "failed",
            "job_id": job_id,
            "error": error_msg,
            "traceback": traceback.format_exc(),
        }
        try:
            result_path.write_text(json.dumps(result, indent=2))
        except Exception:
            pass

        report_progress("Failed", -1, job_id, output_dir)
        print(f"STATUS:FAILED:{job_id}:{error_msg}")
        sys.exit(1)


if __name__ == "__main__":
    main()

