#!/usr/bin/env bash
# Apply the canonical character template (macros, skillbar, keybinds,
# UI window layout) from templates/character/default/ onto a target
# character on this host. Idempotent — safe to re-run.
#
# Usage:
#   ./apply-character-template.sh <character_name> [--no-admin]
#
# Default: target character also gets admin_status=200 (full GM).
# Pass --no-admin to leave them as a normal player.
#
# Configurable via env:
#   EQ2EMU_SERVER       (default: bakerworld) — used in the UI file name
#   EQ2_CLIENT_DIR      (default: /home/jbaker/eq2emu/eq2-game)
#   EQ2EMU_MYSQL_CONTAINER (default: docker-mysql-1)

set -euo pipefail

CHARNAME="${1:-}"
[ -n "$CHARNAME" ] || { echo "usage: $0 <character_name> [--no-admin]" >&2; exit 1; }

ADMIN=200
[ "${2:-}" = "--no-admin" ] && ADMIN=0

SERVER="${EQ2EMU_SERVER:-bakerworld}"
EQ2_CLIENT_DIR="${EQ2_CLIENT_DIR:-/home/jbaker/eq2emu/eq2-game}"
MYSQL_CONTAINER="${EQ2EMU_MYSQL_CONTAINER:-docker-mysql-1}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
TEMPLATE_DIR="$REPO/templates/character/default"

for f in macros.sql skillbar.sql keymap.sql uisettings.ini; do
    [ -f "$TEMPLATE_DIR/$f" ] || { echo "missing template: $TEMPLATE_DIR/$f" >&2; exit 1; }
done

[ -f "$REPO/docker/.env" ] || { echo "missing $REPO/docker/.env" >&2; exit 1; }
PASS=$(grep '^MARIADB_ROOT_PASSWORD=' "$REPO/docker/.env" | cut -d= -f2 | tr -d '"')

docker ps --format '{{.Names}}' | grep -qx "$MYSQL_CONTAINER" || \
    { echo "error: '$MYSQL_CONTAINER' not running" >&2; exit 1; }

CHAR_ID=$(docker exec -e MYSQL_PWD="$PASS" "$MYSQL_CONTAINER" \
    mysql -uroot eq2emu -Bse "SELECT id FROM characters WHERE name='$CHARNAME' LIMIT 1;" 2>/dev/null || true)

[ -n "$CHAR_ID" ] || { echo "error: no character named '$CHARNAME' in DB" >&2; exit 1; }

echo "==> applying template to '$CHARNAME' (char_id=$CHAR_ID, admin_status=$ADMIN)"

TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT

{
    echo "START TRANSACTION;"
    echo "DELETE FROM character_macros   WHERE char_id=$CHAR_ID;"
    echo "DELETE FROM character_skillbar WHERE char_id=$CHAR_ID;"
    sed "s/__CHAR_ID__/$CHAR_ID/g" "$TEMPLATE_DIR/macros.sql"
    sed "s/__CHAR_ID__/$CHAR_ID/g" "$TEMPLATE_DIR/skillbar.sql"
    sed "s/__CHAR_ID__/$CHAR_ID/g" "$TEMPLATE_DIR/keymap.sql"
    echo "UPDATE characters SET admin_status=$ADMIN WHERE id=$CHAR_ID;"
    echo "COMMIT;"
} > "$TMP"

docker exec -i -e MYSQL_PWD="$PASS" "$MYSQL_CONTAINER" \
    mysql -uroot eq2emu < "$TMP" 2>/dev/null

echo "==> DB rows applied (macros, skillbar, keymap, admin_status)"

LCNAME=$(echo "$CHARNAME" | tr '[:upper:]' '[:lower:]')
DEST="$EQ2_CLIENT_DIR/${SERVER}_${LCNAME}_eq2_uisettings.ini"

if [ -f "$DEST" ]; then
    BAK="${DEST}.bak.$(date +%s)"
    cp "$DEST" "$BAK"
    echo "==> backed up existing UI file → $BAK"
fi

cp "$TEMPLATE_DIR/uisettings.ini" "$DEST"
echo "==> wrote UI file → $DEST"

echo
echo "✓ '$CHARNAME' configured. Log out + back in to load the changes."
