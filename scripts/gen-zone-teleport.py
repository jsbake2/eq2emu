#!/usr/bin/env python3
"""
Generate docs/zone-teleport.html — searchable list of zones with
group-member name fields. Pick a zone, fill in friend names, click
generate, copy the resulting block of /zone + /summon commands.

Reads the zones table from the live DB. Filters out instance shells
and tutorial-only zones to keep the list manageable.
"""

import html
import json
from pathlib import Path

import pymysql

REPO = Path(__file__).resolve().parent.parent
ENV = REPO / "docker" / ".env"
OUT = REPO / "docs" / "zone-teleport.html"


def load_env():
    kv = {}
    for line in ENV.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        kv[k.strip()] = v.strip().strip('"').strip("'")
    return kv


def fetch_zones(cur):
    cur.execute("""
        SELECT id, name, file, description, min_level, max_level
        FROM zones
        WHERE instance_type = 'NONE'
          AND name NOT LIKE 'tutorial%'
          AND name NOT LIKE 'StartingArea%'
          AND name != ''
        ORDER BY name
    """)
    return cur.fetchall()


PAGE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Zone teleport</title>
<style>
:root {
  --bg: #1a1d21; --fg: #e6e6e6; --muted: #8b9097; --accent: #6ea8fe;
  --card: #23272e; --hover: #2c3137; --border: #3a3f47; --copied: #6dbf7b;
}
* { box-sizing: border-box; }
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
       background: var(--bg); color: var(--fg); line-height: 1.45; }
header.tabs { display: flex; gap: .25rem; padding: .8rem 1.5rem 0; background: #16181c;
              border-bottom: 1px solid var(--border); position: sticky; top: 0; z-index: 5; }
header.tabs a { padding: .55rem .9rem; border-radius: 6px 6px 0 0; color: var(--muted);
                text-decoration: none; font-size: .9rem; border: 1px solid transparent;
                border-bottom: none; }
header.tabs a:hover { color: var(--fg); background: var(--card); }
header.tabs a.active { color: var(--accent); background: var(--bg); border-color: var(--border); }
main { padding: 1.5rem 2rem 4rem; max-width: 1200px; margin: 0 auto;
       display: grid; grid-template-columns: 360px 1fr; gap: 2rem; }
@media (max-width: 900px) { main { grid-template-columns: 1fr; } }
h1 { margin: .25rem 0 .25rem; font-size: 1.4rem; }
.lead { margin: 0 0 1.5rem; color: var(--muted); font-size: .9rem; }
.controls h2 { margin: 1.2rem 0 .4rem; font-size: .95rem; color: var(--accent);
               text-transform: uppercase; letter-spacing: .05em; }
input[type="search"], input[type="text"] {
  width: 100%; padding: .5rem .7rem; background: var(--card); color: var(--fg);
  border: 1px solid var(--border); border-radius: 6px; font-size: .9rem;
}
input:focus { outline: none; border-color: var(--accent); }
.zone-list { max-height: 50vh; overflow-y: auto; margin-top: .6rem; padding: .25rem;
             background: var(--card); border: 1px solid var(--border); border-radius: 6px; }
.zone-row { padding: .35rem .55rem; border-radius: 4px; cursor: pointer; font-size: .85rem;
            display: flex; justify-content: space-between; align-items: center; gap: .4rem; }
