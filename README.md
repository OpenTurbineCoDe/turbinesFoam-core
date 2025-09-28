# turbinesFoam-core

Containerized core for OpenFOAM v2406 with custom solvers and a Linux-side protocol server.

## Required Installation
- Docker Desktop - Building the core image and running the core container
- GitHub Desktop - Cloning the repository and updating
- Git for Windows 2.51.0 x64 - Accessing docker build and run commands
- VSCode - Run environment


## Layout
- `src/PimpleFoamMy/` – modified PimpleFoam (uncompiled in repo; compiled in image)
- `src/turbinesFoamMy/` – modified turbinesFoam (uncompiled in repo; compiled in image)
- `protocol-server/` – FastAPI server exposing `/initialize`, `/step`, `/health`
- `docker/` – Dockerfile and helper scripts
- `scripts/compile_solvers.sh` – (re)build both solvers inside container

## Quick start

```bash
# 1) Download and install Docker Desktop
# 2) Install GitHub Desktop and clone this repository
# 3) Install and install Git for Windows x64 (Use default installation instructions)
# 4) Open turbinesFoam-core directory in VSCode
#    - Navigate Terminal -> New Terminal
#    - Press +v in the Terminal window and select Git Bash

# 5) Build the image (From bash)
./docker/build.sh

# 6) Run the container (starts protocol server on :5555)
./docker/run.sh

# 7) Health check (from host)
curl http://localhost:5555/health
```
