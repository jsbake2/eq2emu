#!/usr/bin/env python3
"""
Generate docs/mastercrafted-handouts.html — a searchable, click-to-copy
catalog of mastercrafted items. Now supports a "give to <player>" target
in the page header so the operator's GM client (running in a separate VM)
can hand items to other players via /giveitem instead of /summonitem.

Read-only against the live eq2emu DB. Credentials from docker/.env.

Mastercrafted gear filter (the DB has no clean MC/HC flag, so we use a
hand-curated material allowlist):

  * Items where the material token (first word of name, or second word
    after 'Imbued') is in KEEP_MATERIALS_BY_BAND for the item's level
    band. The allowlist is the rare-harvest table from the EQ2 wiki,
    cross-checked against EQ2Emu data — see KEEP_MATERIALS_BY_BAND below.
  * crafted = 1, id < 10_000_000 (skip client-version duplicate IDs).
  * Sub-quality prefixes (crude/shaped/forged/fashioned/tailored/blessed/
    conditioned/pristine) dropped — only the final-quality output kept.
  * Capped at MAX_LEVEL (matches R_Player/MaxLevel on the live server).
  * Dedup by LOWER(name), keeping the lowest id.

Consumables: all crafted Food / Bauble / Thrown items, capped at
MAX_LEVEL. No material filter — there isn't a clean mastercrafted signal
for consumables in this DB, and excess food/totems is harmless.

Sections:
  * Gear: item_type in Weapon / Armor / Shield / Ranged / Bauble / Normal.
  * Consumables: item_type in Food / Bauble / Thrown.
"""

import html
from collections import defaultdict
from pathlib import Path

import pymysql

REPO = Path(__file__).resolve().parent.parent
ENV = REPO / "docker" / ".env"
OUT = REPO / "docs" / "mastercrafted-handouts.html"
LEGACY_MD = REPO / "docs" / "mastercrafted-handouts.md"

GEAR_TYPES = ("Weapon", "Armor", "Shield", "Ranged", "Bauble", "Normal")
GEAR_TYPE_DISPLAY = {
    "Weapon": "Weapons",
    "Armor": "Armor",
    "Shield": "Shields",
    "Ranged": "Ranged",
    "Bauble": "Baubles",
    "Normal": "Jewelry / Belts / Cloaks",
}
CONS_DISPLAY = {"Food": "Food & drink", "Bauble": "Totems & baubles", "Thrown": "Arrows & thrown"}
CONTAINER_TYPES = ("Bag", "House Container")
CONTAINER_DISPLAY = {"Bag": "Bags & sacks", "House Container": "Strong boxes & chests"}
BAND_LABELS = [
    (0, "Levels 1-9"),
    (1, "Levels 10-19"),
    (2, "Levels 20-29"),
    (3, "Levels 30-39"),
    (4, "Levels 40-49"),
    (5, "Levels 50-59"),
    (6, "Levels 60-69"),
    (7, "Levels 70-79"),
    (8, "Levels 80-89"),
    (9, "Levels 90+"),
]
# First-word prefixes that mark sub-quality (failed) crafted variants — drop
# these regardless of material. The Pristine / unprefixed variant is the
# final-quality output we want.
SUBQUALITY_PREFIXES = {"crude", "shaped", "forged", "fashioned", "tailored",
                       "blessed", "conditioned", "pristine"}

