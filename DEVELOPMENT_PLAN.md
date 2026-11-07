# ModelMe Development Plan

## Working rules

- Implement and verify one phase at a time.
- Keep known-good reconstruction behavior until a replacement passes equivalent checks.
- Add dependencies only when the phase first needs them; avoid installing future-phase packages early.
- Never commit measurement uploads, credentials, generated GLBs, local databases, or Blender backups.
- Record actual verification commands and outcomes below. Do not mark unverified work complete.

## Repository baseline (2026-11-08)

- React/Vite frontend exists and includes JSON upload, status polling, GLB preview, and download actions. It does not yet have routes, authentication, dashboard or manual forms.
- A FastAPI service handles uploads and runs Blender in a Python background thread. It uses in-memory job state and local files.
- `reconstruction/` contains parser, validator, measurement mapper, deformation, optimizer, mesh measurement, mesh validation and GLB export modules.
- `assets/base_human/base_human.blend` is the asset used by the current service. Other `.blend` files exist but have not been proven redundant; retain them pending Phase 4 asset review.
- Sample uploads and generated reports/GLBs exist locally. Treat uploaded measurement files as sensitive; exclude them from Git and images.
- Node 26.5.0, npm 11.17.0, Python 3.12.14, Python 3.9.6 legacy virtualenv, and MongoDB 8.2.7 are available. Docker and Blender are not installed. The configured macOS Blender path is missing.
- The project root was not a Git repository when Phase 1 began.
- The local API responded with `status=degraded`, `blender_found=false`, and `base_blend_found=true`. The browser's fetch error occurred while the API was not listening.

## Target repository structure

```text
ModelMe/
├── frontend/                         # React/Vite app
│   └── src/features/                 # auth, profiles, measurements, viewer, history
├── services/
│   ├── api/                           # Node/Express REST API and MongoDB models
│   └── reconstruction/                # Python worker boundary (migrate after parity)
├── backend/                           # Current FastAPI prototype during migration
├── reconstruction/                    # Reusable current Python implementation
├── blender/                           # Headless Blender entry points
├── assets/base_human/                 # Approved base mesh, license and calibration notes
├── tests/                             # unit, service integration, Blender and browser checks
├── docs/architecture.md
├── DEVELOPMENT_PLAN.md
├── docker-compose.yml
└── README.md
```

The temporary `backend/` and `reconstruction/` folders will only be removed after the Express API and worker path have feature parity and pass the same acceptance checks. Old mesh variants are retained until Phase 4 establishes which one is the approved base.

## Phases

### Phase 1 — Project setup and service boundary (active)

**Scope:** establish Git and ignore rules; record architecture; set up Node/Express + MongoDB health checks and environment configuration; keep the existing FastAPI reconstruction routes usable; define local run instructions and deployment boundaries.

**Dependencies:** Node.js 24 LTS runtime, Express 5, Mongoose 9, Helmet 8. MongoDB is a local service for development and a Compose service in deployment. Python 3.12 is the supported Python runtime; current reconstruction dependencies stay in `backend/requirements.txt` until the worker migration.

**Acceptance checks:** clean Git baseline excludes personal measurement files and generated artifacts; Express liveness responds; readiness accurately reports MongoDB; existing reconstruction API remains reachable; frontend proxy routes work; config contains no secrets; API and frontend dependency lockfiles are committed.

**Risks:** no Blender or Docker binary is installed locally, so the Blender container build cannot be verified here. The target stack has a Node/Express API but existing model generation is FastAPI; use a temporary proxy bridge until Phase 6 moves job ownership. Mesh license/provenance is not documented.

### Phase 2 — Authentication and dashboard

**Scope:** registration, login, logout, password reset policy, JWT/session handling, protected routes, user profile basics and dashboard shell.

**Dependencies:** add `jose` for signed tokens, a maintained Argon2 password-hashing package, `zod` for request schemas, React Router for protected UI routes. Add email delivery only if password reset is approved; do not introduce it by default.

**Acceptance checks:** password hashes only; token expiry and logout behavior verified; protected API resources reject anonymous access; one user's account data cannot be read by another; frontend route guards tested.

### Phase 3 — Measurement profiles

