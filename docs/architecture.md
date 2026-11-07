# ModelMe Architecture

## Target data flow

```text
React/Vite → Express API + JWT → MongoDB (users, profiles, measurements, job metadata)
                         │
                         └→ durable job queue → Python worker → Blender
                                                      │
                                                      └→ GLB in object storage
React Three Fiber ← authorized model API/download ←───┘
```

MongoDB stores user/profile/measurement data and generation metadata. GLB binaries stay in object storage. The Express request lifecycle must not wait for a Blender process: it creates a job, returns a job ID, and the worker updates durable progress/results.

## Current architecture and migration bridge

```text
React/Vite → Vite /api proxy → Express health/auth/profile API
                                  │
                                  └→ temporary proxy → FastAPI job API
                                                         │
                                                         └→ Blender subprocess
                                                               └→ reconstruction/*
```

The existing FastAPI app remains the temporary owner of upload and model-generation routes until Phase 6 has a compatible Express job API and Python worker. The existing `reconstruction/` modules remain the source of measurement/deformation behavior until a moved copy passes parity checks. Do not delete either legacy path as part of Phase 1 cleanup.

## Phase 1 service layout

```text
frontend/                        React/Vite client
services/api/src/                Express app, routes, config and DB connection
backend/                         temporary FastAPI reconstruction API
reconstruction/                  existing Python processing modules
blender/                         Blender background scripts
assets/base_human/                configured canonical mesh
docs/architecture.md
DEVELOPMENT_PLAN.md
```

## Phase 2+ target layout

```text
frontend/src/features/{auth,profiles,measurements,viewer,history}/
services/api/src/{config,db,middleware,models,routes,services}/
services/reconstruction/{worker,engine}/
blender/
assets/base_human/{mesh,LICENSE,calibration.json}
tests/{api,frontend,processing,e2e}/
```

## Decisions and constraints

1. **Express is the target public API.** FastAPI is retained as a temporary bridge so the current generation UI and Python/Blender path are not thrown away before replacement.
2. **Python/Blender stays a separate worker.** It owns geometry work, not user authentication or profile authorization.
3. **Calibrate circumference as a cross-section objective.** Do not equate circumference to a single width/depth value. Validation must include measured cross-sections and reference comparisons.
4. **Protect body data and models.** Treat uploaded measurements as sensitive. Auth and per-user authorization are required before public exposure; keep local measurements and GLBs out of Git and container build context.
5. **Use durable state for jobs.** Current jobs are process-memory records plus JSON files. Replace with persisted records/queue in Phase 6; ensure restarts can recover or mark interrupted jobs.
6. **Pin native runtimes.** Python and Blender versions must be explicit in the worker image and verified against the checked-in `.blend` asset.
7. **Retain unverified assets.** Only the root `base_human.blend` is known to be byte-identical to `assets/base_human/base_human.blend`. Other root `.blend` variants remain until Phase 4 identifies their value.
8. **Deployment is a gated outcome.** Docker is not installed locally. Compose files can be prepared, but deployment is not complete until a container build, health check, sample reconstruction and secured deployment pass.
