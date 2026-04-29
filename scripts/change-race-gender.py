#!/usr/bin/env python3
"""
Change a character's race and/or gender via DB update.

Usage:
    ./scripts/change-race-gender.py --name <character> --race <name|id> [--gender F|M]

Race can be a numeric id or a name (case-insensitive). Names accept
EQ2-style two-word forms ("Half Elf", "Wood Elf", "Dark Elf"). Gender
accepts F/M/Female/Male/0/1.

Character must be offline — the world server reads race/gender from the
DB on character load and caches it in memory; an online change is
overwritten on next save.

Notes:
- Only updates characters.race and characters.gender. The visual model
  (characters.model_type, hair_type, etc.) is NOT updated. If the
  rendered model looks wrong after a race change, the operator can
  re-customize in-game via the appearance editor or with admin commands.
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

# From WorldServer/races.h. Names are operator-friendly (spaces, no underscores).
RACES = {
    0:  "Barbarian",
    1:  "Dark Elf",
    2:  "Dwarf",
    3:  "Erudite",
    4:  "Froglok",
    5:  "Gnome",
    6:  "Half Elf",
    7:  "Halfling",
    8:  "High Elf",
    9:  "Human",
    10: "Iksar",
    11: "Kerra",
    12: "Ogre",
    13: "Ratonga",
    14: "Troll",
    15: "Wood Elf",
    16: "Fae",
    17: "Arasai",
    18: "Sarnak",
    19: "Vampire",
    20: "Aerakyn",
}
RACE_BY_NAME = {v.lower().replace(" ", ""): k for k, v in RACES.items()}


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
    try:
        r = subprocess.run(
            ["docker", "exec", SERVER_CONTAINER, "tail", "-n", "300",
             "/eq2emu/eq2emu/server/logs/eq2world.log"],
            capture_output=True, text=True, timeout=10, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None
    needle = name.lower()
    for line in r.stdout.splitlines()[-200:]:
        clean = ANSI.sub("", line).strip()
        if needle in clean.lower():
            return clean
    return None


def parse_race(s):
    if s.isdigit():
        rid = int(s)
        if rid not in RACES:
            sys.exit(f"error: race id {rid} unknown (range 0-20)")
        return rid, RACES[rid]
    key = s.lower().replace(" ", "").replace("-", "").replace("_", "")
    if key not in RACE_BY_NAME:
        names = ", ".join(sorted(set(RACES.values())))
        sys.exit(f"error: unknown race '{s}'. Known: {names}")
    rid = RACE_BY_NAME[key]
    return rid, RACES[rid]


def parse_gender(s):
    s = s.strip().lower()
    if s in ("0", "f", "female"):
        return 0
    if s in ("1", "m", "male"):
        return 1
    sys.exit(f"error: invalid gender '{s}' — use F/M (or 0/1).")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--name", required=True, help="character name")
    p.add_argument("--race", help="race name (e.g. Froglok, Half Elf) or id 0-20")
    p.add_argument("--gender", help="F/M (or Female/Male/0/1)")
    p.add_argument("--force", action="store_true", help="skip offline check")
    p.add_argument("--dry-run", action="store_true", help="print plan, no DB writes")
    args = p.parse_args()

    if not args.race and not args.gender:
        sys.exit("error: nothing to do — pass --race and/or --gender")

    new_race = new_gender = None
    if args.race:
        new_race, race_name = parse_race(args.race)
    if args.gender:
        new_gender = parse_gender(args.gender)

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
                "SELECT id, name, race, gender FROM characters WHERE name = %s",
                (args.name,),
            )
            row = cur.fetchone()
            if not row:
                sys.exit(f"error: no character named '{args.name}'")
            print(f"=== {row['name']} (id={row['id']}) ===")
            print(f"  race    : {row['race']} ({RACES.get(row['race'], '?')})"
                  + (f"  →  {new_race} ({race_name})" if new_race is not None else ""))
            print(f"  gender  : {row['gender']} ({'female' if row['gender']==0 else 'male'})"
                  + (f"  →  {new_gender} ({'female' if new_gender==0 else 'male'})" if new_gender is not None else ""))

            if args.dry_run:
                print("\n--dry-run: no changes written")
                return

            sets, params = [], []
            if new_race is not None:
                sets.append("race = %s")
                params.append(new_race)
            if new_gender is not None:
                sets.append("gender = %s")
                params.append(new_gender)
            params.append(row["id"])
            cur.execute(
                f"UPDATE characters SET {', '.join(sets)} WHERE id = %s",
                params,
            )
            conn.commit()
            print(f"\n✓ updated.")
            print("  Note: visual model (model_type / hair / etc.) was NOT changed —")
            print("  the new race may render with the old model. Use the in-game")
            print("  /appearance customizer or re-create the character if needed.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
