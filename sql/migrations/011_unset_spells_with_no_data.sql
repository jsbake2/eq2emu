-- Migration: revert spell_type to 'Unset' for any bot-AI-eligible spell that
-- has no spell_data rows at all.
--
-- Why: 484 spells across all classes have NO entries in spell_data. Their
-- Lua scripts read parameters via function args — without spell_data those
-- args arrive as nil, the script throws, the cast fails silently, the
-- bot's "is effect on target?" check returns false, and the brain loops
-- recasting forever (same failure mode as Willowskin's nil 'Mit' before
-- migration 007 was applied).
--
-- The recats (003 / 008 / 009 / 010) used spell_display_effects.description
-- to categorize spells — but the descriptions exist independently of
-- spell_data. So spells with descriptions but no spell_data ended up tagged
-- Buff/HoT-Ward/etc. and dropped into the bot's category maps.
--
-- Safer to revert these 484 to Unset until either:
--   (a) spell_data rows get authored for them upstream, or
--   (b) GetNewSpells gets a runtime check that skips spells with no
--       spell_data (cleaner long-term fix, queued separately).
--
-- Apply with:
--   docker exec -i docker-mysql-1 mariadb -ueq2emu -p"$MARIADB_PASSWORD" \
--     eq2emu < FILE

-- UP ----------------------------------------------------------------------

START TRANSACTION;

-- Snapshot count for visibility.
SELECT COUNT(DISTINCT s.id) AS spells_to_unset
FROM spells s
LEFT JOIN (SELECT DISTINCT spell_id FROM spell_data) sd ON sd.spell_id = s.id
WHERE s.spell_type IN ('Buff','HoT-Ward','Heal','Cure','Rez','DD','DoT','Debuff')
  AND sd.spell_id IS NULL;

UPDATE spells s
LEFT JOIN (SELECT DISTINCT spell_id FROM spell_data) sd ON sd.spell_id = s.id
SET s.spell_type = 'Unset'
WHERE s.spell_type IN ('Buff','HoT-Ward','Heal','Cure','Rez','DD','DoT','Debuff')
  AND sd.spell_id IS NULL;

COMMIT;

-- DOWN --------------------------------------------------------------------
-- Reverting requires knowing each spell's prior spell_type — which we lose
-- in this migration. Restore from pre-migration mysqldump if needed.
