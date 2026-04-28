#!/usr/bin/env bash
# Bring the EQ2Emu stack down cleanly.
#
# What it does:
#   1. docker compose down (stops + removes containers and networks)
#
# What it does NOT do:
#   - Touch named volumes (mysql data, anonymous server volume).
#     Use `docker compose down -v` from the docker/ dir if you want
#     to wipe ALL persistent state — that's a destructive operation
#     not in this script's scope.
#   - Take a DB backup. If you want one before stopping, run
#     `scripts/backup-db.sh` first (when it exists) or take a
#     manual mysqldump.
#
# Run from anywhere:
#   ./scripts/server-down.sh

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
DOCKER_DIR="$REPO/docker"

if [ ! -f "$DOCKER_DIR/.env" ]; then
    echo "warning: $DOCKER_DIR/.env not found — compose may fail to read variables" >&2
fi

echo "==> docker compose down"
( cd "$DOCKER_DIR" && docker compose down )

echo ""
echo "✓ server down. data persists in named volumes."
echo "  bring it back up with: ./scripts/server-up.sh"
