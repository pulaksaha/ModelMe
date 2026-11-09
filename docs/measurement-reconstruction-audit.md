# Measurement and reconstruction audit — 2026-11-08

## Scope and evidence

The audited local upload was `input/4d0ff60f-bc31-4e17-9aa2-a0b53c41a6e4.json` (not tracked by Git). It declares schema `1.0.0`, pipeline `aethya-body-v0.1.0`, centimeters, 70 measurement names, 31 landmarks, and capture-quality metadata. The uploaded file is used only for this local audit; no raw user measurement values are checked into the repository.

The repository contains a parser and Blender reconstruction consumer for that format, but no Aethya video/image detector or measurement-generation implementation. Therefore `method` strings below are provenance claims from the input file. ModelMe cannot independently establish that a video was processed, and a field named `video_estimate_plus_scale_anchor` is not evidence of direct image detection.

## Measurement provenance in the audited upload

All 31 `landmarks_3d.points` entries declare `source: reconstruction_model` and confidence `0.95`. Ten explicit left/right landmark pairs have exact reflected coordinates: X coordinates are opposites and Y/Z coordinates match. This is consistent with landmarks generated from a symmetric reconstruction/template; it is not evidence of independently detected person landmarks. The input also contains left/right difference/asymmetry ratio objects, but the original landmark points themselves are perfectly mirrored. The producer that created those objects is absent, so their reliability and relationship to the points cannot be verified.

The measurement entries have 46 flat scalar objects and 24 nested bilateral objects. There are 93 populated scalar/side values and one null field (`weight_kg`). All 93 populated values carry the same confidence `0.93` and uncertainty `1.14 cm`; the null weight has neither. This uniformity appears in the uploaded file metadata, not in ModelMe's measurement detection code. Because the producer code is unavailable, we cannot identify whether these are calibrated estimates, a pipeline-wide default, or copied metadata. ModelMe now preserves these values as supplied and does not create replacement confidence values.

The methods declared by the upload, grouped by source field, are:

- `video_estimate_plus_scale_anchor` (video estimate with a scale anchor claim): `height_cm`. The actual video detector and scale-calibration logic are not in this repository, so the claim is unverified.
- `user_provided_or_scale` (manual value or scale-derived claim): `weight_kg`; the value is null.
- `mesh_cross_section`: `neck_circumference_cm`, `neck_base_circumference_cm`, `head_circumference_cm`, `upper_chest_circumference_cm`, `underbust_circumference_cm`, `abdomen_circumference_cm`, `high_hip_circumference_cm`.
- `mesh_cross_section_with_clothing_offset`: `chest_circumference_cm`, `waist_circumference_cm`, `hip_circumference_cm`.
- `landmark_vertical_difference`: `neck_length_cm`, `shoulder_height_diff_cm`, `waist_height_cm`, `armhole_depth_cm`, `crotch_depth_cm`, `waist_to_hip_cm`, `waist_to_bust_cm`, `waist_to_floor_cm`, `body_rise_cm`.
- `landmark_euclidean_distance`: `shoulder_breadth_cm`, `neck_to_shoulder_cm`.
- `landmark_vector_angle`: `shoulder_slope_deg`.
- `surface_contour_slice`: `back_width_cm`, `front_chest_width_cm`, `back_shoulder_to_shoulder_cm`, `front_shoulder_breadth_cm`.
- `mesh_cross_section_depth`: `chest_depth_cm`, `waist_depth_cm`, `hip_depth_cm`, `torso_depth_cm`.
- `mesh_cross_section_width`: `chest_width_cm`, `waist_width_cm`, `hip_breadth_cm`, `torso_width_cm`.
- `landmark_surface_distance`: `torso_length_cm`.
- `surface_contour_distance`: `front_torso_length_cm`, `back_torso_length_cm`, `shoulder_to_crotch_cm`, `crotch_length_cm`, `front_rise_cm`, `back_rise_cm`.
- `anthropometric_proportion_model`: `sitting_height_cm` (proportion-derived estimate).
- `canonical_t_pose_mesh_distance`: `arm_span_cm`, `arm_reach_cm` (canonical template-derived, not person-specific capture).
- Bilateral `mesh_cross_section`: `upper_arm_circumference_cm`, `biceps_circumference_cm`, `elbow_circumference_cm`, `forearm_circumference_cm`, `wrist_circumference_cm`, `thigh_circumference_cm`, `mid_thigh_circumference_cm`, `knee_circumference_cm`, `calf_circumference_cm`, `ankle_circumference_cm`.
- Bilateral `landmark_euclidean_distance`: `shoulder_to_elbow_cm`, `elbow_to_wrist_cm`, `hand_length_cm`, `hand_breadth_cm`, `hip_to_knee_cm`, `knee_to_ankle_cm`, `foot_length_cm`, `foot_breadth_cm`.
- Bilateral `segment_joint_path`: `shoulder_to_wrist_cm`.
- Bilateral `mesh_surface_loop`: `armhole_circumference_cm`.
- Bilateral `landmark_vertical_difference`: `inseam_cm`.
- Bilateral `landmark_surface_contour`: `outseam_cm`.
- Bilateral `surface_contour_distance`: `crotch_to_waist_front_cm`, `crotch_to_waist_back_cm`.