# Mastercrafted rare-material allowlist per level band (band N covers levels
# N*10 to N*10+9). Sourced from the EQ2 wiki "Rare Harvests by Tier" data
# (https://scholey.org/EQ2/harvest2.html), cross-referenced against the
# EQ2Emu items table to confirm prefix counts pair up. We include both
# member of each rare-pair when the data shows two equally-populated
# variants (xegonite/adamantine at T7, incarnadine/ferrite at T8) since
# both came in as rare-tier in EQ2Emu's classic-era dataset.
#
# Categories per tier: 1-2 rare metals, 1 rare gemstone, 1 rare wood,
# 1 rare leather pelt. Roots/loams/shrubs are alchemy/provisioning rares
# and don't end up in gear item names so we omit them.
KEEP_MATERIALS_BY_BAND = {
    0: {"bronze", "copper", "alder", "waxed", "lapis"},                       # T1 (lvl 1-9)
    1: {"blackened", "silver", "bone", "cured", "coral"},                     # T2 (lvl 10-19)
    2: {"steel", "palladium", "fir", "cuirboilli", "jasper"},                 # T3 (lvl 20-29)
    3: {"feysteel", "ruthenium", "oak", "engraved", "opal"},                  # T4 (lvl 30-39)
    4: {"ebon", "rhodium", "cedar", "augmented", "ruby"},                     # T5 (lvl 40-49)
    5: {"cobalt", "vanadium", "ironwood", "scaled", "pearl"},                 # T6 (lvl 50-59)
    6: {"xegonite", "acrylia", "adamantine", "ebony", "rosewood",
        "dragonhide", "moonstone"},                                           # T7 (lvl 60-69)
    7: {"incarnadine", "tynnonium", "ferrite", "mahogany", "redwood",
        "hidebound"},                                                         # T8 (lvl 70-79)
}

# Server R_Player/MaxLevel — cap the catalog to items a level-capped player
# can actually use. Anything above this is hidden, including consumables.
MAX_LEVEL = 60


def load_env():
    kv = {}
    for line in ENV.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        kv[k.strip()] = v.strip().strip('"').strip("'")
    return kv


def effective_level(req, rec):
    lvl = max(req or 0, rec or 0)
    return lvl if lvl > 0 else 1


