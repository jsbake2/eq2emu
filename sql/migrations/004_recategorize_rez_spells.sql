-- Migration: tag resurrection spells as spell_type='Rez' so bots will cast them.
--
-- Why: Bot::GetRezSpell() walks the rez_spells map populated by
-- Bot::GetNewSpells(). Most rez spells in the DB are tagged 'Heal' or
-- 'HoT-Ward' (because they include a heal-portion of the rezzed target)
-- or 'Unset'. Only 5 spells were tagged 'Rez' before this — meaning
-- Templar bots had 1 rez, Fury 2, and most other healer classes had
-- zero. Bots stayed silent over corpses.
--
-- Detection: friendly_spell=1 + target_type IN (5,6) (ENEMY_CORPSE /
-- GROUP_CORPSE — the only target types that can target a dead body)
-- + description contains "Resurrects target".
--
-- Safety: corpse-target spells can't be cast on living members anyway,
-- so retagging them out of heal_spells doesn't lose any heal coverage.
-- They were broken as Heals because GetHealSpell only walks living
-- group members below HP threshold.
--
-- Apply with:
--   docker exec -i docker-mysql-1 \
--     mariadb -ueq2emu -p"$MARIADB_PASSWORD" eq2emu < FILE

-- UP ----------------------------------------------------------------------

START TRANSACTION;

-- Snapshot: rows this run will update.
SELECT
    (SELECT COUNT(DISTINCT s.id)
     FROM spells s
     JOIN spell_display_effects sde ON sde.spell_id = s.id
     WHERE s.friendly_spell = 1
       AND s.target_type IN (5, 6)
       AND sde.description LIKE 'Resurrects target%'
       AND s.spell_type IN ('Unset', 'Heal', 'HoT-Ward', 'Buff')
    ) AS rows_to_retag;

UPDATE spells s
  JOIN (
    SELECT DISTINCT s.id
    FROM spells s
    JOIN spell_display_effects sde ON sde.spell_id = s.id
    WHERE s.friendly_spell = 1
      AND s.target_type IN (5, 6)
      AND sde.description LIKE 'Resurrects target%'
      AND s.spell_type IN ('Unset', 'Heal', 'HoT-Ward', 'Buff')
  ) AS rez_ids ON rez_ids.id = s.id
SET s.spell_type = 'Rez';

COMMIT;

-- DOWN --------------------------------------------------------------------
-- This loses information — once retagged we can't know whether each row
-- was originally Unset / Heal / HoT-Ward / Buff. Restore from backup if
-- you need a true rollback.
--
-- Approximate revert (puts everything back to Unset):
-- START TRANSACTION;
-- UPDATE spells s
--   JOIN (
--     SELECT DISTINCT s.id
--     FROM spells s
--     JOIN spell_display_effects sde ON sde.spell_id = s.id
--     WHERE s.friendly_spell = 1
--       AND s.target_type IN (5, 6)
--       AND sde.description LIKE 'Resurrects target%'
--   ) AS rez_ids ON rez_ids.id = s.id
-- SET s.spell_type = 'Unset'
-- WHERE s.spell_type = 'Rez';
-- COMMIT;
