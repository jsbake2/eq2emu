-- Per-character keymap persistence (paired with 0002-server-keymap-persistence.patch).
-- Stores the opaque OP_KeymapSaveMsg blob so the server can echo it back on
-- OP_KeymapLoadMsg. Upstream stubs the keymap handlers, so without this
-- table+patch every login resets remapped keys to defaults.
CREATE TABLE IF NOT EXISTS character_keymap (
  char_id    INT(10) UNSIGNED NOT NULL,
  data       MEDIUMBLOB       NOT NULL,
  data_size  INT(10) UNSIGNED NOT NULL DEFAULT 0,
  updated_at TIMESTAMP        DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (char_id),
  CONSTRAINT FK_character_keymap FOREIGN KEY (char_id)
    REFERENCES characters (id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=latin1;
