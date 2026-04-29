# Session state — pick up where we left off

Last updated: **2026-04-29** (post-cleanup push).

This is the running notebook for active development. PROJECT.md owns the
strategy; this file owns "what's actually in flight right now." Update at
the end of each session so future-you (and Claude) can resume cold.

## Quick start

```bash
./scripts/server-up.sh        # bring stack up + apply patches + redeploy lua
./scripts/server-down.sh      # clean shutdown (data persists)

# Auto-start on host reboot (already installed):
sudo systemctl start eq2emu   # bring stack up via the unit
sudo systemctl status eq2emu  # see start/stop output
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
/reload spawnscripts          # reload SpawnScripts after editing custom lua
/cancel_maintained            # popup to right-click maintained-spell removal
/bot list                     # show your bot roster + slot ids
/bot spawn <slot> 1           # spawn + auto-invite to group
/bot summon group             # bring all group bots to you
/bot camp <slot>              # camp by slot id (post-#33 fix)
/bot camp all                 # camp every group bot you own
/bot prepull                  # prime bots to lay wards proactively
```

Apply the canonical character template to a new char:

```bash
./scripts/apply-character-template.sh <character_name> [--no-admin]
```

## Live system state

The container source has the full patch stack applied. All 14 patches
(0012 was retired, 0014 supersedes it) are now committed to `main` or in
open PRs awaiting merge.

| Patch | What | Status |
|---|---|---:|
| 0001 | DefaultSpellGrantTier rule (Expert) | merged |
| 0002 | Keymap persistence | merged |
| 0003 | Bot HP/power formula | merged |
| 0004 | Allow all expansions | merged |
| 0005 | Bot spawn visibility (ghost healer) | merged |
| 0006 | Bot follow smoothing | merged |
| 0007 | Bot followups (X2/Y2/Z2 spawn init, owner-as-target, mana regen, no chat spam) | merged |
| 0009 | Bot spell-chain dedup | merged |
| 0010-buff | Buff duration filter | merged |
| 0010-prepull | /bot prepull + /bot camp [id\|all] | merged |
| 0011-grpae | Group-AE fanout for bot casts | merged |
| 0011-lua | Lua BotCommand binding | merged |
| 0013 | Bot friendly-fire block | merged |
| 0014 | /bot summon runoff fix + /bot camp slot-id regression | **PR #33** open |

DB migrations applied to live (all merged):

| File | Effect |
|---|---|
| sql/migrations/001 | Existing chars promoted to Expert tier |
| sql/migrations/003 | Recategorize priest spells (785 spells) |
| sql/migrations/004 | Tag rez spells (25 spells) |
| sql/migrations/005 | Bot-control spell pack (8 universal hotbar abilities) |
| sql/migrations/006 | Starter loadout (6 backpacks + 5×food + 5×drink) |
| sql/migrations/007 | Tier-7 spell_data backfill (clones tier-1) |
| sql/migrations/008 | Recategorize mage spells (419 spells) |
| sql/migrations/009 | Recategorize scout spells (346 spells) |
| sql/migrations/010 | Recategorize fighter spells (446 spells) |
| sql/migrations/011 | Revert no-data spells back to Unset (514 spells; safety) |
| sql/migrations/012 | Re-tag rezzes that 011 over-demoted (25 spells) |
| sql/migrations/013 | Tier-7 interpolation (43 rows interpolated) |

> **Note:** there is no `migrations/002`. The `character_keymap` table is
> created/used by patch 0002 directly; an explicit migration was never
> written. If a fresh install ever fails on missing `character_keymap`,
> add a `CREATE TABLE character_keymap (char_id, data MEDIUMBLOB, ...)`
> migration.

Plus content captured in PRs (no longer ad-hoc):
- 315 mount Lua scripts (row id → appearance_id translation) — **PR #37**
- Garveninvisiblecube override (skip 4-slot small bag grant) — **PR #34**
- Character UI/hotkeys/macros template + apply script — **PR #35**

## Open PRs (5 — current cleanup batch)

| # | Title | Notes |
|---:|---|---|
| **33** | fix(bots): /bot summon runoff + /bot camp slot regression | Patch 0014; supersedes 0012 (deleted) |
| **34** | content: skip 4-slot 'small bag' on Isle of Refuge | Lua override + extends `deploy-custom-lua.sh` for `lua/SpawnScripts/` |
| **35** | feat: apply-character-template.sh + canonical Default template | Per-host onboarding tool for new characters |
| **36** | docs: client-bundle.md | Operator runbook for handing the EQ2 client to friends |
| **37** | content: capture 315 mount Lua scripts | Persists previously-ad-hoc fixes into git |

Drafts still parked:

| # | Title | Notes |
|---:|---|---|
| **21** | DRAFT — bot cure logic | Wired but parked until in-game cure-need testing |
| **22** | DRAFT — Ollama bot personalities | Design + persona library only, no code |

## Recently validated in-game (works)

