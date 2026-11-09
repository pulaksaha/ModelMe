"""
Backend configuration
"""
import os
import shutil
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# Project paths
# ──────────────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent

ASSETS_DIR      = PROJECT_ROOT / "assets"
BASE_BLEND_FILE = ASSETS_DIR / "base_human" / "base_human.blend"

INPUT_DIR   = PROJECT_ROOT / "input"
OUTPUT_DIR  = PROJECT_ROOT / "output"
STORAGE_DIR = PROJECT_ROOT / "storage" / "generated"

# ──────────────────────────────────────────────────────────────────────────────
# Blender
# ──────────────────────────────────────────────────────────────────────────────
def _detect_blender_executable() -> str:
    configured = os.environ.get("BLENDER_EXECUTABLE")
    if configured:
        return str(Path(configured).expanduser())

    candidates = [
        shutil.which("blender"),
        "/Applications/Blender.app/Contents/MacOS/Blender",
        str(Path.home() / "Applications/Blender.app/Contents/MacOS/Blender"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return str(Path(candidate).resolve())
    return "blender"


BLENDER_EXECUTABLE = _detect_blender_executable()
BLENDER_SCRIPT = PROJECT_ROOT / "blender" / "reconstruct.py"

# ──────────────────────────────────────────────────────────────────────────────
# Reconstruction
# ──────────────────────────────────────────────────────────────────────────────
MAX_OPTIMISATION_ITERATIONS = int(os.environ.get("MAX_OPTIMISATION_ITERATIONS", "12"))
BLENDER_TIMEOUT_SECONDS     = int(os.environ.get("BLENDER_TIMEOUT_SECONDS", "300"))
MAX_UPLOAD_SIZE_MB          = int(os.environ.get("MAX_UPLOAD_SIZE_MB", "10"))
ALLOWED_EXTENSIONS          = {".json"}

# ──────────────────────────────────────────────────────────────────────────────
# API
# ──────────────────────────────────────────────────────────────────────────────
API_HOST = "0.0.0.0"
API_PORT = 8000
_cors_origins = os.environ.get("CORS_ORIGINS")
CORS_ORIGINS = (
    [origin.strip() for origin in _cors_origins.split(",") if origin.strip()]
    if _cors_origins is not None
    else ["http://localhost:3000", "http://127.0.0.1:3000"]
)

