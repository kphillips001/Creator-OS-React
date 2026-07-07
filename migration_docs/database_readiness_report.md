# Telegram Identity Mapping Database Readiness Report

**Audit source:** `fanvue_backup.dump`  
**Backup timestamp:** May 20, 2026  
**Backup format:** PostgreSQL 17.4 custom archive, dump format 1.16  
**Audit method:** Read-only `pg_restore --list`, schema extraction, and in-memory parsing of selected archive data  
**Database changes:** None

## 1. Executive Summary

**Readiness determination: READY WITH CHANGES.**

The identity foundation is architecturally aligned with the database, but the migration should not be applied and the repository should not be integrated in its current form.

The backup confirms the core identity assumptions:

- `fanvue_accounts.id` is the creator/account primary key.
- `fanvue_users.id` is the local fan primary key.
- `fanvue_users.fanvue_account_id` scopes the local fan to a Fanvue account.
- `(fanvue_account_id, fanvue_user_uuid)` is database-enforced unique.
- `user_memory.fanvue_user_id` contains the local `fanvue_users.id` serialized as text in all archived memory rows.
- Canonical chat threads and messages use local `fanvue_users.id` foreign keys.

The proposed mapping correctly preserves these two identities:

```text
Canonical intelligence identity:
    fanvue_account_id + fanvue_users.id

Canonical commerce identity:
    fanvue_account_id + fanvue_users.fanvue_user_uuid
```

However, the proposed migration does not match the archived column types:

- `fanvue_accounts.id` is `BIGINT`, but `telegram_identity_map.fanvue_account_id` is declared `INTEGER`.
- `fanvue_users.id` is `BIGINT`, but `local_fanvue_user_id` is declared `INTEGER`.
- `fanvue_users.fanvue_user_uuid` is native PostgreSQL `UUID`, but `external_fanvue_user_uuid` is declared `TEXT`.

The first two are narrowing mismatches and should be corrected to `BIGINT`. PostgreSQL may support integer/bigint foreign-key comparison through compatible operators, but that is not a sufficient reason to preserve a smaller domain. The UUID field should use `UUID` to preserve database validation and eliminate repeated text casts and case-format sensitivity.

The archived data strongly validates the local intelligence identity but does **not** validate the complete commerce linkage. The backup contains no `buyer_intelligence` rows. Its monetization-event rows do not resolve to the archived account/user records, and `content_usage_log` contains mixed identity values. Those findings appear to reflect test or legacy data, but they prevent this backup from proving Telegram-to-Fanvue purchase continuity.

Before integration, the migration and repository/service error contracts should be revised, then tested against a disposable PostgreSQL database restored from the backup. No Telegram transport task should begin yet.

## 2. Schema Validation

### 2.1 `fanvue_accounts`

| Property | Archived schema |
|---|---|
| Table | `public.fanvue_accounts` |
| Primary key | `id BIGINT` |
| Sequence/default | `fanvue_accounts_id_seq` |
| Fanvue creator identity | `fanvue_creator_uuid UUID` |
| Additional account identity | `fanvue_user_uuid TEXT`, `fanvue_identity JSONB` |
| Active state | `is_active BOOLEAN` |
| Account rows in backup | 2 |

`fanvue_accounts.id` is the correct account scope for Ava's intelligence, persona, content, users, and commerce configuration. The schema contains two account rows even though the current migration target is one creator. This does not invalidate the mapping, but the future operator workflow must select and lock the correct Ava account rather than assume a hard-coded row number without verification.

### 2.2 `fanvue_users`

| Property | Archived schema |
|---|---|
| Table | `public.fanvue_users` |
| Primary key | `id BIGINT` |
| External fan identity | `fanvue_user_uuid UUID NOT NULL` |
| Account scope | `fanvue_account_id BIGINT NOT NULL` |
| Account foreign key | `fanvue_account_id -> fanvue_accounts.id ON DELETE CASCADE` |
| External identity uniqueness | `UNIQUE (fanvue_account_id, fanvue_user_uuid)` |
| Relationship fields | `relationship_status`, `is_subscriber`, `is_follower`, lifecycle timestamps |
| Buyer summary fields | `total_spend`, `purchase_count`, `buyer_tier` |
| Rows in backup | 3 across 2 accounts |