.zone-row:hover { background: var(--hover); }
.zone-row.selected { background: var(--accent); color: #16181c; }
.zone-row .zfile { color: var(--muted); font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
                   font-size: .75rem; }
.zone-row.selected .zfile { color: #16181c; opacity: .75; }
.friend-input { margin-top: .4rem; }
.output { padding: 1rem; background: var(--card); border: 1px solid var(--border);
          border-radius: 8px; min-height: 50vh; }
.output h2 { margin: 0 0 .5rem; font-size: 1rem; color: var(--accent); }
.output .muted { color: var(--muted); font-size: .85rem; margin-bottom: .8rem; }
.cheat-block { background: #16181c; padding: .65rem .9rem; border-radius: 6px;
               font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
               font-size: .85rem; color: var(--fg); margin: .4rem 0; cursor: pointer;
               border: 1px solid transparent; white-space: pre; overflow-x: auto;
               transition: border-color .15s, background .15s; }
.cheat-block:hover { border-color: var(--border); background: #1a1d21; }
.cheat-block.copied { border-color: var(--copied); }
.cheat-block .lbl { color: var(--muted); font-size: .75rem; margin-right: .5rem; }
button.copy-all { margin-top: .8rem; padding: .55rem 1rem; background: var(--accent); color: #16181c;
                  border: 0; border-radius: 6px; font-size: .9rem; cursor: pointer; font-weight: 600; }
button.copy-all:hover { filter: brightness(1.05); }
button.copy-all.copied { background: var(--copied); }
.toast { position: fixed; bottom: 1.5rem; left: 50%; transform: translateX(-50%);
         background: var(--copied); color: #16181c; padding: .5rem 1rem; border-radius: 6px;
         font-size: .85rem; opacity: 0; transition: opacity .2s; pointer-events: none; }
.toast.show { opacity: 1; }
code { background: #2a2e35; padding: .1rem .35rem; border-radius: 3px;
       font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-size: .85em; }
.empty { color: var(--muted); font-style: italic; padding: 1rem .5rem; }
</style>
</head>
<body>
<header class="tabs">
  <a href="mastercrafted-handouts.html">Crafted catalog</a>
  <a href="gm-cheatsheet.html">GM cheatsheet</a>
  <a href="zone-teleport.html" class="active">Zone teleport</a>
</header>
<main>
<div class="controls">
  <h1>Zone teleport</h1>
  <p class="lead">Pick a zone, optionally fill in friend names, then copy the generated commands.</p>

  <h2>Zone</h2>
  <input id="zone-search" type="search" placeholder="Search zones (Antonica, Qeynos, &hellip;)" autocomplete="off">
  <div id="zone-list" class="zone-list"></div>

  <h2>Friends to bring</h2>
  <input id="friend-1" class="friend-input" type="text" placeholder="Friend 1" autocomplete="off">
  <input id="friend-2" class="friend-input" type="text" placeholder="Friend 2" autocomplete="off">
  <input id="friend-3" class="friend-input" type="text" placeholder="Friend 3" autocomplete="off">
  <input id="friend-4" class="friend-input" type="text" placeholder="Friend 4" autocomplete="off">
  <input id="friend-5" class="friend-input" type="text" placeholder="Friend 5" autocomplete="off">
</div>

<div class="output">
  <h2>Generated commands</h2>
  <p class="muted">Click any line to copy it. Or use <em>Copy all</em> to grab the whole block. Each friend gets a <code>/summon</code> after you've zoned, which only works if they're online.</p>
  <div id="cmd-block" class="empty">Pick a zone to start.</div>
  <button id="copy-all" class="copy-all" style="display:none">Copy all</button>
</div>
</main>

<div id="toast" class="toast">copied</div>

<script>
const ZONES = __ZONES_JSON__;

const zoneListEl = document.getElementById('zone-list');
const zoneSearchEl = document.getElementById('zone-search');
const friendEls = [1,2,3,4,5].map(n => document.getElementById('friend-' + n));
const cmdBlock = document.getElementById('cmd-block');
const copyAllBtn = document.getElementById('copy-all');
const toast = document.getElementById('toast');

let selectedZone = null;

function showToast(msg) {
  toast.textContent = msg;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 1200);
}

function copyText(text, onok) {
  navigator.clipboard.writeText(text).then(() => { if (onok) onok(); });
}

function renderZoneList(filter) {
  const f = (filter || '').toLowerCase().trim();
  const filtered = f
    ? ZONES.filter(z => z.name.toLowerCase().includes(f) || (z.file || '').toLowerCase().includes(f))
    : ZONES;
  zoneListEl.innerHTML = '';
  if (filtered.length === 0) {
    const div = document.createElement('div');
    div.className = 'empty';
    div.textContent = 'No matches.';
    zoneListEl.appendChild(div);
    return;
  }
  for (const z of filtered.slice(0, 200)) {
    const row = document.createElement('div');
    row.className = 'zone-row' + (selectedZone === z.name ? ' selected' : '');
    row.dataset.zone = z.name;
    row.innerHTML = '<span>' + z.name + '</span><span class="zfile">' + (z.file || '') + '</span>';
    row.onclick = () => { selectZone(z.name); };
    zoneListEl.appendChild(row);
  }
  if (ZONES.length > filtered.length && !f) {
    const tip = document.createElement('div');
    tip.className = 'empty';
    tip.textContent = 'Showing first 200 of ' + ZONES.length + '. Use search to narrow.';
    zoneListEl.appendChild(tip);
  }
}

function selectZone(name) {
  selectedZone = name;
  for (const r of zoneListEl.querySelectorAll('.zone-row')) {
    r.classList.toggle('selected', r.dataset.zone === name);
  }
  renderCommands();
}

function renderCommands() {
  if (!selectedZone) {
    cmdBlock.className = 'empty';
    cmdBlock.textContent = 'Pick a zone to start.';
    copyAllBtn.style.display = 'none';
    return;
  }
  const friends = friendEls.map(el => el.value.trim()).filter(Boolean);
  const lines = [];
  lines.push('/zone ' + selectedZone);
  for (const f of friends) {
    lines.push('/summon ' + f);
  }
  cmdBlock.className = '';
  cmdBlock.innerHTML = '';
  for (let i = 0; i < lines.length; i++) {
    const block = document.createElement('pre');
    block.className = 'cheat-block';
    const lbl = i === 0 ? 'YOU' : 'BRING';
    block.innerHTML = '<span class="lbl">' + lbl + '</span>' + lines[i];
    block.onclick = () => copyText(lines[i], () => {
      block.classList.add('copied');
      showToast('copied: ' + lines[i]);
      setTimeout(() => block.classList.remove('copied'), 1200);
    });
    cmdBlock.appendChild(block);
  }
  copyAllBtn.style.display = 'inline-block';
  copyAllBtn.onclick = () => copyText(lines.join('\\n'), () => {
    copyAllBtn.classList.add('copied');
    copyAllBtn.textContent = 'Copied ' + lines.length + ' line(s)';
    showToast('copied ' + lines.length + ' line(s)');
    setTimeout(() => {
      copyAllBtn.classList.remove('copied');
      copyAllBtn.textContent = 'Copy all';
    }, 1500);
  });
}

zoneSearchEl.addEventListener('input', () => renderZoneList(zoneSearchEl.value));
for (const el of friendEls) el.addEventListener('input', renderCommands);

renderZoneList('');
</script>
</body>
</html>
"""


def main():
    env = load_env()
    conn = pymysql.connect(
        host="127.0.0.1", port=3306, user="root",
        password=env["MARIADB_ROOT_PASSWORD"], database=env["MARIADB_DATABASE"],
        cursorclass=pymysql.cursors.DictCursor, charset="utf8mb4",
    )
    with conn.cursor() as cur:
        rows = fetch_zones(cur)

    zones = [{"id": r["id"], "name": r["name"], "file": r["file"] or ""} for r in rows]
    payload = json.dumps(zones, ensure_ascii=False)
    out_html = PAGE.replace("__ZONES_JSON__", payload)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(out_html)
    print(f"wrote {OUT} ({len(out_html):,} bytes, {len(zones)} zones)")


if __name__ == "__main__":
    main()
