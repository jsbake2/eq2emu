#!/usr/bin/env bash
# Bring the EQ2Emu stack up cleanly. Idempotent — safe to run while
# the stack is already up; only does work that's actually needed.
#
# What it does:
#   1. docker compose up -d (no-op if already running)
#   2. Wait for mysql to be healthy and eq2world to connect to login
#   3. Re-apply all server-patches/*.patch to the in-container source
#      (idempotent; skips already-applied patches)
#   4. If patches got freshly applied OR the running binary is older
#      than the patched source, rebuild + hot-swap eq2world
#   5. Verify game ports are listening on 127.0.0.1 + 192.168.122.1
#
# Why this matters: container recreation (docker compose down + up)
# resets the source clone to upstream HEAD and may overwrite the
# binary in /eq2emu/eq2emu/server/ via install.sh's first-run hook.
# This script reliably restores the patched state without manual
# steps.
#
# Run from anywhere:
#   ./scripts/server-up.sh

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
DOCKER_DIR="$REPO/docker"
SERVER_CONTAINER="${EQ2EMU_SERVER_CONTAINER:-docker-eq2emu-server-1}"
MYSQL_CONTAINER="${EQ2EMU_MYSQL_CONTAINER:-docker-mysql-1}"
SOURCE_DIR="/eq2emu/eq2emu/source"
SERVER_DIR="/eq2emu/eq2emu/server"

if [ ! -f "$DOCKER_DIR/.env" ]; then
    echo "error: $DOCKER_DIR/.env not found — copy .env.example and fill in secrets first" >&2
    exit 1
fi

echo "==> docker compose up"
( cd "$DOCKER_DIR" && docker compose up -d )

echo "==> waiting for mysql healthy"
until docker exec "$MYSQL_CONTAINER" mysqladmin ping -h localhost --silent >/dev/null 2>&1; do
    sleep 2
done

echo "==> waiting for eq2world to connect to login"
until docker exec "$SERVER_CONTAINER" sh -c \
    "pidof eq2world >/dev/null && grep -q 'Connected to LoginServer' $SERVER_DIR/logs/eq2world.log 2>/dev/null"; do
    sleep 3
done

echo "==> applying server patches"
"$REPO/scripts/apply-server-patches.sh"

# Decide whether a rebuild is needed. Cheap mtime compare: any patched
# source file newer than the running binary means we need to rebuild.
PATCHED_MTIME=$(docker exec "$SERVER_CONTAINER" sh -c \
    "stat -c %Y $SOURCE_DIR/WorldServer/Bots/BotBrain.cpp 2>/dev/null || echo 0")
BINARY_MTIME=$(docker exec "$SERVER_CONTAINER" sh -c \
    "stat -c %Y $SERVER_DIR/eq2world 2>/dev/null || echo 0")

if [ "$PATCHED_MTIME" -gt "$BINARY_MTIME" ]; then
    echo "==> patched source ($PATCHED_MTIME) newer than binary ($BINARY_MTIME) — rebuilding"
    docker exec "$SERVER_CONTAINER" sh -c \
        "cd $SOURCE_DIR/WorldServer && make -j\$(nproc)" 2>&1 | tail -3

    echo "==> hot-swapping eq2world"
    STAMP="$(date +%Y%m%d-%H%M%S)"
    OLD_PID="$(docker exec "$SERVER_CONTAINER" sh -c 'pidof eq2world || true' | tr -d '[:space:]')"
    # `mv` (not `cp`) the running binary out of the path: the kernel keeps
    # the old inode for the running process, but the path becomes free for
    # the new binary. A `cp` would leave the path occupied and the next
    # `cp` of the new binary would hit ETXTBSY ("Text file busy").
    # `sh -e` so any failure aborts BEFORE we kill the running process —
    # otherwise we'd end up with no binary at the path and Dawn looping.
    # `pkill -x eq2world` (NOT `-f './eq2world'`) — `-f` matches the full
    # cmdline, which would also match the sh running this heredoc (its
    # argv contains the literal pattern), making pkill kill its own shell
    # before `|| true` can swallow the failure. `-x` matches only the
    # process name, hitting eq2world cleanly.
    docker exec "$SERVER_CONTAINER" sh -e -c "
        cd $SERVER_DIR &&
        mv eq2world eq2world.pre-up-$STAMP &&
        cp $SOURCE_DIR/WorldServer/eq2world eq2world &&
        chmod +x eq2world &&
        pkill -x eq2world || true
    "

    echo "==> waiting for eq2world to come back (pre-swap pid was $OLD_PID)"
    # Require a NEW pid (different from pre-swap) AND a fresh "Connected
    # to LoginServer" line — otherwise "still up" right after `pkill`
    # passes before Dawn has restarted the binary.
    until docker exec "$SERVER_CONTAINER" sh -c \
        "NEW=\$(pidof eq2world 2>/dev/null); \
         [ -n \"\$NEW\" ] && [ \"\$NEW\" != \"$OLD_PID\" ] && \
         grep -q 'Connected to LoginServer' $SERVER_DIR/logs/eq2world.log"; do
        sleep 3
    done
else
    echo "==> binary is up to date with patched source ($BINARY_MTIME >= $PATCHED_MTIME) — no rebuild"
fi

echo ""
echo "==> verifying game ports"
ss -ulnp 2>/dev/null | grep -E ':9001|:9100' | head -8 || echo "  (couldn't read ss; check manually)"

echo ""
echo "✓ server up. login on UDP 9100, world on UDP 9001 (127.0.0.1 + 192.168.122.1)."
echo "  bring it down with: ./scripts/server-down.sh"
