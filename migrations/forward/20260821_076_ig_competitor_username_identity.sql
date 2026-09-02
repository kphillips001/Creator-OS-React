BEGIN;

ALTER TABLE ig_intelligence.competitors
    DROP CONSTRAINT IF EXISTS ck_ig_competitors_display_name;

ALTER TABLE ig_intelligence.competitors
    ALTER COLUMN display_name DROP NOT NULL;

COMMENT ON COLUMN ig_intelligence.competitors.display_name IS
    'Legacy nullable field retained for migration compatibility; IG username is the canonical identity.';

COMMIT;
