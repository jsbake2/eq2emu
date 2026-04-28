# Mercenary bots — solo group/raid companion

EQ2Emu ships a mercenary-bot system that lets a single player summon AI
companions to form a synthetic group: tank, healer, DPS. This is the
intended path for soloing group dungeons and raid encounters on a
private server with a small playerbase.

The implementation is functional but minimal — see "Known limits"
below. Treat it as a "good enough for friends" tool, not a polished feature.

## What works

- `/bot create <race_id> <gender> <class_id> <name>` — creates a bot
  bound to your character; persisted in the DB so it survives restarts.
  IDs come from `/bot help race` and `/bot help class` (in-game books).
- `/bot list` — shows your bot roster with their bot_id values.
- `/bot spawn <bot_id> 1` — spawns the bot in front of you and
  auto-invites it to your group (the `1` is the auto-invite flag).
- `/bot follow` and `/bot stopfollow` — basic movement when you have a
  bot targeted.
- `/bot attack` — with a hostile mob targeted, makes every bot in your
  group focus that target.
- `/bot maintank` — with another group member targeted, designates them
  as the tank for healing-priority purposes.
- `/bot inv list|give|remove` — the bot has its own inventory; equip it
  through the trade window or `/bot inv give`.
- `/bot settings helm|cloak|taunt|hood` — toggle visuals and taunting.
- `/bot camp` — despawns; spawn again later. State is preserved.
- `/bot delete <bot_id>` — permanent removal.

The bot brain (`source/WorldServer/Bots/BotBrain.cpp`) handles:
- Aggro management — bot follows owner's target in combat.
- Heal logic — checks group-member HP every tick; casts the highest
  available heal when a member drops below threshold.
- Out-of-combat rez and buff casting on group members.
- Movement — moves into melee or spell range as needed.

## Setup recipe (lvl-50 raid group)

1. Create a level-50 character (your main).
2. Create your group:
   ```
   /bot create 9 1 3 Tanken    # Human / male / Guardian (tank)
   /bot create 9 0 13 Healen   # Human / female / Templar (heal)
   /bot create 9 1 24 Damager  # Human / male / Warlock (AoE DPS)
   /bot create 9 0 14 Backup   # Human / female / Inquisitor (backup heal + dps)
   /bot create 9 1 39 Sniper   # Human / male / Ranger (single-target DPS)
   ```
   Race/gender/class IDs come from `/bot help race` and `/bot help class`.
3. Spawn each one with auto-invite to group:
   ```
   /bot list                       # confirm bot_ids
   /bot spawn <id_for_Tanken> 1
   /bot spawn <id_for_Healen> 1
   /bot spawn <id_for_Damager> 1
   /bot spawn <id_for_Backup> 1
   /bot spawn <id_for_Sniper> 1
   ```
4. Designate the tank: target Tanken, then `/bot maintank`.
5. Hand bots gear via `/bot inv give` or trade — pull mastercrafted from
   the `docs/mastercrafted-handouts.html` catalog with `/summonitem`.

To attack: target a mob, then `/bot attack`. Bots will engage their
preferred target and the healer will keep the group up.

## What this branch's patches change

- **HP/power at spawn**: a freshly-spawned bot used to have
  `25 * level + 1` HP — at level 50 that's 1,251 HP, glass cannons even
  for normal mobs. Now matches the formula `Bot::ChangeLevel` uses
  (`level² * 2 + 40` ≈ 5,040 HP at level 50), so summoned bots have
  player-comparable durability immediately.
- **Spell tier**: bots now learn their class spells at the
  `R_Spells/DefaultSpellGrantTier` tier (default 7 = Expert), with
  fallback to Apprentice when the higher tier doesn't exist for a
  given spell. Same rule the player level-up grant honors.

## Known limits

- **No advanced tactics**: BotBrain.cpp is ~200 lines. There's no
  crowd-control, dispel, encounter-mechanic awareness, or interrupt
  handling. The healer heals when HP is low; DPS attacks the target.
  That's it. Raid mechanics like "stack", "spread", "ground AoE
  positioning" need the operator to position bots manually (or just
  brute-force through with HP/healing).
- **Equipment doesn't auto-scale**: bots use whatever gear you put in
  their inventory. They start with nothing.
- **No level-with-owner sync**: bots don't auto-level when their owner
  hits a new level — the operator has to camp and re-spawn (which
  triggers `ChangeLevel`) or use other admin commands. Worth scripting
  if it becomes annoying.
- **No revive after wipe**: if the whole group dies, you camp and
  re-spawn the bots; they don't have a "release/revive" flow yet.
- **Bot help text reads "WIP"** — the in-game help command is a stub.
  This doc is the actual reference.

## Related code

- `source/WorldServer/Bots/Bot.{h,cpp}` — Bot class (extends NPC).
- `source/WorldServer/Bots/BotBrain.{h,cpp}` — combat AI / target select.
- `source/WorldServer/Bots/BotCommands.cpp` — `/bot *` command handlers.
- `source/WorldServer/Bots/BotDB.cpp` — persistence.
- `server-patches/0003-bot-raid-prep.patch` — local raid-viability bumps.
