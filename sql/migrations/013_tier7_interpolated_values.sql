-- Migration: replace tier-1-cloned tier-7 spell_data with proper
-- interpolated Expert-tier values (between tier-5 Adept and tier-9 Master).
--
-- Migration 007 backfilled missing tier-7 rows by cloning tier-1 to
-- prevent nil-param Lua crashes — necessary floor, but ran spells at
-- tier-1 numerical strength when bots cast at tier 7. This migration
-- replaces those cloned values with linear interpolations using the
-- empirical EQ2 tier ratio (Expert sits ~86% of the way from Adept
-- to Master, derived from authentically-authored tier-5/7/9 trios).
--
-- Detection: tier-7.value == tier-1.value AND both tier-5 and tier-9
-- exist for the same (spell_id, index_field) AND tier-5 != tier-1
-- (confirms the spell actually scales). Constants are left alone.
--
-- Touches 43 rows across 19 spells.
--
-- After applying: /reload spells (in-game) or cycle the server.

-- UP ----------------------------------------------------------------------

START TRANSACTION;

UPDATE spell_data SET value = '-10.9853' WHERE id IN (120449);
UPDATE spell_data SET value = '-1648' WHERE id IN (89469);
UPDATE spell_data SET value = '-229' WHERE id IN (120620);
UPDATE spell_data SET value = '-58' WHERE id IN (120476);
UPDATE spell_data SET value = '-648' WHERE id IN (120621);
UPDATE spell_data SET value = '-70' WHERE id IN (120477);
UPDATE spell_data SET value = '1.1571' WHERE id IN (120696);
UPDATE spell_data SET value = '1018' WHERE id IN (120716);
UPDATE spell_data SET value = '117' WHERE id IN (120441);
UPDATE spell_data SET value = '124' WHERE id IN (120482);
UPDATE spell_data SET value = '1246' WHERE id IN (120466);
UPDATE spell_data SET value = '1283' WHERE id IN (120689);
UPDATE spell_data SET value = '135' WHERE id IN (120479);
UPDATE spell_data SET value = '168' WHERE id IN (89468);
UPDATE spell_data SET value = '17' WHERE id IN (97070);
UPDATE spell_data SET value = '194' WHERE id IN (120442);
UPDATE spell_data SET value = '2.1285' WHERE id IN (120483);
UPDATE spell_data SET value = '201.1354' WHERE id IN (120697);
UPDATE spell_data SET value = '216' WHERE id IN (120711);
UPDATE spell_data SET value = '2383' WHERE id IN (120699);
UPDATE spell_data SET value = '252' WHERE id IN (120480);
UPDATE spell_data SET value = '27' WHERE id IN (120445);
UPDATE spell_data SET value = '2969' WHERE id IN (120443);
UPDATE spell_data SET value = '3097' WHERE id IN (120700);
UPDATE spell_data SET value = '31.2417' WHERE id IN (120698);
UPDATE spell_data SET value = '32.0131' WHERE id IN (120464);
UPDATE spell_data SET value = '361' WHERE id IN (120712);
UPDATE spell_data SET value = '37' WHERE id IN (120687);
UPDATE spell_data SET value = '392' WHERE id IN (120709);
UPDATE spell_data SET value = '4' WHERE id IN (120613);
UPDATE spell_data SET value = '4.9412' WHERE id IN (116412);
UPDATE spell_data SET value = '5' WHERE id IN (5478);
UPDATE spell_data SET value = '500' WHERE id IN (120715);
UPDATE spell_data SET value = '55' WHERE id IN (120448);
UPDATE spell_data SET value = '61' WHERE id IN (120688);
UPDATE spell_data SET value = '654' WHERE id IN (120710);
UPDATE spell_data SET value = '67' WHERE id IN (120481);
UPDATE spell_data SET value = '8' WHERE id IN (22525);
UPDATE spell_data SET value = '80.8113' WHERE id IN (120465);
UPDATE spell_data SET value = '82' WHERE id IN (120446);
UPDATE spell_data SET value = '90' WHERE id IN (89467);
UPDATE spell_data SET value = '92' WHERE id IN (75701);
UPDATE spell_data SET value = '944' WHERE id IN (120618);

COMMIT;

-- DOWN --------------------------------------------------------------------
-- Reverts each updated row to the value it had before this migration.
-- Generated as commented SQL — uncomment + run if rolling back.
-- START TRANSACTION;
-- UPDATE spell_data SET value = '-133' WHERE id IN (120620);
-- UPDATE spell_data SET value = '-34' WHERE id IN (120476);
-- UPDATE spell_data SET value = '-378' WHERE id IN (120621);
-- UPDATE spell_data SET value = '-41' WHERE id IN (120477);
-- UPDATE spell_data SET value = '-6.4' WHERE id IN (120449);
-- UPDATE spell_data SET value = '-961' WHERE id IN (89469);
-- UPDATE spell_data SET value = '0.326' WHERE id IN (116412);
-- UPDATE spell_data SET value = '0.7' WHERE id IN (120696);
-- UPDATE spell_data SET value = '1.3' WHERE id IN (120483);
-- UPDATE spell_data SET value = '113' WHERE id IN (120442);
-- UPDATE spell_data SET value = '117.3' WHERE id IN (120697);
-- UPDATE spell_data SET value = '126' WHERE id IN (120711);
-- UPDATE spell_data SET value = '13' WHERE id IN (5478);
-- UPDATE spell_data SET value = '1390' WHERE id IN (120699);
-- UPDATE spell_data SET value = '147' WHERE id IN (120480);
-- UPDATE spell_data SET value = '16' WHERE id IN (120445);
-- UPDATE spell_data SET value = '18.3' WHERE id IN (120698);
-- UPDATE spell_data SET value = '18.7' WHERE id IN (120464);
-- UPDATE spell_data SET value = '1807' WHERE id IN (120700);
-- UPDATE spell_data SET value = '1956' WHERE id IN (120443);
-- UPDATE spell_data SET value = '2' WHERE id IN (120613);
-- UPDATE spell_data SET value = '21' WHERE id IN (120687);
-- UPDATE spell_data SET value = '210' WHERE id IN (120712);
-- UPDATE spell_data SET value = '229' WHERE id IN (120709);
-- UPDATE spell_data SET value = '292' WHERE id IN (120715);
-- UPDATE spell_data SET value = '3' WHERE id IN (97070);
-- UPDATE spell_data SET value = '32' WHERE id IN (120448);
-- UPDATE spell_data SET value = '35' WHERE id IN (120688);
-- UPDATE spell_data SET value = '381' WHERE id IN (120710);
-- UPDATE spell_data SET value = '39' WHERE id IN (120481);
-- UPDATE spell_data SET value = '4' WHERE id IN (22525);
-- UPDATE spell_data SET value = '47.2' WHERE id IN (120465);
-- UPDATE spell_data SET value = '48' WHERE id IN (120446);
-- UPDATE spell_data SET value = '53' WHERE id IN (89467);
-- UPDATE spell_data SET value = '549' WHERE id IN (120618);
-- UPDATE spell_data SET value = '594' WHERE id IN (120716);
-- UPDATE spell_data SET value = '68' WHERE id IN (120441);
-- UPDATE spell_data SET value = '727' WHERE id IN (120466);
-- UPDATE spell_data SET value = '73' WHERE id IN (120482);
-- UPDATE spell_data SET value = '770' WHERE id IN (120689);
-- UPDATE spell_data SET value = '79' WHERE id IN (120479);
-- UPDATE spell_data SET value = '8' WHERE id IN (75701);
-- UPDATE spell_data SET value = '98' WHERE id IN (89468);
-- COMMIT;
