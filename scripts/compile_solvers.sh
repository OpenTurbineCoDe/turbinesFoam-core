#!/usr/bin/env bash
set -euo pipefail

# Resolve SRC_DIR
: "${SRC_DIR:=/opt/turbinesFoam-core/src}"

# Resolve FOAM_BASHRC (prefer env, fallbacks for OpenCFD images)
FOAM_BASHRC_PATH="${FOAM_BASHRC:-}"
if [[ -z "$FOAM_BASHRC_PATH" ]]; then
  if [[ -f /usr/lib/openfoam/openfoam2406/etc/bashrc ]]; then
    FOAM_BASHRC_PATH=/usr/lib/openfoam/openfoam2406/etc/bashrc
  else
    # Last-resort glob (won't error if empty due to '|| true')
    FOAM_BASHRC_PATH=$(ls /usr/lib/openfoam/*/etc/bashrc 2>/dev/null | head -n1 || true)
  fi
fi
if [[ -z "$FOAM_BASHRC_PATH" || ! -f "$FOAM_BASHRC_PATH" ]]; then
  echo "ERROR: Could not locate OpenFOAM bashrc. Set FOAM_BASHRC env." >&2
  exit 1
fi

# Source OpenFOAM env (avoid nounset/errexit issues during sourcing)
set +eux
# shellcheck disable=SC1090
source "$FOAM_BASHRC_PATH"
set -e

echo "[compile] Building PimpleFoamMy..."
pushd "$SRC_DIR/PimpleFoamMy" >/dev/null
wmake
popd >/dev/null

echo "[compile] Building turbinesFoamMy (lib)..."
pushd "$SRC_DIR/turbinesFoamMy/src" >/dev/null
wmake libso
popd >/dev/null

echo "[compile] Done."
