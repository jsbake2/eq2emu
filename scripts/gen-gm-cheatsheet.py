#!/usr/bin/env python3
"""
Generate docs/gm-cheatsheet.html — a click-to-copy reference for the
GM commands we use most. Standalone page so it doesn't bury the main
catalog or zone-teleport pages.

No DB access — all content is hand-curated in this script. Re-run any
time you add a new command worth memorializing.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "docs" / "gm-cheatsheet.html"

# Each section is (title, [(command_with_inline_comment, ...)]). Comments
# after `#` are stripped on click — only the command itself goes to the
# clipboard.
SECTIONS = [
    ("Self / progression", [
        "/level 50                           # set adventure level (step 1 → 10 → 20 → target if past 20)",
        "/setlevel 50                        # alias on some builds",
        "/reload rules                       # apply rule changes without restart",
    ]),
    ("Coin", [
        "/player coins add plat 100          # +100 platinum",
        "/player coins add gold 50           # +50 gold",
        "/player coins add silver 250        # +250 silver",
        "/player coins add copper 1000       # +1000 copper",
    ]),
    ("Items", [
        "/summonitem <id>                    # spawn item into your bag",
        "/summonitem <id> 1 bank             # spawn item directly into your bank",
        "/giveitem <target> <id>             # hand item to another player by name",
        "/itemsearch <name>                  # find ids by name fragment",
        "/summonitem 45462                   # Call of the Veteran (recall to a friend's location)",
    ]),
    ("Travel", [
        "/zone <ZoneName>                    # teleport into a zone (e.g. /zone Antonica)",
        "/zone list <query>                  # search known zones by name",
        "/goto <target>                      # teleport to a player or NPC by name (same zone)",
        "/summon <target>                    # bring a player or NPC to you",
    ]),
    ("Bots", [
        "/bot help race                      # in-game book of race IDs",
        "/bot help class                     # in-game book of class IDs",
        "/bot create <race> <gender> <class> <name>",
        "                                    # create — gender 0=female, 1=male",
        "/bot list                           # list your bots and their bot_ids",
        "/bot spawn <bot_id> 1               # summon + auto-invite to group",
        "/bot summon                         # summon a single targeted bot",
        "/bot summon group                   # summon every group bot you own",
        "/bot camp <bot_id>                  # camp a specific bot by id",
        "/bot camp all                       # camp every group bot you own",
        "/bot prepull                        # prime group bots to lay wards",
        "/bot delete <bot_id>                # permanent delete (do not use in anger)",
    ]),
    ("Targeting / utility", [
        "/target <name>                      # select target by name",
        "/who                                # list players in zone",
        "/loc                                # print your current coordinates",
        "/setdebug 1                         # enable verbose server debug",
    ]),
]

PAGE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GM cheatsheet</title>
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
main { padding: 1.5rem 2rem 4rem; max-width: 920px; margin: 0 auto; }
h1 { margin: .5rem 0 .25rem; font-size: 1.4rem; }
.lead { margin: 0 0 1.5rem; color: var(--muted); font-size: .9rem; }
section { margin: 1.6rem 0; }
section h2 { margin: 0 0 .25rem; font-size: 1rem; color: var(--accent);
             text-transform: uppercase; letter-spacing: .05em; }
.cheat-block { background: #16181c; padding: .65rem .9rem; border-radius: 6px;
               font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
               font-size: .85rem; color: var(--fg); margin: .5rem 0; cursor: pointer;
               border: 1px solid transparent; white-space: pre; overflow-x: auto;
               transition: border-color .15s, background .15s; }
.cheat-block:hover { border-color: var(--border); background: var(--card); }
.cheat-block.copied { border-color: var(--copied); }
.toast { position: fixed; bottom: 1.5rem; left: 50%; transform: translateX(-50%);
         background: var(--copied); color: #16181c; padding: .5rem 1rem; border-radius: 6px;
         font-size: .85rem; opacity: 0; transition: opacity .2s; pointer-events: none; }
.toast.show { opacity: 1; }
code { background: #2a2e35; padding: .1rem .35rem; border-radius: 3px;
       font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-size: .85em; }
</style>
</head>
<body>
<header class="tabs">
  <a href="mastercrafted-handouts.html">Crafted catalog</a>
  <a href="gm-cheatsheet.html" class="active">GM cheatsheet</a>
  <a href="zone-teleport.html">Zone teleport</a>
</header>
<main>
<h1>GM cheatsheet</h1>
<p class="lead">Common commands. Click any line to copy just the command (the inline <code>#</code> comment is stripped).
Replace placeholders like <code>&lt;target&gt;</code> with a player name when relevant.</p>

__SECTIONS__

</main>
<div id="toast" class="toast">copied</div>
<script>
document.addEventListener('click', (e) => {
  const block = e.target.closest('.cheat-block');
  if (!block) return;
  const line = (e.target.textContent || block.textContent).split('\\n').find(l => l.trim()) || block.textContent;
  // Strip inline comments (everything from "#" onward).
  const cmd = line.split('#')[0].trim();
  if (!cmd) return;
  navigator.clipboard.writeText(cmd).then(() => {
    block.classList.add('copied');
    const toast = document.getElementById('toast');
    toast.textContent = 'copied: ' + cmd;
    toast.classList.add('show');
    setTimeout(() => {
      block.classList.remove('copied');
      toast.classList.remove('show');
    }, 1200);
  });
});
</script>
</body>
</html>
"""


def render_sections() -> str:
    out = []
    for title, lines in SECTIONS:
        out.append(f'<section>\n<h2>{title}</h2>')
        # Each command on its own clickable block — easier to target click events
        # at one specific line.
        for line in lines:
            out.append(f'<pre class="cheat-block">{line}</pre>')
        out.append("</section>")
    return "\n".join(out)


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    html = PAGE.replace("__SECTIONS__", render_sections())
    OUT.write_text(html)
    print(f"wrote {OUT} ({len(html):,} bytes, {sum(len(l) for _, l in SECTIONS)} command lines)")


if __name__ == "__main__":
    main()
