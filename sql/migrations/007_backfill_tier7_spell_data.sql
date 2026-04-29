-- Migration: backfill missing tier-7 spell_data rows by cloning tier-1.
--
-- Why: DefaultSpellGrantTier=7 (Expert) — bots receive their class spells
-- at tier 7. spell_data rows hold the parameters Lua scripts read via
-- function args (Stat, Mit, etc.). 89 buff/heal/ward spells have no
-- tier-7 spell_data at all and 6 are partial — when the bot tries to
-- cast at tier 7, the Lua script gets nil parameters, throws an
-- arithmetic error, and the cast effect never lands. The bot's
-- brain sees no effect on target and immediately re-casts → infinite
-- spam loop visible in /g chat ("Willowskin", "Courage", etc.).
--
-- Hits in eq2world.log:
--   16:38:46 E LUA : Error running function 'cast' in Willowskin:
--       Spells/Priest/Druid/Willowskin.lua:22: attempt to perform
--       arithmetic on a nil value (local 'Mit')
--
-- Fix: clone tier-1 rows for any spell missing tier-7 data. The bot
-- still casts AT tier 7 (so all the spell-engine logic that gates on
-- tier works correctly), but with tier-1 numerical values feeding the
-- Lua parameters. Effects are weaker than they "should" be at Expert
-- tier, but they don't crash, and bots use them at all.
--
-- Long-term: the upstream content needs proper tier-7 values per spell
-- (interpolation between tier-5 and tier-9 would be ideal). This
-- migration is a no-crash floor.
--
-- After applying, run `/reload spells` in-game (or cycle the server)
-- to load the new rows into memory.

-- UP ----------------------------------------------------------------------

START TRANSACTION;

-- 1. Spells with NO tier-7 data at all → clone all tier-1 rows.
INSERT INTO spell_data (spell_id, tier, index_field, value_type, value, value2, dynamic_helper)
SELECT sd.spell_id, 7, sd.index_field, sd.value_type, sd.value, sd.value2, sd.dynamic_helper
FROM spell_data sd
JOIN spells s ON s.id = sd.spell_id
WHERE sd.tier = 1
  AND s.spell_type IN ('Buff','HoT-Ward','Heal','Cure','Rez','DD','DoT','Debuff')
  AND NOT EXISTS (SELECT 1 FROM spell_data sd2 WHERE sd2.spell_id = sd.spell_id AND sd2.tier = 7);

-- 2. Spells with PARTIAL tier-7 data → fill in just the missing index_field
-- rows from tier-1.
INSERT INTO spell_data (spell_id, tier, index_field, value_type, value, value2, dynamic_helper)
SELECT sd.spell_id, 7, sd.index_field, sd.value_type, sd.value, sd.value2, sd.dynamic_helper
FROM spell_data sd
JOIN spells s ON s.id = sd.spell_id
WHERE sd.tier = 1
  AND s.spell_type IN ('Buff','HoT-Ward','Heal','Cure','Rez','DD','DoT','Debuff')
  AND EXISTS (SELECT 1 FROM spell_data WHERE spell_id = sd.spell_id AND tier = 7)
  AND NOT EXISTS (
      SELECT 1 FROM spell_data sd2
      WHERE sd2.spell_id = sd.spell_id
        AND sd2.tier = 7
        AND sd2.index_field = sd.index_field
  );

COMMIT;

-- DOWN --------------------------------------------------------------------
-- Rollback removes ONLY the rows this migration added — i.e. tier-7 rows
-- that have an exact value-match in the same spell's tier-1 row. Genuine
-- hand-set tier-7 rows that happen to match tier-1 by coincidence are at
-- risk; if you've added real Expert-tier balancing in spell_data after
-- this migration ran, restore from backup instead.
--
-- START TRANSACTION;
-- DELETE sd FROM spell_data sd
-- JOIN spell_data sd1 ON sd1.spell_id = sd.spell_id AND sd1.tier = 1
--   AND sd1.index_field = sd.index_field
--   AND sd1.value = sd.value AND sd1.value2 = sd.value2
--   AND sd1.value_type = sd.value_type
-- WHERE sd.tier = 7;
-- COMMIT;
