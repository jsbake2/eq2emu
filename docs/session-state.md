# Session state — pick up where we left off

Last updated: **2026-04-29**.

This is the running notebook for active development. PROJECT.md owns the
strategy; this file owns "what's actually in flight right now." Update at
the end of each session so future-you (and Claude) can resume cold.

## Quick start

```bash
./scripts/server-up.sh        # bring stack up + apply patches + redeploy lua
./scripts/server-down.sh      # clean shutdown (data persists)
```

If `server-up.sh` says patches conflict, the container's source clone is in
a hybrid state. Reset it:

```bash
docker exec docker-eq2emu-server-1 sh -c \
  'cd /eq2emu/eq2emu/source && git reset --hard 6651d51071c05093933360ceaee7b99335fe3b2b'
./scripts/server-up.sh
```

In-game admin commands worth knowing:

```
/level 50                     # cap before testing bot AI (bots inherit your level)
/reload spells                # reload master_spell_list after a recat migration
/reload items                 # reload items after item_details_skill changes
/cancel_maintained            # popup to right-click maintained-spell removal
/bot list                     # show your bot roster + slot ids
/bot spawn <slot> 1           # spawn + auto-invite to group
/bot summon group             # bring all group bots to you
/bot camp <slot>              # camp by slot id (was target-only before #24)
/bot camp all                 # camp every group bot you own
/bot prepull                  # prime bots to lay wards proactively
```

## Live system state

The container source has a stack of in-flight patches applied but not all
of them are on `main` yet. The binary running before shutdown was built
with everything in this list:

| Patch | What | PR |
|---|---|---:|
| 0001 | DefaultSpellGrantTier rule (Expert) | merged |
| 0002 | Keymap persistence | merged |
| 0003 | Bot HP/power formula | merged |
| 0004 | Allow all expansions | merged |
| 0005 | Bot spawn visibility (ghost healer) | merged |
| 0006 | Bot follow smoothing | merged |
| 0007 | Bot followups (X2/Y2/Z2 spawn init, owner-as-target, mana regen, no chat spam) | merged |
| 0009 | Bot spell-chain dedup | **PR #20** open |
| 0010 | /bot prepull + /bot camp [id\|all] (incl. camp-by-id slot fix) | **PR #24** open |
| 0010-buff | Buff duration filter (skip <60s buffs in idle) | **PR #20** open |
| 0011 | Lua BotCommand binding | **PR #25** open |
| 0011-grpae | Group-AE fanout for bot casts | **PR #20** open |
| 0012 | Bot summon X2/Y2/Z2 reset → replaced with `HaltMovement()` | **PR #20** open |
| 0013 | Bot friendly-fire block (group safety in AttackAllowed) | **PR #31** open |

DB migrations applied to live:

| File | Effect |
|---|---|
| sql/migrations/001 | Existing chars promoted to Expert tier |
| sql/migrations/002 | character_keymap table |
| sql/migrations/003 | Recategorize priest spells (785 spells, Unset → Buff/HoT-Ward/Heal/etc.) |
| sql/migrations/004 | Tag rez spells (25 corpse-target spells → Rez) |
| sql/migrations/005 | Bot-control spell pack (8 universal hotbar abilities, IDs 2560001-2560015) |
| sql/migrations/006 | Starter loadout (6 backpacks + 5×food + 5×drink — CoV and steed dropped) |
| sql/migrations/007 | Tier-7 spell_data backfill (clones tier-1 to prevent Lua nil crashes) |
| sql/migrations/008 | Recategorize mage spells (419 spells) |
| sql/migrations/009 | Recategorize scout spells (346 spells) |
| sql/migrations/010 | Recategorize fighter spells (446 spells) |
| sql/migrations/011 | Revert no-data spells back to Unset (514 spells; safety against broken Lua) |
| sql/migrations/012 | Re-tag rezzes that 011 over-demoted (25 spells) |
| sql/migrations/013 | Tier-7 interpolation (43 rows interpolated between Adept and Master) |

Plus ad-hoc fixes applied directly to live (not in any migration):
- `usable=1` flipped on 314 baubles with `lua_script` set (so click activates)
- 315 mount Lua scripts patched (row id → appearance_id translation + v546 fallbacks)
- Stalk.lua + Bloom.lua typo fixes deployed via `scripts/deploy-custom-lua.sh`
- 8 bot-control Lua wrappers in `Spells/Commoner/Bot*.lua`

## Open PRs (12)

Recommended merge order — narrow-scope blockers first, drafts last:

| # | Title | Notes |
|---:|---|---|
| **20** | priest recat + bot spell-chain dedup | Foundation. All other bot-AI work assumes this is on main. Includes 0009/0010-buff/0011-grpae/0012 patches + tier-7 backfill + duration filter |
| **23** | tag rez spells | Data only. Independent of #20 |
| **24** | /bot prepull + /bot camp [id\|all] | C++. Depends on #20 indirectly (prepull only useful with recat'd ward map) |
| **25** | bot-control spell pack | UX. Depends on #24 |
| **26** | split GM cheatsheet + zone teleport off catalog | Docs only |
| **27** | starter loadout | Data only. CoV + Spirit Steed already dropped |
| **28** | recategorize mage / scout / fighter | Data only. Stacks on #20 |
| **29** | Lua typo fixes (Stalk + Bloom) | Tiny, harmless |
| **30** | restore catalog features (collections + bags + level cap) | Docs only. Adds 5923 gear / 541 collections |
| **31** | bot friendly-fire block | C++. Independent |
| **21** | DRAFT — bot cure logic | Wired but parked until in-game cure-need testing |
| **22** | DRAFT — Ollama bot personalities | Design + persona library only, no code |

## Recently validated in-game (works)

