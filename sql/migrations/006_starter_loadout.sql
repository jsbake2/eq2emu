-- Migration: enrich the new-character starter loadout for the friends-only
-- private server. Operator-set defaults: 6 big bags, recall item, level-50
-- 5-hour food and drink (5 stacks each), and a starter mount.
--
-- Items chosen:
--   20630   Brewmeister's Backpack            36-slot bag    × 6
--   45462   Call of the Veteran               recall clicky  × 1
--   35993   delectable manticore pie          food, L50, 5hr × 5 stacks of 20
--   36545   Nagafen's Flame                   drink, L50, 5hr × 5 stacks of 20
--   48174   Spirit Steed                      mount clicky   × 1
--
-- Note on bag count: matches Robskin's current loadout (6 Brewmeister's
-- Backpacks). Operator confirmed that's the right count.
--
-- Note on food/drink level: in EQ2 you can consume any tier of food/drink
-- but the buff caps at your level. Picking L50 5-hour items so the loadout
-- stays useful all the way to cap without re-stocking.
--
-- Scope:
--   - starting_items — every NEW character (class_id=255, race_id=255)
--     receives this loadout on first creation. Items are NOT-EQUIPPED
--     so they go into the inventory; player equips bags / consumes food
--     / clicks recall on first login.
--   - Existing characters are NOT backfilled here. Slot assignment is
--     non-trivial without the engine's allocator and ALL existing chars
--     can grab the items themselves with /summonitem. Easy to add a
--     follow-up script if you want a one-shot batch.
--
-- Apply with:
--   docker exec -i docker-mysql-1 \
--     mariadb -ueq2emu -p"$MARIADB_PASSWORD" eq2emu < FILE

-- UP ----------------------------------------------------------------------

START TRANSACTION;

-- ============================================================================
-- 0. Drop the upstream unique index on (class_id, race_id, type, item_id).
--
-- The bot/character spawn code (UpdateStartingItems in WorldDatabase.cpp)
-- iterates starting_items rows and creates one character_items row per
-- starting_items row, so multiple rows with the same item_id ARE supported
-- — the unique constraint is just upstream over-defensiveness. Dropping
-- it lets us grant 6 bags / 5 stacks of food / 5 stacks of drink as
-- separate rows and have the engine create them as separate inventory
-- entries (which is what "stack" means visually).
-- ============================================================================
ALTER TABLE starting_items DROP INDEX IF EXISTS NewIndex;
-- Keep the FK_starting_items index (item_id) for FK perf.

-- ============================================================================
-- 1. starting_items — new-character grants.
-- ============================================================================

-- Clean any prior partial run so this is idempotent.
DELETE FROM starting_items
WHERE class_id = 255 AND race_id = 255
  AND item_id IN (20630, 45462, 35993, 36545, 48174);

-- 6 × Brewmeister's Backpack (36-slot)
INSERT INTO starting_items (class_id, race_id, type, item_id, count) VALUES
  (255, 255, 'NOT-EQUIPPED', 20630, 1),
  (255, 255, 'NOT-EQUIPPED', 20630, 1),
  (255, 255, 'NOT-EQUIPPED', 20630, 1),
  (255, 255, 'NOT-EQUIPPED', 20630, 1),
  (255, 255, 'NOT-EQUIPPED', 20630, 1),
  (255, 255, 'NOT-EQUIPPED', 20630, 1);

-- 1 × Call of the Veteran (recall to a friend)
INSERT INTO starting_items (class_id, race_id, type, item_id, count) VALUES
  (255, 255, 'NOT-EQUIPPED', 45462, 1);

-- 5 stacks × 50 of food (delectable manticore pie, L50, 5hr)
INSERT INTO starting_items (class_id, race_id, type, item_id, count) VALUES
  (255, 255, 'NOT-EQUIPPED', 35993, 20),
  (255, 255, 'NOT-EQUIPPED', 35993, 20),
  (255, 255, 'NOT-EQUIPPED', 35993, 20),
  (255, 255, 'NOT-EQUIPPED', 35993, 20),
  (255, 255, 'NOT-EQUIPPED', 35993, 20);

-- 5 stacks × 50 of drink (Nagafen's Flame, L50, 5hr)
INSERT INTO starting_items (class_id, race_id, type, item_id, count) VALUES
  (255, 255, 'NOT-EQUIPPED', 36545, 20),
  (255, 255, 'NOT-EQUIPPED', 36545, 20),
  (255, 255, 'NOT-EQUIPPED', 36545, 20),
  (255, 255, 'NOT-EQUIPPED', 36545, 20),
  (255, 255, 'NOT-EQUIPPED', 36545, 20);

-- 1 × Spirit Steed (mount clicky)
INSERT INTO starting_items (class_id, race_id, type, item_id, count) VALUES
  (255, 255, 'NOT-EQUIPPED', 48174, 1);

COMMIT;

-- DOWN --------------------------------------------------------------------
-- Reverses the starting_items grant.
--
-- The unique-index drop in section 0 is NOT auto-restored — re-adding it
-- would fail if anyone has added another duplicate-item starter row since.
-- Restore manually if needed:
--     ALTER TABLE starting_items
--       ADD UNIQUE KEY NewIndex (class_id, race_id, `type`, item_id);
--
-- START TRANSACTION;
-- DELETE FROM starting_items
-- WHERE class_id = 255 AND race_id = 255
--   AND item_id IN (20630, 45462, 35993, 36545, 48174);
-- COMMIT;
