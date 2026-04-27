#!/usr/bin/env bash
# Apply all patches in server-patches/ to the WorldServer/LoginServer source
# clone inside the running eq2emu-server container.
#
# Idempotent: patches that already apply in reverse are treated as already
# applied (skipped, not errored).

set -euo pipefail

CONTAINER="${EQ2EMU_SERVER_CONTAINER:-docker-eq2emu-server-1}"
SOURCE_DIR="/eq2emu/eq2emu/source"
PATCH_STAGE="/tmp/eq2emu-patches"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
PATCH_DIR="$REPO_ROOT/server-patches"

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    echo "error: container '$CONTAINER' is not running" >&2
    exit 1
fi

shopt -s nullglob
patches=("$PATCH_DIR"/*.patch)
shopt -u nullglob

if [ ${#patches[@]} -eq 0 ]; then
    echo "no patches in $PATCH_DIR — nothing to do"
    exit 0
fi

docker exec "$CONTAINER" sh -c "rm -rf $PATCH_STAGE && mkdir -p $PATCH_STAGE"

for p in "${patches[@]}"; do
    docker cp "$p" "$CONTAINER:$PATCH_STAGE/$(basename "$p")"
done

echo "applying ${#patches[@]} patch(es) to $SOURCE_DIR in $CONTAINER..."
for p in "${patches[@]}"; do
    name="$(basename "$p")"
    if docker exec "$CONTAINER" sh -c \
        "cd $SOURCE_DIR && git apply --reverse --check $PATCH_STAGE/$name" 2>/dev/null; then
        echo "  [skip] $name (already applied)"
        continue
    fi

    if docker exec "$CONTAINER" sh -c \
        "cd $SOURCE_DIR && git apply --check $PATCH_STAGE/$name" 2>/dev/null; then
        docker exec "$CONTAINER" sh -c \
            "cd $SOURCE_DIR && git apply $PATCH_STAGE/$name"
        echo "  [ok]   $name"
    else
        echo "  [fail] $name (conflict — resolve manually)" >&2
        exit 1
    fi
done

echo "done. rebuild with: docker exec $CONTAINER /eq2emu/compile_source.sh"