- ✅ Bot recat populates spell maps (defiler/inquisitor cast wards/buffs in idle)
- ✅ Group-AE fanout: Coercer's Breeze / Power of Mind / Signet of Intuition land on the whole group (was only buffing the bot itself before #20)
- ✅ Bot rez (after migration 012 re-tag): Inquisitor / Fury / Defiler etc. cast Resurrects-target spells on group corpses
- ✅ `/bot camp <slot>`, `/bot camp all`
- ✅ `/bot inv give` (target bot, opens trade window)
- ✅ Bot-control hotbar spells dispatch correctly (Bot Prepull cast → BotCommand binding → /bot prepull → wards lay)
- ✅ Tier-7 interpolation (Willowskin Mit went 549 → 944 etc.)
- ✅ Friendly-fire block (Patch 0013)

## Open questions / known issues / parked

- **Mount visuals don't render** — even after fixing `usable=1` flag, translating 315 Lua mount IDs from row id → appearance_id, and falling back to v546-compatible appearances. Speed bonus applies but no horse model. Probably a packet path issue. **Parked.** Workaround: removed Spirit Steed from starter loadout; users who want a mount can `/summonitem` and live without the visual.
- **Vigor / Vim** — different stat profiles (Vigor=MaxPower, Vim=STA+INT) so chain dedup correctly keeps both. User accepted "option A" (cast both). If chat clutter becomes annoying, build a curated `bot_spell_replacements` table.
- **`/bot summon group` run-off** — *might* still happen even with HaltMovement. User said "99999 out of 100000 times" they run off. Latest binary uses `HaltMovement()` instead of manual X2/Y2/Z2 reset. Untested after that swap. If still broken, dig into brain `MoveCloser` paths during `ProcessOutOfCombatSpells` — buff target lookups may chase a far group member.
- **Bot prepull chat message visibility** — works (bot reacts), but the "Primed on N bot(s)" message lands on a tab the user wasn't watching. Could move to a more visible channel.

## Next features to build (when you want to pick up)

1. **Healer-mode toggle** (`/bot mode <id> debuff|dps`) — discussed and approved. Per-bot flag in `bots` table; `Bot::GetCombatSpell` priority change. Mid-game DPS impact: healers contribute more by debuffing mob mit/avoidance than by weak DDs.
2. **Cure logic out of draft (#21)** — already wired; needs in-game cure-need test (bot member with curable detriment) to validate.
3. **Healer-mode for buffs in combat** — short-duration buffs (which my filter currently skips in idle) should fire during combat. The combat path doesn't go through GetBuffSpell, so should already work, but worth verifying.
4. **Spell-chain `bot_spell_replacements` table** — curated list of "X replaces Y" for cases like Vigor/Vim where the data doesn't link them but they're functionally redundant.
5. **Tier-7 interpolation expansion** — current run only catches 43 rows because most cloned spells lack tier-5 / tier-9 neighbors. If upstream content gets more tier coverage, re-run `scripts/interpolate-tier7-spell-data.py`.
6. **Ollama bot personalities** (PR #22) — design is in `docs/bot-personalities/`, hand off to a real implementation when bot AI is settled.
7. **Mount visual debug** — instrument the spawn-appearance packet to confirm `mount_type` field reaches the v546 client correctly. Currently a known-issue parking lot.

## Active branches

```
content/recategorize-priest-spells     PR #20
content/recategorize-rez-spells        PR #23
feature/bot-prepull-and-camp-by-id     PR #24
feature/bot-control-spell-pack         PR #25
docs/web-pages-restructure             PR #26
content/starter-loadout                PR #27
content/recategorize-other-classes     PR #28
fix/upstream-lua-typos                 PR #29
docs/restore-catalog-features          PR #30
fix/bot-friendly-fire                  PR #31
fix/bot-cure-logic                     PR #21 (DRAFT)
feature/ollama-bot-chat                PR #22 (DRAFT)
```

## Recent context / decisions

- **Stacked-PR anti-pattern surfaced early** — when PRs target a parent feature branch instead of `main`, merging the parent doesn't bring child commits with it. Fixed by always targeting `main` in PR creation. PR #13 had to backfill missing patches that got lost this way.
- **`pkill -x` not `pkill -f`** in `server-up.sh` hot-swap — `-f` matches the cmdline of the heredoc shell itself, killing it before `|| true` swallows the failure. Always use `-x eq2world`.
- **Container source can drift** — patches stacked in-place on the live container may not match any branch's `server-patches/` exactly. To get a clean diff for committing: `git reset --hard 6651d51` in the container source, replay only the patches you care about, then `python3 yourfix.py` and `git diff` for the isolated delta.
- **EQ2Emu DB has separate `id` and `appearance_id` columns** — the runtime mount/appearance protocol uses `appearance_id`, but most upstream Lua scripts pass `id` (the row's primary key). This was the systematic root cause behind 315 broken mount scripts. The fix is to translate at the data layer; doing it in `EQ2Emu_lua_SetMount` would also work but I went with data so the translation is auditable.
- **v546 client (DoF era)** — only renders appearance_ids with `min_client_version <= 546`. Mounts added in EoF/RoK+ don't have models in this client; we fallback to basic horse / ghost horse / palomino etc thematically.
- **Tier-7 ratio = 0.857** — derived empirically from spells with authentic tier-5/7/9 trios (e.g. Willowskin index 0: 9.4 → 11.8 → 12.2). Used for interpolation in migration 013.
- **Prepull chat message vs. dispatch** — the `Prepull primed on N bot(s)` message lands on a tab the user wasn't watching, but the dispatch IS firing (Bot Prepull cast log entry → Voracity ward cast immediately after). When in doubt, check `eq2world.log` for `PrintTarget(cast)` entries on the bot.
