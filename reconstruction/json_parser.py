"""
JSON Parser — Measurement File Loader
======================================
Parses anthropometric measurement JSON files produced by the Aethya Body pipeline.
Schema-aware and flexible: does not assume all fields are present.

Author: Body Reconstruction Engine
Version: 0.1.0
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes representing parsed measurement data
# ---------------------------------------------------------------------------

@dataclass
class MeasurementSide:
    """One side of a bilateral measurement, retaining its own provenance."""
    value: Optional[float]
    method: Optional[str] = None
    confidence: Optional[float] = None
    uncertainty_cm: Optional[float] = None
    status: Optional[str] = None


@dataclass
class MeasurementEntry:
    """A single measurement field from the JSON."""
    name: str
    value: Optional[float]
    method: Optional[str]
    confidence: Optional[float]
    uncertainty_cm: Optional[float]
    status: Optional[str]
    sides: Dict[str, MeasurementSide] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        """True if the value is present and not null."""
        return self.value is not None or any(side.value is not None for side in self.sides.values())

    def side_value(self, side: str) -> Optional[float]:
        """Return an explicit bilateral value; never infer an aggregate."""
        item = self.sides.get(side.lower())
        return item.value if item else None

    @property
    def weight(self) -> float:
        """
        Reliability weight for optimisation.
        Higher confidence + lower uncertainty → higher weight.
        Clamp between 0 and 1.
        """
        if not self.is_valid:
            return 0.0
        conf = self.confidence if self.confidence is not None else 0.5
        # Uncertainty penalty: lower uncertainty → higher weight
        # Reference scale: 2 cm uncertainty ≈ 0.5 weight reduction
        unc = self.uncertainty_cm if self.uncertainty_cm is not None else 2.0
        unc_penalty = max(0.0, 1.0 - unc / 10.0)
        return float(min(1.0, conf * unc_penalty))


@dataclass
class LandmarkPoint:
    """A 3D landmark in the JSON coordinate frame (world_y_up, cm)."""
    name: str
    x_cm: float   # lateral (left positive in JSON)
    y_cm: float   # vertical (height) in JSON world_y_up frame
    z_cm: float   # depth (front positive in JSON)
    confidence: Optional[float]
    visibility: str
    source: str

    def to_blender(self) -> Tuple[float, float, float]:
        """
        Convert from JSON world_y_up (cm) to Blender Z-up (metres).
        JSON: X=lateral, Y=height, Z=depth
        Blender: X=lateral, Y=depth, Z=height

        Returns (x_m, y_m, z_m) in Blender coordinates (metres).
        """
        return (
            self.x_cm / 100.0,     # lateral stays X
            self.z_cm / 100.0,     # JSON Z (depth) → Blender Y
            self.y_cm / 100.0,     # JSON Y (height) → Blender Z
        )


@dataclass
class CrossSectionData:
    """Width and depth measurements for a named body cross-section."""
    region: str          # e.g. 'chest', 'waist', 'hip', 'neck'
    width_cm: float
    depth_cm: float

    @property
    def estimated_circumference_cm(self) -> float:
        """
        Approximate circumference using ellipse perimeter formula (Ramanujan approximation).
        Half-axes: a = width/2, b = depth/2
        """
        import math
        a = self.width_cm / 2.0
        b = self.depth_cm / 2.0
        h = ((a - b) ** 2) / ((a + b) ** 2)
        return math.pi * (a + b) * (1 + (3 * h) / (10 + math.sqrt(4 - 3 * h)))


@dataclass
class GenderClassification:
    """Gender classification from the JSON."""
    final_gender: str
    confidence: float
    consensus: str


@dataclass
class ShapeClassification:
    """Body shape classification from the JSON."""
    shape: str         # e.g. "Hourglass"
    shape_code: str    # e.g. "hourglass"
    category_type: str # e.g. "standard_female"


@dataclass
class ParsedMeasurements:
    """
    Complete parsed measurement file.
    All measurement access is by field name.
    Missing measurements are represented as MeasurementEntry with value=None.
    """
    session_id: str
    schema_version: str
    unit: str
    pipeline_version: str

    # Core measurement map: field_name → MeasurementEntry
    measurements: Dict[str, MeasurementEntry] = field(default_factory=dict)

    # Landmarks: landmark_name → LandmarkPoint
    landmarks: Dict[str, LandmarkPoint] = field(default_factory=dict)
    landmark_coordinate_frame: str = "world_y_up"
    landmark_coordinate_unit: str = "cm"

    # Cross-section geometry
    cross_sections: Dict[str, CrossSectionData] = field(default_factory=dict)

    # Ratios (raw dict, flexible)
    ratios: Dict[str, Any] = field(default_factory=dict)

    # Classification
    gender: Optional[GenderClassification] = None
    shape: Optional[ShapeClassification] = None

    # Source file
    source_path: Optional[Path] = None

    # -----------------------------------------------------------------------
    # Convenience accessors
    # -----------------------------------------------------------------------

    def get_value(self, field_name: str) -> Optional[float]:
        """Return a scalar measurement only; bilateral fields have no scalar value."""
        entry = self.measurements.get(field_name)
        return entry.value if entry else None

    def get_entry(self, field_name: str) -> Optional[MeasurementEntry]:
        """Return the full MeasurementEntry or None."""
        return self.measurements.get(field_name)

    def get_side_value(self, field_name: str, side: str) -> Optional[float]:
        """Return a left/right measurement without collapsing the two sides."""
        entry = self.measurements.get(field_name)
        return entry.side_value(side) if entry else None

    def available_measurements(self) -> List[str]:
        """List all measurement field names that have non-null values."""
        return [k for k, v in self.measurements.items() if v.is_valid]

    def missing_measurements(self) -> List[str]:
        """List all measurement field names with null values."""
        return [k for k, v in self.measurements.items() if not v.is_valid]

    def summary(self) -> str:
        """Short human-readable summary."""
        avail = len(self.available_measurements())
        total = len(self.measurements)
        lm = len(self.landmarks)
        gender = self.gender.final_gender if self.gender else "unknown"
        shape = self.shape.shape if self.shape else "unknown"
        return (
            f"Session: {self.session_id} | "
            f"Measurements: {avail}/{total} available | "
            f"Landmarks: {lm} | "
            f"Gender: {gender} | Shape: {shape}"
        )


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class MeasurementJSONParser:
    """
    Flexible parser for Aethya Body anthropometric measurement JSON files.

    Designed to be schema-aware but not schema-strict:
    - Unknown fields are preserved in ratios.
    - Null measurement values are stored as MeasurementEntry(value=None).
    - Missing top-level sections degrade gracefully.
    """

    def parse_file(self, path: str | Path) -> ParsedMeasurements:
        """Load and parse a measurement JSON file from disk."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Measurement file not found: {path}")
        if path.suffix.lower() != ".json":
            raise ValueError(f"Expected .json file, got: {path.suffix}")

        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)

        logger.info(f"Loaded measurement JSON: {path.name}")
        result = self.parse_dict(raw)
        result.source_path = path
        return result

    def parse_dict(self, raw: Dict[str, Any]) -> ParsedMeasurements:
        """Parse a raw dict (e.g. already loaded from JSON)."""
        parsed = ParsedMeasurements(
            session_id=raw.get("session_id", "unknown"),
            schema_version=raw.get("schema_version", "unknown"),
            unit=raw.get("unit", "cm"),
            pipeline_version=raw.get("pipeline_version", "unknown"),
        )

        # Parse measurements
        if "measurements" in raw:
            parsed.measurements = self._parse_measurements(raw["measurements"])

        # Parse landmarks
        if "landmarks_3d" in raw:
            lm_block = raw["landmarks_3d"]
            parsed.landmark_coordinate_frame = lm_block.get("coordinate_frame", "world_y_up")
            parsed.landmark_coordinate_unit = lm_block.get("coordinate_unit", "cm")
            if "points" in lm_block:
                parsed.landmarks = self._parse_landmarks(lm_block["points"])

        # Parse cross-sections from nested ratios path
        if "ratios" in raw:
            parsed.ratios = raw["ratios"]
            parsed.cross_sections = self._parse_cross_sections(raw["ratios"])

        # Parse gender classification
        if "gender_classification" in raw:
            parsed.gender = self._parse_gender(raw["gender_classification"])

        # Parse shape classification
        if "shape_classification" in raw:
            parsed.shape = self._parse_shape(raw["shape_classification"])

        logger.info(parsed.summary())
        return parsed

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _parse_measurements(self, raw_meas: Dict[str, Any]) -> Dict[str, MeasurementEntry]:
        """Parse the measurements block."""
        result: Dict[str, MeasurementEntry] = {}
        for name, entry_data in raw_meas.items():
            if not isinstance(entry_data, dict):
                logger.warning(f"Skipping non-dict measurement entry: {name}")
                continue
            value = self._number(entry_data.get("value"), f"{name}.value")
            sides: Dict[str, MeasurementSide] = {}
            for side_name in ("left", "right"):
                if side_name not in entry_data:
                    continue
                side_data = entry_data[side_name]
                if not isinstance(side_data, dict):
                    raise ValueError(f"{name}.{side_name} must be an object")
                sides[side_name] = MeasurementSide(
                    value=self._number(side_data.get("value"), f"{name}.{side_name}.value"),
                    method=side_data.get("method"),
                    confidence=side_data.get("confidence"),
                    uncertainty_cm=side_data.get("uncertainty_cm"),
                    status=side_data.get("status"),
                )

            result[name] = MeasurementEntry(
                name=name,
                value=value,
                method=entry_data.get("method"),
                confidence=entry_data.get("confidence"),
                uncertainty_cm=entry_data.get("uncertainty_cm"),
                status=entry_data.get("status"),
                sides=sides,
            )
        return result

    @staticmethod
    def _number(raw_value: Any, label: str) -> Optional[float]:
        """Convert a present numeric value; preserve null and reject malformed values."""
        if raw_value is None:
            return None
        try:
            import math
            value = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label} must be numeric or null") from exc
        if not math.isfinite(value):
            raise ValueError(f"{label} must be finite")
        return value

    def _parse_landmarks(self, raw_points: Dict[str, Any]) -> Dict[str, LandmarkPoint]:
        """Parse landmarks_3d.points block."""
        result: Dict[str, LandmarkPoint] = {}
        for name, pt in raw_points.items():
            if not isinstance(pt, dict):
                continue
            # A missing coordinate is unknown, not the origin.
            if any(pt.get(axis) is None for axis in ("x", "y", "z")):
                raise ValueError(f"landmarks_3d.points.{name} requires non-null x, y, and z")
            x = pt["x"]
            y = pt["y"]
            z = pt["z"]
            try:
                x, y, z = float(x), float(y), float(z)
            except (TypeError, ValueError):
                logger.warning(f"Cannot parse landmark coords for {name}: {pt}")
                continue

            result[name] = LandmarkPoint(
                name=name,
                x_cm=x,
                y_cm=y,
                z_cm=z,
                confidence=self._number(pt.get("confidence"), f"landmarks_3d.points.{name}.confidence"),
                visibility=pt.get("visibility", "unknown"),
                source=pt.get("source", "unknown"),
            )
        return result

    def _parse_cross_sections(self, ratios: Dict[str, Any]) -> Dict[str, CrossSectionData]:
        """
        Extract cross-section width/depth data.
        Location: ratios → body_shape_features → torso_cross_sections_cm
        """
        result: Dict[str, CrossSectionData] = {}
        bsf = ratios.get("body_shape_features", {})
        if not isinstance(bsf, dict):
            return result

        cs = bsf.get("torso_cross_sections_cm", {})
        if not isinstance(cs, dict):
            return result

        for region, dims in cs.items():
            if not isinstance(dims, dict):
                continue
            w = dims.get("width")
            d = dims.get("depth")
            if w is not None and d is not None:
                try:
                    result[region] = CrossSectionData(
                        region=region,
                        width_cm=float(w),
                        depth_cm=float(d),
                    )
                except (TypeError, ValueError):
                    logger.warning(f"Cannot parse cross-section for {region}: {dims}")

        return result

    def _parse_gender(self, raw: Dict[str, Any]) -> GenderClassification:
        return GenderClassification(
            final_gender=raw.get("final_gender", "unknown"),
            confidence=float(raw.get("overall_confidence", 0.5)),
            consensus=raw.get("consensus", "unknown"),
        )

    def _parse_shape(self, raw: Dict[str, Any]) -> ShapeClassification:
        return ShapeClassification(
            shape=raw.get("shape", "unknown"),
            shape_code=raw.get("shape_code", "unknown"),
            category_type=raw.get("category_type", "unknown"),
        )


# ---------------------------------------------------------------------------
# Module-level convenience function
# ---------------------------------------------------------------------------

def load_measurements(path: str | Path) -> ParsedMeasurements:
    """Convenience function to parse a measurement JSON file."""
    return MeasurementJSONParser().parse_file(path)

