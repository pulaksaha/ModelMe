"""
Body Reconstruction Engine
==========================
Modular pipeline for anthropometric 3D human body reconstruction.

Modules:
    json_parser            – Parse and validate measurement JSON files
    measurement_validator  – Validate measurement values and units
    body_parameter_mapper  – Map JSON measurements to deformation parameters
    body_deformer          – Vertex-level mesh deformation
    landmark_adjuster      – Landmark-based anatomical positioning
    cross_section_analyzer – Horizontal mesh cross-section measurement
    measurement_calculator – Compute measurements from 3D mesh
    optimization_engine    – Iterative measurement refinement
    mesh_validator         – Post-deformation mesh sanity checks
    model_exporter         – GLB export utilities
"""

__version__ = "0.1.0"

