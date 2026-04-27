-- Migration: upgrade existing character spellbooks and new-character starter
-- spells to Expert (tier 7) to match the R_Spells/DefaultSpellGrantTier default.
--
-- Tier mapping in this DB (verified against item_details_skill scroll rows):
--   1-4 = Apprentice I through IV  (4 is "Journeyman" in newer naming)
--   5   = Adept / Adept I
--   7   = Expert / Adept III
--   9   = Master / Master I
--
-- Prereqs:
--   * Server binary built with the DefaultSpellGrantTier rule patch so that
--     spells granted from this point forward also default to tier 7.
--   * DB backup before running (e.g. mysqldump character_spells starting_spells).
--
-- Scope:
--   * character_spells: rows at tier 1 OR tier 4 are promoted to tier 7 IFF
--     a row for that spell_id exists in spell_tiers at tier 7. Apprentice-only
--     spells (harvesting, tradeskill verbs, archetype passives — most only
--     have a tier-1 row) are left untouched.
--   * starting_spells: same logic, so newly created characters also start
--     at Expert.
--   * The tier-4 clause catches rows set by an earlier (buggy) version of
--     this migration that wrote tier 4 thinking it was Expert. Re-running the
--     corrected migration is safe and idempotent.
--   * Scroll-scribed, quest-rewarded, and GM-granted tiers are not touched.
--
-- Rollback: see DOWN section at bottom.
--
-- Apply with:
--   docker exec -i docker-eq2emu-server-1 \
--     mysql -h mysql -uroot -p"$MARIADB_ROOT_PASSWORD" eq2emu \
--     < sql/migrations/001_upgrade_existing_spells_to_expert.sql

-- UP ------------------------------------------------------------------------

START TRANSACTION;

-- Snapshot: rows this run will update (visible in mysql CLI output).
SELECT
    (SELECT COUNT(*) FROM character_spells cs
       WHERE cs.tier IN (1, 4)
         AND EXISTS (SELECT 1 FROM spell_tiers st
                       WHERE st.spell_id = cs.spell_id AND st.tier = 7)) AS character_rows_to_upgrade,
    (SELECT COUNT(*) FROM starting_spells ss
       WHERE ss.tier IN (1, 4)
         AND EXISTS (SELECT 1 FROM spell_tiers st
                       WHERE st.spell_id = ss.spell_id AND st.tier = 7)) AS starter_rows_to_upgrade;

UPDATE character_spells cs
   JOIN spell_tiers st ON st.spell_id = cs.spell_id AND st.tier = 7
   SET cs.tier = 7
 WHERE cs.tier IN (1, 4);

UPDATE starting_spells ss
   JOIN spell_tiers st ON st.spell_id = ss.spell_id AND st.tier = 7
   SET ss.tier = 7
 WHERE ss.tier IN (1, 4);

COMMIT;

-- DOWN ----------------------------------------------------------------------
-- Reverses the migration. Only safe if no *legitimately-earned* tier-7 grants
-- have landed since the UP was applied — otherwise this will also downgrade
-- spells the player earned at Expert the normal way. If in doubt, restore
-- from the pre-migration DB backup instead.
--
-- START TRANSACTION;
-- UPDATE character_spells SET tier = 1 WHERE tier = 7;
-- UPDATE starting_spells  SET tier = 1 WHERE tier = 7;
-- COMMIT;
