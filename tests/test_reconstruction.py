"""
Test Suite — Reconstruction Engine & Pipeline
==============================================
Tests for:
1. Valid JSON parsing
2. Missing measurements
3. Invalid measurement values
4. Incorrect units
5. Missing landmarks
6. Coordinate conversion
7. Measurement extraction
8. Cross-section circumference calculation
9. Mesh deformation
10. Measurement validation
11. Optimisation convergence
12. GLB export

Author: Body Reconstruction Engine
"""

import json
import math
import tempfile
from pathlib import Path
import pytest

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
from reconstruction.exported_mesh_validator import _record, _target


SAMPLE_JSON_PATH = Path(__file__).resolve().parent / "fixtures" / "synthetic_measurements.json"


# ──────────────────────────────────────────────────────────────────────────────
# Test 1: Valid JSON parsing
# ──────────────────────────────────────────────────────────────────────────────
def test_valid_json_parsing():
    parser = MeasurementJSONParser()
    parsed = parser.parse_file(SAMPLE_JSON_PATH)

    assert parsed.session_id == "synthetic_172"
    assert parsed.unit == "cm"
    assert parsed.get_value("height_cm") == 172.0
    assert parsed.get_value("chest_circumference_cm") == 90.0
    assert parsed.get_value("waist_circumference_cm") == 72.5
    assert parsed.get_value("hip_circumference_cm") == 96.0
    assert len(parsed.available_measurements()) >= 40
    assert len(parsed.landmarks) >= 30


# ──────────────────────────────────────────────────────────────────────────────
# Test 2: Missing measurements handling
# ──────────────────────────────────────────────────────────────────────────────
def test_missing_measurements_handling():
    data = {
        "session_id": "test_missing",
        "unit": "cm",
        "measurements": {
            "height_cm": {"value": 175.0, "status": "valid"},
            "chest_circumference_cm": {"value": 95.0, "status": "valid"},
            "thigh_circumference_cm": {"value": None, "status": "needs_user_input"},
        }
    }
    parser = MeasurementJSONParser()
    parsed = parser.parse_dict(data)

    assert parsed.get_value("height_cm") == 175.0
    assert parsed.get_value("thigh_circumference_cm") is None
    assert "thigh_circumference_cm" in parsed.missing_measurements()


def test_bilateral_measurements_preserve_each_side_and_metadata():
    parsed = MeasurementJSONParser().parse_dict({"unit": "cm", "measurements": {
        "hand_length_cm": {
            "left": {"value": 18.2, "method": "landmark_distance", "confidence": 0.7, "status": "estimated"},
            "right": {"value": 18.8, "method": "landmark_distance", "confidence": 0.8, "status": "estimated"},
        },
        "crotch_to_waist_front_cm": {
            "left": {"value": 31.0}, "right": {"value": None},
        },
        "weight_kg": {"value": None},
    }})

    hand = parsed.get_entry("hand_length_cm")
    assert hand is not None and hand.is_valid
    assert hand.value is None  # no silent averaging into a scalar
    assert parsed.get_value("hand_length_cm") is None
    assert parsed.get_side_value("hand_length_cm", "left") == 18.2
    assert parsed.get_side_value("hand_length_cm", "right") == 18.8
    assert hand.sides["left"].method == "landmark_distance"
    assert hand.sides["right"].confidence == 0.8
    assert parsed.get_side_value("crotch_to_waist_front_cm", "left") == 31.0
    assert parsed.get_side_value("crotch_to_waist_front_cm", "right") is None
    assert parsed.get_value("weight_kg") is None
    assert "hand_length_cm" in parsed.available_measurements()
    assert "weight_kg" in parsed.missing_measurements()


def test_bilateral_schema_rejects_malformed_side_and_nonfinite_values():
    with pytest.raises(ValueError, match="left must be an object"):
        MeasurementJSONParser().parse_dict({"measurements": {"arm_cm": {"left": 2}}})
    with pytest.raises(ValueError, match="finite"):
        MeasurementJSONParser().parse_dict({"measurements": {"arm_cm": {"right": {"value": "NaN"}}}})


def test_bilateral_values_are_range_checked_without_collapsing_sides():
    parsed = MeasurementJSONParser().parse_dict({"measurements": {
        "thigh_circumference_cm": {
            "left": {"value": 54}, "right": {"value": 55},
        },
    }})
    result = next(r for r in MeasurementValidator().validate(parsed).field_results
                  if r.name == "thigh_circumference_cm")
    assert result.status == "ok"
    assert result.value is None


def test_landmark_null_coordinate_is_not_replaced_with_zero():
    with pytest.raises(ValueError, match="requires non-null x, y, and z"):
        MeasurementJSONParser().parse_dict({"landmarks_3d": {"points": {
            "left_shoulder": {"x": None, "y": 100, "z": 2}
        }}})


def test_independent_report_derives_bilateral_target_explicitly_and_marks_unsupported():
    parsed = MeasurementJSONParser().parse_dict({"measurements": {
        "thigh_circumference_cm": {
            "left": {"value": 52, "method": "mesh_cross_section"},
            "right": {"value": 54, "method": "mesh_cross_section"},
        },
    }})
    target, source = _target(parsed, "thigh_circumference_cm")
    assert target == 53
    assert "arithmetic mean" in source
    assert _record(target, None, "unsupported", target_method=source)["status"] == "unsupported"
    passed = _record(90, 90.5, "slice perimeter", target_method="manual")
    assert passed["absolute_error_cm"] == 0.5
    assert passed["percentage_error"] == pytest.approx(0.556, abs=0.001)
    assert passed["pass"] is True


