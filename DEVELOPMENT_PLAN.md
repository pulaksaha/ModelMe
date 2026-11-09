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
- Node 26.5.0, npm 11.17.0, Python 3.12.14, a retained Python 3.9.6 legacy virtualenv, and MongoDB 8.2.7 are available. A clean `.venv312` is installed for project work. Docker is not installed. Blender 5.2.3 LTS was installed during this work at `/Applications/Blender.app/Contents/MacOS/Blender`.
- The project root was not a Git repository when Phase 1 began.
- The local API responded with `status=degraded`, `blender_found=false`, and `base_blend_found=true`. The browser's fetch error occurred while the API was not listening.
- Phase 1 created local Git baseline commit `98e104f`; measurement uploads and generated output remain ignored and untracked.

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

### Phase 1 — Project setup and service boundary (local acceptance passed; container verification pending)

**Scope:** establish Git and ignore rules; record architecture; set up Node/Express + MongoDB health checks and environment configuration; keep the existing FastAPI reconstruction routes usable; define local run instructions and deployment boundaries.

**Dependencies:** Node.js 24 LTS runtime, Express 5, Mongoose 9, Helmet 8. MongoDB is a local service for development and a Compose service in deployment. Python 3.12 is the supported Python runtime; current reconstruction dependencies stay in `backend/requirements.txt` until the worker migration.

**Acceptance checks:** clean Git baseline excludes personal measurement files and generated artifacts; Express liveness responds; readiness accurately reports MongoDB and reconstruction service status; existing reconstruction API remains reachable; frontend proxy routes work; config contains no secrets; API and frontend dependency lockfiles are committed. Local acceptance passed in the 2026-11-08 audit. Container image build and Blender-in-container smoke test remain unverified because Docker is not installed.

**Risks:** Docker is unavailable locally, so the container build cannot be verified. Blender is now available and a standalone cube GLB smoke test passes outside the restricted process sandbox; full human-model generation remains a separate unverified check. The target stack has a Node/Express API but existing model generation is FastAPI; use a temporary proxy bridge until Phase 6 moves job ownership. Mesh license/provenance is not documented.

### Phase 2 — Authentication and dashboard (implemented; production checks pending)

**Scope:** registration, login, logout, password reset policy, JWT/session handling, protected routes, user profile basics and dashboard shell.

**Dependencies:** add `jose` for signed tokens, a maintained Argon2 password-hashing package, `zod` for request schemas, React Router for protected UI routes. Add email delivery only if password reset is approved; do not introduce it by default.

**Acceptance checks:** password hashes only; token expiry and logout behavior verified; protected API resources reject anonymous access; one user's account data cannot be read by another; frontend route guards tested.

**Implementation status:** registration/login/logout and `/me` routes use MongoDB, Argon2id and JWTs in HttpOnly, SameSite Strict cookies; logout revokes the current token version. The Express reconstruction bridge requires a session and stores each successful upload's `job_id` ownership before returning it. React Router guards the dashboard; login/register pages and a dashboard shell are in place. Password reset/email delivery, profile/measurement pages and model history remain later phases. API/auth tests and the Vite build pass; browser checks verified login/register rendering and anonymous redirection to login. Production/deployment testing remains pending.

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

