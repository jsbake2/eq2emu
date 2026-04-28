#!/usr/bin/env python3
"""
Recategorize spells.spell_type for class-eligible spells whose enum value is
'Unset'. Drives bot AI: Bot::GetNewSpells() bins each class spell into a per-
category map (buff_spells, hot_ward_spells, etc.) by spell_type; anything tagged
Unset falls through `default:` and is never picked up by the brain.

The signal we use is `spell_display_effects.description` (the human-readable
in-game tooltip text), which has 98%+ coverage for priest-class Unset spells.
Description text is a reliable category signal — far better than name regex.

Usage:
    scripts/recategorize-spells.py --classes priest               # priest tree dry-run
    scripts/recategorize-spells.py --classes priest --write-sql FILE
    scripts/recategorize-spells.py --classes priest --apply       # direct write

Run as a host script; talks to the mysql container on 127.0.0.1:3306.
Credentials read from docker/.env.
"""

import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pymysql

REPO = Path(__file__).resolve().parent.parent
ENV = REPO / "docker" / ".env"

# Class groups we can target. Keep these aligned with classes.h.
CLASS_GROUPS = {
    "priest": [11, 12, 13, 14, 15, 16, 17, 18, 19, 20],   # PRIEST..DEFILER
    "fighter": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],            # FIGHTER..PALADIN
    "mage": [21, 22, 23, 24, 25, 26, 27, 28, 29, 30],      # MAGE..NECROMANCER
    "scout": [31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42],  # SCOUT..BEASTLORD
}

# Categorization rules in priority order — first match wins.
# Each rule is (category, list-of-regex-patterns). Patterns matched against
# the *concatenated* descriptions for the spell (lowercased).
#
# Cures and rezzes are deliberately not in this set yet — they belong in the
# cure-logic PR (separate workstream) where we also wire up GetCureSpell().
RULES = [
    # Wards, reactive heals, heals-over-time → HoT-Ward.
    # Order matters: this fires before plain Heal so reactive procs and
    # tick-heals don't get demoted to instant Heal.
    ("HoT-Ward", [
        r"\bwards (?:target|group|caster)\b",
        r"\bshields?\b.*\bdamage\b",
        r"\bheals?\b.*\bevery\s+\d",                          # HoTs
        r"\bheals?\b.*\bwhen\s+(?:target|caster)\s+is\s+hit",  # reactive heal
        r"\btriggers?\b.*\bwhen\b.*\b(?:hit|struck|damaged|attacked)",
        r"\bgrants?\s+a\s+total\s+of\s+\d+\s+triggers?\b",     # reactive proc
        r"\bwhen\s+damaged\b.*\bchance\b.*\bcasts?\b",         # damage-trigger proc
    ]),

    # Plain instant heals (no "every Y seconds", no trigger)
    ("Heal", [
        r"\bheals?\s+(?:target|caster|group\s+members)(?:\s+\(\s*ae\s*\))?\s+for\s+\d",
    ]),

    # DoTs — periodic damage on enemy
    ("DoT", [
        r"\binflicts?\s+\d.*\bevery\s+\d",
    ]),

    # Detaunts (must come before Buff — these are friendly-cast threat reducers)
    ("Detaunt", [
        r"\bdecreases\s+threat\b",
    ]),

    # Group/single-target/self buffs → Buff
    # The "Increases X" form covers stat buffs, mitigation, haste, regen, etc.
    # "Shapechanges caster" covers druid forms.
    # "Summons a limited pet" covers shaman/cleric pet-buff spells.
    ("Buff", [
        r"\bincreases\s+(?:mitigation|max\s+health|max\s+power|haste|sta|str|agi|wis|int|attack\s+speed|dps|crit|spell\s+damage|defense|parry|deflection|riposte|aggression|ministration|focus|disruption|piercing|crushing|slashing|ranged|ordination|subjugation|wisdom|stamina|strength|agility|intelligence|spell\s+resists|elemental|noxious|arcane|magic\s+resist|absorb|hate\s+gain|in-?combat\s+power\s+regen|in-?combat\s+health\s+regen|out-?of-?combat|heal\s+amount|threat\s+amount|spell\s+casting|reuse\s+speed|recovery\s+speed|out-?of-?combat\s+power|out-?of-?combat\s+health)",
        r"\bincreases\s+power\s+regeneration\b",
        r"\bincreases\s+health\s+regeneration\b",
        r"\bincreases\s+the\s+amount\s+of\s+(?:health|power)\s+gained\b",
        r"\bshapechanges\s+caster\b",
        r"\bgrants\s+see\s+(?:invis|stealth)\b",
        r"\bgrants?\s+(?:fervor|noxious|arcane|elemental)\b",
        r"\bsummons\s+a\s+(?:limited\s+)?pet\b",                # pet-buff spells
        r"\badds\s+additional\s+(?:healing|damage|effect)\b",   # spell enhancers
        r"\b(?:on\s+a\s+).*?(?:successful\s+)?(?:hit|attack|kill)\b.*?\bcasts?\b",  # proc-on-hit/kill buffs
        r"\bgrants\s+a\s+(?:\d+%|small|moderate|major)\s+chance",               # generic proc buff
    ]),

    # Snare, Root, Stun, Interrupt — keep them debuffs not buffs even though
    # they target enemies (friendly_spell=0). We don't strictly need to touch
    # these for prepull/buff goals, but tagging them prevents any future
    # accident where a Root spell would land in the buff pool.
    ("Root", [
        r"\broots?\s+target\b",
    ]),
    ("Snare", [
        r"\bdecreases\s+(?:speed|movement)\b.*\btarget\b",
    ]),
]