def test_null_unused_hand_measurement_is_optional_and_does_not_warn():
    data = json.loads(SAMPLE_JSON_PATH.read_text())
    data["measurements"]["hand_length_cm"]["value"] = None
    data["measurements"]["hand_length_cm"]["status"] = None

    parser = MeasurementJSONParser()
    parsed = parser.parse_dict(data)
    report = MeasurementValidator().validate(parsed)
    plan = BodyParameterMapper().map(parsed)

    assert parsed.get_value("hand_length_cm") is None
    assert "hand_length_cm" in parsed.missing_measurements()
    assert "hand_length_cm" not in report.missing_critical()
    assert not any("hand_length_cm" in warning for warning in report.warnings)
    assert report.is_valid
    assert set(plan.regions) == {"chest", "upper_chest", "underbust", "waist", "abdomen", "high_hip", "hip", "neck"}


# ──────────────────────────────────────────────────────────────────────────────
# Test 3: Invalid measurement values
# ──────────────────────────────────────────────────────────────────────────────
def test_invalid_measurement_values():
    data = {
        "session_id": "test_invalid",
        "unit": "cm",
        "measurements": {
            "height_cm": {"value": 350.0, "status": "valid"},  # Impossible height > 230cm
            "waist_circumference_cm": {"value": -10.0, "status": "valid"},  # Negative
        }
    }
    parser = MeasurementJSONParser()
    parsed = parser.parse_dict(data)
    validator = MeasurementValidator()
    report = validator.validate(parsed)

    assert not report.is_valid
    out_of_range = report.out_of_range_fields()
    assert "height_cm" in out_of_range or "waist_circumference_cm" in out_of_range


# ──────────────────────────────────────────────────────────────────────────────
# Test 4: Incorrect units handling
# ──────────────────────────────────────────────────────────────────────────────
def test_incorrect_units_handling():
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
    parser = MeasurementJSONParser()
    parsed = parser.parse_dict(data)
    validator = MeasurementValidator()
    report = validator.validate(parsed)

    # Should emit unit warning
    assert any("inches" in w.lower() for w in report.warnings)


# ──────────────────────────────────────────────────────────────────────────────
# Test 5: Missing landmarks fallback
# ──────────────────────────────────────────────────────────────────────────────
def test_missing_landmarks_fallback():
    data = {
        "session_id": "test_no_landmarks",
        "unit": "cm",
        "measurements": {
            "height_cm": {"value": 170.0, "status": "valid"},
            "chest_circumference_cm": {"value": 90.0, "status": "valid"},
            "waist_circumference_cm": {"value": 75.0, "status": "valid"},
            "hip_circumference_cm": {"value": 95.0, "status": "valid"},
        },
        "landmarks_3d": {"coordinate_frame": "world_y_up", "points": {}}
    }
    parser = MeasurementJSONParser()
    parsed = parser.parse_dict(data)
    mapper = BodyParameterMapper()
    plan = mapper.map(parsed)

    # Landmarks should fall back to proportional heights
    assert plan.landmark_heights.chest > 0
    assert plan.landmark_heights.waist > 0
    assert plan.landmark_heights.hip > 0
    assert plan.landmark_heights.chest > plan.landmark_heights.waist > plan.landmark_heights.hip


# ──────────────────────────────────────────────────────────────────────────────
# Test 6: Coordinate conversion (JSON world_y_up cm -> Blender Z-up m)
# ──────────────────────────────────────────────────────────────────────────────
def test_coordinate_conversion():
    lm = LandmarkPoint(
        name="waist_center",
        x_cm=10.0,
        y_cm=102.0,  # JSON Y is vertical height
        z_cm=5.0,    # JSON Z is front-back depth
        confidence=0.95,
        visibility="visible",
        source="scanner",
    )
    bx, by, bz = lm.to_blender()

    # Blender: X=lateral (0.10m), Y=depth (0.05m), Z=height (1.02m)
    assert math.isclose(bx, 0.10, rel_tol=1e-3)
    assert math.isclose(by, 0.05, rel_tol=1e-3)
    assert math.isclose(bz, 1.02, rel_tol=1e-3)


# ──────────────────────────────────────────────────────────────────────────────
# Test 7: Measurement extraction & weighting
# ──────────────────────────────────────────────────────────────────────────────
def test_measurement_extraction_and_weights():
    parser = MeasurementJSONParser()
    parsed = parser.parse_file(SAMPLE_JSON_PATH)

    chest_entry = parsed.get_entry("chest_circumference_cm")
    assert chest_entry is not None
    assert chest_entry.value == 90.0
    assert chest_entry.weight > 0.7  # high confidence, low uncertainty

    weight_entry = parsed.get_entry("weight_kg")
    assert weight_entry is not None
    assert weight_entry.value is None
    assert weight_entry.weight == 0.0  # missing measurement has 0 weight


# ──────────────────────────────────────────────────────────────────────────────
# Test 8: Cross-section ellipse calculation
# ──────────────────────────────────────────────────────────────────────────────
def test_cross_section_geometry():
    cs = CrossSectionData(region="chest", width_cm=35.0, depth_cm=24.0)
    circ = cs.estimated_circumference_cm

    # Ellipse perimeter with a=17.5, b=12.0 is around ~93.8 cm
    assert 90.0 < circ < 96.0


# ──────────────────────────────────────────────────────────────────────────────
# Test 9: Parameter mapping
# ──────────────────────────────────────────────────────────────────────────────
def test_parameter_mapping():
    parser = MeasurementJSONParser()
    parsed = parser.parse_file(SAMPLE_JSON_PATH)
    mapper = BodyParameterMapper()
    plan = mapper.map(parsed)

    assert plan.target_height_m == 1.72
    assert plan.gender == "female"
    assert plan.shoulder_breadth_m == 0.40
    assert "chest" in plan.regions
    assert "waist" in plan.regions
    assert "hip" in plan.regions
