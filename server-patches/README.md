# Server patches

Local C++ modifications to the upstream EQ2EMu WorldServer/LoginServer source.

## Base

Patches are generated against the upstream repo at:

- URL: `https://github.com/emagi/eq2emu.git`
- Expected base commit: `6651d51071c05093933360ceaee7b99335fe3b2b` (set in `UPSTREAM_BASE`)

The base is a guideline — patches apply with `git apply --3way`, so drift is tolerated until a hunk conflicts.

## Layout

```
server-patches/
├── README.md
├── UPSTREAM_BASE                       # commit SHA the patches were cut against
└── 0001-<short-name>.patch             # ordered patch files, applied in lexical order
```

Paths inside each patch are relative to the upstream repo root (`source/WorldServer/...`).

## Applying

From the host:

```bash
scripts/apply-server-patches.sh
```

This copies the patch set into the running server container, runs `git apply --3way` against
`/eq2emu/eq2emu/source`, and reports which patches were applied / already-applied / conflicted.
Idempotent — safe to re-run.

After patches apply, rebuild:

```bash
docker exec docker-eq2emu-server-1 /eq2emu/compile_source.sh
```

Then hot-swap the binary and let Dawn auto-restart eq2world — see `docs/server-builds.md`.

## Regenerating

If you edit source inside the container, regenerate the patch from the upstream diff:

```bash
docker exec docker-eq2emu-server-1 \
  sh -c 'cd /eq2emu/eq2emu/source && git diff -- <paths>' \
  > server-patches/NNNN-<name>.patch
```

## Current patches

- `0001-default-spell-grant-tier.patch` — adds `R_Spells/DefaultSpellGrantTier` rule (default 7 = Expert)
  and uses it in `Client::AddSendNewSpells` so level-up spell awards grant the higher tier when
  available, falling back to tier 1. Tier mapping: 1-4 = Apprentice I-IV (4 also "Journeyman"),
  5 = Adept, 7 = Expert (Adept III), 9 = Master I.
- `0002-server-keymap-persistence.patch` — persists the client's keymap (key remaps)
  across logins. Upstream stubs the `OP_KeymapLoadMsg` / `OP_KeymapSaveMsg` handlers,
  so every login resets remapped keys to defaults. This patch stores the client's
  opaque save blob in a per-character `character_keymap` table (created by
  `sql/002_character_keymap.sql`), and echoes it back during `SendZoneInfo()` so the
  AoM-era client receives it as part of zone-in. Also handles explicit
  `OP_KeymapLoadMsg` requests for client versions that ask for it.
- `0003-bot-raid-prep.patch` — bumps mercenary-bot HP/power formula at spawn time
  from `25 * level + 1` (lvl-50 bot = 1,251 HP, way too low for a tank role) to
  `level² * 2 + 40` (lvl-50 bot = 5,040 HP, comparable to a player), matching the
  formula already used by `Bot::ChangeLevel`. Also makes bots respect
  `R_Spells/DefaultSpellGrantTier` so their cast tier matches the player default
  (Expert by default, Apprentice fallback when the higher tier doesn't exist).
- `0004-allow-all-expansions.patch` — removes the per-expansion client-version
  gate in `WorldDatabase::GetZoneRequirements`. Upstream blocks zones with
  `expansion_id >= 40` (RoK and beyond) from clients older than RoK's protocol
  version; this friends-only server runs DoF-era v546 clients but wants
  access to RoK / TSO / SF / DoV / CoE content that's already populated in
  the DB. Rendering may be rough for some encounters but the operator chose
  to find out empirically rather than stay locked to EoF.
- `0005-bot-spawn-visibility.patch` — fixes the "ghost healer" bug. When a
  bot is spawned with the auto-invite flag (`/bot spawn <id> 1`), upstream
  calls `ZoneServer::SendSpawn(bot, client)` directly. That function checks
  `IsSendingSpawn(spawn_id)` and silently deletes the packet if the spawn's
  per-client state is not `SPAWN_STATE_SENDING`. Nothing in the bot-spawn
  path sets that state, so the packet is dropped — the bot is fully active
  server-side (heals, attacks land), but the client never receives the
  spawn so it can't render or target the bot. Adds a `Player::SetSpawnMap`
  call immediately before `SendSpawn` to flip the state, matching the
  regular `CheckSendSpawnToClient` flow.
- `0006-bot-follow-smoothing.patch` — fixes the out-of-combat follow yo-yo.
  `BotBrain::Think` used `MaxCombatRange` (4.0) as both the follow trigger
  and the engine's stop distance, causing rapid back-and-forth: chase →
  reach 4 units → stop → player moves 5 units → chase again. Now triggers
  chase only at `3 * MaxCombatRange` (12 units) and sets `m_followDistance`
  to match so `MoveToLocation` doesn't bounce off the inner stop threshold.

  Note: an earlier version of this patch also tried to move `HaltMovement()`
  from the end of `Command_Bot_Spawn` to before `AddSpawn` to address
  spawn-time wandering. That hit a crash because `Entity::HaltMovement`
  unconditionally calls `RunToLocation`, which dereferences `GetZone()` —
  a freshly-allocated bot has no zone yet. That reorder was reverted;
  spawn-time wander remains a known minor issue and would need a
  zone-aware halt or different defensive call to fix safely.
