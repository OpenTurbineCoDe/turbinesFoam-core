#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME=${IMAGE_NAME:-turbinesfoam-core:v2406}
CONTAINER_NAME=${CONTAINER_NAME:-turbinesfoam-core}
PORT=${PORT:-5555}

# Map protocol port; mount nothing by default (image contains compiled solvers)
docker run --rm -it \
  --name "$CONTAINER_NAME" \
  -p "${PORT}:5555" \
  "$IMAGE_NAME"
