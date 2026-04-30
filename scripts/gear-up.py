#!/usr/bin/env python3
"""
Equip a character or bots with a level-appropriate set of mastercrafted
armor + jewelry, picked from the live items DB based on:

  - class → archetype (per the operator's gear-spec)
  - level → tier band (L7/L12/L22/L32/L42 armor, L7/L17/L27/L37/L47 jewelry)
  - material name in the item's name (e.g. "Imbued Ebon Vanguard Cuirass")
  - class-wearable check via items.adventure_classes bitmask

Two modes:

  --player <name>           Drops a full set into the player's inventory bags.
                            (Bag id 0, fills the first non-full backpack.)

  --bot-ids 1,2,3           Equips each bot directly via bot_equipment table.
                            (Slot ids from /bot list; targets the caller's
                            character account.)
                            Use --owner <name> to pick a different account.

Common flags:

  --dry-run                 Print plan; no DB writes.
  --replace                 For player: clear existing slot before insert.
                            For bots: bot_equipment ON DUPLICATE KEY UPDATE
                            already replaces, this is a no-op.
  --force                   Skip the offline check.

Bots are picked up on next spawn — camp + /bot spawn after running.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pymysql
import pymysql.cursors

REPO = Path(__file__).resolve().parent.parent
ENV = REPO / "docker" / ".env"
SERVER_CONTAINER = "docker-eq2emu-server-1"

ANSI = re.compile(r"\x1b\[[0-9;]*m")

# ---------------------------------------------------------------------------
# Class → archetype / set-keyword map (curated from the operator's spec).
#
# class_id constants come from eq2emu's WorldServer/classes.h. We map every
# final class to:
#   - armor_type:    'plate' | 'chain' | 'leather' | 'cloth'
#   - set_keywords:  acceptable second-word patterns in armor item names
#                    (e.g. "Imbued Ebon Vanguard Cuirass" → 'vanguard')
#   - stat_priority: list of attribute-subtype ids the class cares about
# ---------------------------------------------------------------------------

GUARDIAN, BERSERKER = 3, 4
MONK, BRUISER = 6, 7
SHADOWKNIGHT, PALADIN = 9, 10
TEMPLAR, INQUISITOR = 13, 14
WARDEN, FURY = 16, 17
MYSTIC, DEFILER = 19, 20
WIZARD, WARLOCK = 23, 24
ILLUSIONIST, COERCER = 26, 27
CONJUROR, NECROMANCER = 29, 30
SWASHBUCKLER, BRIGAND = 32, 33
RANGER, ASSASSIN = 34, 35
TROUBADOUR, DIRGE = 36, 37

# ITEM_STAT_* indices from Items.h (item_stats.subtype where type=0):
STR, STA, AGI, WIS, INT = 0, 1, 2, 3, 4

# Jewelry name → stat keyword. Mastercrafted jewelry naming convention is
# "Imbued [Material] [Type] of [StatName]" — match the StatName.
STAT_NAMES = {
    STR: "Strength",
    STA: "Stamina",
    AGI: "Agility",
    WIS: "Wisdom",
    INT: "Intelligence",
}

ARMOR_PLATE = "plate"
ARMOR_CHAIN = "chain"
ARMOR_LEATHER = "leather"
ARMOR_CLOTH = "cloth"


@dataclass
class ClassSpec:
    armor_type: str
    set_keywords: list[str]   # ordered preference; first match wins
    stats: list[int]          # priority stats for jewelry / weapon scoring
    primary_weapons: list[str]   # weapon name keywords for slot 0 (e.g. 'great sword', 'mace')
    secondary: list[str]         # ordered fallback list for offhand: 'shield' / 'symbol' / 'dagger' / 'orb'
                                  # empty list = 2H-only (no offhand)
    ranged: list[str]            # weapon name keywords for ranged slot (bow / wand / etc.)


CLASS_SPECS: dict[int, ClassSpec] = {
    # Plate tanks — 1H + shield, or 2H weapon. Bow ranged.
    GUARDIAN:     ClassSpec(ARMOR_PLATE,   ["vanguard", "plate"],          [STR, STA],
                            primary_weapons=["long sword", "battle hammer", "battle axe"], secondary=["shield"],
                            ranged=["throwing", "javelin"]),
    BERSERKER:    ClassSpec(ARMOR_PLATE,   ["vanguard", "plate"],          [STR, STA],
                            primary_weapons=["great axe", "great sword", "double headed axe", "long sword"], secondary=[],
                            ranged=["throwing", "javelin"]),
    SHADOWKNIGHT: ClassSpec(ARMOR_PLATE,   ["vanguard", "plate"],          [STR, STA],
                            primary_weapons=["long sword", "battle axe", "battle hammer"], secondary=["shield"],
                            ranged=["throwing"]),
    PALADIN:      ClassSpec(ARMOR_PLATE,   ["vanguard", "plate"],          [STR, STA],
                            primary_weapons=["long sword", "battle hammer", "mace"], secondary=["shield"],
                            ranged=["throwing"]),

    # Plate healers — 1H mace/hammer + symbol, or 2H staff.
    TEMPLAR:      ClassSpec(ARMOR_PLATE,   ["devout", "vanguard", "plate"], [WIS, INT, STA],
                            primary_weapons=["battle hammer", "mace", "flail"], secondary=["round shield", "buckler", "symbol"],
                            ranged=["throwing"]),
    INQUISITOR:   ClassSpec(ARMOR_PLATE,   ["devout", "vanguard", "plate"], [WIS, INT, STA],
                            primary_weapons=["battle hammer", "mace", "flail"], secondary=["round shield", "buckler", "symbol"],
                            ranged=["throwing"]),

    # Brawlers — claws/knuckles or 2H bo staff.
    MONK:         ClassSpec(ARMOR_LEATHER, ["leather"],                    [STR, STA, AGI],
                            primary_weapons=["claws", "knuckles", "bo staff"], secondary=[],
                            ranged=["throwing"]),
    BRUISER:      ClassSpec(ARMOR_LEATHER, ["leather"],                    [STR, STA, AGI],
                            primary_weapons=["claws", "knuckles", "bo staff"], secondary=[],
                            ranged=["throwing"]),

    # Druids — staff or 1H + symbol.
    WARDEN:       ClassSpec(ARMOR_LEATHER, ["tunic", "leather"],           [WIS, INT, STA],
                            primary_weapons=["quarter staff", "club", "fighting baton"], secondary=["round shield", "buckler", "symbol"],
                            ranged=["throwing"]),
    FURY:         ClassSpec(ARMOR_LEATHER, ["tunic", "leather"],           [WIS, INT, STA],
                            primary_weapons=["quarter staff", "club", "fighting baton"], secondary=["round shield", "buckler", "symbol"],
                            ranged=["throwing"]),

    # Shamans — chain healers — 1H mace/club + symbol, or 2H.
    MYSTIC:       ClassSpec(ARMOR_CHAIN,   ["reverent", "chainmail", "brigandine"], [WIS, INT, STA],
                            primary_weapons=["club", "mace", "flail"], secondary=["round shield", "buckler", "symbol"],
                            ranged=["throwing"]),
    DEFILER:      ClassSpec(ARMOR_CHAIN,   ["reverent", "chainmail", "brigandine"], [WIS, INT, STA],
                            primary_weapons=["club", "mace", "flail"], secondary=["round shield", "buckler", "symbol"],
                            ranged=["throwing"]),

    # Scouts — dual wield daggers / dirks, or rapier.
    SWASHBUCKLER: ClassSpec(ARMOR_CHAIN,   ["brigandine", "chainmail"],    [AGI, STR, STA],
                            primary_weapons=["rapier", "long sword", "dagger"], secondary=["dagger"],
                            ranged=["short bow", "long bow"]),
    BRIGAND:      ClassSpec(ARMOR_CHAIN,   ["brigandine", "chainmail"],    [AGI, STR, STA],
                            primary_weapons=["dagger", "dirk", "rapier"], secondary=["dagger"],
                            ranged=["short bow", "long bow"]),
    RANGER:       ClassSpec(ARMOR_CHAIN,   ["brigandine", "chainmail"],    [AGI, STR, STA],
                            primary_weapons=["dagger", "long sword"], secondary=["dagger"],
                            ranged=["long bow", "short bow"]),
    ASSASSIN:     ClassSpec(ARMOR_CHAIN,   ["brigandine", "chainmail"],    [AGI, STR, STA],
                            primary_weapons=["dagger", "dirk"], secondary=["dagger"],
                            ranged=["long bow", "short bow"]),

    # Bards — rapier or longsword.
    TROUBADOUR:   ClassSpec(ARMOR_CHAIN,   ["melodic", "brigandine", "chainmail"], [INT, WIS, STA],
                            primary_weapons=["rapier", "long sword", "dagger"], secondary=["dagger"],
                            ranged=["short bow", "long bow"]),
    DIRGE:        ClassSpec(ARMOR_CHAIN,   ["melodic", "brigandine", "chainmail"], [INT, WIS, STA],
                            primary_weapons=["rapier", "long sword", "dagger"], secondary=["dagger"],
                            ranged=["short bow", "long bow"]),

    # Cloth DPS — staff or wand. Wand goes in ranged slot.
    WIZARD:       ClassSpec(ARMOR_CLOTH,   ["robe", "blouse"],             [INT, WIS, STA],
                            primary_weapons=["greatstaff", "spellbinders staff", "quarter staff", "dagger"], secondary=[],
                            ranged=["wand"]),
    WARLOCK:      ClassSpec(ARMOR_CLOTH,   ["robe", "blouse"],             [INT, WIS, STA],
                            primary_weapons=["greatstaff", "spellbinders staff", "quarter staff", "dagger"], secondary=[],
                            ranged=["wand"]),
    CONJUROR:     ClassSpec(ARMOR_CLOTH,   ["robe", "blouse"],             [INT, WIS, STA],
                            primary_weapons=["greatstaff", "spellbinders staff", "quarter staff", "dagger"], secondary=[],
                            ranged=["wand"]),
    NECROMANCER:  ClassSpec(ARMOR_CLOTH,   ["robe", "blouse"],             [INT, WIS, STA],
                            primary_weapons=["greatstaff", "spellbinders staff", "quarter staff", "dagger"], secondary=[],
                            ranged=["wand"]),

    # Cloth buffs (enchanters)
    ILLUSIONIST:  ClassSpec(ARMOR_CLOTH,   ["blouse", "robe"],             [INT, WIS, STA],
                            primary_weapons=["greatstaff", "spellbinders staff", "quarter staff", "dagger"], secondary=[],
                            ranged=["wand"]),
    COERCER:      ClassSpec(ARMOR_CLOTH,   ["blouse", "robe"],             [INT, WIS, STA],
                            primary_weapons=["greatstaff", "spellbinders staff", "quarter staff", "dagger"], secondary=[],
                            ranged=["wand"]),
}

# Material per armor-type per band. Bands are a level FLOOR — L42 covers
# 42-50, L32 covers 32-41, etc. L1-6 gets nothing (returns []).
ARMOR_BANDS: dict[str, dict[int, str]] = {
    ARMOR_PLATE:   {7: "bronze",  12: "blackened iron", 22: "steel",      32: "feysteel", 42: "ebon"},
    ARMOR_CHAIN:   {7: "bronze",  12: "blackened iron", 22: "steel",      32: "feysteel", 42: "ebon"},
    ARMOR_LEATHER: {7: "waxed",   12: "cured",          22: "cuirboilli", 32: "engraved", 42: "augmented"},
    ARMOR_CLOTH:   {7: "sackcloth", 12: "roughspun",    22: "ruckas",     32: "cloth",    42: "linen"},
}

# Jewelry tiers — different breakpoints from armor (7,17,27,37,47).
JEWELRY_TIERS = [7, 17, 27, 37, 47]


def band_for_armor(level: int) -> int | None:
    """Pick the highest band whose floor is <= level."""
    for floor in [42, 32, 22, 12, 7]:
        if level >= floor:
            return floor
    return None


def band_for_jewelry(level: int) -> int | None:
    for floor in [47, 37, 27, 17, 7]:
        if level >= floor:
            return floor
    return None


# Slot bits for armor (1 << slot_id from Items.h). EQ2_AMMO/RANGE/CHARM
# excluded from the armor catalog — handled separately or out of scope for v1.
ARMOR_SLOTS = {
    "head":      (2, 1 << 2),
    "chest":     (3, 1 << 3),
    "shoulders": (4, 1 << 4),
    "forearms":  (5, 1 << 5),
    "hands":     (6, 1 << 6),
    "legs":      (7, 1 << 7),
    "feet":      (8, 1 << 8),
    "waist":     (18, 1 << 18),
    "cloak":     (19, 1 << 19),
}

# Jewelry slots — note ear_2 is intentionally absent (this client has only
# one ear slot in its UI, per operator spec).
JEWELRY_SLOTS = {
    "left_ring":   (9,  1 << 9),
    "right_ring":  (10, 1 << 10),
    "ear_1":       (11, 1 << 11),
    "neck":        (13, 1 << 13),
    "left_wrist":  (14, 1 << 14),
    "right_wrist": (15, 1 << 15),
    "charm_1":     (20, 1 << 20),
    "charm_2":     (21, 1 << 21),
}

# Weapon slots.
WEAPON_SLOTS = {
    "primary":   (0,  1 << 0),
    "secondary": (1,  1 << 1),
    "ranged":    (16, 1 << 16),
}

ALL_SLOTS = {**ARMOR_SLOTS, **JEWELRY_SLOTS, **WEAPON_SLOTS}


# ---------------------------------------------------------------------------
# Env / DB
# ---------------------------------------------------------------------------

def load_env() -> dict[str, str]:
    kv = {}
    for line in ENV.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        kv[k.strip()] = v.strip().strip('"').strip("'")
    return kv


def connect_db():
    env = load_env()
    return pymysql.connect(
        host="127.0.0.1", port=3306,
        user="root", password=env["MARIADB_ROOT_PASSWORD"],
        database=env["MARIADB_DATABASE"],
        cursorclass=pymysql.cursors.DictCursor, charset="utf8mb4",
        autocommit=False,
    )


def check_offline(name: str) -> str | None:
    try:
        result = subprocess.run(
            ["docker", "exec", SERVER_CONTAINER, "tail", "-n", "300",
             "/eq2emu/eq2emu/server/logs/eq2world.log"],
            capture_output=True, text=True, timeout=10, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None
    needle = name.lower()
    for line in result.stdout.splitlines()[-200:]:
        clean = ANSI.sub("", line).strip()
        if needle in clean.lower():
            return clean
    return None


# ---------------------------------------------------------------------------
# Item catalog queries
# ---------------------------------------------------------------------------

# Only "crude" and "shaped" are unambiguous craft-failure prefixes.
# "Forged X" / "Fashioned X" / "Tailored X" are the PRISTINE final names
# for many item types (jewelry uses "Fashioned", cloth uses "Tailored",
# metal weapons sometimes use "Forged"). Excluding them dropped bracelets,
# belts, and other valid mastercrafted items from the picks.
SUBQUALITY_REGEX = "^(crude|shaped) "


def _armor_query(cursor, name_pattern: str, level: int, slot_bit: int, class_id: int) -> dict | None:
    cursor.execute(
        """
        SELECT id, name, required_level, recommended_level
          FROM items
         WHERE LOWER(name) LIKE %s
           AND LOWER(name) NOT REGEXP %s
           AND item_type = 'Armor'
           AND crafted = 1
           AND id < 10000000
           AND required_level <= %s
           AND (slots & %s) > 0
           AND ((adventure_classes >> %s) & 1) = 1
         ORDER BY required_level DESC, id ASC
         LIMIT 1
        """,
        (name_pattern, SUBQUALITY_REGEX, level, slot_bit, class_id),
    )
    return cursor.fetchone()


def find_armor(cursor, class_id: int, level: int, slot_bit: int) -> dict | None:
    """Return best-matching armor row for (class, level, slot).

    Two-pass match:
      1. With set keyword (matches "Imbued Ebon Vanguard Cuirass" etc.)
         Higher tiers have explicit set names that disambiguate
         tank/healer/etc. plate variants.
      2. Material + slot + class (matches "Bronze Vanguard Cuirass",
         "Sackcloth Cap"). Lower tiers don't carry the set keyword
         in slot pieces beyond chest, and the material+class+slot
         filter is enough.
    """
    spec = CLASS_SPECS.get(class_id)
    if not spec:
        return None
    band = band_for_armor(level)
    if band is None:
        return None
    material = ARMOR_BANDS[spec.armor_type][band]

    for kw in spec.set_keywords:
        for prefix in ["imbued ", ""]:
            row = _armor_query(cursor, f"{prefix}{material} {kw}%", level, slot_bit, class_id)
            if row:
                return row

    for prefix in ["imbued ", ""]:
        row = _armor_query(cursor, f"{prefix}{material} %", level, slot_bit, class_id)
        if row:
            return row

    # Final fallback: any mastercrafted item the class can wear in this
    # slot. Catches belts (Cuirboilli Leather Belt — leather material
    # regardless of armor type), cloaks, and other non-armor-set pieces
    # that don't follow the chain/plate/etc. material naming.
    band = band_for_armor(level)
    if band is None:
        return None
    band_lo = band - 5
    cursor.execute(
        """
        SELECT id, name, required_level, recommended_level
          FROM items
         WHERE item_type IN ('Armor', 'Normal')
           AND crafted = 1
           AND id < 10000000
           AND required_level BETWEEN %s AND %s
           AND (slots & %s) > 0
           AND ((adventure_classes >> %s) & 1) = 1
           AND LOWER(name) NOT REGEXP %s
         ORDER BY required_level DESC, id ASC
         LIMIT 1
        """,
        (band_lo, level, slot_bit, class_id, SUBQUALITY_REGEX),
    )
    return cursor.fetchone()


def find_jewelry(cursor, class_id: int, level: int, slot_bit: int) -> dict | None:
    """Return best-matching MASTERCRAFTED jewelry for (class, level, slot).

    Three-pass match:
      1. Imbued + "of <PriorityStat>" naming (Imbued Jasper Ring of Wisdom)
         — only exists for ring/charm slots in this DB.
      2. Any Imbued mastercrafted (Imbued Jasper Ring) — fewer matches but
         broader slot coverage.
      3. Any non-Imbued pristine mastercrafted (Jasper Orb, Gold Symbol)
         — covers ears/neck/wrist/symbol/orb slots that don't get Imbued
         versions.

    All passes require crafted=1 and exclude sub-quality crafting prefixes.
    Returns None for slots that have no mastercrafted option in this tier
    — better than picking a quest-reward drop (operator wants MC only).
    """
    spec = CLASS_SPECS.get(class_id)
    if not spec:
        return None
    band = band_for_jewelry(level)
    if band is None:
        return None
    lo, hi = band - 3, band + 5
    if hi > level:
        hi = level

    # Pass 1: Imbued + "of Stat"
    for stat in spec.stats:
        stat_word = STAT_NAMES[stat].lower()
        cursor.execute(
            """
            SELECT i.id, i.name, i.required_level
              FROM items i
             WHERE i.crafted = 1
               AND i.id < 10000000
               AND i.required_level BETWEEN %s AND %s
               AND (i.slots & %s) > 0
               AND ((i.adventure_classes >> %s) & 1) = 1
               AND LOWER(i.name) LIKE 'imbued %%'
               AND LOWER(i.name) LIKE %s
               AND LOWER(i.name) NOT REGEXP %s
             ORDER BY i.required_level DESC, i.id ASC
             LIMIT 1
            """,
            (lo, hi, slot_bit, class_id, f"%of {stat_word}%", SUBQUALITY_REGEX),
        )
        row = cursor.fetchone()
        if row:
            return row

    # Pass 2: any Imbued mastercrafted
    cursor.execute(
        """
        SELECT i.id, i.name, i.required_level
          FROM items i
         WHERE i.crafted = 1
           AND i.id < 10000000
           AND i.required_level BETWEEN %s AND %s
           AND (i.slots & %s) > 0
           AND ((i.adventure_classes >> %s) & 1) = 1
           AND LOWER(i.name) LIKE 'imbued %%'
           AND LOWER(i.name) NOT REGEXP %s
         ORDER BY i.required_level DESC, i.id ASC
         LIMIT 1
        """,
        (lo, hi, slot_bit, class_id, SUBQUALITY_REGEX),
    )
    row = cursor.fetchone()
    if row:
        return row

    # Pass 3: any pristine mastercrafted (no Imbued prefix)
    cursor.execute(
        """
        SELECT i.id, i.name, i.required_level
          FROM items i
         WHERE i.crafted = 1
           AND i.id < 10000000
           AND i.required_level BETWEEN %s AND %s
           AND (i.slots & %s) > 0
           AND ((i.adventure_classes >> %s) & 1) = 1
           AND LOWER(i.name) NOT REGEXP %s
         ORDER BY i.required_level DESC, i.id ASC
         LIMIT 1
        """,
        (lo, hi, slot_bit, class_id, SUBQUALITY_REGEX),
    )
    return cursor.fetchone()


# Each secondary entry in ClassSpec.secondary is a literal item-name
# keyword. Look across both Weapon and Shield item types — symbols and
# round shields are both Shield-type, daggers are Weapon-type.
SECONDARY_ITEM_TYPES = ["Weapon", "Shield"]


def find_weapon(cursor, class_id: int, level: int, slot_bit: int,
                keywords: list[str], item_types: list[str]) -> dict | None:
    """Pick a mastercrafted weapon (or shield) matching one of the listed
    keywords. Tries each keyword in order; first hit wins.

    The materials are not constrained — wood-based (fir, briarwood,
    etc.) and metal (steel, ebon) both ship as 'Imbued [Material] X' at
    matching required_levels."""
    band = band_for_armor(level)
    if band is None:
        return None
    # Weapons follow armor tier breakpoints reasonably (required_level 22
    # for L22 band etc.). Allow a bit of drift.
    lo, hi = band - 3, level
    type_placeholders = ", ".join(["%s"] * len(item_types))
    # Two passes per keyword: imbued first, then plain mastercrafted.
    for kw in keywords:
        for prefix in ["imbued %", "%"]:
            cursor.execute(
                f"""
                SELECT i.id, i.name, i.required_level
                  FROM items i
                 WHERE i.item_type IN ({type_placeholders})
                   AND i.crafted = 1
                   AND i.id < 10000000
                   AND i.required_level BETWEEN %s AND %s
                   AND (i.slots & %s) > 0
                   AND ((i.adventure_classes >> %s) & 1) = 1
                   AND LOWER(i.name) LIKE %s
                   AND LOWER(i.name) NOT REGEXP %s
                 ORDER BY i.required_level DESC, i.id ASC
                 LIMIT 1
                """,
                (*item_types, lo, hi, slot_bit, class_id, f"{prefix}{kw}%", SUBQUALITY_REGEX),
            )
            row = cursor.fetchone()
            if row:
                return row
    return None


# ---------------------------------------------------------------------------
# Player / bot resolution
# ---------------------------------------------------------------------------

def get_player(cursor, name: str) -> dict | None:
    cursor.execute(
        "SELECT id, account_id, name, class, level FROM characters WHERE name = %s",
        (name,),
    )
    return cursor.fetchone()


def get_bot(cursor, char_id: int, slot_index: int) -> dict | None:
    cursor.execute(
        """
        SELECT id, char_id, bot_id, name, class, race
          FROM bots
         WHERE char_id = %s AND bot_id = %s
        """,
        (char_id, slot_index),
    )
    return cursor.fetchone()


def find_player_inventory_bag(cursor, char_id: int) -> int:
    """Return bag row-id of the first non-full inventory bag for this char,
    or 0 (top-level inventory) as a fallback."""
    cursor.execute(
        """
        SELECT ci.id, ci.slot, b.num_slots
          FROM character_items ci
          JOIN item_details_bag b ON b.item_id = ci.item_id
         WHERE ci.char_id = %s AND ci.bag_id = 0
         ORDER BY ci.slot
        """,
        (char_id,),
    )
    bags = cursor.fetchall()
    for bag in bags:
        cursor.execute(
            "SELECT COUNT(*) AS used FROM character_items WHERE char_id = %s AND bag_id = %s",
            (char_id, bag["id"]),
        )
        used = cursor.fetchone()["used"]
        if used < bag["num_slots"]:
            return bag["id"]
    return 0


def next_free_inv_slot(cursor, char_id: int, bag_id: int) -> int:
    cursor.execute(
        "SELECT slot FROM character_items WHERE char_id = %s AND bag_id = %s",
        (char_id, bag_id),
    )
    used = {r["slot"] for r in cursor.fetchall()}
    for s in range(0, 256):
        if s not in used:
            return s
    raise RuntimeError(f"no free slot in bag {bag_id}")


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

def collect_gear(cursor, class_id: int, level: int) -> list[tuple[str, int, dict]]:
    """Return list of (slot_label, slot_id, item_row) for armor + jewelry +
    weapons."""
    spec = CLASS_SPECS.get(class_id)
    if not spec:
        return []
    out = []

    for label, (slot_id, slot_bit) in ARMOR_SLOTS.items():
        row = find_armor(cursor, class_id, level, slot_bit)
        if row:
            out.append((label, slot_id, row))

    for label, (slot_id, slot_bit) in JEWELRY_SLOTS.items():
        row = find_jewelry(cursor, class_id, level, slot_bit)
        if row:
            out.append((label, slot_id, row))

    # Primary weapon
    primary_slot_id, primary_slot_bit = WEAPON_SLOTS["primary"]
    row = find_weapon(cursor, class_id, level, primary_slot_bit,
                      spec.primary_weapons, ["Weapon"])
    if row:
        out.append(("primary", primary_slot_id, row))

    # Secondary (shield/symbol/dagger) — try each entry in spec.secondary
    # in order; first match wins. Empty list means class is 2H-only.
    if spec.secondary:
        sec_slot_id, sec_slot_bit = WEAPON_SLOTS["secondary"]
        row = find_weapon(cursor, class_id, level, sec_slot_bit,
                          spec.secondary, SECONDARY_ITEM_TYPES)
        if row:
            out.append(("secondary", sec_slot_id, row))

    # Ranged
    if spec.ranged:
        rng_slot_id, rng_slot_bit = WEAPON_SLOTS["ranged"]
        row = find_weapon(cursor, class_id, level, rng_slot_bit,
                          spec.ranged, ["Weapon", "Ranged"])
        if row:
            out.append(("ranged", rng_slot_id, row))

    return out


def equip_bot(conn, bot_row: dict, gear: list, dry_run: bool):
    name = bot_row["name"]
    bot_pk = bot_row["id"]
    print(f"\n=== {name} (class={bot_row['class']}, slot={bot_row['bot_id']}) ===")
    for label, slot_id, item in gear:
        print(f"  {label:12s} slot={slot_id:2d}  → [{item['id']}] {item['name']}")
    if dry_run:
        return
    with conn.cursor() as cur:
        for label, slot_id, item in gear:
            cur.execute(
                "INSERT INTO bot_equipment (bot_id, slot, item_id) VALUES (%s, %s, %s) "
                "ON DUPLICATE KEY UPDATE item_id = VALUES(item_id)",
                (bot_pk, slot_id, item["id"]),
            )


def equip_player(conn, char_row: dict, gear: list, dry_run: bool, replace: bool):
    name = char_row["name"]
    char_id = char_row["id"]
    account_id = char_row["account_id"]
    print(f"\n=== {name} (class={char_row['class']}, level={char_row['level']}) ===")
    for label, slot_id, item in gear:
        print(f"  {label:12s} → [{item['id']}] {item['name']}")
    if dry_run:
        return
    with conn.cursor() as cur:
        bag_id = find_player_inventory_bag(cur, char_id)
        for _, _, item in gear:
            slot = next_free_inv_slot(cur, char_id, bag_id)
            cur.execute(
                "INSERT INTO character_items "
                "(type, account_id, char_id, bag_id, slot, item_id, count) "
                "VALUES ('NOT-EQUIPPED', %s, %s, %s, %s, %s, 1)",
                (account_id, char_id, bag_id, slot, item["id"]),
            )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--player", help="character name to gear up")
    g.add_argument("--bot-ids", help="comma-separated bot slot ids (from /bot list)")
    p.add_argument("--owner", help="owner character (for --bot-ids; default: jbaker1's main)")
    p.add_argument("--dry-run", action="store_true", help="print plan only")
    p.add_argument("--replace", action="store_true", help="for player, wipe slot before insert")
    p.add_argument("--force", action="store_true", help="skip offline check")
    args = p.parse_args()

    conn = connect_db()
    try:
        with conn.cursor() as cursor:
            if args.player:
                if not args.force:
                    line = check_offline(args.player)
                    if line:
                        print(f"error: '{args.player}' looks online — recent log line:", file=sys.stderr)
                        print(f"  {line}", file=sys.stderr)
                        print(f"  /camp first, or pass --force.", file=sys.stderr)
                        sys.exit(2)
                char = get_player(cursor, args.player)
                if not char:
                    sys.exit(f"error: no character named '{args.player}'")
                if char["class"] not in CLASS_SPECS:
                    sys.exit(f"error: class id {char['class']} not in gear catalog (commoner / unsupported)")
                gear = collect_gear(cursor, char["class"], char["level"])
                if not gear:
                    sys.exit(f"error: no gear matched (level {char['level']} too low?)")
                equip_player(conn, char, gear, args.dry_run, args.replace)
            else:
                # Bot-ids mode. Owner defaults to character with admin_status=200
                # named most recently — or take --owner explicitly.
                owner_name = args.owner
                if not owner_name:
                    cursor.execute(
                        "SELECT name FROM characters ORDER BY id LIMIT 1"
                    )
                    row = cursor.fetchone()
                    owner_name = row["name"] if row else None
                    if not owner_name:
                        sys.exit("error: no characters in DB; pass --owner")
                owner = get_player(cursor, owner_name)
                if not owner:
                    sys.exit(f"error: owner '{owner_name}' not found")

                slot_ids = [int(x) for x in args.bot_ids.split(",")]
                missing = []
                bots = []
                for sid in slot_ids:
                    bot = get_bot(cursor, owner["id"], sid)
                    if bot:
                        bots.append(bot)
                    else:
                        missing.append(sid)
                if missing:
                    sys.exit(f"error: no bots at slot(s) {missing} for owner '{owner_name}'")

                # We don't online-check bots — bots are equipped via bot_equipment,
                # which is read at spawn time. If a bot is currently spawned, the
                # change still applies on next spawn (camp + /bot spawn).
                print(f"# owner: {owner_name} (char_id={owner['id']})")
                for bot in bots:
                    if bot["class"] not in CLASS_SPECS:
                        print(f"  skipping {bot['name']}: class {bot['class']} not in gear catalog")
                        continue
                    # Bots inherit owner level (per session-state). Use that.
                    level = owner["level"]
                    gear = collect_gear(cursor, bot["class"], level)
                    if not gear:
                        print(f"  skipping {bot['name']}: no gear matched for level {level}")
                        continue
                    equip_bot(conn, bot, gear, args.dry_run)

            if not args.dry_run:
                conn.commit()
                print("\n✓ committed.")
            else:
                print("\n--dry-run: no changes written")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
