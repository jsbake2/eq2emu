-- Migration: add aoe_enabled flag to the bots table.
--
-- Backs the in-memory flag added by patch 0015-bot-aoe-toggle-and-aggro-guard.
-- The /bot aoe on|off command updates this column so the choice survives
-- camp + respawn (otherwise GetCombatSpell would re-include AoE spells on
-- every fresh spawn, which defeats the point of the toggle for fights you
-- specifically want single-target only).
--
-- Default 1 = AoE allowed, matches the legacy behavior. /bot aoe off flips
-- it to 0 and the spell-selector skips any spell whose tier has
-- max_aoe_targets > 0 (the "blue circle" PB-AE / auto-AOE spells like
-- Regal Arc, Soul Tide, Poison Breath, etc — 493 such spells in the DB).
--
-- Apply with:
--   docker exec -i docker-eq2emu-server-1 \
--     mariadb -ueq2emu -p"$MARIADB_PASSWORD" eq2emu \
--     < sql/migrations/014_bot_aoe_enabled.sql

-- UP ----------------------------------------------------------------------

ALTER TABLE bots
  ADD COLUMN aoe_enabled TINYINT(1) UNSIGNED NOT NULL DEFAULT 1
  AFTER class;

-- DOWN --------------------------------------------------------------------
-- Reverses the column add. The patch's LoadBot path already tolerates
-- the column being absent (the SELECT is wrapped, falls through silently),
-- so dropping the column won't break older binaries.
--
-- ALTER TABLE bots DROP COLUMN aoe_enabled;
