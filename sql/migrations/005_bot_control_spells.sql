-- Migration: add 8 universal "bot control" spells so every player gets
-- hotbar-castable abilities for the bot commands.
--
-- Spell IDs reserved in the 2_560_001+ block (well above any standard
-- EQ2 content range, so no collision risk).
--
-- ID         Name              Wraps
-- ---------  ----------------  -------------------
-- 2560001    Bot Prepull       /bot prepull
-- 2560002    Bot Camp All      /bot camp all
-- 2560003    Bot Summon All    /bot summon group
-- 2560011    Bot Spawn 1       /bot spawn 1
-- 2560012    Bot Spawn 2       /bot spawn 2
-- 2560013    Bot Spawn 3       /bot spawn 3
-- 2560014    Bot Spawn 4       /bot spawn 4
-- 2560015    Bot Spawn 5       /bot spawn 5
--
-- The spell rows reference Lua scripts in
-- /eq2emu/eq2emu/server/Spells/Commoner/Bot*.lua. Those Lua files are
-- deployed by scripts/deploy-custom-lua.sh (called from server-up.sh).
--
-- The Lua scripts call the BotCommand(caster, "subcmd args") binding
-- added in server-patches/0011-lua-bot-command-binding.patch — that
-- binding dispatches to Commands::Command_Bot as if the player typed
-- the command. So all permission checks and target validation happen
-- in the existing /bot handler, not duplicated here.
--
-- Apply with:
--   docker exec -i docker-mysql-1 \
--     mariadb -ueq2emu -p"$MARIADB_PASSWORD" eq2emu < FILE

-- UP ----------------------------------------------------------------------

START TRANSACTION;

-- ============================================================================
-- Helper: clean any prior partial run (idempotent re-applies safe).
-- ============================================================================
DELETE FROM spells              WHERE id BETWEEN 2560001 AND 2560015;
DELETE FROM spell_tiers         WHERE spell_id BETWEEN 2560001 AND 2560015;
DELETE FROM spell_classes       WHERE spell_id BETWEEN 2560001 AND 2560015;
DELETE FROM spell_display_effects WHERE spell_id BETWEEN 2560001 AND 2560015;
DELETE FROM starting_spells     WHERE spell_id BETWEEN 2560001 AND 2560015;
DELETE FROM character_spells    WHERE spell_id BETWEEN 2560001 AND 2560015;

-- ============================================================================
-- spells rows.
--   type=2          utility ability (matches Sprint/Forage)
--   cast_type=0     instant cast (one-shot, NOT toggle)
--   target_type=0   self
--   friendly_spell=1
--   spell_book_type=2  abilities tab (matches Sprint)
--   not_maintained=1   no buff icon
--   cast_while_moving=1
--   is_active=1
-- ============================================================================
INSERT INTO spells (id, name, description, type, cast_type, target_type,
    friendly_spell, lua_script, icon, icon_backdrop, cast_while_moving,
    not_maintained, is_active, spell_book_type, success_message, fade_message)
VALUES
  (2560001, 'Bot Prepull',
   'Prime your group mercenaries to lay wards proactively before the pull.',
   2, 0, 0, 1, 'Spells/Commoner/BotPrepull.lua', 408, 317, 1, 1, 1, 2, '', ''),
  (2560002, 'Bot Camp All',
   'Camp every group mercenary you own at once.',
   2, 0, 0, 1, 'Spells/Commoner/BotCampAll.lua', 17, 317, 1, 1, 1, 2, '', ''),
  (2560003, 'Bot Summon All',
   'Summon every group mercenary you own to your location.',
   2, 0, 0, 1, 'Spells/Commoner/BotSummonAll.lua', 230, 317, 1, 1, 1, 2, '', ''),
  (2560011, 'Bot Spawn 1',
   'Spawn the bot in your roster slot 1 (matches /bot list).',
   2, 0, 0, 1, 'Spells/Commoner/BotSpawn1.lua', 218, 317, 1, 1, 1, 2, '', ''),
  (2560012, 'Bot Spawn 2',
   'Spawn the bot in your roster slot 2.',
   2, 0, 0, 1, 'Spells/Commoner/BotSpawn2.lua', 280, 317, 1, 1, 1, 2, '', ''),
  (2560013, 'Bot Spawn 3',
   'Spawn the bot in your roster slot 3.',
   2, 0, 0, 1, 'Spells/Commoner/BotSpawn3.lua', 235, 317, 1, 1, 1, 2, '', ''),
  (2560014, 'Bot Spawn 4',
   'Spawn the bot in your roster slot 4.',
   2, 0, 0, 1, 'Spells/Commoner/BotSpawn4.lua', 184, 317, 1, 1, 1, 2, '', ''),
  (2560015, 'Bot Spawn 5',
   'Spawn the bot in your roster slot 5.',
   2, 0, 0, 1, 'Spells/Commoner/BotSpawn5.lua', 224, 317, 1, 1, 1, 2, '', '');

