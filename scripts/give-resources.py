#!/usr/bin/env python3
"""
Grant coin / status / faction adjustments to a character.

Usage:
    ./scripts/give-resources.py --name <character> [flags]

Flags:
    --plat N            add N platinum (default 0)
    --gold N            add N gold (handles overflow → plat at end)
    --silver N          add N silver
    --copper N          add N copper
    --status N          add N status points
    --faction NAME=AMT  adjust faction by AMT (positive = raise, negative = lower).
                        Faction matched by case-insensitive substring on factions.name.
                        Repeatable: --faction "Qeynos=2000" --faction "Foo=-500"

Coin overflow is normalized at the end (1000 copper → 10 silver → 1 gold,
1 plat = 100 gold etc.). Status is just additive. Faction adjustments
upsert into character_factions and clamp the resulting level to
[-50000, 50000] (the engine's typical range).

Character must be offline — character_details is read into memory on
load and overwritten on save.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

import pymysql

REPO = Path(__file__).resolve().parent.parent
ENV = REPO / "docker" / ".env"
SERVER_CONTAINER = "docker-eq2emu-server-1"
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def load_env():
    kv = {}
    for line in ENV.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        kv[k.strip()] = v.strip().strip('"').strip("'")
    return kv


def check_offline(name):
    """Return None if the character is offline, else a description string.

    Trusts the authoritative characters.is_online flag — the world server
    sets it on login and clears it on logout/disconnect. The previous
    implementation tailed eq2world.log, which produced false positives
    for hours after a player had camped because old log lines remain in
    the buffer.
    """
    try:
        env = load_env()
        conn = pymysql.connect(
            host="127.0.0.1", port=3306, user="root",
            password=env["MARIADB_ROOT_PASSWORD"], database=env["MARIADB_DATABASE"],
            cursorclass=pymysql.cursors.DictCursor, charset="utf8mb4",
        )
    except (pymysql.MySQLError, KeyError, OSError):
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT is_online FROM characters WHERE name = %s LIMIT 1",
                (name,),
            )
            row = cur.fetchone()
            if row and row.get("is_online"):
                return "characters.is_online = 1 (DB)"
    finally:
        conn.close()
    return None


def normalize_coin(c, s, g, p):
    """Roll up copper → silver → gold → plat. 100 of each tier per next."""
    if c >= 100:
        s += c // 100
        c %= 100
    if s >= 100:
        g += s // 100
        s %= 100
    if g >= 100:
        p += g // 100
        g %= 100
    return c, s, g, p


def find_faction(cur, query):
    cur.execute(
        "SELECT id, name FROM factions WHERE LOWER(name) LIKE %s ORDER BY id LIMIT 5",
        (f"%{query.lower()}%",),
    )
    rows = cur.fetchall()
    if not rows:
        return None, []
    if len(rows) > 1:
        return None, rows
    return rows[0], []


FACTION_MIN, FACTION_MAX = -50000, 50000


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--name", required=True, help="character name")
    p.add_argument("--plat", type=int, default=0)
    p.add_argument("--gold", type=int, default=0)
    p.add_argument("--silver", type=int, default=0)
    p.add_argument("--copper", type=int, default=0)
    p.add_argument("--status", type=int, default=0)
    p.add_argument("--faction", action="append", default=[],
                   help="NAME=AMOUNT (repeatable; substring match on faction name)")
    p.add_argument("--force", action="store_true", help="skip offline check")
    p.add_argument("--dry-run", action="store_true", help="print plan, no DB writes")
    args = p.parse_args()

    coin_delta_total = abs(args.plat) + abs(args.gold) + abs(args.silver) + abs(args.copper)
    if not (coin_delta_total or args.status or args.faction):
        sys.exit("error: nothing to do — pass at least one of --plat/--gold/--silver/--copper/--status/--faction")

    # Pre-parse faction adjustments.
    faction_changes = []
    for spec in args.faction:
        if "=" not in spec:
            sys.exit(f"error: --faction expects NAME=AMOUNT; got '{spec}'")
        name_q, amt_q = spec.rsplit("=", 1)
        try:
            amt = int(amt_q)
        except ValueError:
            sys.exit(f"error: --faction amount must be an integer; got '{amt_q}'")
        faction_changes.append((name_q.strip(), amt))

    if not args.force:
        line = check_offline(args.name)
        if line:
            print(f"error: '{args.name}' looks online — recent log line:", file=sys.stderr)
            print(f"  {line}", file=sys.stderr)
            print(f"  /camp first, then re-run; or pass --force.", file=sys.stderr)
            sys.exit(2)

    env = load_env()
    conn = pymysql.connect(
        host="127.0.0.1", port=3306, user="root",
        password=env["MARIADB_ROOT_PASSWORD"], database=env["MARIADB_DATABASE"],
        cursorclass=pymysql.cursors.DictCursor, charset="utf8mb4",
        autocommit=False,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name FROM characters WHERE name = %s",
                (args.name,),
            )
            char = cur.fetchone()
            if not char:
                sys.exit(f"error: no character named '{args.name}'")
            char_id = char["id"]

            cur.execute(
                """
                SELECT coin_copper, coin_silver, coin_gold, coin_plat, status_points
                  FROM character_details WHERE char_id = %s
                """,
                (char_id,),
            )
            details = cur.fetchone()
            if not details:
                sys.exit(f"error: no character_details row for char_id={char_id}")

            print(f"=== {char['name']} (id={char_id}) ===")

            # Coin
            new_c = details["coin_copper"] + args.copper
            new_s = details["coin_silver"] + args.silver
            new_g = details["coin_gold"] + args.gold
            new_p = details["coin_plat"] + args.plat
            new_c, new_s, new_g, new_p = normalize_coin(new_c, new_s, new_g, new_p)
            if coin_delta_total:
                print(f"  coin    : {details['coin_plat']}p {details['coin_gold']}g "
                      f"{details['coin_silver']}s {details['coin_copper']}c"
                      f"  →  {new_p}p {new_g}g {new_s}s {new_c}c")

            # Status
            new_status = details["status_points"] + args.status
            if args.status:
                print(f"  status  : {details['status_points']}  →  {new_status}")

            # Faction resolution + plan
            faction_plan = []
            for name_q, amt in faction_changes:
                fac, candidates = find_faction(cur, name_q)
                if not fac and candidates:
                    matches = ", ".join(f"{c['id']}:{c['name']}" for c in candidates)
                    sys.exit(f"error: faction '{name_q}' is ambiguous: {matches}")
                if not fac:
                    sys.exit(f"error: faction '{name_q}' not found")
                cur.execute(
                    "SELECT faction_level FROM character_factions "
                    "WHERE char_id = %s AND faction_id = %s",
                    (char_id, fac["id"]),
                )
                cur_row = cur.fetchone()
                cur_lvl = cur_row["faction_level"] if cur_row else 0
                new_lvl = max(FACTION_MIN, min(FACTION_MAX, cur_lvl + amt))
                faction_plan.append((fac, cur_lvl, new_lvl))
                print(f"  faction : {fac['name']:30s} {cur_lvl:+6d}  →  {new_lvl:+6d}  (Δ{amt:+})")

            if args.dry_run:
                print("\n--dry-run: no changes written")
                return

            if coin_delta_total or args.status:
                cur.execute(
                    """
                    UPDATE character_details
                       SET coin_copper = %s, coin_silver = %s, coin_gold = %s, coin_plat = %s,
                           status_points = %s
                     WHERE char_id = %s
                    """,
                    (new_c, new_s, new_g, new_p, new_status, char_id),
                )

            for fac, cur_lvl, new_lvl in faction_plan:
                cur.execute(
                    """
                    INSERT INTO character_factions (char_id, faction_id, faction_level)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE faction_level = VALUES(faction_level)
                    """,
                    (char_id, fac["id"], new_lvl),
                )

            conn.commit()
            print("\n✓ committed.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
