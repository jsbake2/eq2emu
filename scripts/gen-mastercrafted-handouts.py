#!/usr/bin/env python3
"""
Generate docs/mastercrafted-handouts.html — a searchable, click-to-copy
catalog of mastercrafted gear and crafted consumables, so GM Jason can copy
a single /summonitem command and paste it into the EQ2 client (which
accepts one command per chat input).

Read-only against the live eq2emu DB. Credentials from docker/.env.

Mastercrafted gear filter:
  * Items with name LIKE 'Imbued <material> ...' where <material> is in the
    hand-curated KEEP_MATERIALS_BY_BAND allowlist. The DB has no reliable
    mastercrafted/handcrafted flag (every crafted item rolls up to
    items.tier=3 regardless of quality), so the operator marked which
    per-tier materials are real mastercrafted vs handcrafted-imbued.
  * Item types: Weapon, Armor, Shield, Ranged, Bauble.
  * Dedup: id < 10_000_000 only; further deduped by LOWER(name) keeping
    the lowest id.
  * Capped at MAX_LEVEL (matches R_Player/MaxLevel on the live server).

Consumables: all crafted Food / Bauble / Thrown items, capped at MAX_LEVEL.
No mastercrafted filter — there isn't a clean signal in the DB and excess
food/totems is fine.
"""

import html
import json
from collections import defaultdict
from pathlib import Path

import pymysql

REPO = Path(__file__).resolve().parent.parent
ENV = REPO / "docker" / ".env"
OUT = REPO / "docs" / "mastercrafted-handouts.html"
LEGACY_MD = REPO / "docs" / "mastercrafted-handouts.md"

GEAR_TYPES = ("Weapon", "Armor", "Shield", "Ranged", "Bauble")
GEAR_TYPE_DISPLAY = {
    "Weapon": "Weapons",
    "Armor": "Armor",
    "Shield": "Shields",
    "Ranged": "Ranged",
    "Bauble": "Baubles",
}
CONS_DISPLAY = {"Food": "Food & drink", "Bauble": "Totems & baubles", "Thrown": "Arrows & thrown"}
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
# Hand-curated rare-material allowlist per level band (keyed by band index;
# band N covers levels N*10 to N*10+9). The DB has no clean mastercrafted
# flag, so we list the actual mastercrafted rare materials per tier here.
# Materials not listed are filtered out even if the auto-detector would
# have included them (most often common-metal handcrafted-imbued items).
# Source: operator (Jason) walked the auto-detected list and marked which
# materials are real mastercrafted vs handcrafted.
KEEP_MATERIALS_BY_BAND = {
    0: {"bronze"},                          # T1 (lvl 1-9)
    1: {"blackened", "bone", "cured"},      # T2 (lvl 10-19)
    2: {"steel", "fir", "cuirboilli"},      # T3 (lvl 20-29)
    3: {"feysteel", "oak", "engraved"},     # T4 (lvl 30-39)
    4: {"ebon", "cedar", "augmented"},      # T5 (lvl 40-49)
}

# Server R_Player/MaxLevel — cap the catalog to items a level-capped player
# can actually use. Anything above this is hidden, including consumables.
MAX_LEVEL = 50


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


def fetch_gear(cur):
    sql = f"""
        SELECT id, name, item_type, required_level, recommended_level
          FROM items
         WHERE crafted = 1 AND id < 10000000
           AND name LIKE 'Imbued %'
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
        band = band_for(r["required_level"], r["recommended_level"])
        material = key.split()[1] if len(key.split()) > 1 else ""
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
.search { display: block; width: 100%; padding: .55rem .8rem; margin: .8rem 0 0;
          background: var(--card); color: var(--fg); border: 1px solid var(--border);
          border-radius: 6px; font-size: .95rem; }
.search:focus { outline: none; border-color: var(--accent); }
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

PAGE_SCRIPT = """\
<script>
document.addEventListener('click', (e) => {
  const btn = e.target.closest('button.copy');
  if (!btn) return;
  const cmd = btn.dataset.cmd;
  navigator.clipboard.writeText(cmd).then(() => {
    const original = btn.textContent;
    btn.textContent = 'copied!';
    btn.classList.add('copied');
    setTimeout(() => { btn.textContent = original; btn.classList.remove('copied'); }, 900);
  });
});

const search = document.getElementById('search');
search.addEventListener('input', () => {
  const q = search.value.trim().toLowerCase();
  document.querySelectorAll('section.type').forEach(typeSec => {
    let any = false;
    typeSec.querySelectorAll('.item').forEach(it => {
      const hay = it.dataset.search;
      const show = !q || hay.includes(q);
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


def render(gear_rows, consumable_rows, rare_by_band):
    gear_buckets = bucket(gear_rows)
    cons_buckets = bucket(consumable_rows)

    # nav
    nav = ['<nav>', '<h1>Mastercrafted handouts</h1>',
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
    nav.append('</ul></nav>')

    main = ['<main>', '<header class="page">',
            '<h1>Mastercrafted handout catalog</h1>',
            '<p>Click a copy button to put a single <code>/summonitem</code> command on your clipboard, '
            'then paste into the EQ2 chat. Use the search box to filter by name.</p>',
            '<div class="hint">Other useful GM commands: '
            '<code>/giveitem &lt;player&gt; &lt;id&gt;</code> to hand to another player &middot; '
            '<code>/summonitem &lt;id&gt; 1 bank</code> to bank instead of bag &middot; '
            '<code>/player coins add plat 100</code> for coin.</div>',
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
                    cmd = f"/summonitem {r['id']}"
                    search_blob = f'{name.lower()} {r["id"]} {typ.lower()}'
                    out.append(
                        f'<div class="item" data-search="{html.escape(search_blob, quote=True)}">'
                        f'<button class="copy" data-cmd="{html.escape(cmd, quote=True)}" type="button">copy</button>'
                        f'<span class="name">{html.escape(name)} '
                        f'<span class="lvl">&middot; lvl {lvl}</span></span>'
                        f'<span class="id">{r["id"]}</span>'
                        f'</div>'
                    )
                out.append('</div></section>')
            out.append('</section>')
        return out

    main.extend(render_section("gear", "Mastercrafted gear", gear_buckets, GEAR_TYPES, GEAR_TYPE_DISPLAY))
    main.extend(render_section("cons", "Crafted consumables", cons_buckets, ("Food", "Bauble", "Thrown"), CONS_DISPLAY))
    main.append('</main>')

    rare_summary = {b: sorted(list(v)) for b, v in rare_by_band.items()}
    body = ['<body>', '<div class="layout">'] + nav + main + ['</div>']
    body.append(f'<!-- rare materials by band: {json.dumps(rare_summary)} -->')
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

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(gear_rows, cons_rows, KEEP_MATERIALS_BY_BAND))
    if LEGACY_MD.exists():
        LEGACY_MD.unlink()
    print(f"wrote {OUT} ({len(gear_rows)} gear, {len(cons_rows)} consumable, capped at lvl {MAX_LEVEL})")


if __name__ == "__main__":
    main()
