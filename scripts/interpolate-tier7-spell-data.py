"""Compute proper tier-7 (Expert) values for spell_data rows that migration
007 cloned from tier-1 as a no-crash floor. Replace those values with linear
interpolations between tier-5 (Adept) and tier-9 (Master) — matches the
EQ2 tier curve where Expert sits roughly 86% of the way from Adept to Master.

Detection of cloned rows:
- tier-7.value == tier-1.value (was cloned, presumably)
- tier-5 row exists at the same (spell_id, index_field)
- tier-9 row exists at the same (spell_id, index_field)
- tier-5.value differs from tier-1.value (confirms the spell scales)

Skip rows where any of these don't hold (we'd have nothing to interpolate
between, or risk corrupting legitimate tier-7 = tier-1 constants).

Run as a host script; talks to docker-mysql-1 on 127.0.0.1:3306.
"""

from pathlib import Path
import re
import pymysql

REPO = Path("/home/jbaker/repos/eq2emu")
ENV = REPO / "docker" / ".env"
OUT = REPO / "sql" / "migrations" / "013_tier7_interpolated_values.sql"

# EQ2 tier curve — Expert sits ~86% of the way from Adept (5) to Master (9).
# Computed empirically from spells where authentic tier-5/7/9 exist (e.g.
# Willowskin index 0: 9.4 → 11.8 → 12.2, ratio 0.857).
TIER_RATIO = 0.857


def load_env():
    kv = {}
    for line in ENV.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        kv[k.strip()] = v.strip().strip('"').strip("'")
    return kv


def parse_value(val_str, vtype):
    """Convert SQL-stored value string to a number. Handles ints, floats,
    and the occasional formatted decimal. Returns None if unparseable."""
    if val_str is None:
        return None
    val_str = val_str.strip()
    if not val_str:
        return None
    try:
        if vtype == "FLOAT":
            return float(val_str)
        if vtype == "INT":
            # Some int rows are stored as e.g. "549.000"; strip decimal
            if "." in val_str:
                return int(float(val_str))
            return int(val_str)
        # BOOL, STRING — don't interpolate
        return None
    except (ValueError, TypeError):
        return None


def format_value(num, vtype):
    if vtype == "INT":
        return str(int(round(num)))
    # FLOAT — preserve up to 4 decimals, trim trailing zeros
    s = f"{num:.4f}"
    s = s.rstrip("0").rstrip(".")
    return s if s else "0"


