#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME=${IMAGE_NAME:-turbinesfoam-core:v2406}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

docker build \
  -f "$SCRIPT_DIR/Dockerfile" \
  -t "$IMAGE_NAME" \
  "$(dirname "$SCRIPT_DIR")"