**Scope:** manual input and edit forms for height, optional weight, chest, waist, hip, shoulder width, neck, arm length, upper-arm circumference, thigh, inseam and leg length; unit selection, measuring guidance and server validation; MongoDB profile and measurement version records.

**Dependencies:** reuse Mongoose and `zod`; add no form package unless a concrete complexity justifies it. Use React Router from Phase 2.

**Acceptance checks:** valid and invalid unit/range cases; weight is metadata and never deforms geometry; profile and measurement ownership enforced; edits create explicit versions/history.

### Phase 4 — 3D model preparation

**Scope:** confirm base mesh license, inspect topology and scale, record reference dimensions, choose or create shape keys/controlled deformation regions, and produce a baseline GLB.

**Dependencies:** Blender LTS pinned in the worker image; current `.blend` asset; existing inspection/export modules. No new Python package until inspection identifies a need.

**Acceptance checks:** license evidence recorded; mesh object names, units, scale and topology documented; baseline export opens in Three.js; manual deformation does not damage the source mesh.

### Phase 5 — Measurement processing engine

**Scope:** normalize measurements against reference dimensions; map measurements to calibrated deformation controls; account for circumference as a cross-section target rather than assuming one-axis scaling; validate mesh and final dimensions; document uncertainty and limitations.

**Dependencies:** existing Python modules and Blender Python API. Add numerical libraries only if the calibrated optimization method requires them and can be justified.

**Acceptance checks:** synthetic calibration cases, regression targets, missing/low-confidence inputs, mesh integrity and per-measurement tolerance reports.

### Phase 6 — Backend and worker integration

**Scope:** Express owns authenticated profile/model APIs and durable jobs; Python worker accepts validated job payloads; worker progress/results are persisted; remove the temporary FastAPI proxy only after parity.

**Dependencies:** MongoDB/Mongoose jobs and metadata; durable worker queue (evaluate BullMQ + Redis versus Mongo-backed queue at this phase); object storage SDK/provider chosen then, not before. Do not store GLB binaries in MongoDB.

**Acceptance checks:** retry, timeout, cancellation policy, restart recovery, idempotency, error logging, ownership checks and upload-size limits. A request never waits for Blender synchronously.

### Phase 7 — 3D visualization

**Scope:** load GLB, rotate/zoom/pan, front/side/back camera presets, reset camera, show measurement metadata and download.

**Dependencies:** existing React Three Fiber, Three.js and Drei packages; React Router from Phase 2. Add no viewer package unless existing controls cannot meet requirements.

**Acceptance checks:** preview valid GLB, recover visibly from invalid GLB, controls verified on desktop/mobile, download authorization enforced.

### Phase 8 — Model history

**Scope:** associate models with profiles, generation date/status/version, revisit prior models, compare versions and securely retrieve files.

**Dependencies:** Phase 6 persisted jobs and chosen object storage; MongoDB metadata only.

**Acceptance checks:** versions remain immutable, ownership checks cover list/detail/download, deletion/retention rules are explicit, comparison uses saved measurement/model metadata.

### Phase 9 — Testing and deployment

**Scope:** API, UI, auth, measurement, Blender and end-to-end tests; GLB optimization; production containers; secrets, TLS, storage, monitoring, backups and deployment runbook.

**Dependencies:** Docker/Compose for local parity; CI provider and cloud/object-storage provider chosen with the user before credentials or external resources are configured.

**Acceptance checks:** clean environment setup, repeatable deployment, health/readiness checks, rollback procedure, no secret/sample-personal-data leakage, documented performance and known limitations.

## Current verification log

- **2026-11-08 — Existing API health request:** returned `degraded`; Blender missing, base `.blend` found. This confirms the local generation blocker; it does not verify reconstruction.
- **Frontend dev server:** previously opened at `http://localhost:3000/`; this verifies only that the UI renders, not API/model generation.
- **Docker build / MongoDB-backed Express tests / Blender generation:** not yet run for this phase.

## Phase 1 work in progress

1. Establish repository hygiene and local baseline.
2. Add Express health endpoints and MongoDB readiness connection.
3. Keep legacy FastAPI generation route available through a proxy while frontend talks to Express.
4. Install and lock only Phase 1 dependencies.
5. Run Phase 1 checks, document limitations, and then start Phase 2.