def band_for(req, rec):
    lvl = effective_level(req, rec)
    if lvl >= 90:
        return 9
    return min(9, max(0, lvl // 10))


def fetch(cur, sql):
    cur.execute(sql)
    return cur.fetchall()


def material_word(name_lower):
    """Extract the material token from a crafted item name. Names follow either
    'Imbued <material> <slot...>' (charm-imbued mastercrafted) or
    '<material> <slot...>' (plain mastercrafted)."""
    parts = name_lower.split()
    if not parts:
        return ""
    if parts[0] == "imbued" and len(parts) >= 2:
        return parts[1]
    return parts[0]


def fetch_gear(cur):
    sql = f"""
        SELECT id, name, item_type, required_level, recommended_level
          FROM items
         WHERE crafted = 1 AND id < 10000000
           AND item_type IN ({",".join(f"'{t}'" for t in GEAR_TYPES)})
         ORDER BY id
    """
    seen = {}
    for r in fetch(cur, sql):
        key = r["name"].lower()
        if key in seen:
            continue
        if effective_level(r["required_level"], r["recommended_level"]) > MAX_LEVEL:
            continue
        parts = key.split()
        if not parts or parts[0] in SUBQUALITY_PREFIXES:
            continue
        band = band_for(r["required_level"], r["recommended_level"])
        material = material_word(key)
        if material not in KEEP_MATERIALS_BY_BAND.get(band, set()):
            continue
        seen[key] = r
    return list(seen.values())


def fetch_consumables(cur):
    sql = """
        SELECT id, name, item_type, required_level, recommended_level
          FROM items
         WHERE crafted = 1 AND id < 10000000
           AND item_type IN ('Food', 'Bauble', 'Thrown')
         ORDER BY id
    """
    seen = {}
    for r in fetch(cur, sql):
        key = r["name"].lower()
        if key in seen:
            continue
        if effective_level(r["required_level"], r["recommended_level"]) > MAX_LEVEL:
            continue
        seen[key] = r
    return list(seen.values())


def fetch_containers(cur):
    """Crafted bags + strong-box-style house containers. Most are level 0
    (no level requirement), so the level cap doesn't filter much. No
    material allowlist — bags follow material naming inconsistently and
    the catalog should just show what's available."""
    types_in = ",".join(f"'{t}'" for t in CONTAINER_TYPES)
    sql = f"""
        SELECT id, name, item_type, required_level, recommended_level
          FROM items
         WHERE crafted = 1 AND id < 10000000
           AND item_type IN ({types_in})
         ORDER BY id
    """
    seen = {}
    for r in fetch(cur, sql):
        key = r["name"].lower()
        if key in seen:
            continue
        if effective_level(r["required_level"], r["recommended_level"]) > MAX_LEVEL:
            continue
        parts = key.split()
        if not parts or parts[0] in SUBQUALITY_PREFIXES:
            continue
        seen[key] = r
    return list(seen.values())


def bucket(rows):
    """Group by (band, item_type)."""
    by_band = defaultdict(lambda: defaultdict(list))
    for r in rows:
        b = band_for(r["required_level"], r["recommended_level"])
        by_band[b][r["item_type"]].append(r)
    for band in by_band:
        for typ in by_band[band]:
            by_band[band][typ].sort(
                key=lambda r: (effective_level(r["required_level"], r["recommended_level"]), r["name"].lower())
            )
    return by_band


PAGE_HEAD = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mastercrafted handout catalog</title>
<style>
:root {
  --bg: #1a1d21; --fg: #e6e6e6; --muted: #8b9097; --accent: #6ea8fe;
  --card: #23272e; --hover: #2c3137; --border: #3a3f47; --copied: #6dbf7b;
}
* { box-sizing: border-box; }
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
       background: var(--bg); color: var(--fg); line-height: 1.45; }
.layout { display: grid; grid-template-columns: 260px 1fr; min-height: 100vh; }
nav { position: sticky; top: 0; height: 100vh; overflow-y: auto; padding: 1rem;
      border-right: 1px solid var(--border); background: #16181c; }
nav h1 { font-size: 1rem; margin: 0 0 .75rem; color: var(--accent); }
nav ul { list-style: none; padding: 0; margin: 0 0 1rem; font-size: .9rem; }
nav li { margin: .15rem 0; }
nav a { color: var(--muted); text-decoration: none; }
nav a:hover { color: var(--fg); }
nav .section-label { color: var(--accent); font-weight: 600; margin-top: .9rem; display: block;
                     font-size: .8rem; text-transform: uppercase; letter-spacing: .05em; }
main { padding: 1rem 2rem 4rem; max-width: 1100px; }
header.page { position: sticky; top: 0; background: var(--bg); padding: 1rem 0; z-index: 10;
              border-bottom: 1px solid var(--border); }
header.page h1 { margin: 0 0 .5rem; font-size: 1.3rem; }
header.page p { margin: 0; color: var(--muted); font-size: .9rem; }
.search, .give-to { display: block; width: 100%; padding: .55rem .8rem; margin: .8rem 0 0;
          background: var(--card); color: var(--fg); border: 1px solid var(--border);
          border-radius: 6px; font-size: .95rem; }
.search:focus, .give-to:focus { outline: none; border-color: var(--accent); }
.give-to.set { border-color: var(--copied); }
.target-row { display: grid; grid-template-columns: auto 1fr auto; gap: .5rem;
              align-items: center; margin-top: .8rem; }
.target-row label { color: var(--muted); font-size: .85rem; white-space: nowrap; }
.target-row .give-to { margin-top: 0; }
.target-row .target-mode { color: var(--muted); font-size: .75rem;
                           font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; }
.target-row .target-mode.give { color: var(--copied); }
section.band { margin-top: 2rem; }
section.band > h2 { margin: 0 0 .25rem; font-size: 1.1rem; color: var(--accent); }
section.band > .band-meta { color: var(--muted); font-size: .85rem; margin-bottom: .8rem; }
section.type { margin-top: 1rem; }
section.type > h3 { margin: 0 0 .4rem; font-size: .95rem; color: var(--fg);
                    border-bottom: 1px solid var(--border); padding-bottom: .25rem; }
.items { display: grid; gap: .25rem; }
.item { display: grid; grid-template-columns: auto 1fr auto; gap: .6rem; align-items: center;
        padding: .35rem .6rem; background: var(--card); border-radius: 4px; font-size: .88rem; }
.item:hover { background: var(--hover); }
.item .name { color: var(--fg); }
.item .lvl { color: var(--muted); font-size: .8rem; }
.item .id  { color: var(--muted); font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
             font-size: .8rem; }
button.copy { background: transparent; color: var(--accent); border: 1px solid var(--border);
              border-radius: 4px; padding: .2rem .55rem; font-size: .75rem; cursor: pointer;
              font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; }
button.copy:hover { border-color: var(--accent); }
button.copy.copied { color: var(--copied); border-color: var(--copied); }
.empty { color: var(--muted); font-style: italic; padding: .5rem 0; }
.hint  { background: #2a2e35; padding: .6rem .8rem; border-radius: 6px; margin: .8rem 0 0;
         border-left: 3px solid var(--accent); font-size: .85rem; }
code { background: #2a2e35; padding: .1rem .35rem; border-radius: 3px;
       font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-size: .85em; }
@media (max-width: 800px) {
  .layout { grid-template-columns: 1fr; }
  nav { position: static; height: auto; }
}
</style>
</head>
"""

PAGE_SCRIPT = r"""\
<script>
const giveTo = document.getElementById('give-to');
const targetMode = document.getElementById('target-mode');

// Persist target across reloads so the operator doesn't retype every session.
const SAVED_TARGET_KEY = 'mc_handout_target';
const saved = localStorage.getItem(SAVED_TARGET_KEY);
if (saved) giveTo.value = saved;

function buildCommand(itemId) {
  const player = giveTo.value.trim();
  return player ? `/giveitem ${player} ${itemId}` : `/summonitem ${itemId}`;
}

function refreshTargetMode() {
  const player = giveTo.value.trim();
  if (player) {
    targetMode.textContent = `→ /giveitem ${player}`;
    targetMode.classList.add('give');
    giveTo.classList.add('set');
  } else {
    targetMode.textContent = '→ /summonitem (self)';
    targetMode.classList.remove('give');
    giveTo.classList.remove('set');
  }
}

giveTo.addEventListener('input', () => {
  localStorage.setItem(SAVED_TARGET_KEY, giveTo.value);
  refreshTargetMode();
});
refreshTargetMode();

document.addEventListener('click', (e) => {
  const btn = e.target.closest('button.copy');
  if (!btn) return;
  const cmd = buildCommand(btn.dataset.itemid);
  navigator.clipboard.writeText(cmd).then(() => {
    const original = btn.textContent;
    btn.textContent = 'copied!';
    btn.classList.add('copied');
    setTimeout(() => { btn.textContent = original; btn.classList.remove('copied'); }, 900);
  });
});

const search = document.getElementById('search');
search.addEventListener('input', () => {
  const tokens = search.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
  document.querySelectorAll('section.type').forEach(typeSec => {
    let any = false;
    typeSec.querySelectorAll('.item').forEach(it => {
      const hay = it.dataset.search;
      const show = !tokens.length || tokens.every(t => hay.includes(t));
      it.style.display = show ? '' : 'none';
      if (show) any = true;
    });
    typeSec.style.display = any ? '' : 'none';
  });
  document.querySelectorAll('section.band').forEach(bandSec => {
    const visible = bandSec.querySelectorAll('section.type:not([style*="none"])').length;
    bandSec.style.display = visible ? '' : 'none';
  });
});
</script>
"""


def render(gear_rows, consumable_rows, container_rows):
    gear_buckets = bucket(gear_rows)
    cons_buckets = bucket(consumable_rows)
    container_buckets = bucket(container_rows)

    # nav
    nav = ['<nav>', '<h1>Crafted item catalog</h1>',
           '<input id="search" class="search" type="search" placeholder="Search items&hellip;">',
           '<span class="section-label">Gear</span>', '<ul>']
    for b, label in BAND_LABELS:
        if b in gear_buckets:
            total = sum(len(v) for v in gear_buckets[b].values())
            nav.append(f'<li><a href="#gear-band-{b}">{html.escape(label)} ({total})</a></li>')
    nav.append('</ul>')
    nav.append('<span class="section-label">Consumables</span>')
    nav.append('<ul>')
    for b, label in BAND_LABELS:
        if b in cons_buckets:
            total = sum(len(v) for v in cons_buckets[b].values())
            nav.append(f'<li><a href="#cons-band-{b}">{html.escape(label)} ({total})</a></li>')
    nav.append('</ul>')
    if container_buckets:
        nav.append('<span class="section-label">Containers</span>')
        nav.append('<ul>')
        for b, label in BAND_LABELS:
            if b in container_buckets:
                total = sum(len(v) for v in container_buckets[b].values())
                nav.append(f'<li><a href="#cont-band-{b}">{html.escape(label)} ({total})</a></li>')
        nav.append('</ul>')
    nav.append('</nav>')

    main = ['<main>', '<header class="page">',
            '<h1>Mastercrafted handout catalog</h1>',
            '<p>Mastercrafted gear (rare-harvest crafted) and crafted consumables, deduped, '
            f'capped at level {MAX_LEVEL}. Use the search box to narrow the list, set a player '
            'name in <em>Give to</em> to switch the copy buttons from <code>/summonitem</code> '
            'to <code>/giveitem &lt;player&gt;</code>, then click <em>copy</em> on any row.</p>',
            '<div class="target-row">',
            '<label for="give-to">Give to:</label>',
            '<input id="give-to" class="give-to" type="text" '
            'placeholder="leave blank to summon to yourself" '
            'autocomplete="off" spellcheck="false">',
            '<span id="target-mode" class="target-mode">→ /summonitem (self)</span>',
            '</div>',
            '<div class="hint">Tips: '
            '<code>/summonitem &lt;id&gt; 1 bank</code> to drop into bank instead of bag &middot; '
            '<code>/player coins add plat 100</code> for coin &middot; '
            'item id is shown on the right of each row if you ever need to type the command by hand.</div>',
            '</header>']

    def render_section(prefix, label_root, buckets, type_order, type_display):
        out = []
        for b, label in BAND_LABELS:
            if b not in buckets:
                continue
            band_items = buckets[b]
            total = sum(len(v) for v in band_items.values())
            out.append(f'<section class="band" id="{prefix}-band-{b}">')
            out.append(f'<h2>{html.escape(label_root)} &mdash; {html.escape(label)}</h2>')
            out.append(f'<div class="band-meta">{total} items</div>')
            for typ in type_order:
                if typ not in band_items:
                    continue
                rows = band_items[typ]
                out.append('<section class="type">')
                out.append(f'<h3>{html.escape(type_display.get(typ, typ))} ({len(rows)})</h3>')
                out.append('<div class="items">')
                for r in rows:
                    lvl = effective_level(r["required_level"], r["recommended_level"])
                    name = r["name"].strip()
                    search_blob = f'{name.lower()} {r["id"]} {typ.lower()}'
                    out.append(
                        f'<div class="item" data-search="{html.escape(search_blob, quote=True)}">'
                        f'<button class="copy" data-itemid="{r["id"]}" type="button">copy</button>'
                        f'<span class="name">{html.escape(name)} '
                        f'<span class="lvl">&middot; lvl {lvl}</span></span>'
                        f'<span class="id">{r["id"]}</span>'
                        f'</div>'
                    )
                out.append('</div></section>')
            out.append('</section>')
        return out

    main.extend(render_section("gear", "Gear", gear_buckets, GEAR_TYPES, GEAR_TYPE_DISPLAY))
    main.extend(render_section("cons", "Consumables", cons_buckets, ("Food", "Bauble", "Thrown"), CONS_DISPLAY))
    main.extend(render_section("cont", "Containers", container_buckets, CONTAINER_TYPES, CONTAINER_DISPLAY))
    main.append('</main>')

    body = ['<body>', '<div class="layout">'] + nav + main + ['</div>']
    body.append(PAGE_SCRIPT)
    body.append('</body></html>')
    return PAGE_HEAD + "\n".join(body)


def main():
    env = load_env()
    conn = pymysql.connect(
        host="127.0.0.1", port=3306, user="root",
        password=env["MARIADB_ROOT_PASSWORD"], database=env["MARIADB_DATABASE"],
        cursorclass=pymysql.cursors.DictCursor, charset="utf8mb4",
    )
    with conn.cursor() as cur:
        gear_rows = fetch_gear(cur)
        cons_rows = fetch_consumables(cur)
        container_rows = fetch_containers(cur)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(gear_rows, cons_rows, container_rows))
    if LEGACY_MD.exists():
        LEGACY_MD.unlink()
    print(f"wrote {OUT} ({len(gear_rows)} gear, {len(cons_rows)} consumable, "
          f"{len(container_rows)} container, capped at lvl {MAX_LEVEL})")


if __name__ == "__main__":
    main()