The backup contains no user whose `fanvue_account_id` is orphaned, no null external UUID, and no duplicate account/UUID pair. Archived local IDs range from 3 to 7213.

The schema does not declare a composite uniqueness constraint on `(id, fanvue_account_id, fanvue_user_uuid)`. The proposed migration's validation trigger is therefore a reasonable way to prove that all three supplied identifiers belong to the same row without modifying `fanvue_users`.

### 2.3 `user_memory`

| Property | Archived schema |
|---|---|
| Primary key | `id BIGINT` |
| User identifier | `fanvue_user_id TEXT NOT NULL` |
| Account identifier | `fanvue_account_id BIGINT NOT NULL` |
| Account foreign key | `fanvue_account_id -> fanvue_accounts.id ON DELETE CASCADE` |
| Unique constraints | `(fanvue_account_id, fanvue_user_id)` and global `fanvue_user_id` |
| Direct user foreign key | None |
| Rows in backup | 3 |

All three archived memory identifiers are numeric text, and all three match `fanvue_users.id` within the same account. No duplicate account/user pair and no orphaned memory row were observed.

This is direct data evidence that the intelligence identity is `fanvue_account_id + local fanvue_users.id`, with the local ID stringified only because of the legacy memory column type.

### 2.4 Conversations

`chat_threads.fanvue_user_id` and `chat_messages.fanvue_user_id` are `BIGINT` foreign keys to `fanvue_users.id`. Both tables also carry `fanvue_account_id BIGINT` with account foreign keys.

The archive contains:

- 2 canonical chat threads; both match a local user under the same account.
- 765 canonical chat messages; all match a local user under the same account.

This independently confirms that conversation ownership uses the local user ID rather than the external Fanvue UUID.

### 2.5 Buyer, ownership, and monetization schema

| Table | Account type | User type | Archived rows | Observation |
|---|---|---|---:|---|
| `buyer_intelligence` | `BIGINT` | `TEXT` | 0 | Unique account/user constraint exists, but no data validates its identifier domain |
| `content_usage_log` | `INTEGER` | `TEXT` plus optional `fanvue_user_uuid TEXT` | 12 | Mixed/legacy identifiers; only one `fanvue_user_id` matches a canonical local user |
| `fanvue_monetization_events` | `TEXT` | `TEXT`, optional `local_user_id INTEGER` | 17 | Archived account/user values do not resolve to current canonical account/user rows |

The content usage rows include nine numeric `fanvue_user_id` values, two null values, and one other-format value. Only one account/user pair resolves to an archived canonical local user. None of the optional `fanvue_user_uuid` values resolves to an archived external user UUID.

All 17 monetization rows have nonnumeric account identifiers, no populated `local_user_id`, and no `fanvue_user_id` matching an archived external Fanvue UUID. These appear to be synthetic or legacy records, but the archive alone cannot establish that interpretation as fact.

The foundation's explicit local and external identity fields are therefore necessary, but the existing commerce tables cannot be treated as evidence that end-to-end purchase attribution is already correct.

### 2.6 Table-name and object conflicts

The archive contains no `telegram_identity_map` table and no functions or triggers named:

- `validate_telegram_identity_canonical_user`
- `telegram_identity_canonical_user_guard`
- `set_telegram_identity_updated_at`
- `telegram_identity_updated_at`

No direct naming collision was found in the backup.

## 3. Identity Validation

### 3.1 Canonical intelligence identity

**Validated.**

The following independent evidence supports `fanvue_account_id + fanvue_users.id`:

1. `fanvue_users.id` is the local primary key.
2. `user_memory` stores that local ID as text and scopes it by account.
3. Every archived memory row resolves to a local user in the same account.
4. Chat threads and messages use local user foreign keys.
5. Every archived canonical chat row resolves correctly.
6. The existing DecisionEngine key serializes the same pair.

Although local `fanvue_users.id` is globally unique in PostgreSQL, retaining `fanvue_account_id` is still correct. It enforces creator scope in application contracts and prevents accidental cross-account resolution.

### 3.2 Canonical commerce identity

**Schema-validated; data continuity not proven.**

`fanvue_users.fanvue_user_uuid` is a native UUID, is required, and is unique within the Fanvue account. That makes `(fanvue_account_id, fanvue_user_uuid)` the correct external Fanvue fan identity.

However, the backup's buyer and monetization data do not demonstrate a working flow from commerce event to that UUID and then to `fanvue_users.id`:

- `buyer_intelligence` has no rows.
- Archived monetization events use values that do not match the canonical account/user records.
- Archived content usage contains mixed identity values.

The mapping table can safely store the correct external UUID, but it cannot repair those pre-existing pipelines by itself. A verified link must be populated from `fanvue_users`, not inferred from legacy commerce-table values.

### 3.3 Telegram mapping invariant

The proposed three-part mapping is correct:

```text
telegram_user_id
  -> fanvue_account_id
  -> local_fanvue_user_id
  -> external_fanvue_user_uuid
```

The repository's triple-match join and migration trigger appropriately require all Fanvue values to point to one existing `fanvue_users` row. Telegram usernames and Fanvue usernames are not used, which avoids mutable-name identity merges.

## 4. Migration Review

### 4.1 Field compatibility

| Proposed field | Proposed type | Actual referenced type | Assessment |
|---|---|---|---|
| `id` | `BIGSERIAL` | New local key | Compatible |
| `telegram_user_id` | `BIGINT` | Telegram numeric ID | Compatible |
| `telegram_chat_id` | `BIGINT` | Telegram chat ID, including negative values | Compatible |
| `fanvue_account_id` | `INTEGER` | `fanvue_accounts.id BIGINT` | **Change to BIGINT** |
| `local_fanvue_user_id` | `INTEGER` | `fanvue_users.id BIGINT` | **Change to BIGINT** |
| `external_fanvue_user_uuid` | `TEXT` | `fanvue_users.fanvue_user_uuid UUID` | **Prefer UUID and direct comparison** |
| `is_active` | `BOOLEAN` | New mapping state | Compatible |
| timestamps | `TIMESTAMPTZ` | New audit timestamps | Compatible |

The current integer fields can represent the archived IDs, but that is not the compatibility standard. They should preserve the referenced domains exactly.

### 4.2 Foreign keys

The referenced tables and keys exist. `ON DELETE RESTRICT` is a defensible safety choice: deleting a mapped Fanvue account/user should require first resolving the Telegram mapping instead of silently cascading it.

The local-user foreign key proves only `local_fanvue_user_id -> fanvue_users.id`. The validation trigger correctly adds account/UUID consistency. If the UUID column is changed to native `UUID`, the trigger and repository joins should compare UUID values directly rather than cast the database column to text.

All table, function, trigger, and sequence references should be schema-qualified with `public.` or the intended deployment schema. The current script relies on the executing session's `search_path`, while the archived database objects live in `public`.

### 4.3 Uniqueness

The constraints correctly prevent:

- one Telegram user from mapping to multiple canonical users;
- one local canonical user from mapping to multiple Telegram users;
- one external commerce identity from mapping to multiple Telegram users.

They apply to inactive rows as well. This deliberately preserves historical ownership and requires update/reactivation instead of inserting a replacement row. That policy is safe if intentional and should be documented in the operator workflow.

### 4.4 Indexes

The uniqueness constraints already create indexes that support exact Telegram-user and account/local-user lookups, including queries filtered by `is_active`. The two additional partial active indexes are likely redundant for the expected one-row lookup pattern. They are not incompatible, but they add write and maintenance cost without a demonstrated query-plan benefit.