def main():
    env = load_env()
    conn = pymysql.connect(
        host="127.0.0.1", port=3306, user="root",
        password=env["MARIADB_ROOT_PASSWORD"], database=env["MARIADB_DATABASE"],
        cursorclass=pymysql.cursors.DictCursor, charset="utf8mb4",
    )
    cur = conn.cursor()

    # Pull every spell that has both tier-5 and tier-9 data — these are
    # interpolation candidates.
    cur.execute("""
        SELECT spell_id
        FROM (
          SELECT spell_id, COUNT(DISTINCT tier) AS cnt
          FROM spell_data
          WHERE tier IN (1, 5, 7, 9)
          GROUP BY spell_id
        ) x
        WHERE cnt >= 3
    """)
    candidate_spell_ids = [r["spell_id"] for r in cur.fetchall()]
    print(f"Spells with at least 3 of tier 1/5/7/9: {len(candidate_spell_ids)}")

    if not candidate_spell_ids:
        print("nothing to do")
        return

    # Fetch all rows for these spells in one go.
    placeholders = ",".join(["%s"] * len(candidate_spell_ids))
    cur.execute(f"""
        SELECT id, spell_id, tier, index_field, value_type, value, value2, dynamic_helper
        FROM spell_data
        WHERE spell_id IN ({placeholders}) AND tier IN (1, 5, 7, 9)
    """, candidate_spell_ids)
    rows = cur.fetchall()

    # Index by (spell_id, index_field, tier).
    by_key = {}
    for r in rows:
        by_key[(r["spell_id"], r["index_field"], r["tier"])] = r

    # Walk tier-7 rows, attempt interpolation.
    interpolated = 0
    skipped_constant = 0
    skipped_no_neighbors = 0
    skipped_unparseable = 0
    updates = []  # (row_id, new_value_str, old_value_str, spell_id, index_field)

    for (sid, idx, tier), row in by_key.items():
        if tier != 7:
            continue
        vtype = row["value_type"]
        if vtype not in ("INT", "FLOAT"):
            continue

        t1 = by_key.get((sid, idx, 1))
        t5 = by_key.get((sid, idx, 5))
        t9 = by_key.get((sid, idx, 9))

        if t1 is None or t5 is None or t9 is None:
            skipped_no_neighbors += 1
            continue

        v1 = parse_value(t1["value"], vtype)
        v5 = parse_value(t5["value"], vtype)
        v7 = parse_value(row["value"], vtype)
        v9 = parse_value(t9["value"], vtype)
        if None in (v1, v5, v7, v9):
            skipped_unparseable += 1
            continue

        # Detect cloned: tier-7 == tier-1.
        if v7 != v1:
            # Authentic tier-7 — leave it alone.
            continue

        # Scaling check: tier-5 should differ from tier-1.
        if v5 == v1:
            skipped_constant += 1
            continue

        # Compute interpolation.
        new_v7 = v5 + TIER_RATIO * (v9 - v5)
        new_str = format_value(new_v7, vtype)
        if new_str == row["value"]:
            continue  # no change

        updates.append((row["id"], new_str, row["value"], sid, idx))
        interpolated += 1

    print(f"\nInterpolated:        {interpolated}")
    print(f"Skipped (constant):  {skipped_constant}  (tier-5 == tier-1, not scaling)")
    print(f"Skipped (no nbrs):   {skipped_no_neighbors}")
    print(f"Skipped (unparse):   {skipped_unparseable}")

    if not updates:
        return

    # Emit migration file.
    OUT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "-- Migration: replace tier-1-cloned tier-7 spell_data with proper",
        "-- interpolated Expert-tier values (between tier-5 Adept and tier-9 Master).",
        "--",
        "-- Migration 007 backfilled missing tier-7 rows by cloning tier-1 to",
        "-- prevent nil-param Lua crashes — necessary floor, but ran spells at",
        "-- tier-1 numerical strength when bots cast at tier 7. This migration",
        "-- replaces those cloned values with linear interpolations using the",
        "-- empirical EQ2 tier ratio (Expert sits ~86% of the way from Adept",
        "-- to Master, derived from authentically-authored tier-5/7/9 trios).",
        "--",
        "-- Detection: tier-7.value == tier-1.value AND both tier-5 and tier-9",
        "-- exist for the same (spell_id, index_field) AND tier-5 != tier-1",
        "-- (confirms the spell actually scales). Constants are left alone.",
        "--",
        f"-- Touches {interpolated} rows across {len({u[3] for u in updates})} spells.",
        "--",
        "-- After applying: /reload spells (in-game) or cycle the server.",
        "",
        "-- UP " + "-" * 70,
        "",
        "START TRANSACTION;",
        "",
    ]
    # Group updates by new_value to compress (e.g. "SET value='944' WHERE id IN (...)").
    from collections import defaultdict
    by_value = defaultdict(list)
    for row_id, new_v, old_v, sid, idx in updates:
        by_value[new_v].append(row_id)

    for new_v, ids in sorted(by_value.items()):
        # chunk into 500
        for chunk_start in range(0, len(ids), 500):
            chunk = ids[chunk_start:chunk_start + 500]
            lines.append(
                f"UPDATE spell_data SET value = '{new_v}' "
                f"WHERE id IN ({','.join(map(str, chunk))});"
            )

    lines.append("")
    lines.append("COMMIT;")
    lines.append("")
    lines.append("-- DOWN " + "-" * 68)
    lines.append("-- Reverts each updated row to the value it had before this migration.")
    lines.append("-- Generated as commented SQL — uncomment + run if rolling back.")
    lines.append("-- START TRANSACTION;")
    by_old = defaultdict(list)
    for row_id, new_v, old_v, sid, idx in updates:
        by_old[old_v].append(row_id)
    for old_v, ids in sorted(by_old.items()):
        for chunk_start in range(0, len(ids), 500):
            chunk = ids[chunk_start:chunk_start + 500]
            lines.append(
                f"-- UPDATE spell_data SET value = '{old_v}' "
                f"WHERE id IN ({','.join(map(str, chunk))});"
            )
    lines.append("-- COMMIT;")

    OUT.write_text("\n".join(lines) + "\n")
    print(f"\nWrote migration → {OUT}")
    print(f"Lines: {len(lines)}, file size: {OUT.stat().st_size} bytes")


if __name__ == "__main__":
    main()
