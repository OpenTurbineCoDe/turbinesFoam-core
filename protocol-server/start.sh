#!/usr/bin/env bash
set -euo pipefail

# Ensure OpenFOAM environment is available for any subprocesses
source /opt/openfoam*/etc/bashrc

# Activate venv
CORE_HOME=${CORE_HOME:-/opt/turbinesFoam-core}
source "$CORE_HOME/.venv/bin/activate"

# Start the service
exec uvicorn app.main:app --host 0.0.0.0 --port 5555
