#!/usr/bin/env bash
set -euo pipefail

: "${CORE_HOME:=/opt/turbinesFoam-core}"
: "${FOAM_BASHRC:=/usr/lib/openfoam/openfoam2406/etc/bashrc}"

# Optional: don't crash if OpenFOAM env isn't needed
# source "$FOAM_BASHRC" || true

# Activate venv
source "$CORE_HOME/.venv/bin/activate"

# Run from the server dir
cd "$CORE_HOME/protocol-server"

# IMPORTANT: this assumes your FastAPI file is protocolserver.py with "app = FastAPI()"
exec python3 -m uvicorn app:app --host 0.0.0.0 --port 5555 --workers 1 --timeout-keep-alive 120
