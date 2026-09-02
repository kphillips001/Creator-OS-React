BEGIN;
DROP INDEX IF EXISTS x_intelligence.uq_x_intelligence_single_own_account;
ALTER TABLE x_intelligence.competitors DROP COLUMN IF EXISTS account_role;
COMMIT;