-- ============================================================================
-- spell_tiers — instant cast, no power cost. Recast scales with risk:
--   prepull / spawn-N have a longer cooldown (30s) since they're prep moves
--   summon all has a 30s cooldown to discourage spamming
--   camp all is 60s — meant to be deliberate
-- ============================================================================
INSERT INTO spell_tiers (spell_id, tier, hp_req, hp_req_percent, hp_upkeep,
    power_req, power_req_percent, power_upkeep, power_by_level, savagery_req,
    savagery_req_percent, savagery_upkeep, dissonance_req, dissonance_req_percent,
    dissonance_upkeep, req_concentration, cast_time, recovery, recast, radius,
    max_aoe_targets, min_range, `range`, duration1, duration2, resistibility,
    hit_bonus, call_frequency, given_by) VALUES
  (2560001, 1, 0,0,0, 0,0,0,0, 0,0,0, 0,0,0, 0, 0, 0,  300, 0, 0, 0, 0, 0, 0, 0, 0, 0, 'class'),
  (2560002, 1, 0,0,0, 0,0,0,0, 0,0,0, 0,0,0, 0, 0, 0,  600, 0, 0, 0, 0, 0, 0, 0, 0, 0, 'class'),
  (2560003, 1, 0,0,0, 0,0,0,0, 0,0,0, 0,0,0, 0, 0, 0,  300, 0, 0, 0, 0, 0, 0, 0, 0, 0, 'class'),
  (2560011, 1, 0,0,0, 0,0,0,0, 0,0,0, 0,0,0, 0, 0, 0,  300, 0, 0, 0, 0, 0, 0, 0, 0, 0, 'class'),
  (2560012, 1, 0,0,0, 0,0,0,0, 0,0,0, 0,0,0, 0, 0, 0,  300, 0, 0, 0, 0, 0, 0, 0, 0, 0, 'class'),
  (2560013, 1, 0,0,0, 0,0,0,0, 0,0,0, 0,0,0, 0, 0, 0,  300, 0, 0, 0, 0, 0, 0, 0, 0, 0, 'class'),
  (2560014, 1, 0,0,0, 0,0,0,0, 0,0,0, 0,0,0, 0, 0, 0,  300, 0, 0, 0, 0, 0, 0, 0, 0, 0, 'class'),
  (2560015, 1, 0,0,0, 0,0,0,0, 0,0,0, 0,0,0, 0, 0, 0,  300, 0, 0, 0, 0, 0, 0, 0, 0, 0, 'class');

-- ============================================================================
-- spell_classes — adventure_class_id=255 means universal (all classes).
-- ============================================================================
INSERT INTO spell_classes (spell_id, adventure_class_id, tradeskill_class_id, level, classic_level) VALUES
  (2560001, 255, 255, 1, 0),
  (2560002, 255, 255, 1, 0),
  (2560003, 255, 255, 1, 0),
  (2560011, 255, 255, 1, 0),
  (2560012, 255, 255, 1, 0),
  (2560013, 255, 255, 1, 0),
  (2560014, 255, 255, 1, 0),
  (2560015, 255, 255, 1, 0);

-- ============================================================================
-- spell_display_effects — tooltip lines.
-- ============================================================================
INSERT INTO spell_display_effects (spell_id, tier, percentage, description, bullet, `index`) VALUES
  (2560001, 1, 100, 'Primes your group bots to lay wards proactively before the pull.', 0, 0),
  (2560002, 1, 100, 'Camps every group mercenary you own.', 0, 0),
  (2560003, 1, 100, 'Summons every group mercenary you own to your location.', 0, 0),
  (2560011, 1, 100, 'Spawns the bot in your roster slot 1.', 0, 0),
  (2560012, 1, 100, 'Spawns the bot in your roster slot 2.', 0, 0),
  (2560013, 1, 100, 'Spawns the bot in your roster slot 3.', 0, 0),
  (2560014, 1, 100, 'Spawns the bot in your roster slot 4.', 0, 0),
  (2560015, 1, 100, 'Spawns the bot in your roster slot 5.', 0, 0);

-- ============================================================================
-- starting_spells — granted to every new character (race_id=255, class_id=255).
-- knowledge_slot = -1 puts them in the unassigned tray (matches Sprint).
-- ============================================================================
INSERT INTO starting_spells (race_id, class_id, spell_id, tier, knowledge_slot) VALUES
  (255, 255, 2560001, 1, -1),
  (255, 255, 2560002, 1, -1),
  (255, 255, 2560003, 1, -1),
  (255, 255, 2560011, 1, -1),
  (255, 255, 2560012, 1, -1),
  (255, 255, 2560013, 1, -1),
  (255, 255, 2560014, 1, -1),
  (255, 255, 2560015, 1, -1);

-- ============================================================================
-- character_spells — backfill for every existing character.
-- knowledge_slot = -1 (unassigned). They'll show up in the abilities tab.
-- ============================================================================
INSERT INTO character_spells (char_id, spell_id, tier, knowledge_slot)
SELECT c.id, s.spell_id, 1, -1
FROM characters c
CROSS JOIN (
    SELECT 2560001 spell_id UNION ALL SELECT 2560002 UNION ALL SELECT 2560003 UNION ALL
    SELECT 2560011         UNION ALL SELECT 2560012 UNION ALL SELECT 2560013 UNION ALL
    SELECT 2560014         UNION ALL SELECT 2560015
) s;

COMMIT;

-- DOWN --------------------------------------------------------------------
-- Cleanly remove every row this migration inserted.
--
-- START TRANSACTION;
-- DELETE FROM character_spells     WHERE spell_id BETWEEN 2560001 AND 2560015;
-- DELETE FROM starting_spells      WHERE spell_id BETWEEN 2560001 AND 2560015;
-- DELETE FROM spell_display_effects WHERE spell_id BETWEEN 2560001 AND 2560015;
-- DELETE FROM spell_classes        WHERE spell_id BETWEEN 2560001 AND 2560015;
-- DELETE FROM spell_tiers          WHERE spell_id BETWEEN 2560001 AND 2560015;
-- DELETE FROM spells               WHERE id BETWEEN 2560001 AND 2560015;
-- COMMIT;
