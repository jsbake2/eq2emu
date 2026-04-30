-- Migration: recategorize cure spells (spell_type + det_type) so the bot
-- cure logic in patch 0008-bot-cure-logic.patch can actually pick them.
--
-- Bot::GetNewSpells() bins spells by spells.spell_type. Anything tagged
-- 'Unset' falls through and never lands in cure_spells. The det-type-aware
-- selector in Bot::GetCureSpell() also matches on spells.det_type.
--
-- Coverage strategy: hand-target the small set of real cure spells (~15
-- across priest + mage trees + Sarnak racial). Skip:
--   * "Enhance: *" rows — AA enhancements, not castable spells
--   * "Trauma/Noxious/Arcane/Elemental Remedy" rows — those are out-of-combat
--     regen buffs despite the name (descriptions confirm this)
--   * Random "Cure" rows (id 9026 = tradeskill, 2550340 = stub, 2000525 =
--     "Mana Cure" buff that procs)
--   * Pot Cure * potions (consumables, not bot castables)
--
-- det_type values from WorldServer/Entity.h:
--   1 = TRAUMA, 2 = ARCANE, 3 = NOXIOUS, 4 = ELEMENTAL, 5 = CURSE
--   0 = generic / any (the runtime falls back to this when no
--       specific-type cure matches)
--
-- Apply with:
--   docker exec -i docker-mysql-1 \
--     mariadb -ueq2emu -p"$MARIADB_PASSWORD" eq2emu \
--     < sql/migrations/016_recategorize_cure_spells.sql

-- UP ----------------------------------------------------------------------

START TRANSACTION;

-- Specific-type cures (priest core + mage tree)
UPDATE spells SET spell_type = 'Cure', det_type = 1 WHERE id = 120024;  -- Cure Trauma (templar/cleric/inq)
UPDATE spells SET spell_type = 'Cure', det_type = 2 WHERE id = 210006;  -- Cure Magic (mage DPS)
UPDATE spells SET spell_type = 'Cure', det_type = 2 WHERE id = 210019;  -- Cure Arcane (sorcerer base)
UPDATE spells SET spell_type = 'Cure', det_type = 3 WHERE id = 110005;  -- Cure Noxious (priest)
UPDATE spells SET spell_type = 'Cure', det_type = 5 WHERE id = 110004;  -- Cure Curse (priest + chanter)

-- Generic priest "Cure" + Apprentice's Cure — dispels any (any det_type)
UPDATE spells SET spell_type = 'Cure', det_type = 0 WHERE id = 110000;  -- Apprentice's Cure
UPDATE spells SET spell_type = 'Cure', det_type = 0 WHERE id = 110003;  -- Cure (priest generic)

-- Sarnak racial group cure (any det)
UPDATE spells SET spell_type = 'Cure', det_type = 0 WHERE id IN (440072, 440073, 440074);  -- Brood Cure I/II/III

COMMIT;

-- DOWN --------------------------------------------------------------------
-- Reverses every UPDATE above. Safe to run iff no manual edits to these
-- IDs happened since (a re-tag would need to be re-applied).
--
-- START TRANSACTION;
-- UPDATE spells SET spell_type = 'Unset', det_type = 0 WHERE id = 120024;
-- UPDATE spells SET spell_type = 'Unset', det_type = 0 WHERE id = 210006;
-- UPDATE spells SET det_type = 0           WHERE id = 210019;  -- was already 'Cure'
-- UPDATE spells SET det_type = 0           WHERE id = 110005;  -- was already 'Cure'
-- UPDATE spells SET spell_type = 'Unset', det_type = 0 WHERE id = 110004;
-- UPDATE spells SET spell_type = 'Unset', det_type = 0 WHERE id IN (110000, 110003);
-- UPDATE spells SET spell_type = 'Unset', det_type = 0 WHERE id IN (440072, 440073, 440074);
-- COMMIT;
