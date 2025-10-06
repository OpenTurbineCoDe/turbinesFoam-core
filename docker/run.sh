set -euo pipefail

IMAGE="turbinesfoam-core:v2406"   # IMAGE TAG
CONTAINER_NAME="turbinesfoam-core"

# Host <-> container paths/ports
HOST_PORT=5555
CONTAINER_PORT=5555

# Optional: map a host work dir (e.g., a case) into /work (read/write)
HOST_WORKDIR="$(pwd)/work"      # create if you want to run cases from host
mkdir -p "$HOST_WORKDIR"

# Launch interactive shell with OpenFOAM env + your compiled binaries
# - Remove "-it" if running in Docker Desktop GUI
docker run --rm -it \
  --name "$CONTAINER_NAME" \
  -p "${HOST_PORT}:${CONTAINER_PORT}" \
  -v "$HOST_WORKDIR":/work \
  "$IMAGE" \
  bash -lc 'source "$FOAM_BASHRC"; echo "OpenFOAM: $(foamVersion)"; echo "User bins: $FOAM_USER_APPBIN"; exec bash'