### 4.5 Triggers

The canonical-user guard is logically correct and closes a real integrity gap that separate foreign keys cannot close. The `updated_at` trigger is also appropriate.

Required changes:

- use the actual `BIGINT` and `UUID` domains;
- schema-qualify the function and table references;
- verify trigger/function creation and error behavior on PostgreSQL 17 using a disposable restored copy.

### 4.6 Rollback and migration operations

The script is transactional, which is good. It does not include or pair with a rollback migration. A rollback must explicitly remove triggers/functions and then the table in dependency-safe order.

The repository has no established migration framework or migration ledger. Before applying any SQL, the project must define:

- how applied migrations are recorded;
- how preflight checks are run;
- how rollback is invoked;
- which database role owns the table and functions;
- what runtime role receives `SELECT`, `INSERT`, and `UPDATE` privileges.

## 5. Repository Review

### Compatible behavior

- Queries resolve Telegram users through all three canonical Fanvue values.
- `create_mapping()` uses `INSERT ... SELECT` from `fanvue_users`, preventing creation against a nonexistent or mismatched canonical row.
- `update_mapping()` repeats the triple validation.
- Lookups default to active mappings and can include inactive mappings for administrative behavior.
- Reverse lookup is scoped by account and local user ID.
- Parameter binding is used for all identity values.
- The existing connection context handles commit and rollback.

### Required changes before integration

1. **Match native UUID semantics.** If the migration uses `UUID`, remove `::text` joins and bind/normalize UUID values explicitly. The current text comparison is case-sensitive against PostgreSQL's canonical lowercase UUID text representation.
2. **Schema-qualify tables.** Use `public.telegram_identity_map` and `public.fanvue_users`, or an explicitly configured schema.
3. **Normalize duplicate exceptions.** Service prechecks are race-prone. The database constraints still prevent duplicates, but concurrent inserts can raise raw `psycopg` unique violations instead of `DuplicateTelegramIdentityError`.
4. **Add database-backed repository tests.** Current tests use a fake repository and do not exercise PostgreSQL types, constraints, joins, triggers, transaction rollback, or concurrent uniqueness.

### Nonblocking observations

- `deactivate_mapping()` intentionally does not join `fanvue_users`; this permits deactivating a mapping even if canonical data has become inconsistent. That is operationally useful.
- Updating a mapping can reassign it to another canonical user. This is powerful and should be restricted to an audited operator workflow.
- No created/updated-by or linking-evidence fields exist. They were not required for the minimal foundation, but the manual linking procedure should retain equivalent audit evidence somewhere before production use.

## 6. Service Review

### Compatible behavior

- Returns the exact validated identity contract needed by a future gateway.
- Generates the existing engine key without invoking or changing the DecisionEngine.
- Rejects unknown and inactive Telegram identities.
- Prevents duplicate Telegram and canonical-user mappings at the normal service layer.
- Does not create users, memory, buyer intelligence, relationship profiles, or transport behavior.
- Python `int` safely represents PostgreSQL `BIGINT` values.

### Required changes before integration

1. Validate `is_active` as a real Boolean during update.
2. Use a native UUID value or strict UUID parsing for `external_fanvue_user_uuid`, aligned with the revised migration.
3. Translate database unique-constraint violations into `DuplicateTelegramIdentityError` so concurrency does not leak persistence-specific exceptions.
4. Translate foreign-key/trigger integrity failures into `InvalidTelegramIdentityError` consistently.
5. Add tests for missing mappings, invalid UUIDs, mismatched account/local/UUID triples, database constraint races, reactivation, and failed updates.

The service's current in-memory tests demonstrate orchestration behavior but do not establish compatibility with the archived PostgreSQL schema.

## 7. Risk Analysis

