# Blender Integration

## Local installation and configuration

Download the Apple Silicon `.dmg` from the [official Blender macOS installation page](https://docs.blender.org/manual/en/5.2/getting_started/installing/macos.html), open it, and move `Blender.app` into `/Applications`. On this Mac, Blender 5.2.3 LTS is installed at:

```text
/Applications/Blender.app/Contents/MacOS/Blender
```

ModelMe resolves the executable in this order:

1. `BLENDER_EXECUTABLE` from the process environment (or `.env`).
2. `blender` found on `PATH`.
3. `/Applications/Blender.app/Contents/MacOS/Blender`.
4. `~/Applications/Blender.app/Contents/MacOS/Blender`.

Copy `.env.example` to `.env` and set `BLENDER_EXECUTABLE` if Blender is installed in a nonstandard location. The Python processing process must receive the environment variable. For a local shell, load it before launching FastAPI:

```sh
set -a
. ./.env
set +a
./.venv312/bin/python -m uvicorn backend.main:app --reload --port 8000
```

The Express development command reads the root `.env` itself. Compose passes the configured executable path into the isolated reconstruction container; that image installs its pinned Linux Blender separately.

## Verify Blender and `bpy`

```sh
"$BLENDER_EXECUTABLE" --version
"$BLENDER_EXECUTABLE" --background --python-expr \
  "import bpy; print('BPY_OK', bpy.app.version_string)"
```

Some macOS Blender builds crash during Metal detection when launched inside a restricted process sandbox. If the command exits with SIGSEGV before printing `BPY_OK`, run it from a normal Terminal or an approved unsandboxed process. The crash happens before Python starts and does not prove the installed Blender is unusable.

## Run the safe export smoke test

This test creates an isolated cube scene, exports a GLB, and validates the GLB magic/version/declared byte length. It does not open or modify the human base mesh and does not call the human reconstruction script.

```sh
"$BLENDER_EXECUTABLE" --background --python blender/blender_smoke.py -- \
  --output output/blender_smoke_test.glb
```

The generated file is in the ignored `output/` folder. The script exits nonzero if export or GLB validation fails.

## Health behavior

`GET /api/health` on FastAPI checks that the configured Blender path is an executable file and that `assets/base_human/base_human.blend` exists. It returns `status: ok` only when both are available. This endpoint does not run Blender or validate the base mesh topology on every health request; the separate smoke script verifies `bpy` and export capability.
