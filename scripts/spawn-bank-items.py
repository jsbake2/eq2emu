#!/usr/bin/env python3
"""
Spawn items into a character's bank bags from a YAML spec.

YAML format:

    character: Robskin
    bank:
      1:                              # bank slot (1-indexed, matches in-game UI)
        - {item: 35993, count: 20}    # by item_id
        - {item: "Nagafen's Flame", count: 20}   # or by name (case-insensitive, must be unique)
      2:
        - {item: 152754}              # count defaults to 1

Each bank slot must already contain a Bag-type item; the script places the
listed items into that bag at slots 0..N (in YAML order).

Usage:
    ./scripts/spawn-bank-items.py <yaml_file> [--dry-run] [--replace] [--force]

    --dry-run   print the plan, no DB writes
    --replace   wipe existing bag contents before inserting
                (default: error if any target slot is occupied)
    --force     skip the offline check

Reads MARIADB credentials from docker/.env. Connects to mysql via the
host-exposed 127.0.0.1:3306 (per docker-compose.override.yaml).
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

import pymysql
import yaml

REPO = Path(__file__).resolve().parent.parent
ENV = REPO / "docker" / ".env"
SERVER_CONTAINER = "docker-eq2emu-server-1"

# bag_id sentinel for the BANK top-level slots (per WorldServer/Items/Items.h).
BANK_BAG_ID = -3

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


def check_offline(char_name):
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
                (char_name,),
            )
            row = cur.fetchone()
            if row and row.get("is_online"):
                return "characters.is_online = 1 (DB)"
    finally:
        conn.close()
    return None


def get_char(cursor, name):
    cursor.execute("SELECT id, account_id FROM characters WHERE name = %s", (name,))
    row = cursor.fetchone()
    if not row:
        sys.exit(f"error: no character named '{name}'")
    return row["id"], row["account_id"]


def lookup_item(cursor, ref):
    """Resolve YAML 'item' field (int id or string name) → (id, name)."""
    if isinstance(ref, int):
        cursor.execute("SELECT id, name FROM items WHERE id = %s", (ref,))
        row = cursor.fetchone()
        if not row:
            sys.exit(f"error: item id {ref} not found")
        return row["id"], row["name"]
    cursor.execute(
        "SELECT id, name FROM items WHERE LOWER(name) = LOWER(%s) ORDER BY id",
        (ref,),
    )
    rows = cursor.fetchall()
    if not rows:
        sys.exit(f"error: no item named '{ref}'")
    if len(rows) > 1:
        ids = ", ".join(str(r["id"]) for r in rows[:8])
        sys.exit(f"error: name '{ref}' matches {len(rows)} items (ids: {ids}…); use the id")
    return rows[0]["id"], rows[0]["name"]


def get_bank_bag(cursor, char_id, bank_slot_1indexed):
    """Find the bag in BANK slot N (1-indexed). Return (row_id, num_slots)."""
    slot = bank_slot_1indexed - 1
    cursor.execute(
        """
        SELECT ci.id, ci.item_id, b.num_slots
          FROM character_items ci
          LEFT JOIN item_details_bag b ON b.item_id = ci.item_id
         WHERE ci.char_id = %s AND ci.bag_id = %s AND ci.slot = %s
        """,
        (char_id, BANK_BAG_ID, slot),
    )
    row = cursor.fetchone()
    if not row:
        sys.exit(f"error: no item in bank slot {bank_slot_1indexed}")
    if not row["num_slots"]:
        sys.exit(
            f"error: item in bank slot {bank_slot_1indexed} (item_id "
            f"{row['item_id']}) is not a Bag"
        )
    return row["id"], row["num_slots"]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("yaml_file", help="YAML file describing what to spawn")
    p.add_argument("--dry-run", action="store_true", help="print plan, no writes")
    p.add_argument("--replace", action="store_true", help="wipe bag contents before inserting")
    p.add_argument("--force", action="store_true", help="skip the offline check")
    args = p.parse_args()

    spec = yaml.safe_load(Path(args.yaml_file).read_text())
    char_name = spec["character"]
    bank = spec.get("bank") or {}

    if not args.force:
        line = check_offline(char_name)
        if line:
            print(f"error: '{char_name}' looks online — recent log line:", file=sys.stderr)
            print(f"  {line}", file=sys.stderr)
            print(f"  /camp first, then re-run; or pass --force.", file=sys.stderr)
            sys.exit(2)

    env = load_env()
    conn = pymysql.connect(
        host="127.0.0.1", port=3306,
        user="root", password=env["MARIADB_ROOT_PASSWORD"],
        database=env["MARIADB_DATABASE"],
        cursorclass=pymysql.cursors.DictCursor, charset="utf8mb4",
        autocommit=False,
    )

    try:
        with conn.cursor() as cursor:
            char_id, account_id = get_char(cursor, char_name)

            plan = []
            for bank_slot, items in bank.items():
                bag_row_id, num_slots = get_bank_bag(cursor, char_id, bank_slot)
                if len(items) > num_slots:
                    sys.exit(
                        f"error: bank slot {bank_slot} bag has {num_slots} slots, "
                        f"{len(items)} items requested"
                    )
                for slot_idx, entry in enumerate(items):
                    ref = entry["item"]
                    count = int(entry.get("count", 1))
                    item_id, item_name = lookup_item(cursor, ref)
                    plan.append((bank_slot, bag_row_id, slot_idx, item_id, item_name, count))

            print(f"=== plan for {char_name} (char_id={char_id}) ===")
            for bank_slot, bag_row_id, slot, item_id, item_name, count in plan:
                print(f"  bank #{bank_slot} (bag row {bag_row_id}) slot {slot}: "
                      f"{count}x [{item_id}] {item_name}")

            if args.dry_run:
                print("\n--dry-run: no changes written")
                return

            seen_bags = set()
            for bank_slot, bag_row_id, *_ in plan:
                if bag_row_id in seen_bags:
                    continue
                seen_bags.add(bag_row_id)
                if args.replace:
                    cursor.execute(
                        "DELETE FROM character_items WHERE char_id = %s AND bag_id = %s",
                        (char_id, bag_row_id),
                    )
                else:
                    requested_slots = {p[2] for p in plan if p[1] == bag_row_id}
                    cursor.execute(
                        "SELECT slot FROM character_items WHERE char_id = %s AND bag_id = %s",
                        (char_id, bag_row_id),
                    )
                    occupied = {r["slot"] for r in cursor.fetchall()}
                    conflict = sorted(occupied & requested_slots)
                    if conflict:
                        sys.exit(
                            f"error: bank slot {bank_slot} (bag row {bag_row_id}) "
                            f"has occupied inner slots {conflict}; pass --replace to wipe"
                        )

            for bank_slot, bag_row_id, slot, item_id, item_name, count in plan:
                cursor.execute(
                    "INSERT INTO character_items "
                    "(type, account_id, char_id, bag_id, slot, item_id, count) "
                    "VALUES ('NOT-EQUIPPED', %s, %s, %s, %s, %s, %s)",
                    (account_id, char_id, bag_row_id, slot, item_id, count),
                )

            conn.commit()
            print(f"\n✓ {len(plan)} row(s) inserted into {char_name}'s bank.")
            print("  Log in to verify; the client will load fresh state on character select.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
