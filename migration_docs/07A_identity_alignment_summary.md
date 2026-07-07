# Telegram Identity Foundation Alignment Summary

## Outcome

The Telegram identity foundation is aligned with the PostgreSQL schema captured in `fanvue_backup.dump` and validated against disposable PostgreSQL 17 restores.

The work remained limited to identity mapping. No Telegram listener, sender, authentication runtime, DecisionEngine integration, memory behavior, buyer intelligence, or relationship behavior was added or modified.

The configured `fanvue_chatbot` database was not migrated. A final read-only check confirmed that it still has no `public.telegram_identity_map` table.

## Changes Made

### Native schema types

Updated `migrations/20260619_001_create_telegram_identity_map.sql`:

- `fanvue_account_id`: `INTEGER` -> `BIGINT`
- `local_fanvue_user_id`: `INTEGER` -> `BIGINT`
- `external_fanvue_user_uuid`: `TEXT` -> `UUID`

These now match:

- `public.fanvue_accounts.id BIGINT`
- `public.fanvue_users.id BIGINT`
- `public.fanvue_users.fanvue_user_uuid UUID`

The obsolete nonempty-text UUID check was removed because PostgreSQL's UUID type now validates the domain.

### Schema qualification

The forward migration and repository now explicitly reference:

- `public.telegram_identity_map`
- `public.fanvue_accounts`
- `public.fanvue_users`
- schema-qualified trigger functions

This removes reliance on the connection's `search_path`.

### UUID handling

Updated `app/models/telegram_identity.py`:

- Mapping and canonical identity models now expose `uuid.UUID` values.
- Database rows are normalized to `UUID` during model construction.

Updated `app/repositories/telegram_identity_repository.py`:

- Accepts native `UUID` values.
- Uses direct UUID equality for joins, creation, and updates.
- Removed all `::text` UUID comparisons.

Updated `app/services/telegram_identity_service.py`:

- Accepts UUID objects or UUID strings at its boundary.
- Parses and normalizes strings to `uuid.UUID` before repository calls.
- Rejects malformed UUIDs with `InvalidTelegramIdentityError`.
- Validates `is_active` as a real Boolean.

### Exception translation

The repository now converts PostgreSQL write failures into persistence-level exceptions:

- uniqueness violations -> `TelegramIdentityConflictError`
- other integrity violations -> `TelegramIdentityIntegrityError`

The service converts those into domain exceptions:

- `TelegramIdentityConflictError` -> `DuplicateTelegramIdentityError`
- `TelegramIdentityIntegrityError` -> `InvalidTelegramIdentityError`

This covers constraint races that occur after service-level duplicate prechecks and prevents raw PostgreSQL constraint exceptions from reaching future transport callers.

### Rollback support

Created:

- `migrations/20260619_001_drop_telegram_identity_map.sql`

The rollback removes:

- `public.telegram_identity_map`
- `public.set_telegram_identity_updated_at()`
- `public.validate_telegram_identity_canonical_user()`

Dropping the table first removes its triggers. The rollback leaves all pre-existing Fanvue tables and data intact.

### Test improvements

Expanded `app/test_telegram_identity_foundation.py` from 7 to 12 unit tests. Added coverage for:

- UUID parsing and normalization;
- invalid UUID rejection;
- strict Boolean validation;
- repository duplicate-race translation;
- repository integrity-error translation.

Created `app/test_telegram_identity_postgres.py` with seven opt-in PostgreSQL integration tests:

- native schema types;
- create and resolve with PostgreSQL UUID;
- database uniqueness translation;
- simulated duplicate race through the service;
- invalid canonical triple rejection;
- deactivate/reactivate;
- update to another valid canonical user.

Created `app/test_telegram_identity_migration_cycle.py` with an opt-in forward/rollback test that verifies:

- migration application;
- `BIGINT`, `BIGINT`, and `UUID` types;
- rollback removal of the table and functions;
- preservation of `public.fanvue_users`.

