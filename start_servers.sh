#!/usr/bin/env bash
# ==============================================================================
# ModelMe — Full Stack Service Launcher
# ==============================================================================
# Starts:
#   1. MongoDB (Port 27017)
#   2. FastAPI Reconstruction Engine (Port 8000)
#   3. Express API Gateway (Port 3001)
#   4. Vite React Frontend (Port 3000)
# ==============================================================================

set -e
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

echo "=== [1/4] Checking MongoDB (Port 27017) ==="
if ! nc -z 127.0.0.1 27017 2>/dev/null; then
  echo "Starting MongoDB with workspace storage..."
  mkdir -p "$PROJECT_ROOT/storage/mongodb_data"
  /opt/homebrew/bin/mongod \
    --dbpath "$PROJECT_ROOT/storage/mongodb_data" \
    --logpath "$PROJECT_ROOT/storage/mongodb.log" \
    --bind_ip 127.0.0.1 \
    --logappend &
  sleep 2
fi
echo "✓ MongoDB is online."

echo "=== [2/4] Starting FastAPI Reconstruction Service (Port 8000) ==="
"$PROJECT_ROOT/.venv/bin/python" -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
FASTAPI_PID=$!
sleep 1
echo "✓ FastAPI service running (PID: $FASTAPI_PID)."

echo "=== [3/4] Starting Express API Gateway (Port 3001) ==="
(cd "$PROJECT_ROOT/services/api" && node --env-file-if-exists=../../.env src/server.js) &
EXPRESS_PID=$!
sleep 1
echo "✓ Express API gateway running (PID: $EXPRESS_PID)."

echo "=== [4/4] Starting React / Three.js Frontend (Port 3000) ==="
(cd "$PROJECT_ROOT/frontend" && npm run dev) &
VITE_PID=$!
sleep 1
echo "✓ Vite dev server running (PID: $VITE_PID)."

echo ""
echo "===================================================================="
echo "  🎉 ModelMe Human Reconstruction Engine is RUNNING!"
echo "===================================================================="
echo "  👉 Web Interface:  http://localhost:3000"
echo "  👉 API Gateway:    http://localhost:3001"
echo "  👉 FastAPI Engine: http://localhost:8000"
echo "===================================================================="
echo "Press CTRL+C to stop all services."
echo ""

# Graceful cleanup on interrupt or exit
cleanup() {
  echo ""
  echo "Shutting down ModelMe services..."
  kill -TERM "$FASTAPI_PID" "$EXPRESS_PID" "$VITE_PID" 2>/dev/null || true
  wait "$FASTAPI_PID" "$EXPRESS_PID" "$VITE_PID" 2>/dev/null || true
  echo "All services stopped."
  exit 0
}

trap cleanup INT TERM EXIT
wait

