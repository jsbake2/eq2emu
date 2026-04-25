-- Migration: upgrade existing character spellbooks and new-character starter
-- spells from Apprentice (tier 1) to Expert (tier 4), to match the new
-- R_Spells/DefaultSpellGrantTier runtime default.
--
-- Prereqs:
--   * Server binary built with the DefaultSpellGrantTier rule patch, so that
--     spells granted from this point forward also default to tier 4.
--   * Take a DB backup before running (see docs/operations.md once it exists,
--     or run: scripts/backup_db.py).
--
-- Scope:
--   * character_spells: every row at tier 1 is promoted to tier 4 IFF a row
--     for that spell_id exists in spell_tiers at tier 4. Spells with no
--     higher tier are left at tier 1 (matches the in-memory fallback).
--   * starting_spells: same logic, so newly created characters also start
--     at Expert.
--   * Apprentice-only passives (given_by_type SpellScroll, tradeskill spells,
--     etc.) intentionally not touched — this migration is only for the
--     auto-grant path.
--
-- Rollback: see DOWN section at bottom.
--
-- Note: EQ2EMu does not run migrations automatically. Apply with:
--   docker compose exec mysql mysql -uroot -p"$MARIADB_ROOT_PASSWORD" eq2emu \
--     < sql/migrations/001_upgrade_existing_spells_to_expert.sql

-- UP ------------------------------------------------------------------------

START TRANSACTION;

-- Snapshot affected row counts for the operator (visible in mysql CLI output).
SELECT
    (SELECT COUNT(*) FROM character_spells cs
       WHERE cs.tier = 1
         AND EXISTS (SELECT 1 FROM spell_tiers st
                       WHERE st.spell_id = cs.spell_id AND st.tier = 4)) AS character_rows_to_upgrade,
    (SELECT COUNT(*) FROM starting_spells ss
       WHERE ss.tier = 1
         AND EXISTS (SELECT 1 FROM spell_tiers st
                       WHERE st.spell_id = ss.spell_id AND st.tier = 4)) AS starter_rows_to_upgrade;

UPDATE character_spells cs
   JOIN spell_tiers st ON st.spell_id = cs.spell_id AND st.tier = 4
   SET cs.tier = 4
 WHERE cs.tier = 1;

UPDATE starting_spells ss
   JOIN spell_tiers st ON st.spell_id = ss.spell_id AND st.tier = 4
   SET ss.tier = 4
 WHERE ss.tier = 1;

COMMIT;

-- DOWN ----------------------------------------------------------------------
-- Reverses the migration. Only run if you are certain no *legitimate* tier-4
-- grants have happened since the UP was applied — otherwise this will also
-- downgrade spells that the player earned at Expert the normal way. If in
-- doubt, restore from the pre-migration DB backup instead.
--
-- START TRANSACTION;
-- UPDATE character_spells SET tier = 1 WHERE tier = 4;
-- UPDATE starting_spells  SET tier = 1 WHERE tier = 4;
-- COMMIT;