The database-backed tests require an explicit `TEST_DATABASE_URL`. They skip safely during ordinary unit runs and cannot accidentally use the configured application database unless a caller deliberately points the test variable there.

## Disposable Database Validation

### Environment

- PostgreSQL service: local PostgreSQL 17
- Backup: `fanvue_backup.dump`
- Dump source version: PostgreSQL 17.4
- Configured application database: `fanvue_chatbot`
- Disposable databases: uniquely named databases created alongside the configured database

### Full repository/service validation

Process:

1. Created `fanvue_identity_alignment_codex_20260619`.
2. Restored `fanvue_backup.dump` with `pg_restore --exit-on-error --no-owner --no-privileges`.
3. Applied the revised forward migration.
4. Ran `app.test_telegram_identity_postgres` with its connection explicitly pointed to the disposable database.
5. Executed the rollback migration.
6. Verified the identity table and both functions were absent.
7. Verified `public.fanvue_users` remained present.
8. Dropped the disposable database.

Result:

```text
7 PostgreSQL integration tests passed
Migration apply passed
Rollback passed
Fanvue schema preservation passed
Disposable database cleanup passed
```

### Reproducible migration-cycle validation

Process:

1. Created a second clean disposable database.
2. Restored the backup.
3. Ran `app.test_telegram_identity_migration_cycle`.
4. The test applied and rolled back the migration itself.
5. Dropped the second disposable database.

Result:

```text
1 migration-cycle test passed
Disposable database cleanup passed
```

### Configured database safety check

After cleanup, a read-only query confirmed:

```text
configured database: fanvue_chatbot
public.telegram_identity_map present: false
```

No migration was applied to the configured application database.

## Verification Summary

Unit tests:

```text
12 tests passed
```

Disposable PostgreSQL integration tests:

```text
7 tests passed
```

Disposable migration-cycle tests:

```text
1 test passed
```

Additional checks:

- Full `app` compilation passed.
- `git diff --check` passed; only line-ending notices were emitted.
- Active branch remained `telegram-migration`.
- No prohibited intelligence or transport file was changed.

## Files Modified

- `app/models/telegram_identity.py`
- `app/repositories/telegram_identity_repository.py`
- `app/services/telegram_identity_service.py`
- `app/test_telegram_identity_foundation.py`
- `migrations/20260619_001_create_telegram_identity_map.sql`

## Files Created

- `app/test_telegram_identity_postgres.py`
- `app/test_telegram_identity_migration_cycle.py`
- `migrations/20260619_001_drop_telegram_identity_map.sql`
- `migration_docs/07A_identity_alignment_summary.md`

## Remaining Risks

1. **Production commerce continuity remains unproven.** The backup's buyer table is empty and its legacy monetization/content rows do not consistently resolve to canonical users. This identity work does not repair those pipelines.
2. **The backup is a snapshot, not the current deployment.** Repeat schema and identity preflight checks against the current target database immediately before a real migration.
3. **No migration ledger exists.** The project still needs an approved procedure for recording migration state, assigning ownership/permissions, and invoking rollback.
4. **Identity linking evidence is not defined.** The owner workflow must prove that a Telegram user and Fanvue user are the same person without username matching.
5. **Canonical reassignment is powerful.** `update_mapping()` can move a Telegram identity to another valid Fanvue user. Future administrative access must restrict and audit this operation.
6. **Inactive mappings retain uniqueness.** Reactivation/update is required; inserting a replacement mapping is intentionally rejected.
7. **No Telegram gateway exists.** The identity service is validated but is not connected to message processing, which is intentional at this phase.

## Readiness

The identity foundation changes requested by the database readiness audit are complete and validated on a disposable restore.

The next task may design the identity-linking and channel-neutral gateway contract, but it should still stop before live Telegram transport until the operator linking workflow and current-database preflight procedure are approved.

