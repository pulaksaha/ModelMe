# Temporary Reconstruction Service Contract

This contract describes the existing FastAPI interface behind the Express API gateway. It is a migration bridge, not the final authenticated job API. The Python service is reachable directly at port `8000` for local development and is internal-only in Compose. Browser clients should call Express at `/api`.

## Health

- `GET /api/health` returns HTTP 200 with `status`, `blender_found`, `base_blend_found`, `blender_path`, and `base_blend`.
- `status` is `ok` only when both Blender and the configured base `.blend` file exist; otherwise it is `degraded`.
- Express `GET /api/health/ready` returns 200 only when MongoDB is connected and the Python health endpoint returns `status: ok`. It returns 503 and identifies each dependency when either is unavailable.
- Express `GET /api/health/live` checks only that the Node process can respond.

## Reconstruction routes

All routes are currently mounted under `/api/reconstruction` and forwarded by Express without changing the request/response payload.

| Method and path | Request | Success response |
| --- | --- | --- |
| `POST /upload` | `multipart/form-data`, field `file`; JSON file containing a top-level `measurements` object | `job_id`, source session/schema/unit metadata, available/missing measurement names, landmark count, validation status/warnings |
| `POST /generate` | JSON `{ "job_id": "..." }` | `{ "job_id": "...", "status": "started", "message": "..." }`; processing continues in the Python service background thread |
| `GET /status/{job_id}` | None | Job identifier, status, progress, stage message, and any error information |
| `GET /result/{job_id}` | None | Completed result JSON; HTTP 425 while the job is not complete |
| `GET /download/{job_id}` | None | Generated GLB file when available |
| `GET /report/{job_id}` | None | Validation report JSON when available |

Upload errors use HTTP 400 for unsupported extensions, 413 for oversized payloads, and 422 for malformed JSON or invalid measurement data. Unknown jobs return 404. The Python service keeps job state in memory and is not durable across restarts. Express requires a valid session for reconstruction routes, records each successful upload's `job_id` and owner in MongoDB, and checks ownership before forwarding status, generation, result, download, or report requests. FastAPI remains internal in Compose and should not be exposed directly. The ownership sidecar protects account access, but Phase 6 still needs to replace Python in-memory jobs with durable job records.

The parser accepts flexible measurement keys. The current validator treats height, chest circumference, waist circumference and hip circumference as critical; shoulder/section dimensions and neck circumference are quality-improving inputs. Other fields, including `hand_length_cm`, are optional metadata for this engine: the mapper, deformation and optimizer do not consume them. A null optional value is retained in `missing_measurements` and is not fabricated or treated as a generation error. Critical nulls still fail validation; missing quality-improving fields remain warnings.

## Ownership and migration boundary

The Python service owns measurement parsing, validation, the existing reconstruction job state, Blender invocation, and generated files. Express owns MongoDB readiness and is the sole browser-facing API gateway. Phase 6 will move durable job creation/status and authorization into Express/MongoDB, then replace this proxy only after endpoint parity and regression checks.
