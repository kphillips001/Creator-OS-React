BEGIN;

ALTER TABLE x_intelligence.competitors
    ADD COLUMN IF NOT EXISTS account_role TEXT NOT NULL DEFAULT 'COMPETITOR';

ALTER TABLE x_intelligence.competitors
    DROP CONSTRAINT IF EXISTS ck_x_intelligence_competitors_account_role,
    ADD CONSTRAINT ck_x_intelligence_competitors_account_role
        CHECK (account_role IN ('COMPETITOR', 'OWN_ACCOUNT'));

CREATE UNIQUE INDEX IF NOT EXISTS uq_x_intelligence_single_own_account
    ON x_intelligence.competitors (account_role)
    WHERE account_role = 'OWN_ACCOUNT';

COMMIT;
