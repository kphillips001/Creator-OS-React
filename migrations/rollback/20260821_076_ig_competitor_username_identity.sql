BEGIN;

UPDATE ig_intelligence.competitors
SET display_name = username
WHERE display_name IS NULL;

ALTER TABLE ig_intelligence.competitors
    ALTER COLUMN display_name SET NOT NULL;

ALTER TABLE ig_intelligence.competitors
    ADD CONSTRAINT ck_ig_competitors_display_name CHECK (BTRIM(display_name) <> '');

COMMENT ON COLUMN ig_intelligence.competitors.display_name IS NULL;

COMMIT;