For every method described as mesh-, landmark-, surface-, contour-, or canonical-mesh-based, the declared landmarks are sourced from `reconstruction_model`; therefore these values are derived from an existing reconstruction/template according to the file's own provenance, not directly captured body measurements. The precise upstream generation algorithm is unavailable.

## Parser/schema corrections

`reconstruction/json_parser.py` previously read only top-level `entry.value`; bilateral shapes such as `hand_length_cm.left.value` therefore appeared null and lost their side values and method metadata. `MeasurementEntry` now stores separate left/right `MeasurementSide` records and offers `get_side_value`. Its scalar `value` and `get_value()` remain null for bilateral-only entries; no averaging is hidden in parsing. Explicit arithmetic mean is used only by the independent validation report when it needs one bilateral target, and that method is named in the report.

Null landmark coordinates previously defaulted to zero, which made unknown locations appear at the origin. The parser now rejects null coordinates. Numeric measurement values must be finite; null remains null. The validator checks bilateral values side-by-side and does not turn them into a scalar. `weight_kg` remains null and optional.

## Base mesh and deformation findings

`assets/base_human/base_human.blend` contains a generic MPFB/MakeHuman `Human` template: 19,158 vertices, 18,486 faces, 165.94 cm base height, 105.10 cm bounding-box width and 43.00 cm depth. It has nine shape keys (Basis plus MPFB gender/ethnicity keys) and a mask modifier. The shape keys are macro/gender/ethnicity settings, not independent chest/waist/limb controls. The asset's redistribution/license provenance is still undocumented.

The existing deformer changes height, shoulder breadth, and smooth torso sections (chest, underbust, waist, abdomen, high hip, hip and neck). Width/depth are only separately targeted where the mapper has those values; otherwise circumference drives both axes. The shoulder operation affects nearby arm vertices as a side effect. There is no independent arm circumference/length, hand, leg length, inseam, thigh, calf or foot deformation control. The model has limb/finger vertex groups, but the current deformer and GLB exporter do not use them to apply per-side measurements. The exporter disables skinning.

## Independent exported-GLB validation

`reconstruction/exported_mesh_validator.py` re-imports the exported GLB and measures that artifact with a separate triangle-plane intersection implementation; it does not call `CrossSectionAnalyzer` or `MeshMeasurementCalculator`. The JSON report is attached under `independent_glb_validation` in each generation report and is served by the existing `/api/reconstruction/report/{job_id}` route.

