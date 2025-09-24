#!/usr/bin/env bash
set -euo pipefail

# Rebuild both solvers inside a running container (or at image build time).
# Requires OpenFOAM env to be sourced first.
if [[ -z "${SRC_DIR:-}" ]]; then
  echo "SRC_DIR not set. Using default /opt/turbinesFoam-core/src"
  SRC_DIR=/opt/turbinesFoam-core/src
fi

source /opt/openfoam*/etc/bashrc

echo "[compile] Building PimpleFoamMy..."
pushd "$SRC_DIR/PimpleFoamMy"
wmake
popd

echo "[compile] Building turbinesFoamMy..."
pushd "$SRC_DIR/turbinesFoamMy"
wmake
popd

echo "[compile] Done."