- ✅ Bot recat populates spell maps (defiler/inquisitor cast wards/buffs in idle)
- ✅ Group-AE fanout: Coercer's Breeze etc. land on the whole group
- ✅ Bot rez (after migration 012 re-tag): Inquisitor / Fury / Defiler etc. cast Resurrects-target spells on group corpses
- ✅ `/bot camp <slot>` (post-PR #33 fix), `/bot camp all`
- ✅ `/bot inv give` (target bot, opens trade window)
- ✅ Bot-control hotbar spells dispatch correctly
- ✅ Tier-7 interpolation
- ✅ Friendly-fire block
- ✅ `/bot summon group` no longer animates run-off (PR #33)
- ✅ Character template apply (`scripts/apply-character-template.sh`) — Default + Derfan tested

## Open questions / known issues / parked

- **Mount visuals don't render** — even with PR #37 capturing the 315 row-id→appearance_id translations, the v546 client still doesn't render most mount appearances. Speed bonus + sub-stats apply. **Parked.** Spirit Steed dropped from starter loadout; users can `/summonitem` and live without the visual.
- **Vigor / Vim** — different stat profiles (Vigor=MaxPower, Vim=STA+INT). User accepted "option A" (cast both). If chat clutter becomes annoying, build a curated `bot_spell_replacements` table.
- **Bot prepull chat message visibility** — works (bot reacts), but the "Primed on N bot(s)" message lands on a tab the user wasn't watching. Could move to a more visible channel.
- **Templar low-level rez gating** — Templars don't get a rez until level 8 (Revive); Battle's Reprieve at 22; Resurrect at 50. Bots inherit owner's level so a level-7 owner's Templar bot has no rez. Not a bug — confirmed in spell_classes data.

## Next features to build (when you want to pick up)

1. **Healer-mode toggle** (`/bot mode <id> debuff|dps`) — discussed and approved. Per-bot flag in `bots` table; `Bot::GetCombatSpell` priority change.
2. **Cure logic out of draft (#21)** — already wired; needs in-game cure-need test.
3. **Healer-mode for buffs in combat** — short-duration buffs (filter currently skips in idle) should fire during combat. Worth verifying.
4. **Spell-chain `bot_spell_replacements` table** — curated list of "X replaces Y" for cases like Vigor/Vim where the data doesn't link them.
5. **Tier-7 interpolation expansion** — current run only catches 43 rows. If upstream content gets more tier coverage, re-run `scripts/interpolate-tier7-spell-data.py`.
6. **Ollama bot personalities** (PR #22) — design is in `docs/bot-personalities/`, hand off to a real implementation when bot AI is settled.
7. **Mount visual debug** — instrument the spawn-appearance packet to confirm `mount_type` field reaches the v546 client correctly.
8. **Migration 002 (CREATE TABLE character_keymap)** — write it so a clean re-install doesn't depend on the table existing already.

## Recent context / decisions

- **Stacked-PR drag-along** — when PRs target a parent feature branch instead of `main`, merging the parent doesn't bring child commits with it; merging a child also drags unrelated parent files into `main`. Fixed by always targeting `main`. Symptom we hit: merging the data PRs in this round dragged `0010-bot-prepull-and-camp-by-id.patch` onto `main` early, which made later PR #24 a near no-op merge.
- **Patch number collisions** — multiple patches sharing a number prefix (e.g. `0010-bot-buff-duration-filter.patch` + `0010-bot-prepull-and-camp-by-id.patch`) sort and apply alphabetically and don't conflict in git. Treat the number as a "stage" not a unique id; suffixes do the disambiguation.
- **`pkill -x` not `pkill -f`** in `server-up.sh` hot-swap — `-f` matches the cmdline of the heredoc shell itself. Always `-x eq2world`.
- **EQ2Emu DB has separate `id` and `appearance_id` columns** — runtime mount/appearance protocol uses `appearance_id`. Most upstream Lua scripts pass `id`. Fix is at the data layer (PR #37 captures 315 of these translations).
- **v546 client (DoF era)** — only renders appearance_ids with `min_client_version <= 546`. Mounts added in EoF/RoK+ don't have models in this client; fall back to basic horse / ghost horse / palomino thematically.
- **Tier-7 ratio = 0.857** — derived empirically from authentic tier-5/7/9 trios. Used for interpolation in migration 013.
- **Slot-id vs runtime spawn-id** — `/bot delete`, `/bot follow`, `/bot stopfollow` all use `SpawnedBots[index]` to translate slot → runtime spawn id. `/bot camp` was the odd one out, using `GetSpawnByID` directly. Worked early on by coincidence (fresh zone IDs ≈ slot numbers); broke after restart. Fixed in PR #33.
- **`docker compose down -v` doesn't wipe everything** — the mysql service uses a bind mount (`./data:/var/lib/mysql`), not a named volume, so `-v` does NOT delete the DB. Only the anonymous binary volume gets reset. Don't trust the doc claim of "wipes DB."
- **Cadence push** — operator called out that fixes were piling up on the live binary without making it back into PRs. Cleanup batch (#33–#37) closes the gap.