| Risk | Severity | Evidence | Required action |
|---|---:|---|---|
| Narrow foreign-key columns | High | Migration uses `INTEGER`; referenced keys are `BIGINT` | Change both mapping columns to `BIGINT` |
| UUID domain mismatch | High | Migration uses `TEXT`; canonical column is `UUID` | Use native `UUID`; remove text casts |
| Commerce continuity unproven | Critical | Empty buyer table; archived monetization identities do not resolve | Audit a current database and execute controlled purchase-link tests |
| Existing content identity ambiguity | High | Only 1 of 12 usage rows matches canonical local identity | Classify/clean legacy rows before relying on ownership continuity |
| Backup staleness | High | Archive is dated May 20, 2026 | Compare preflight results with the current target database before application |
| No database-backed migration test | High | Migration was not applied anywhere in this task | Test upgrade, constraints, repository operations, and rollback on disposable restore |
| Raw uniqueness race error | Medium-High | Service precheck is not atomic | Map PostgreSQL integrity errors to domain exceptions |
| Search-path dependence | Medium | Migration/repository use unqualified table names | Schema-qualify objects |
| No rollback migration | Medium-High | Only forward SQL exists | Create and test explicit rollback procedure |
| Redundant indexes | Low | Unique indexes cover primary lookup prefixes | Confirm query plans; remove unnecessary partial indexes |
| Inactive mapping cannot be replaced | Medium | Full uniqueness includes inactive rows | Confirm update/reactivation policy and document it |
| Operator may select wrong account | High | Backup contains two accounts; target intends one Ava account | Verify Ava account by immutable Fanvue identity, not assumed numeric ID |
| Reassignment without audit evidence | Medium-High | Update can change canonical target | Restrict and audit administrative linking workflow |
| Backup may contain synthetic data | Medium | Several commerce identifiers are noncanonical | Do not generalize data quality conclusions without current-db audit |

No evidence indicates that the new mapping would create Telegram-specific intelligence. The primary risk is applying an only-partially-compatible schema and then assuming that existing commerce rows prove purchase continuity when they do not.

## 8. Readiness Determination

# READY WITH CHANGES

The canonical identity design is correct and the mapping boundary is the right integration approach. The current implementation is **not ready to migrate or integrate unchanged**.

Required readiness gates:

1. Change `fanvue_account_id` and `local_fanvue_user_id` to `BIGINT`.
2. Change `external_fanvue_user_uuid` to native `UUID` and align repository/service comparisons.
3. Schema-qualify migration and repository objects.
4. Normalize database constraint errors into service domain errors.
5. Add and test a rollback migration/procedure.
6. Run the revised migration and repository integration tests on a disposable database restored from this backup.
7. Repeat read-only identity preflight checks against the current target database immediately before application.
8. Prove one controlled Telegram identity -> canonical user -> Fanvue purchase/ownership round trip before any live transport integration.

Until these gates pass:

- do not apply the migration;
- do not populate identity mappings;
- do not build a Telegram listener or sender against this repository;
- do not treat the archived monetization rows as proof of commerce continuity.

## 9. Recommended Next Task

Perform a narrowly scoped **Identity Foundation Schema Alignment and Disposable-Database Validation** task.

That task should:

1. Revise only the mapping migration, mapping repository/service, identity model, and their tests.
2. Match the archived native domains: `BIGINT`, `BIGINT`, and `UUID`.
3. Schema-qualify all database objects.
4. Add deterministic PostgreSQL integrity-error translation.
5. Add an explicit rollback migration or documented reversible migration pair.
6. Restore `fanvue_backup.dump` into a disposable non-production PostgreSQL database.
7. Apply the revised migration only to that disposable database.
8. Test create, resolve, duplicate, mismatched triple, deactivate, reactivate, update, concurrent insert, and rollback behavior.
9. Record schema/data preflight queries for later read-only execution against the current production target.
10. Stop before any Telegram authentication, listener, sender, DecisionEngine gateway, memory change, buyer change, or relationship change.

The next task should produce evidence that the revised foundation works on real PostgreSQL—not merely that its service logic works against an in-memory fake.

