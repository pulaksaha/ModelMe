"""
Reconstruction Service
======================
Manages reconstruction jobs: launching Blender, tracking status,
and reading results.

Each job is identified by a UUID.
State is tracked via JSON files in the output directory.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Job state
# ──────────────────────────────────────────────────────────────────────────────

JOB_STAGES = [
    "queued",
    "reading_json",
    "validating_measurements",
    "preparing_template",
    "applying_deformation",
    "optimising",
    "computing_measurements",
    "validating_mesh",
    "exporting_glb",
    "complete",
    "failed",
]

STAGE_PROGRESS = {
    "queued":                    0,
    "reading_json":              5,
    "validating_measurements":   10,
    "preparing_template":        20,
    "applying_deformation":      35,
    "optimising":                55,
    "computing_measurements":    70,
    "validating_mesh":           80,
    "exporting_glb":             90,
    "complete":                  100,
    "failed":                    -1,
}


@dataclass
class JobState:
    job_id: str
    status: str           # one of JOB_STAGES
    progress: int         # 0–100
    stage_message: str
    input_path: str
    output_dir: str
    glb_path: Optional[str] = None
    report_path: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


# ──────────────────────────────────────────────────────────────────────────────
# In-memory job store (for local dev; replace with DB for production)
# ──────────────────────────────────────────────────────────────────────────────

_jobs: Dict[str, JobState] = {}
_lock = threading.Lock()


def _set_job(state: JobState):
    with _lock:
        _jobs[state.job_id] = state


def _get_job(job_id: str) -> Optional[JobState]:
    with _lock:
        return _jobs.get(job_id)


# ──────────────────────────────────────────────────────────────────────────────
# Service
# ──────────────────────────────────────────────────────────────────────────────

class ReconstructionService:
    """Manages the reconstruction pipeline for a FastAPI backend."""

    def __init__(self, project_root: Path):
        from backend.config import (
            BLENDER_EXECUTABLE, BLENDER_SCRIPT, OUTPUT_DIR,
            STORAGE_DIR, MAX_OPTIMISATION_ITERATIONS, BLENDER_TIMEOUT_SECONDS,
        )
        self.project_root      = project_root
        self.blender_exe       = BLENDER_EXECUTABLE
        self.blender_script    = BLENDER_SCRIPT
        self.output_dir        = OUTPUT_DIR
        self.storage_dir       = STORAGE_DIR
        self.max_iterations    = MAX_OPTIMISATION_ITERATIONS
        self.blender_timeout   = BLENDER_TIMEOUT_SECONDS

        from backend.config import BASE_BLEND_FILE
        self.base_blend        = BASE_BLEND_FILE

        # Ensure directories exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def create_job(self, input_path: Path) -> str:
        """Register a new reconstruction job. Returns job_id."""
        job_id = str(uuid.uuid4())
        job_output_dir = self.storage_dir / job_id
        job_output_dir.mkdir(parents=True, exist_ok=True)

        state = JobState(
            job_id=job_id,
            status="queued",
            progress=0,
            stage_message="Job queued",
            input_path=str(input_path),
            output_dir=str(job_output_dir),
        )
        _set_job(state)
        logger.info(f"Job created: {job_id} → {job_output_dir}")
        return job_id

    def start_job(self, job_id: str) -> bool:
        """
        Launch Blender reconstruction in a background thread.
        Returns True if job was found and launched.
        """
        state = _get_job(job_id)
        if state is None:
            return False

        thread = threading.Thread(
            target=self._run_blender,
            args=(job_id,),
            daemon=True,
        )
        thread.start()
        return True

    def get_status(self, job_id: str) -> Optional[dict]:
        """Return job status dict or None if not found."""
        state = _get_job(job_id)
        if state is None:
            return None

        # Also check progress file from Blender script
        prog_file = Path(state.output_dir) / f"{job_id}_progress.json"
        if prog_file.exists():
            try:
                prog_data = json.loads(prog_file.read_text())
                state.stage_message = prog_data.get("stage", state.stage_message)
                state.progress = prog_data.get("progress", state.progress)
            except Exception:
                pass

        return state.to_dict()

    def get_result(self, job_id: str) -> Optional[dict]:
        """Return the full result dict for a completed job."""
        state = _get_job(job_id)
        if state is None:
            return None

        result_path = Path(state.output_dir) / f"{job_id}_result.json"
        if result_path.exists():
            try:
                return json.loads(result_path.read_text())
            except Exception as e:
                return {"error": f"Cannot read result file: {e}"}

        return {"status": state.status, "progress": state.progress}

    # ──────────────────────────────────────────────────────────────────────────
    # Private: Blender subprocess runner
    # ──────────────────────────────────────────────────────────────────────────

    def _run_blender(self, job_id: str):
        """Runs Blender in background mode in a thread."""
        state = _get_job(job_id)
        if state is None:
            return

        _update_job(job_id, status="reading_json", progress=5,
                    stage_message="Starting Blender")

        cmd = [
            self.blender_exe,
            "--background",
            str(self.base_blend),
            "--python",
            str(self.blender_script),
            "--",
            "--json_path",      state.input_path,
            "--output_dir",     state.output_dir,
            "--job_id",         job_id,
            "--project_root",   str(self.project_root),
            "--max_iterations", str(self.max_iterations),
        ]

        logger.info(f"Launching Blender: {' '.join(cmd[:4])} ...")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.blender_timeout,
            )

            stdout = result.stdout
            stderr = result.stderr

            # Parse result from Blender stdout
            glb_path = None
            report_path = None
            success = False

            for line in stdout.splitlines():
                if line.startswith("STATUS:SUCCESS:"):
                    success = True
                elif line.startswith("STATUS:FAILED:"):
                    success = False

            # Read result file
            result_file = Path(state.output_dir) / f"{job_id}_result.json"
            if result_file.exists():
                result_data = json.loads(result_file.read_text())
                glb_path    = result_data.get("glb_path")
                report_path = result_data.get("report_path")
                if result_data.get("status") == "success":
                    success = True

            if success and glb_path:
                _update_job(
                    job_id, status="complete", progress=100,
                    stage_message="Reconstruction complete",
                    glb_path=glb_path,
                    report_path=report_path,
                )
                logger.info(f"Job {job_id} completed. GLB: {glb_path}")
            else:
                err = stderr[-500:] if stderr else "Unknown error"
                _update_job(
                    job_id, status="failed", progress=-1,
                    stage_message="Reconstruction failed",
                    error=err,
                )
                logger.error(f"Job {job_id} FAILED.\nstderr: {stderr[-300:]}")

        except subprocess.TimeoutExpired:
            _update_job(
                job_id, status="failed", progress=-1,
                stage_message="Timed out",
                error=f"Blender process timed out after {self.blender_timeout}s",
            )
        except Exception as e:
            _update_job(
                job_id, status="failed", progress=-1,
                stage_message="Internal error",
                error=str(e),
            )


def _update_job(
    job_id: str,
    status: str,
    progress: int,
    stage_message: str,
    glb_path: Optional[str] = None,
    report_path: Optional[str] = None,
    error: Optional[str] = None,
):
    with _lock:
        state = _jobs.get(job_id)
        if state:
            state.status        = status
            state.progress      = progress
            state.stage_message = stage_message
            if glb_path:
                state.glb_path = glb_path
            if report_path:
                state.report_path = report_path
            if error:
                state.error = error

