# ModelMe

ModelMe creates a measurement-driven human avatar with a React web UI and a Python/Blender processing pipeline. The application is being migrated toward the target stack described in [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md): Express + MongoDB for the public API and data, with Python/Blender as an isolated worker.

## Current structure

- `frontend/` — React/Vite UI and React Three Fiber GLB viewer
- `services/api/` — Express API gateway, MongoDB readiness, account sessions, job ownership checks, frontend static serving and temporary reconstruction proxy
- `backend/` — existing FastAPI upload/job API, retained until Phase 6 migration is verified
- `reconstruction/` — existing Python parser, validators, parameter mapping, deformation, optimization and GLB export
- `blender/` — Blender background scripts
- `assets/base_human/base_human.blend` — current configured source mesh
- `docs/architecture.md` — current and target service diagrams
- `docs/service-contract.md` — temporary Express-to-FastAPI interface and migration limits
- `DEVELOPMENT_PLAN.md` — detailed phases, dependencies, acceptance checks, and verification log

## Phase 1 local setup

Requirements: Node.js 24 or newer, Python 3.12, MongoDB, and Blender for generation. Docker is optional for the container path but must be installed to run Compose. The current machine has Blender 5.2.3 LTS installed at `/Applications/Blender.app/Contents/MacOS/Blender`; Docker is not installed.

1. Create a local environment file from `.env.example`; set `BLENDER_EXECUTABLE` to a valid Blender path. Generate a private value with `openssl rand -base64 48` and put it in `JWT_SECRET`. Never commit `.env`.
2. Start MongoDB on `127.0.0.1:27017`.
3. Install Express dependencies and start the API:

```sh
cd services/api
npm ci
npm run dev
```

4. In a second terminal, run the existing FastAPI reconstruction API:

```sh
cd <project-root>
python3.12 -m venv .venv312
./.venv312/bin/pip install -r backend/requirements.lock.txt
set -a
. ./.env
set +a
./.venv312/bin/python -m uvicorn backend.main:app --reload --port 8000
```

5. In a third terminal, start the frontend:

```sh
cd frontend
npm ci
npm run dev
```

Open `http://localhost:3000`. Vite forwards `/api` to Express on port 3001; Express temporarily forwards `/api/reconstruction` to FastAPI on port 8000. Check `http://localhost:3001/api/health/ready` for MongoDB readiness and `http://localhost:8000/api/health` for Blender/base-mesh readiness.

To verify Blender and create a test GLB without touching the human model, follow [docs/blender.md](docs/blender.md).

Run the Phase 1 checks from the repository root:

```sh
(cd services/api && npm test)
./.venv312/bin/python -m unittest tests/test_reconstruction_unittest.py
./.venv312/bin/python -m pytest -q tests/test_reconstruction.py tests/test_backend.py
(cd frontend && npm run build && npm audit --audit-level=moderate)
```

## Container deployment draft

Compose defines three services: Express + built frontend, MongoDB, and the retained Python/Blender reconstruction service. From the repository root:

```sh
docker compose up --build
```

When the image build succeeds, open `http://localhost:8080`. Compose persists MongoDB, uploaded input JSON, and generated GLBs in named volumes. The default host bind is loopback only. Authentication and reconstruction ownership checks are implemented, but there is no password reset/email flow, durable job state, retention policy, or external object storage yet. Docker is unavailable on the current machine, so the image has not been built or verified.

## Privacy and cleanup

Uploaded measurement JSON and generated models are excluded from Git and Docker build contexts. Old `.blend` variants are retained locally until Phase 4 confirms whether they are redundant. `assets/base_human/base_human.blend` is the only mesh currently referenced by the application; its license/provenance still needs verification.
