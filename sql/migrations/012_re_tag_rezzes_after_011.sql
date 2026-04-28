-- Migration: re-tag rez spells that migration 011 incorrectly demoted to Unset.
--
-- Why: migration 011 reverts spell_type to Unset for any bot-AI spell that
-- has no spell_data rows. The rule was meant to exclude broken-Lua spells
-- (Willowskin-style nil-param crashes), but rez spell Lua scripts only
-- take (Caster, Target) — they don't read parameters from spell_data and
-- don't need any. So 011 swept all 25 rez spells back to Unset, which
-- emptied the bot's rez_spells map and broke the rez pipeline:
--
--   bot dies → group member dies → Bot::GetRezSpell() → rez_spells empty →
--   returns null → bot stays silent over corpse.
--
-- Fix: re-tag the same set 003 / 004 caught — corpse-target friendly spells
-- with "Resurrects target" in description — back to Rez. Bypasses the
-- has-spell_data gate because the engine handles rez mechanics in the
-- ::Resurrect path, not in the Lua param surface.
--
-- Apply with:
--   docker exec -i docker-mysql-1 \
--     mariadb -ueq2emu -p"$MARIADB_PASSWORD" eq2emu < FILE
-- After applying: /reload spells (or server cycle) to load updated tags.

-- UP ----------------------------------------------------------------------

START TRANSACTION;

UPDATE spells s
JOIN (
    SELECT DISTINCT s.id
    FROM spells s
    JOIN spell_display_effects sde ON sde.spell_id = s.id
    WHERE s.friendly_spell = 1
      AND s.target_type IN (5, 6)
      AND sde.description LIKE 'Resurrects target%'
      AND s.spell_type = 'Unset'
) AS rez_ids ON rez_ids.id = s.id
SET s.spell_type = 'Rez';

COMMIT;

-- DOWN --------------------------------------------------------------------
-- Pure inverse — reverts the spell_type write back to Unset.
--
-- START TRANSACTION;
-- UPDATE spells s
-- JOIN (
--     SELECT DISTINCT s.id FROM spells s
--     JOIN spell_display_effects sde ON sde.spell_id = s.id
--     WHERE s.friendly_spell = 1 AND s.target_type IN (5, 6)
--       AND sde.description LIKE 'Resurrects target%'
--       AND s.spell_type = 'Rez'
-- ) AS rez_ids ON rez_ids.id = s.id
-- SET s.spell_type = 'Unset';
-- COMMIT;