# Class id → readable name for output.
CLASS_NAMES = {
    11: "PRIEST", 12: "CLERIC", 13: "TEMPLAR", 14: "INQUISITOR",
    15: "DRUID", 16: "WARDEN", 17: "FURY",
    18: "SHAMAN", 19: "MYSTIC", 20: "DEFILER",
}


def load_env():
    kv = {}
    for line in ENV.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        kv[k.strip()] = v.strip().strip('"').strip("'")
    return kv


def fetch_candidate_spells(cur, class_ids):
    placeholders = ",".join(["%s"] * len(class_ids))
    cur.execute(f"""
        SELECT s.id, s.name, s.spell_type, s.cast_type, s.target_type,
               s.friendly_spell,
               GROUP_CONCAT(sde.description SEPARATOR ' || ') AS descriptions
        FROM spells s
        JOIN spell_classes sc ON sc.spell_id = s.id
        LEFT JOIN spell_display_effects sde ON sde.spell_id = s.id
        WHERE sc.adventure_class_id IN ({placeholders})
          AND s.spell_type = 'Unset'
        GROUP BY s.id
    """, class_ids)
    return cur.fetchall()


def classify(row):
    """Return one of the spell_type enum strings, or None if no match."""
    desc = (row["descriptions"] or "").lower()
    if not desc:
        return None

    for category, patterns in RULES:
        for pat in patterns:
            if re.search(pat, desc):
                # Refinement: don't tag hostile-cast effects as Buff/HoT-Ward/Heal.
                # (Detaunt is a hostile spell — cast on enemy with friendly_spell=0.)
                if category in ("Buff", "HoT-Ward", "Heal") and not row["friendly_spell"]:
                    continue
                # Don't tag friendly-cast effects as Root/Snare/DoT.
                if category in ("Root", "Snare", "DoT") and row["friendly_spell"]:
                    continue
                return category
    return None


def report(results):
    """results: list of (row, new_category) — None for unmatched."""
    by_cat = Counter()
    by_class = defaultdict(Counter)
    samples = defaultdict(list)
    matched = 0
    for row, cat in results:
        if cat:
            matched += 1
            by_cat[cat] += 1
            if len(samples[cat]) < 5:
                samples[cat].append(row["name"])

    total = len(results)
    print(f"\nCandidate Unset spells in scope: {total}")
    print(f"Matched by heuristic:           {matched} ({matched*100//max(total,1)}%)")
    print(f"Unmatched (left as Unset):      {total - matched}")
    print("\nBy proposed category:")
    for cat, n in by_cat.most_common():
        print(f"  {cat:10s} {n:5d}   e.g. {', '.join(samples[cat])}")


