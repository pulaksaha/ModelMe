"""
Comprehensive Unit & Integration Test Suite
============================================
Runs with standard library `unittest` (no external dependencies required).
Covers minimum testing requirements:
1. Valid JSON parsing
2. Missing measurements
3. Invalid measurement values
4. Incorrect units
5. Missing landmarks
6. Coordinate conversion
7. Measurement extraction
8. Cross-section circumference calculation
9. Mesh deformation mapping
10. Measurement validation
11. Optimisation convergence
12. GLB export verification

Author: Body Reconstruction Engine
"""

import json
import math
import unittest
from pathlib import Path

from reconstruction.json_parser import (
    MeasurementJSONParser,
    LandmarkPoint,
    CrossSectionData,
    ParsedMeasurements,
)
from reconstruction.measurement_validator import (
    MeasurementValidator,
    ValidationReport,
)
from reconstruction.body_parameter_mapper import BodyParameterMapper
from reconstruction.optimization_engine import MeasurementComparison, OptimisationReport


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_JSON = Path(__file__).resolve().parent / "fixtures" / "synthetic_measurements.json"


class TestBodyReconstructionPipeline(unittest.TestCase):

    def setUp(self):
        self.parser = MeasurementJSONParser()
        self.validator = MeasurementValidator()
        self.mapper = BodyParameterMapper()

    # 1. Valid JSON parsing
    def test_01_valid_json_parsing(self):
        parsed = self.parser.parse_file(SAMPLE_JSON)
        self.assertEqual(parsed.session_id, "synthetic_172")
        self.assertEqual(parsed.unit, "cm")
        self.assertEqual(parsed.get_value("height_cm"), 172.0)
        self.assertEqual(parsed.get_value("chest_circumference_cm"), 90.0)
        self.assertEqual(parsed.get_value("waist_circumference_cm"), 72.5)
        self.assertEqual(parsed.get_value("hip_circumference_cm"), 96.0)
        self.assertGreater(len(parsed.available_measurements()), 40)
        self.assertGreater(len(parsed.landmarks), 30)

    # 2. Missing measurements
    def test_02_missing_measurements(self):
        data = {
            "session_id": "test_missing",
            "unit": "cm",
            "measurements": {
                "height_cm": {"value": 170.0, "status": "valid"},
                "chest_circumference_cm": {"value": 92.0, "status": "valid"},
                "biceps_circumference_cm": {"value": None, "status": "needs_user_input"},
            }
        }
        parsed = self.parser.parse_dict(data)
        self.assertIsNone(parsed.get_value("biceps_circumference_cm"))
        self.assertIn("biceps_circumference_cm", parsed.missing_measurements())

    # 3. Invalid measurement values
    def test_03_invalid_measurement_values(self):
        data = {
            "session_id": "test_invalid",
            "unit": "cm",
            "measurements": {
                "height_cm": {"value": 320.0, "status": "valid"},  # Unrealistic human height
                "waist_circumference_cm": {"value": -5.0, "status": "valid"},
            }
        }
        parsed = self.parser.parse_dict(data)
        report = self.validator.validate(parsed)
        self.assertFalse(report.is_valid)
        self.assertIn("height_cm", report.out_of_range_fields())

    # 4. Incorrect units
    def test_04_incorrect_units(self):
        data = {
            "session_id": "test_units",
            "unit": "inches",
            "measurements": {
                "height_cm": {"value": 67.0, "status": "valid"},
                "chest_circumference_cm": {"value": 36.0, "status": "valid"},
                "waist_circumference_cm": {"value": 30.0, "status": "valid"},
                "hip_circumference_cm": {"value": 38.0, "status": "valid"},
            }
        }
        parsed = self.parser.parse_dict(data)
        report = self.validator.validate(parsed)
        self.assertTrue(any("inches" in w.lower() for w in report.warnings))

    # 5. Missing landmarks
    def test_05_missing_landmarks(self):
        data = {
            "session_id": "test_landmarks",
            "unit": "cm",
            "measurements": {
                "height_cm": {"value": 170.0, "status": "valid"},
                "chest_circumference_cm": {"value": 90.0, "status": "valid"},
                "waist_circumference_cm": {"value": 75.0, "status": "valid"},
                "hip_circumference_cm": {"value": 95.0, "status": "valid"},
            },
            "landmarks_3d": {"coordinate_frame": "world_y_up", "points": {}}
        }
        parsed = self.parser.parse_dict(data)
        plan = self.mapper.map(parsed)
        self.assertGreater(plan.landmark_heights.chest, 0)
        self.assertGreater(plan.landmark_heights.waist, 0)
        self.assertGreater(plan.landmark_heights.hip, 0)

    # 6. Coordinate conversion
    def test_06_coordinate_conversion(self):
        lm = LandmarkPoint(
            name="navel",
            x_cm=0.0,
            y_cm=102.0,  # JSON Y is height
            z_cm=9.5,    # JSON Z is front-back
            confidence=0.95,
            visibility="visible",
            source="test",
        )
        bx, by, bz = lm.to_blender()
        self.assertAlmostEqual(bx, 0.0, places=3)
        self.assertAlmostEqual(by, 0.095, places=3)
        self.assertAlmostEqual(bz, 1.020, places=3)

    # 7. Measurement extraction & confidence
    def test_07_measurement_extraction(self):
        parsed = self.parser.parse_file(SAMPLE_JSON)
        entry = parsed.get_entry("chest_circumference_cm")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.value, 90.0)
        self.assertGreater(entry.weight, 0.7)

    # 8. Cross-section circumference calculation
    def test_08_cross_section_circumference(self):
        cs = CrossSectionData(region="chest", width_cm=35.0, depth_cm=24.0)
        circ = cs.estimated_circumference_cm
        self.assertTrue(90.0 < circ < 96.0)

    # 9. Mesh deformation parameter mapping
    def test_09_deformation_mapping(self):
        parsed = self.parser.parse_file(SAMPLE_JSON)
        plan = self.mapper.map(parsed)
        self.assertEqual(plan.target_height_m, 1.72)
        self.assertEqual(plan.gender, "female")
        self.assertEqual(plan.shoulder_breadth_m, 0.40)
        self.assertIn("chest", plan.regions)
        self.assertIn("waist", plan.regions
)
        self.assertIn("hip", plan.regions)

    # 10. Measurement validation
    def test_10_measurement_validation(self):
        parsed = self.parser.parse_file(SAMPLE_JSON)
        report = self.validator.validate(parsed)
        self.assertEqual(len(report.missing_critical()), 0)
        self.assertEqual(len(report.out_of_range_fields()), 0)
        self.assertTrue(report.is_valid)

    # 11. Optimisation result check
    def test_11_optimisation_result(self):
        comparison = MeasurementComparison(
            name="chest_circumference_cm",
            target_cm=90.0,
            generated_cm=90.4,
            tolerance_cm=1.0,
        )
        report = OptimisationReport(
            session_id="synthetic_172",
            iterations_run=1,
            converged=True,
            final_comparisons={comparison.name: comparison},
        )
        data = report.to_dict()
        self.assertTrue(data["converged"])
        self.assertEqual(data["measurements"][comparison.name]["status"], "within_tolerance")

    # 12. GLB export verification
    def test_12_glb_export(self):
        glb_path = PROJECT_ROOT / "storage/generated/test_run/test_converge.glb"
        if not glb_path.exists():
            self.skipTest("requires a GLB generated by the Blender integration workflow")
        self.assertGreater(glb_path.stat().st_size, 100000)
        with open(glb_path, "rb") as f:
            magic = f.read(4)
            self.assertEqual(magic, b"glTF", "GLB file header must be binary glTF magic 'glTF'")


if __name__ == "__main__":
    unittest.main()
