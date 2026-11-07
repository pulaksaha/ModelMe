"""
Backend API Tests
=================
Tests for FastAPI endpoints:
- GET  /api/health
- POST /api/reconstruction/upload
- POST /api/reconstruction/generate
- GET  /api/reconstruction/status/{job_id}
- GET  /api/reconstruction/result/{job_id}
- GET  /api/reconstruction/download/{job_id}

Author: Body Reconstruction Engine
"""

import io
import json
from pathlib import Path
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)
SAMPLE_JSON_PATH = Path(__file__).resolve().parent / "fixtures" / "synthetic_measurements.json"


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "blender_found" in data
    assert isinstance(data["blender_found"], bool)
    assert data["base_blend_found"] is True
    assert data["status"] in {"ok", "degraded"}


def test_upload_valid_json():
    with open(SAMPLE_JSON_PATH, "rb") as f:
        response = client.post(
            "/api/reconstruction/upload",
            files={"file": ("170_measurements.json", f, "application/json")}
        )
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert data["session_id"] == "synthetic_172"
    assert data["unit"] == "cm"
    assert len(data["available_measurements"]) >= 40
    assert "height_cm" in data["available_measurements"]


def test_upload_invalid_format():
    response = client.post(
        "/api/reconstruction/upload",
        files={"file": ("test.txt", io.BytesIO(b"not a json"), "text/plain")}
    )
    assert response.status_code == 400


def test_upload_corrupt_json():
    response = client.post(
        "/api/reconstruction/upload",
        files={"file": ("corrupt.json", io.BytesIO(b"{\"invalid\": }"), "application/json")}
    )
    assert response.status_code == 422


def test_job_status_not_found():
    response = client.get("/api/reconstruction/status/non-existent-uuid")
    assert response.status_code == 404


def test_job_flow_upload_and_status():
    # 1. Upload
    with open(SAMPLE_JSON_PATH, "rb") as f:
        up_resp = client.post(
            "/api/reconstruction/upload",
            files={"file": ("test.json", f, "application/json")}
        )
    assert up_resp.status_code == 200
    job_id = up_resp.json()["job_id"]

    # 2. Check initial status
    st_resp = client.get(f"/api/reconstruction/status/{job_id}")
    assert st_resp.status_code == 200
    st_data = st_resp.json()
    assert st_data["job_id"] == job_id
    assert st_data["status"] == "queued"
