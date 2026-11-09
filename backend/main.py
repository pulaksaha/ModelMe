"""
FastAPI Backend — Main Application
===================================
Body Reconstruction API server.

Endpoints:
    POST /api/reconstruction/upload    — Upload measurement JSON
    POST /api/reconstruction/generate  — Start reconstruction job
    GET  /api/reconstruction/status/{job_id}  — Job status
    GET  /api/reconstruction/result/{job_id}  — Job result + GLB path
    GET  /api/reconstruction/download/{job_id} — Download GLB file
    GET  /api/health                   — Health check

Start with:
    cd /Users/pulaksaha/usero/model
    pip3 install -r backend/requirements.txt
    python3 -m uvicorn backend.main:app --reload --port 8000
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# ──────────────────────────────────────────────────────────────────────────────
# Ensure project root is on sys.path
# ──────────────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import (
    API_HOST, API_PORT, CORS_ORIGINS,
    BLENDER_EXECUTABLE, BASE_BLEND_FILE,
    INPUT_DIR, STORAGE_DIR, MAX_UPLOAD_SIZE_MB, ALLOWED_EXTENSIONS,
)
from backend.services.reconstruction_service import ReconstructionService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# App setup
# ──────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Body Reconstruction API",
    description="3D Human Body Reconstruction from Anthropometric Measurements",
    version="0.1.0",
)

FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

INPUT_DIR.mkdir(parents=True, exist_ok=True)
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

svc = ReconstructionService(PROJECT_ROOT)

# ──────────────────────────────────────────────────────────────────────────────
# Health
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health_check():
    blender_path = shutil.which(BLENDER_EXECUTABLE) or BLENDER_EXECUTABLE
    blender_ok = Path(blender_path).is_file() and os.access(blender_path, os.X_OK)
    blend_ok   = BASE_BLEND_FILE.exists()
    return {
        "status":        "ok" if (blender_ok and blend_ok) else "degraded",
        "blender_found": blender_ok,
        "base_blend_found": blend_ok,
        "blender_path":  blender_path,
        "base_blend":    str(BASE_BLEND_FILE),
    }

# ──────────────────────────────────────────────────────────────────────────────
# Upload
# ──────────────────────────────────────────────────────────────────────────────

@app.post("/api/reconstruction/upload")
async def upload_measurements(file: UploadFile = File(...)):
    """
    Upload a measurement JSON file.
    Returns a job_id to use for subsequent calls.
    Validates the JSON structure before accepting.
    """
    # Extension check
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Only .json files are accepted, got '{suffix}'")

    # Size check
    content = await file.read()
    size_mb = len(content) / 1024 / 1024
    if size_mb > MAX_UPLOAD_SIZE_MB:
        raise HTTPException(413, f"File too large ({size_mb:.2f} MB, max {MAX_UPLOAD_SIZE_MB} MB)")

    # JSON validity
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise HTTPException(422, f"Invalid JSON: {e}")

    # Basic schema check: must have 'measurements' key
    if "measurements" not in data:
        raise HTTPException(422, "JSON must contain a 'measurements' object")

    # Validate using our parser
    try:
        from reconstruction.json_parser import MeasurementJSONParser
        from reconstruction.measurement_validator import MeasurementValidator

        parser = MeasurementJSONParser()
        parsed = parser.parse_dict(data)
        val = MeasurementValidator()
        report = val.validate(parsed)
    except Exception as e:
        raise HTTPException(422, f"Measurement validation error: {e}")

    # Save file with unique name
    safe_name = f"{uuid.uuid4()}.json"
    save_path = INPUT_DIR / safe_name
    save_path.write_bytes(content)

    # Register job
    job_id = svc.create_job(save_path)

    # Build measurement summary for the response
    available = parsed.available_measurements()
    missing   = parsed.missing_measurements()

    return {
        "job_id":                job_id,
        "filename":              file.filename,
        "session_id":            parsed.session_id,
        "schema_version":        parsed.schema_version,
        "unit":                  parsed.unit,
        "gender":                parsed.gender.final_gender if parsed.gender else None,
        "body_shape":            parsed.shape.shape if parsed.shape else None,
        "available_measurements": available,
        "missing_measurements":   missing,
        "landmark_count":        len(parsed.landmarks),
        "validation_status":     report.overall_status,
        "validation_warnings":   report.warnings[:10],  # first 10 warnings
    }

# ──────────────────────────────────────────────────────────────────────────────
# Generate
# ──────────────────────────────────────────────────────────────────────────────

@app.post("/api/reconstruction/generate")
async def generate_model(payload: dict, background_tasks: BackgroundTasks):
    """
    Start reconstruction for a previously uploaded job_id.
    Returns immediately; check /status/{job_id} for progress.
    """
    job_id = payload.get("job_id")
    if not job_id:
        raise HTTPException(400, "job_id is required")

    status = svc.get_status(job_id)
    if status is None:
        raise HTTPException(404, f"Job not found: {job_id}")
    if status["status"] not in ("queued", "failed"):
        raise HTTPException(409, f"Job is already {status['status']}")

    # Launch Blender in background thread
    launched = svc.start_job(job_id)
    if not launched:
        raise HTTPException(500, "Failed to start reconstruction job")

    return {
        "job_id": job_id,
        "status": "started",
        "message": "Reconstruction started in background. Poll /api/reconstruction/status/{job_id}",
    }

# ──────────────────────────────────────────────────────────────────────────────
# Status
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/reconstruction/status/{job_id}")
async def get_status(job_id: str):
    status = svc.get_status(job_id)
    if status is None:
        raise HTTPException(404, f"Job not found: {job_id}")
    return status

# ──────────────────────────────────────────────────────────────────────────────
# Result
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/reconstruction/result/{job_id}")
async def get_result(job_id: str):
    status = svc.get_status(job_id)
    if status is None:
        raise HTTPException(404, f"Job not found: {job_id}")
    if status["status"] != "complete":
        raise HTTPException(
            425,
            f"Job not yet complete (status: {status['status']}). "
            f"Current progress: {status['progress']}%"
        )
    result = svc.get_result(job_id)
    return result

# ──────────────────────────────────────────────────────────────────────────────
# Download GLB
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/reconstruction/download/{job_id}")
async def download_glb(job_id: str):
    status = svc.get_status(job_id)
    if status is None:
        raise HTTPException(404, f"Job not found: {job_id}")
    if status["status"] != "complete":
        raise HTTPException(425, "Job not yet complete")

    glb_path = status.get("glb_path")
    if not glb_path or not Path(glb_path).exists():
        raise HTTPException(404, "GLB file not found")

    # Security: ensure path is within storage dir
    glb_path = Path(glb_path).resolve()
    storage_dir = STORAGE_DIR.resolve()
    try:
        glb_path.relative_to(storage_dir)
    except ValueError:
        raise HTTPException(403, "Access denied")

    return FileResponse(
        path=str(glb_path),
        media_type="model/gltf-binary",
        filename=f"reconstruction_{job_id}.glb",
    )

# ──────────────────────────────────────────────────────────────────────────────
# Download report
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/reconstruction/report/{job_id}")
async def download_report(job_id: str):
    status = svc.get_status(job_id)
    if status is None:
        raise HTTPException(404, f"Job not found: {job_id}")

    report_path = status.get("report_path")
    if not report_path or not Path(report_path).exists():
        raise HTTPException(404, "Validation report not found")

    report_path = Path(report_path).resolve()
    storage_dir = STORAGE_DIR.resolve()
    try:
        report_path.relative_to(storage_dir)
    except ValueError:
        raise HTTPException(403, "Access denied")

    return FileResponse(
        path=str(report_path),
        media_type="application/json",
        filename=f"validation_report_{job_id}.json",
    )


# Serve the built web app from the same origin in container deployments. Vite
# serves the frontend separately during development and proxies /api requests.
if FRONTEND_DIST.exists():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

    @app.get("/{frontend_path:path}", include_in_schema=False)
    async def serve_frontend(frontend_path: str):
        if frontend_path == "api" or frontend_path.startswith("api/"):
            raise HTTPException(404, "API route not found")
        requested = (FRONTEND_DIST / frontend_path).resolve()
        try:
            requested.relative_to(FRONTEND_DIST.resolve())
        except ValueError:
            raise HTTPException(404, "Not found")
        if requested.is_file():
            return FileResponse(requested)
        index_file = FRONTEND_DIST / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        raise HTTPException(404, "Frontend build not found")


# ──────────────────────────────────────────────────────────────────────────────
# Dev server entrypoint
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=API_HOST, port=API_PORT, reload=True)

