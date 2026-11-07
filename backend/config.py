"""
Backend configuration
"""
import os
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
BLENDER_EXECUTABLE = os.environ.get(
    "BLENDER_EXECUTABLE",
    "/Applications/Blender.app/Contents/MacOS/Blender",
)
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

