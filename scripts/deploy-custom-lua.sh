#!/usr/bin/env bash
# Deploy custom Lua scripts into the eq2world container's runtime tree.
# Idempotent — overwrites in place.
#
# Tree mappings (host repo → container path):
#   lua/spells/<Subdir>/        → /eq2emu/eq2emu/server/Spells/<Subdir>/
#   lua/SpawnScripts/<Subdir>/  → /eq2emu/eq2emu/server/SpawnScripts/<Subdir>/
#
# eq2world resolves Lua paths relative to its CWD (/eq2emu/eq2emu/server/),
# so a spell row with lua_script="Spells/Commoner/BotPrepull.lua" or a
# spawn-script reference of "SpawnScripts/IsleRefuge1/Foo.lua" must have a
# matching file under that path in the container.
#
# These trees live in an anonymous Docker volume — survive `compose down`
# but reset on `compose down -v`. Re-run after any reset.
#
# Run from anywhere; called automatically by scripts/server-up.sh.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
CONTAINER="${EQ2EMU_SERVER_CONTAINER:-docker-eq2emu-server-1}"

# host_subdir:container_subdir
TREES=(
    "lua/spells:Spells"
    "lua/SpawnScripts:SpawnScripts"
)

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    echo "error: container '$CONTAINER' is not running" >&2
    exit 1
fi

total=0
deployed_any=0
for mapping in "${TREES[@]}"; do
    host_rel="${mapping%%:*}"
    container_sub="${mapping##*:}"
    src="$REPO/$host_rel"
    dest="/eq2emu/eq2emu/server/$container_sub"

    [ -d "$src" ] || continue
    deployed_any=1

    # Walk each top-level subdirectory (e.g. Commoner, IsleRefuge1) and
    # docker cp its contents into the matching destination. Trailing dot
    # ensures we copy contents, not the directory itself.
    for dir in "$src"/*/; do
        [ -d "$dir" ] || continue
        sub="$(basename "$dir")"
        docker exec "$CONTAINER" mkdir -p "$dest/$sub"
        docker cp "$dir." "$CONTAINER:$dest/$sub/"
        n=$(find "$dir" -maxdepth 1 -name '*.lua' | wc -l)
        total=$((total + n))
        echo "  deployed $n script(s) → $container_sub/$sub/"
    done
done

if [ $deployed_any -eq 0 ]; then
    echo "no custom lua trees populated under $REPO/lua/ — nothing to deploy"
    exit 0
fi

echo "done. ${total} custom lua script(s) deployed to $CONTAINER."