def emit_sql(results, target, classes_label, class_ids):
    """Write a migration file. Uses spell IDs in a CASE expression."""
    by_cat = defaultdict(list)
    for row, cat in results:
        if cat:
            by_cat[cat].append((row["id"], row["name"]))

    lines = []
    lines.append(f"-- Migration: recategorize Unset {classes_label} spells by display-effect heuristic")
    lines.append(f"-- Generated by scripts/recategorize-spells.py")
    lines.append(f"-- Classes: {', '.join(CLASS_NAMES.get(c, str(c)) for c in class_ids)}")
    lines.append("--")
    lines.append("-- Why: Bot::GetNewSpells() bins class spells by spells.spell_type. Anything")
    lines.append("--      tagged 'Unset' is never picked by the brain (default branch returns 0)")
    lines.append("--      so wards, group buffs, reactive heals, etc. exist on the bot's spell")
    lines.append("--      list but never fire. Recategorizing pulls them into buff_spells /")
    lines.append("--      hot_ward_spells / etc. where ProcessOutOfCombatSpells can find them.")
    lines.append("--")
    lines.append("-- Rollback: see DOWN section.")
    lines.append("--")
    lines.append("-- Apply with:")
    lines.append("--   docker exec -i docker-mysql-1 \\")
    lines.append("--     mariadb -ueq2emu -p\"$MARIADB_PASSWORD\" eq2emu < FILE")
    lines.append("")
    lines.append("-- UP " + "-" * 70)
    lines.append("")
    lines.append("START TRANSACTION;")
    lines.append("")
    for cat in sorted(by_cat):
        ids = [str(i) for i, _ in by_cat[cat]]
        n = len(ids)
        lines.append(f"-- {cat}: {n} spells")
        # Bulk update via IN(...). Chunk to avoid 1MB query limit.
        for chunk_start in range(0, len(ids), 500):
            chunk = ids[chunk_start:chunk_start + 500]
            lines.append(
                f"UPDATE spells SET spell_type = '{cat}' "
                f"WHERE id IN ({','.join(chunk)}) AND spell_type = 'Unset';"
            )
        lines.append("")
    lines.append("COMMIT;")
    lines.append("")
    lines.append("-- DOWN " + "-" * 68)
    lines.append("-- Restores all spells touched here back to 'Unset'. Safe to run iff no")
    lines.append("-- legitimate manual Buff/HoT-Ward/etc. retags happened on these IDs since.")
    lines.append("--")
    lines.append("-- START TRANSACTION;")
    all_ids = sorted({i for ids in by_cat.values() for i, _ in ids})
    for chunk_start in range(0, len(all_ids), 500):
        chunk = [str(i) for i in all_ids[chunk_start:chunk_start + 500]]
        lines.append(
            f"-- UPDATE spells SET spell_type = 'Unset' WHERE id IN ({','.join(chunk)});"
        )
    lines.append("-- COMMIT;")
    target.write_text("\n".join(lines) + "\n")
    print(f"\nWrote SQL migration → {target}")


def apply_direct(cur, results):
    by_cat = defaultdict(list)
    for row, cat in results:
        if cat:
            by_cat[cat].append(row["id"])
    for cat, ids in by_cat.items():
        for chunk_start in range(0, len(ids), 500):
            chunk = ids[chunk_start:chunk_start + 500]
            placeholders = ",".join(["%s"] * len(chunk))
            cur.execute(
                f"UPDATE spells SET spell_type = %s "
                f"WHERE id IN ({placeholders}) AND spell_type = 'Unset'",
                [cat] + chunk,
            )
            print(f"  {cat:10s} {cur.rowcount:5d} rows in chunk")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--classes", required=True, choices=sorted(CLASS_GROUPS),
                    help="class group to scan")
    ap.add_argument("--write-sql", type=Path,
                    help="emit a migration file instead of just reporting")
    ap.add_argument("--apply", action="store_true",
                    help="directly write changes to DB (skip migration file)")
    ap.add_argument("--show-unmatched", action="store_true",
                    help="print the spells the heuristic skipped, for tuning")
    args = ap.parse_args()

    if args.apply and args.write_sql:
        sys.exit("--apply and --write-sql are mutually exclusive")

    env = load_env()
    conn = pymysql.connect(
        host="127.0.0.1", port=3306, user="root",
        password=env["MARIADB_ROOT_PASSWORD"], database=env["MARIADB_DATABASE"],
        cursorclass=pymysql.cursors.DictCursor, charset="utf8mb4",
    )

    class_ids = CLASS_GROUPS[args.classes]
    with conn.cursor() as cur:
        rows = fetch_candidate_spells(cur, class_ids)
        results = [(row, classify(row)) for row in rows]

        report(results)

        if args.show_unmatched:
            print("\nUnmatched samples (first 30):")
            for row, cat in results:
                if cat is None:
                    print(f"  [{row['id']}] {row['name']:35s}  fr={row['friendly_spell']} "
                          f"tt={row['target_type']} ct={row['cast_type']} :: "
                          f"{(row['descriptions'] or '')[:120]}")

        if args.write_sql:
            emit_sql(results, args.write_sql, args.classes, class_ids)
        elif args.apply:
            ans = input("\nApply changes directly to DB? [y/N] ").strip().lower()
            if ans == "y":
                apply_direct(cur, results)
                conn.commit()
                print("Committed.")
            else:
                print("Aborted.")


if __name__ == "__main__":
    main()