The report contains target, generated value, absolute error, percentage error, pass/fail, and a method for each requested metric. `arm_span_cm` currently uses exported lateral bounding-box width as an explicitly named proxy. Inseam, thigh and calf generated values are marked unsupported because this mesh has no calibrated crotch/limb section locator; their target is the explicitly documented arithmetic mean of populated bilateral values. Unsupported metrics fail the overall independent check. The target metadata is preserved in each record, so a mesh-derived target is not misrepresented as direct capture.

## Controlled run on the uploaded file

Run command: Blender 5.2.3 background reconstruction on the audited upload, 12 optimization iterations, output under `/private/tmp/modelme-reconstruction-audit/`.

- Parser: 69/70 named fields available (all 24 bilateral entries retained), 31 landmarks; the only null field is optional `weight_kg`.
- The generated mesh differs from the copied base mesh at all 19,158 vertices; maximum point displacement is 28.8828 cm.
- Compared with the original asset dimensions (105.10 × 43.00 × 165.94 cm), the re-imported GLB measures 101.146 × 40.277 × 167.357 cm (width × depth × height). The GLB dimensions, rather than the pre-export object state, are used for the accuracy report.
- Existing mesh integrity check: passed, 0 warnings and 0 errors.
- GLB: generated and re-imported by Blender; 626,148 bytes.
- Existing optimizer: `converged=false` after 12 iterations. This means the pipeline did not converge; it must not be presented as measurements matched.
- Independent GLB checks: failed overall. Chest circumference 92.730 → 94.986 cm (2.256 cm / 2.433%, fail); waist 75.300 → 75.899 cm (0.599 cm / 0.796%, pass); hip 95.840 → 97.371 cm (1.531 cm / 1.598%, fail); shoulder breadth 41.000 → 32.118 cm (8.882 cm / 21.663%, fail); chest width 35.000 → 30.500 cm (4.500 cm / 12.858%, fail); chest depth 24.000 → 20.923 cm (3.077 cm / 12.820%, fail); waist width 29.000 → 25.285 cm (3.715 cm / 12.810%, fail); waist depth 19.000 → 19.116 cm (0.116 cm / 0.608%, pass); hip breadth 36.000 → 32.833 cm (3.167 cm / 8.796%, fail); hip depth 25.000 → 21.396 cm (3.604 cm / 14.414%, fail); height 170.000 → 167.357 cm (2.643 cm / 1.555%, fail); arm-span target 164.000 cm versus 101.146 cm bbox proxy (62.854 cm / 38.326%, fail). Inseam/thigh/calf are unsupported.
- This run proves the current file can pass through parsing, deformation, Blender export and independent GLB re-import. It does not prove person-specific accuracy: most target values in this input are themselves declared mesh/landmark/template-derived. The independent report fails; body accuracy is not accepted.
- Browser/app loading is not verified in this run: local API/Vite/MongoDB processes were not listening, and the direct Blender process cannot exercise React Three Fiber. The frontend's existing report/download links remain present and now label a failed accuracy check accurately. End-to-end browser verification is pending.

## Remaining work before accuracy acceptance

1. Obtain/document the upstream extractor source and calibrate provenance/confidence/uncertainty from real video/image measurements against ground truth.
2. Establish a body-specific canonical landmark model, preserve measured left/right asymmetry, and stop deriving all landmarks from a symmetric reconstruction template.
3. Fix the height metric discrepancy and align the height reference plane, object transforms, optimizer, exported coordinates and validator.
4. Calibrate chest/waist/hip width-depth mapping and improve independent exported slice accuracy against a physical/model ground-truth fixture.
5. Add actual limb station detection and independently adjustable bilateral arms, legs, hands and feet; until then report them unsupported.
6. Verify GLB loading and report retrieval through the running Express → FastAPI route in a browser. This audit did not have the app services running.
7. Document mesh license/provenance and rerun the audit on an authorized, labeled ground-truth fixture.