- **2026-11-08 — `services/api`: `npm test`:** 4 passed. Covers Express liveness, API 404, and both Mongo readiness states.
- **2026-11-08 — MongoDB-backed Express runtime:** `GET /api/health/ready` returned HTTP 200 with `mongodb=connected`.
- **2026-11-08 — Proxy smoke check:** Express forwarded `GET /api/reconstruction/status/not-a-job` to FastAPI and returned its expected 404 JSON; Vite on port 3000 forwarded both health and reconstruction routes successfully.
- **2026-11-08 — `./.venv312/bin/python -m unittest tests/test_reconstruction_unittest.py`:** 12 passed against a synthetic fixture. The checked-in unit test no longer reads the local measurement file.
- **2026-11-08 — `./.venv312/bin/python -m pytest -q tests/test_reconstruction.py tests/test_backend.py`:** 15 passed; one Starlette deprecation warning from its HTTPX TestClient compatibility layer.
- **2026-11-08 — `frontend/npm run build` with Vite 8.3.6:** passed. The output contains a 1.09 MB JavaScript chunk; performance splitting remains a follow-up.
- **2026-11-08 — `frontend/npm audit --audit-level=moderate`:** 0 vulnerabilities after upgrading Vite and its React plugin.
- **2026-11-08 — Compose YAML:** parsed successfully with PyYAML and the expected three services/dependency conditions. Docker Compose's own config validation was unavailable.
- **2026-11-08 — Phase 1 audit, dependency review:** API and frontend `npm ls --depth=0` show only declared direct dependencies installed; `pip check` reports no broken requirements. No unused direct dependency or duplicate implementation was identified. FastAPI and Express are intentionally separate during the migration bridge; no asset, model, dataset, or reconstruction script was removed.
- **2026-11-08 — Phase 1 audit, MongoDB:** `mongosh --quiet --eval 'db.adminCommand({ping:1})'` returned `{ ok: 1 }`; the running Express process returned MongoDB connected.
- **2026-11-08 — Phase 1 audit, gateway:** HTTP checks confirmed Vite `/api` → Express and Express `/api/reconstruction` → FastAPI. A synthetic measurement fixture upload traversed all three services and returned a job ID. A generation request reached FastAPI and returned `started`; status then became `failed` with the exact missing Blender executable path. This verifies request routing and error reporting, not successful GLB generation.
- **2026-11-08 — Phase 1 audit, health:** Express liveness returned HTTP 200. Readiness now checks MongoDB and Python `/api/health`; it returned HTTP 503 with `mongodb=connected`, `reconstruction=unavailable`. Python returned HTTP 200 with `status=degraded`, `blender_found=false`, `base_blend_found=true`. The status accurately reflects the unavailable local Blender executable.
- **2026-11-08 — Phase 1 audit, environment and repository hygiene:** `.env` is not tracked; secret-pattern scan found no committed credentials; `.env.example` contains example settings only. Only the canonical base `.blend` and synthetic JSON fixture are tracked. `git diff --check` passed.
- **2026-11-08 — Phase 1 audit, Python dependencies:** `./.venv312/bin/pip check` reports no broken requirements.
- **2026-11-08 — Phase 1 audit, Express tests:** `services/api/npm test`: 5 passed, 0 failed. The loopback test runner required local-network permission; the unrestricted run passed.
- **2026-11-08 — Phase 1 audit, backend tests:** `./.venv312/bin/python -m pytest -q`: 27 passed, one Starlette/HTTPX deprecation warning. Explicit `unittest` run: 12 passed.
- **2026-11-08 — Phase 1 audit, frontend/dependencies:** Vite 8.3.6 production build passed (one chunk size warning, 1.09 MB / 304 KB gzip); `npm audit --audit-level=moderate`: 0 vulnerabilities.
- **2026-11-08 — Phase 1 audit, docs and configuration:** added `docs/service-contract.md` for Python route payloads, health semantics, and migration limits; corrected the example `FRONTEND_DIST` path; removed a premature JWT placeholder at the time of the audit. Phase 2 later added an explicit blank `JWT_SECRET` setting and generated an ignored local secret in `.env`.
- **2026-11-08 — Phase 1 audit, Compose:** PyYAML parses `mongo`, `reconstruction`, and `api`, with the API waiting for both dependencies to be healthy. Docker Compose schema/build and a Blender-in-container smoke test remain unverified because Docker is not installed.
- **2026-11-08 — Blender integration:** detected Blender `5.2.3 LTS` at `/Applications/Blender.app/Contents/MacOS/Blender`; `.env` and `.env.example` now configure that path. Python resolves explicit environment settings, then `PATH`, then standard macOS app locations. The FastAPI health check now verifies the configured binary is executable as well as the base mesh being present.
- **2026-11-08 — Blender background verification:** a direct sandboxed background launch exited 139 before Python during macOS Metal detection. Running the same smoke test through the approved unsandboxed command succeeded: `bpy_accessible=true`, created `ModelMeSmokeTestCube`, exported `/Users/pulaksaha/usero/model/output/blender_smoke_test.glb` (1,744 bytes), GLB v2 magic/declared length validated. The script uses a blank scene and does not load or alter the human mesh or reconstruction script. Blender issue [#165753](https://projects.blender.org/blender/blender/issues/165753) describes the matching sandbox/Metal failure; no user machine issue was inferred.
- **2026-11-08 — Blender/API readiness after install:** FastAPI `/api/health` returned HTTP 200 with `blender_found=true` and `base_blend_found=true`; Express and Vite-proxied `/api/health/ready` returned HTTP 200 with MongoDB connected and reconstruction available. `tests/test_backend.py`: 6 passed with `.env` loaded.
- **2026-11-08 — Phase 2 authentication:** `services/api/npm test`: 9 passed, including Argon2id verification, JWT expiry/tamper checks, Mongo registration/login/logout, HttpOnly cookie behavior, anonymous denial, and a job owned by another ID returning 404. Frontend Vite build passed; browser checked login/register pages and anonymous `/` redirection to `/login`. This is local-development verification, not a production security review.
- **Human-model generation (2026-11-08):** the current reconstruction pipeline was run on the local uploaded file. Blender exported a 626,148-byte GLB and its mesh sanity check passed, but the 12-iteration optimizer did not converge. The independent re-imported-GLB validation failed multiple dimensions. This is a verified pipeline run, not an accuracy acceptance.

## Phase 1 acceptance checklist (audit 2026-11-08)

- [x] Git baseline and lockfiles exist; personal measurements and generated artifacts are excluded.
- [x] Express is the browser-facing `/api` gateway; Vite forwarding and FastAPI proxy were exercised over HTTP.
- [x] MongoDB ping and Express connection status were verified.
- [x] Python interface and payload/error semantics are documented; synthetic upload and job-status routes were exercised through the gateway.
- [x] Express liveness and dependency-aware readiness report actual local service status.
- [x] Python unit/API suite and Express tests pass; frontend production build and dependency audit pass.
- [x] No user model/data/reconstruction script was deleted; only a verified duplicate root base mesh and disposable OS/Python cache files were removed before the baseline commit.

Phase 1 setup and service-boundary acceptance is complete. Phase 2 authentication is implemented with local tests. Docker deployment checks remain pending because Docker is unavailable.

### Measurement/reconstruction audit status (2026-11-08)

The full findings are in [docs/measurement-reconstruction-audit.md](docs/measurement-reconstruction-audit.md). Key code changes from that audit:

- `reconstruction/json_parser.py` retains nested `left`/`right` measurements and their side-level provenance; bilateral values are not silently averaged. Null/invalid landmark coordinates no longer become zero.
- `reconstruction/measurement_validator.py` checks bilateral values individually and leaves null measurements null.
- `reconstruction/exported_mesh_validator.py` re-imports the GLB and independently measures its geometry. The report includes target, generated, absolute/percentage error, explicit method and pass/fail; unsupported limb measurements fail overall validation.
- `blender/reconstruct.py` records vertex-level geometry changes and the independent exported-GLB report. The frontend now labels failed target checks instead of implying that export means measurements matched.

Verification: `./.venv312/bin/python -m pytest -q` passed **33 tests** (one existing Starlette/HTTPX deprecation warning); `frontend/npm run build` passed with a large-chunk warning; `git diff --check` passed. Blender 5.2.3 processed the actual ignored upload, changed 19,158/19,158 vertices, passed mesh integrity, exported a 626,148-byte GLB, and re-imported it for independent measurements. The independent report failed: height 167.357/170 cm; chest/waist/hip circumferences 94.986/92.730, 75.899/75.300 and 97.371/95.840 cm; shoulder breadth 32.118/41 cm; chest/waist/hip cross-section width/depth checks mostly exceeded tolerance; arm-span bbox proxy 101.146/164 cm. Exported GLB dimensions are 101.146 × 40.277 × 167.357 cm versus the source asset's 105.10 × 43.00 × 165.94 cm. Inseam, thigh and calf generated measurements are unsupported. Full figures and measurement definitions are recorded in the audit document.

The audited JSON declares all 31 landmarks as `reconstruction_model` with confidence 0.95; 10 paired landmarks are exactly mirrored. It declares 93 populated scalar/side measurements with identical confidence 0.93 and uncertainty 1.14 cm. The upstream extractor is absent, so the video/image origin and calibration behind those metadata claims cannot be verified. Most dimensions are declared as mesh-, landmark-, contour-, anthropometric-proportion-, or canonical-T-pose-derived. The input is therefore not evidence of 69 direct measurements of the person.

**Phase 4/5 accuracy gate: not passed.** The selected asset is a generic MPFB/MakeHuman template (19,158 vertices, 18,486 faces, 165.94 cm high, 105.10 cm bbox wide, 43.00 cm deep) with nine gender/ethnicity macro keys, no independent body-region shape-key controls. Current deformation independently adjusts height, shoulder breadth and torso sections only. Limb, hand, foot and per-side body shape controls remain unsupported. Mesh license/provenance remains unverified.

**Still pending:** real upstream capture/extractor code and ground-truth calibration; landmark asymmetry preservation; height mismatch correction; calibrated cross-section mapping; independent bilateral limb stations/deformation; running service + browser verification of GLB loading and report download. Do not mark measurement-driven reconstruction complete or proceed past the Phase 4/5 accuracy gate until these checks pass on a labeled authorized fixture. Docker deployment checks also remain pending because Docker is unavailable.
