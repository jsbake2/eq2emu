#!/usr/bin/env bash
# Deploy custom Lua spell scripts into the eq2world container's
# /eq2emu/eq2emu/server/Spells/ tree. Idempotent — overwrites in place.
#
# eq2world resolves spell.lua_script paths relative to its CWD, which is
# /eq2emu/eq2emu/server/. So a spell row with lua_script =
# "Spells/Commoner/BotPrepull.lua" must have a corresponding file at
# /eq2emu/eq2emu/server/Spells/Commoner/BotPrepull.lua.
#
# That tree lives in an anonymous Docker volume — survives `compose down`
# but reset on `compose down -v`. Re-running this script after any reset
# restores the custom scripts.
#
# Run from anywhere; called automatically by scripts/server-up.sh.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
SRC="$REPO/lua/spells"
CONTAINER="${EQ2EMU_SERVER_CONTAINER:-docker-eq2emu-server-1}"
DEST="/eq2emu/eq2emu/server/Spells"

if [ ! -d "$SRC" ]; then
    echo "no custom lua at $SRC — nothing to deploy"
    exit 0
fi

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    echo "error: container '$CONTAINER' is not running" >&2
    exit 1
fi

# Walk each top-level subdirectory of $SRC (Commoner, Priest, etc.) and
# docker cp its contents into the matching destination. Trailing dot on
# the source ensures we copy contents, not the directory itself.
copied=0
for dir in "$SRC"/*/; do
    [ -d "$dir" ] || continue
    sub="$(basename "$dir")"
    docker exec "$CONTAINER" mkdir -p "$DEST/$sub"
    docker cp "$dir." "$CONTAINER:$DEST/$sub/"
    n=$(find "$dir" -maxdepth 1 -name '*.lua' | wc -l)
    copied=$((copied + n))
    echo "  deployed $n script(s) → Spells/$sub/"
done

echo "done. ${copied} custom lua script(s) deployed to $CONTAINER."
