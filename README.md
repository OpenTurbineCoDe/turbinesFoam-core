# turbinesFoam-core

Containerized core for OpenFOAM v2406 with custom solvers and a Linux-side protocol server.

## Layout
- `src/PimpleFoamMy/` – modified PimpleFoam (uncompiled in repo; compiled in image)
- `src/turbinesFoamMy/` – modified turbinesFoam (uncompiled in repo; compiled in image)
- `protocol-server/` – FastAPI server exposing `/initialize`, `/step`, `/health`
- `docker/` – Dockerfile and helper scripts
- `scripts/compile_solvers.sh` – (re)build both solvers inside container

## Quick start

```bash
# 1) Build the image
./docker/build.sh

# 2) Run the container (starts protocol server on :5555)
./docker/run.sh

# 3) Health check (from host)
curl http://localhost:5555/health
