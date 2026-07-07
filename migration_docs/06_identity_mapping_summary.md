# Telegram Identity Mapping Foundation Summary

## Outcome

The Telegram identity mapping foundation is implemented on the `telegram-migration` branch.

It resolves a stable Telegram user identity to the existing FanvueChatbot canonical identities without creating Telegram-specific memory, buyer intelligence, relationship state, or DecisionEngine behavior:

```text
telegram_user_id
  -> fanvue_account_id
  -> local_fanvue_user_id (fanvue_users.id)
  -> external_fanvue_user_uuid
  -> engine_user_id (fanvue_account_id:local_fanvue_user_id)
```

No Telegram client, listener, sender, authentication runtime, or transport dependency was added.

## Files Created

### Domain models

- `app/models/__init__.py`
- `app/models/telegram_identity.py`

`TelegramIdentityMapping` represents the persisted mapping. `CanonicalTelegramIdentity` is the validated result intended for a future transport adapter. Both use explicit local and external Fanvue identifier names to prevent the existing `fanvue_user_id` ambiguity from crossing the new boundary.

### Repository

- `app/repositories/telegram_identity_repository.py`

`TelegramIdentityRepository` provides:

- lookup by Telegram user ID;
- lookup by canonical local user ID and Fanvue account;
- lookup by mapping ID;
- mapping creation;
- mapping update;
- mapping deactivation.

Repository reads join back to `fanvue_users` using all three canonical values. Creation and update use `INSERT ... SELECT` / `UPDATE ... FROM` so the account ID, local user ID, and external Fanvue UUID must identify the same existing row.

The database connection factory is injectable for isolated testing. Production behavior defaults to the existing `app.database.get_db_connection` helper.

### Service

- `app/services/telegram_identity_service.py`

`TelegramIdentityService` provides:

- Telegram identity resolution;
- canonical identity validation;
- duplicate Telegram-user prevention;
- duplicate canonical-user prevention;
- mapping creation and update;
- inactive mapping rejection;
- mapping deactivation;
- generation of the existing DecisionEngine key format without calling or modifying the DecisionEngine.

Unknown, inactive, duplicate, and invalid mappings are represented by explicit service exceptions. The service never creates a `fanvue_users` row or any intelligence record.

### Database migration

- `migrations/20260619_001_create_telegram_identity_map.sql`

The migration creates `telegram_identity_map` with:

- `id`;
- `telegram_user_id`;
- `telegram_chat_id`;
- `fanvue_account_id`;
- `local_fanvue_user_id`;
- `external_fanvue_user_uuid`;
- `is_active`;
- `created_at`;
- `updated_at`.

The migration is additive and has **not** been applied.

Its safeguards include:

- foreign keys to `fanvue_accounts` and `fanvue_users`;
- one mapping per Telegram user;
- one mapping per canonical account/local-user pair;
- one mapping per canonical account/external-UUID pair;
- positive Telegram user ID and nonzero chat ID validation;
- nonempty external UUID validation;
- a database trigger proving that the account, local user ID, and external UUID belong to the same `fanvue_users` row;
- automatic `updated_at` maintenance;
- active lookup indexes.

The full uniqueness constraints intentionally retain historical ownership after deactivation. An inactive identity must be explicitly updated/reactivated rather than silently replaced by a second mapping.

### Tests

- `app/test_telegram_identity_foundation.py`

The standard-library `unittest` suite uses an in-memory fake repository and does not connect to or mutate the configured database. It covers:

- mapping creation;
- canonical identity resolution;
- duplicate Telegram-user rejection;
- duplicate canonical-user rejection;
- inactive mapping rejection;
- mapping deactivation;
- mapping update.

## Existing Files Modified

None.

The implementation does not modify:

- DecisionEngine;
- MemoryService or memory repositories;
- buyer intelligence services or repositories;
- relationship services or profiles;
- existing Fanvue conversation or commerce behavior;
- Telegram transport or authentication behavior.

## Verification

Focused tests:

```text
.\bot\Scripts\python.exe -m unittest app.test_telegram_identity_foundation -v
Ran 7 tests — OK
```

Syntax verification:

```text
.\bot\Scripts\python.exe -m compileall -q app
Passed
```

`git diff --check` also completed without whitespace errors.

The system Python did not contain the repository's declared `psycopg` dependency, so verification used the existing project virtual environment, which contains `psycopg 3.3.3`. No dependency was installed or changed.

## Future Integration Points

A future Telegram transport task should call the service after update authentication, normalization, and deduplication, but before conversation persistence or DecisionEngine invocation:

```text
Telegram update
  -> authenticate/normalize
  -> deduplicate
  -> TelegramIdentityService.resolve_telegram_identity()
  -> canonical identity result
  -> conversation gateway
  -> existing DecisionEngine
```

The future gateway may consume:

- `telegram_user_id` and `telegram_chat_id` for transport correlation;
- `fanvue_account_id` and `local_fanvue_user_id` for existing intelligence ownership;
- `external_fanvue_user_uuid` for Fanvue commerce correlation;
- `engine_user_id` for the existing DecisionEngine input contract.

Before applying the migration, a separate database-readiness task should:

1. Verify the deployed types and constraints of `fanvue_accounts.id`, `fanvue_users.id`, and `fanvue_users.fanvue_user_uuid`.
2. Confirm that every intended mapping has one existing `fanvue_users` row.
3. Audit the known local-ID/external-UUID ambiguity in buyer and ownership tables.
4. Review the migration against a non-production copy and test upgrade/rollback procedures.
5. Define the verified operator workflow that establishes the Telegram-to-Fanvue user link; usernames must not be used as proof.

No transport integration should bypass the service or send Telegram IDs directly into memory, buyer intelligence, relationship services, conversation intelligence, or the DecisionEngine.

