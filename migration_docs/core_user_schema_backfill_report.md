# Core User Schema and Backfill Specification

**Status:** Planning only  
**Canonical intelligence owner:** Platform-neutral core user  
**Primary conversational identity:** Telegram  
**Optional integrations:** Fanvue and DropFans commerce; KVIQA CRM/vault

This document proposes database definitions and a migration sequence. It is not an executable migration and authorizes no database or application change.

## 1. Executive Summary

Introduce `public.core_users` as the canonical owner of memory, conversations, buyer intelligence, relationship state, and entitlements. Telegram is the authoritative external identity for Telegram conversations, but Telegram IDs remain external identifiers; they do not become intelligence foreign keys. Fanvue, DropFans, KVIQA, and future systems attach optional identities to the same `core_user_id`.

The safe transition is additive:

1. Create neutral identity tables and a durable backfill provenance map.
2. Create exactly one core user for each existing `public.fanvue_users` row, without attempting cross-record person merges.
3. Attach each Fanvue UUID as an optional external identity.
4. Add nullable `core_user_id BIGINT` columns to existing intelligence tables.
5. Backfill only through deterministic legacy keys and quarantine ambiguity.
6. Compare legacy and core-key reads before switching authority.
7. Support new Telegram-only users through the core path, with no `fanvue_users` row.
8. Retain legacy columns until behavioral parity, rollback, and a sustained observation period are complete.

The archived schema confirms that legacy memory uses `(fanvue_account_id, text(fanvue_users.id))`, while canonical chat tables use `fanvue_users.id BIGINT`. It does not establish the identifier domain of `buyer_intelligence.fanvue_user_id`; the backup contains no buyer rows. Buyer backfill therefore needs stricter classification than memory and conversation backfill.

No existing intelligence values should be recalculated during identity migration. DecisionEngine behavior is preserved by supplying the same memory and relationship data through a neutral `UserContext`.

## 2. Core User Schema

### 2.1 Proposed definition

The following is specification SQL, not a migration to apply:

```sql
CREATE TABLE public.core_users (
    id                          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    status                      TEXT NOT NULL DEFAULT 'pending',
    merged_into_core_user_id    BIGINT NULL,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    activated_at                TIMESTAMPTZ NULL,
    suspended_at                TIMESTAMPTZ NULL,
    deleted_at                  TIMESTAMPTZ NULL,
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT core_users_status_check
        CHECK (status IN ('pending', 'active', 'suspended', 'merged', 'deleted')),
    CONSTRAINT core_users_merged_target_fk
        FOREIGN KEY (merged_into_core_user_id)
        REFERENCES public.core_users(id)
        ON DELETE RESTRICT,
    CONSTRAINT core_users_not_self_merged_check
        CHECK (merged_into_core_user_id IS NULL OR merged_into_core_user_id <> id),
    CONSTRAINT core_users_merge_state_check
        CHECK (
            (status = 'merged' AND merged_into_core_user_id IS NOT NULL)
            OR
            (status <> 'merged' AND merged_into_core_user_id IS NULL)
        ),
    CONSTRAINT core_users_activation_state_check
        CHECK (status = 'pending' OR activated_at IS NOT NULL),
    CONSTRAINT core_users_suspension_state_check
        CHECK (status <> 'suspended' OR suspended_at IS NOT NULL),
    CONSTRAINT core_users_deletion_state_check
        CHECK (status <> 'deleted' OR deleted_at IS NOT NULL)
);

CREATE INDEX core_users_status_idx
    ON public.core_users (status);

CREATE INDEX core_users_merge_target_idx
    ON public.core_users (merged_into_core_user_id)
    WHERE merged_into_core_user_id IS NOT NULL;
```

An `updated_at` trigger may be added using a schema-qualified function. It should be one shared, reviewed utility rather than a differently named function per table.

### 2.2 Rationale

- `BIGINT GENERATED ... AS IDENTITY` matches the actual local-key domain and avoids provider semantics.
- The primary key is immutable and never copied from Telegram, Fanvue, DropFans, or KVIQA.
- Lifecycle timestamps make state transitions auditable without embedding profile, CRM, or commerce fields in the identity row.
- `ON DELETE RESTRICT` prevents an identity merge target from disappearing through a cascade.
- A merged record remains resolvable for history but receives no new intelligence writes.
- Status is constrained in the database. A PostgreSQL enum is avoided so future lifecycle additions can use a normal reviewed constraint migration.

`core_users` must not contain usernames, Telegram chat IDs, Fanvue account IDs, buyer totals, relationship state, CRM tags, or vault identifiers. Those belong to their respective domains.

### 2.3 Lifecycle rules

| State | Allowed use |
|---|---|
| `pending` | Minimal verified identity/onboarding state; normal intelligence processing blocked |
| `active` | Normal conversation and intelligence ownership |
| `suspended` | State retained; normal processing and delivery blocked by policy |
| `merged` | Read redirects to target; no direct writes |
| `deleted` | Communication disabled; privacy/retention workflow controls retained evidence |

State transitions should be recorded in a separate lifecycle audit table before implementation. The state constraints alone do not preserve who changed state, why, or the previous value.

### 2.4 Backfill provenance

A durable migration map is required because rollback and validation must not infer which core user came from which legacy row:

```sql
CREATE TABLE public.core_user_backfill_map (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_system           TEXT NOT NULL,
    source_schema           TEXT NOT NULL,
    source_table            TEXT NOT NULL,
    source_record_id        BIGINT NOT NULL,
    source_scope_id         BIGINT NULL,
    core_user_id            BIGINT NOT NULL,
    external_identity_id    BIGINT NULL,
    backfill_batch_id       UUID NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT core_user_backfill_map_core_fk
        FOREIGN KEY (core_user_id) REFERENCES public.core_users(id) ON DELETE RESTRICT,
    CONSTRAINT core_user_backfill_map_source_unique
        UNIQUE (source_system, source_schema, source_table, source_record_id)
);

CREATE UNIQUE INDEX core_user_backfill_map_core_fanvue_user_uq
    ON public.core_user_backfill_map (core_user_id)
    WHERE source_system = 'fanvue' AND source_table = 'fanvue_users';
```

The `external_identity_id` foreign key is added after `external_identities` exists. The map is migration evidence, not the runtime identity resolver.

## 3. External Identity Schema

### 3.1 Proposed definition

```sql
CREATE TABLE public.external_identities (
    id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    core_user_id            BIGINT NOT NULL,
    provider                TEXT NOT NULL,
    provider_account_key    TEXT NULL,
    external_user_id        TEXT NOT NULL,
    status                  TEXT NOT NULL DEFAULT 'observed',
    verification_method     TEXT NOT NULL,
    verified_at             TIMESTAMPTZ NULL,
    last_seen_at            TIMESTAMPTZ NULL,
    metadata                JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT external_identities_core_user_fk
        FOREIGN KEY (core_user_id) REFERENCES public.core_users(id) ON DELETE RESTRICT,
    CONSTRAINT external_identities_provider_check
        CHECK (provider ~ '^[a-z][a-z0-9_]{1,62}$'),
    CONSTRAINT external_identities_external_user_id_check
        CHECK (length(btrim(external_user_id)) > 0),
    CONSTRAINT external_identities_status_check
        CHECK (status IN ('observed', 'pending', 'active', 'suspended', 'revoked')),
    CONSTRAINT external_identities_verification_check
        CHECK (
            (status IN ('active', 'suspended', 'revoked') AND verified_at IS NOT NULL)
            OR status IN ('observed', 'pending')
        ),
    CONSTRAINT external_identities_metadata_object_check
        CHECK (jsonb_typeof(metadata) = 'object'),
    CONSTRAINT external_identities_provider_identity_uq
        UNIQUE NULLS NOT DISTINCT
        (provider, provider_account_key, external_user_id)
);

CREATE INDEX external_identities_core_user_idx
    ON public.external_identities (core_user_id);

CREATE INDEX external_identities_active_core_provider_idx
    ON public.external_identities (core_user_id, provider)
    WHERE status = 'active';
```

`UNIQUE NULLS NOT DISTINCT` is appropriate for the validated PostgreSQL 17 target: two global identities with null account scope cannot bypass uniqueness. If a future deployment must support PostgreSQL below 15, replace it with an equivalent expression index and reserve the sentinel value explicitly.

### 3.2 Provider semantics

| Provider | `provider_account_key` | `external_user_id` | Required? |
|---|---|---|---|
| Telegram | Managed Ava bot/account key, or null while only one exists | Numeric Telegram user ID serialized canonically | Required for Telegram-originated user |
| Fanvue | Fanvue creator account ID or stable UUID | `fanvue_users.fanvue_user_uuid` | No |
| DropFans | Audited account/connection key | Provider customer ID | No |
| KVIQA | Workspace/tenant key if required | CRM contact ID | No |
| Future | Adapter-defined immutable scope | Provider-native immutable user ID | No |

The generic table stores IDs as text because provider identifier types differ. Dedicated provider tables preserve stronger native types where needed. Provider values are lower-case adapter identifiers, not a closed Fanvue-era enumeration.

### 3.3 Identity rules

- An active identity resolves to exactly one core user.
- Historical/revoked rows retain uniqueness; a provider identity cannot silently be reassigned.
- Username, display name, phone visibility, approximate purchase time, and model inference are never identity evidence.
- Identity merge or reassignment requires a separately audited operator workflow.
- Provider deletion/revocation does not delete the core user.
- KVIQA and commerce identities are optional projections/bindings and cannot own memory.

## 4. Telegram Identity Schema

### 4.1 Proposed definition

```sql
CREATE TABLE public.telegram_identities (
    external_identity_id        BIGINT PRIMARY KEY,
    telegram_user_id            BIGINT NOT NULL,
    telegram_chat_id            BIGINT NOT NULL,
    is_primary                  BOOLEAN NOT NULL DEFAULT TRUE,
    can_receive_messages        BOOLEAN NOT NULL DEFAULT TRUE,
    activated_at                TIMESTAMPTZ NULL,
    deactivated_at              TIMESTAMPTZ NULL,
    deactivation_reason         TEXT NULL,
    last_update_id              BIGINT NULL,
    last_message_at             TIMESTAMPTZ NULL,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT telegram_identities_external_fk
        FOREIGN KEY (external_identity_id)
        REFERENCES public.external_identities(id)
        ON DELETE RESTRICT,
    CONSTRAINT telegram_identities_user_positive_check
        CHECK (telegram_user_id > 0),
    CONSTRAINT telegram_identities_chat_nonzero_check
        CHECK (telegram_chat_id <> 0),
    CONSTRAINT telegram_identities_activation_check
        CHECK (
            (can_receive_messages AND activated_at IS NOT NULL AND deactivated_at IS NULL)
            OR
            (NOT can_receive_messages)
        ),
    CONSTRAINT telegram_identities_user_uq UNIQUE (telegram_user_id)
);

CREATE INDEX telegram_identities_chat_idx
    ON public.telegram_identities (telegram_chat_id);

CREATE INDEX telegram_identities_receivable_idx
    ON public.telegram_identities (telegram_user_id)
    WHERE can_receive_messages;
```

Before implementation, a database guard or a transactional service invariant must prove that the referenced `external_identities` row has `provider = 'telegram'` and the same canonical numeric `external_user_id`. A normal cross-table `CHECK` cannot do this. The preferred choices are a schema-qualified constraint trigger or making the specialization the single authoritative storage of the numeric ID and deriving the generic representation.

### 4.2 Activation and deactivation

- First authenticated supported Telegram interaction atomically creates the core user, active external identity, and Telegram detail row after the approved consent gate.
- Concurrent first messages converge through `telegram_user_id` uniqueness; the losing transaction reloads the winner.
- Deactivation sets `can_receive_messages = false`, records time/reason, and changes the external identity status. It does not delete memory or create another core user.
- A username change updates metadata only.
- A chat destination change updates `telegram_chat_id` only after the transport proves it belongs to the same Telegram user.
- The current single-Ava design permits one primary Telegram identity per core user. If multiple identities are later permitted, add a unique partial index on the resolved `core_user_id`; do not assume this requirement today without defining recovery behavior.

Telegram-only proof: neither table has a foreign key to `fanvue_accounts` or `fanvue_users`. A valid core user can have only one Telegram external identity and still own all intelligence.

## 5. Memory Migration Design

### 5.1 Confirmed legacy state

`public.user_memory` has `id BIGINT`, `fanvue_account_id BIGINT NOT NULL`, and `fanvue_user_id TEXT NOT NULL`. The backup contains three rows; each text ID is numeric and matches `public.fanvue_users.id` in the same account. There is no direct user foreign key. Existing unique constraints include `(fanvue_account_id, fanvue_user_id)` and a global `fanvue_user_id` constraint.

### 5.2 Additive target

```sql
ALTER TABLE public.user_memory
    ADD COLUMN core_user_id BIGINT NULL;

ALTER TABLE public.user_memory
    ADD CONSTRAINT user_memory_core_user_fk
    FOREIGN KEY (core_user_id)
    REFERENCES public.core_users(id)
    ON DELETE RESTRICT
    NOT VALID;

CREATE UNIQUE INDEX user_memory_core_user_uq
    ON public.user_memory (core_user_id)
    WHERE core_user_id IS NOT NULL;
```

The foreign key is proposed initially as `NOT VALID` so deployment does not scan/lock the entire legacy table before backfill. It must be validated after backfill. `core_user_id` remains nullable until all valid legacy rows are mapped and the application supports Telegram-only creation without legacy columns.

### 5.3 Deterministic backfill

```sql
UPDATE public.user_memory AS um
SET core_user_id = bm.core_user_id
FROM public.core_user_backfill_map AS bm
WHERE bm.source_system = 'fanvue'
  AND bm.source_schema = 'public'
  AND bm.source_table = 'fanvue_users'
  AND bm.source_record_id::text = um.fanvue_user_id
  AND bm.source_scope_id = um.fanvue_account_id
  AND um.core_user_id IS NULL;
```

Preflight must reject nonnumeric memory IDs, account/user mismatches, duplicate intended core owners, and rows that would map differently from an already populated `core_user_id`. Do not cast unvalidated text directly to `BIGINT` in the update.

### 5.4 Read/write transition and rollback

- Legacy users: write both the existing identity path and `core_user_id` on the same memory row; never create two memory roots.
- Telegram-only users: write `core_user_id`; legacy Fanvue identity columns must become nullable or be removed from the insert requirement in a later reviewed step.
- Shadow reads load both keys, compare the same row ID and canonicalized payload, and return the legacy result until the authority flag changes.
- After parity, core reads become authoritative while legacy fields remain populated for backfilled users.
- Rollback switches reads/writes back to legacy for legacy users. Telegram-only processing must be paused or remain on the core path; it cannot be represented safely by fabricated Fanvue keys.
- Identity columns and provenance are not dropped during rollback. Existing intelligence values remain untouched.

## 6. Conversation Migration Design

### 6.1 Confirmed legacy state

`public.chat_threads.fanvue_user_id` and `public.chat_messages.fanvue_user_id` are `BIGINT` foreign keys to `fanvue_users.id`; both also carry `fanvue_account_id BIGINT`. The backup contains two canonical threads and 765 messages, all resolving to a user in the same account.

### 6.2 Additive target

```sql
ALTER TABLE public.chat_threads
    ADD COLUMN core_user_id BIGINT NULL;

ALTER TABLE public.chat_messages
    ADD COLUMN core_user_id BIGINT NULL;

ALTER TABLE public.chat_threads
    ADD CONSTRAINT chat_threads_core_user_fk
    FOREIGN KEY (core_user_id) REFERENCES public.core_users(id)
    ON DELETE RESTRICT NOT VALID;

ALTER TABLE public.chat_messages
    ADD CONSTRAINT chat_messages_core_user_fk
    FOREIGN KEY (core_user_id) REFERENCES public.core_users(id)
    ON DELETE RESTRICT NOT VALID;

CREATE INDEX chat_threads_core_user_idx
    ON public.chat_threads (core_user_id);

CREATE INDEX chat_messages_core_user_time_idx
    ON public.chat_messages (core_user_id, created_at);
```

Use the real timestamp column name confirmed at implementation preflight if it differs from `created_at`. New channel-neutral columns for channel/external message identity belong to a later conversation-schema specification; this task changes ownership only.

### 6.3 Backfill and integrity

Backfill threads through `(fanvue_account_id, fanvue_user_id)` to the provenance map, then backfill messages through their thread. Compare a message's legacy user/account with its thread before assigning it. Any disagreement is a blocking data-quality defect.

The target should enforce message/thread ownership consistency. One option is a unique key on `(chat_threads.id, core_user_id)` plus a composite foreign key from `(chat_messages.thread_id, core_user_id)`. Add this only after columns are populated and existing constraints/column names are confirmed.

Validation must preserve:

- thread and message row counts;
- message ordering and timestamps;
- content hashes and reply relationships;
- exact owner equality between message and thread;
- Fanvue external thread/message IDs as legacy transport metadata.

Rollback returns reads to legacy ownership and leaves `core_user_id` populated. Telegram-originated threads cannot fall back to Fanvue and must be gated off if a full core rollback is required.

## 7. Buyer Intelligence Migration Design

### 7.1 Confirmed uncertainty

`public.buyer_intelligence` uses `fanvue_account_id BIGINT` and `fanvue_user_id TEXT`, with a unique account/user constraint. The backup has zero rows, so the text identifier's real production domain is unproven. Existing callers may use either local IDs or external UUIDs. The current buyer-to-memory synchronization can therefore join unlike domains.

### 7.2 Additive target

```sql
ALTER TABLE public.buyer_intelligence
    ADD COLUMN core_user_id BIGINT NULL;

ALTER TABLE public.buyer_intelligence
    ADD CONSTRAINT buyer_intelligence_core_user_fk
    FOREIGN KEY (core_user_id) REFERENCES public.core_users(id)
    ON DELETE RESTRICT NOT VALID;

CREATE UNIQUE INDEX buyer_intelligence_core_user_uq
    ON public.buyer_intelligence (core_user_id)
    WHERE core_user_id IS NOT NULL;
```

This preserves one aggregate buyer profile per core user. It does not make the legacy buyer table a cross-provider transaction ledger; normalized transactions and entitlements require a later commerce design.

### 7.3 Classification before backfill

Every populated legacy row must be classified into exactly one category:

1. **Local-ID match:** numeric text matches `fanvue_users.id` in the same account.
2. **External-UUID match:** valid UUID matches `fanvue_users.fanvue_user_uuid` in the same account.
3. **Conflicting match:** local and external interpretations resolve differently.
4. **Orphan:** syntactically valid but no same-account user exists.
5. **Invalid/synthetic:** neither accepted identifier form nor approved import evidence.

Only categories 1 and 2 with exactly one target may be backfilled. Conflict, orphan, and invalid rows go to a reviewed exception report; they are never matched by username or spend similarity.

### 7.4 Behavioral preservation and rollback

- Copy ownership only; do not recompute totals, tier, counts, subscription state, or relationship fields during this migration.
- Shadow-compare buyer profile reads by legacy and core keys.
- Buyer-memory synchronization must join on `core_user_id` only after both sides are fully backfilled and parity-tested.
- New Telegram-only users have a valid absent/lazy or zero buyer profile without any commerce identity.
- Rollback restores legacy read authority for legacy rows and leaves core ownership/provenance intact.
- Provider-neutral aggregation is a separate later task; do not mix it into identity backfill.

## 8. Fanvue Backfill Plan

### 8.1 Deterministic rule

For every source row in `public.fanvue_users`:

```text
(fanvue_account_id, fanvue_users.id, fanvue_user_uuid)
  -> one new core_users row
  -> one core_user_backfill_map row
  -> one active external_identities row with provider = fanvue
```

Do not deduplicate users across Fanvue accounts or UUIDs. The legacy data does not prove person equivalence. Later verified linking/merge may consolidate identities through a separately approved workflow.

Backfilled core users should normally be `active`, with `activated_at` set to the best reliable legacy creation/activation timestamp and provenance recording that it was a migration activation. Do not invent consent facts; consent must have its own state/audit design.

### 8.2 Idempotent sequence

1. Generate one `backfill_batch_id UUID` for the run.
2. Lock the migration operation against concurrent identity backfills.
3. Snapshot preflight counts and hashes.
4. Insert core users only for source rows absent from `core_user_backfill_map`.
5. Insert the provenance rows in the same transaction/batch.
6. Insert Fanvue external identities using account scope and canonical UUID text.
7. Record each external identity ID back on its provenance row.
8. Backfill memory, threads, messages, then buyer intelligence.
9. Validate constraints and parity before changing any feature flag.

The implementation should use set-based SQL with `RETURNING` captured through a staging relation or a controlled per-row repository transaction. Positional matching between sequence values and unordered query results is forbidden.

### 8.3 Preflight conflict and orphan queries

These queries are proposed checks and must be reviewed against the live/restored schema before execution:

```sql
-- Duplicate Fanvue external identities within account: must return zero rows.
SELECT fanvue_account_id, fanvue_user_uuid, count(*)
FROM public.fanvue_users
GROUP BY fanvue_account_id, fanvue_user_uuid
HAVING count(*) > 1;

-- Orphan Fanvue account references: must return zero rows.
SELECT fu.id, fu.fanvue_account_id
FROM public.fanvue_users fu
LEFT JOIN public.fanvue_accounts fa ON fa.id = fu.fanvue_account_id
WHERE fa.id IS NULL;

-- Unresolvable memory owners: must return zero or be quarantined.
SELECT um.id, um.fanvue_account_id, um.fanvue_user_id
FROM public.user_memory um
LEFT JOIN public.fanvue_users fu
  ON fu.fanvue_account_id = um.fanvue_account_id
 AND fu.id::text = um.fanvue_user_id
WHERE fu.id IS NULL;

-- Conversation account/user disagreement: must return zero rows.
SELECT ct.id, ct.fanvue_account_id, ct.fanvue_user_id
FROM public.chat_threads ct
JOIN public.fanvue_users fu ON fu.id = ct.fanvue_user_id
WHERE fu.fanvue_account_id <> ct.fanvue_account_id;

-- Existing source mapping conflicts: must return zero rows.
SELECT source_record_id, count(DISTINCT core_user_id)
FROM public.core_user_backfill_map
WHERE source_system = 'fanvue'
  AND source_schema = 'public'
  AND source_table = 'fanvue_users'
GROUP BY source_record_id
HAVING count(DISTINCT core_user_id) <> 1;
```

### 8.4 Post-backfill validation

```sql
-- Exactly one provenance row per Fanvue user.
SELECT
  (SELECT count(*) FROM public.fanvue_users) AS fanvue_users,
  (SELECT count(*) FROM public.core_user_backfill_map
    WHERE source_system = 'fanvue'
      AND source_schema = 'public'
      AND source_table = 'fanvue_users') AS mapped_users;

-- No mapped source points to a missing/mismatched Fanvue external identity.
SELECT bm.source_record_id, bm.core_user_id
FROM public.core_user_backfill_map bm
JOIN public.fanvue_users fu ON fu.id = bm.source_record_id
LEFT JOIN public.external_identities ei
  ON ei.id = bm.external_identity_id
 AND ei.core_user_id = bm.core_user_id
 AND ei.provider = 'fanvue'
 AND ei.provider_account_key = fu.fanvue_account_id::text
 AND ei.external_user_id = fu.fanvue_user_uuid::text
WHERE bm.source_system = 'fanvue'
  AND bm.source_table = 'fanvue_users'
  AND ei.id IS NULL;

-- No backfilled memory remains ownerless.
SELECT count(*)
FROM public.user_memory um
JOIN public.fanvue_users fu
  ON fu.fanvue_account_id = um.fanvue_account_id
 AND fu.id::text = um.fanvue_user_id
WHERE um.core_user_id IS NULL;
```

The archived baseline predicts three Fanvue users, three memory owners, two threads, and 765 messages. Those figures are evidence for the backup only, not hard-coded production acceptance values.

### 8.5 Rollback boundaries

Before core read authority, rollback means disabling new writes, returning flags to legacy, verifying legacy rows were never removed, and optionally removing only records created by the recorded batch after proving no Telegram-only or later provider data references them. After Telegram-only users exist, destructive rollback of neutral identity is unsafe. Rollback must instead preserve neutral tables and disable the new processing path.

Never delete a core user merely because its Fanvue identity is removed. Never reverse-map Telegram-only users into `fanvue_users`.

## 9. UserContext Contract

### 9.1 Contract

`UserContext` is an immutable application-level input assembled before DecisionEngine invocation:

```text
UserContext
  core_user_id: int
  core_user_status: pending | active | suspended | merged | deleted

  creator_context:
    creator_profile_id
    persona_id / Ava configuration
    locale/timezone/configuration required by behavior

  channel_context:
    channel: telegram | fanvue_legacy | future
    external_identity_id
    conversation_thread_id
    inbound_message_id
    reply/delivery context

  memory:
    existing user_memory payload and version

  relationship:
    relationship/intimacy/emotional/engagement state

  buyer:
    aggregate buyer profile, zero/absent state allowed
    verified provider summaries, if any

  entitlements:
    provider-neutral active grants needed for the decision

  external_identities:
    optional verified provider references

  compatibility:
    optional legacy fanvue_account_id
    optional legacy local_fanvue_user_id
    optional legacy engine_user_id
```

### 9.2 Consumer requirements

| Consumer | Required context | Must not require |
|---|---|---|
| DecisionEngine | Core ID, creator/persona, memory, relationship, buyer state, active channel context | Fanvue user/account identity as person key |
| MemoryService | Core ID, memory version/payload | Parsed `account_id:user_id` for new users |
| Buyer Intelligence | Core ID, aggregate profile, verified normalized events | A Fanvue customer identity |
| Relationship services | Core ID, memory/relationship state, creator context | Telegram or commerce-specific IDs |
| Delivery adapter | Channel identity/destination and generated result | Ownership of memory or buyer state |

### 9.3 Compatibility boundary

During migration, an identity gateway may produce the legacy composite engine key only for backfilled Fanvue users. That field is optional and must not be parsed inside new core repositories. Telegram-only contexts have no legacy key, Fanvue account, or Fanvue user.

Preserve DecisionEngine behavior by freezing inputs and comparing routes, memory deltas, offer decisions, safety decisions, and generated prompt context. The identity gateway changes how context is loaded, not the decision rules.

## 10. Feature Flag Strategy

Use independently observable flags with a small number of valid modes; avoid arbitrary combinations.

| Phase | Identity writes | Intelligence writes | Read authority | Telegram-only processing |
|---|---|---|---|---|
| 0 Baseline | Legacy only | Legacy only | Legacy | Off |
| 1 Schema dark | Core backfill only | Legacy only | Legacy | Off |
| 2 Shadow read | Core + provenance | Same existing rows with core ownership | Legacy; compare core | Off |
| 3 Dual-key write | Core identity authoritative for mapping | One row, both key domains populated | Legacy; compare core | Off |
| 4 Core read canary | Core | One row through core repository | Core for allowlist; fallback/compare legacy | Off |
| 5 Telegram-only canary | Core | Core-only allowed for new users | Core | Allowlist |
| 6 Core authority | Core | Core | Core | On |
| 7 Legacy retirement | Core | Core | Core | On |

Recommended conceptual flags:

- `CORE_IDENTITY_MODE = off | shadow | authoritative`
- `CORE_INTELLIGENCE_READ_MODE = legacy | compare | core`
- `CORE_INTELLIGENCE_WRITE_MODE = legacy | dual_key | core`
- `TELEGRAM_NEW_USER_MODE = off | allowlist | enabled`

Configuration validation must reject unsafe combinations, such as Telegram new users enabled while core writes are off. “Dual write” means populating both ownership columns on the same logical row, not maintaining independent memory/buyer records.

Rollback order:

1. Stop inbound processing and drain/hold identity-dependent workers.
2. Disable new Telegram user creation.
3. Return read authority to legacy for legacy users.
4. Return writes to legacy fields while preserving core ownership.
5. Reconcile writes made during the canary window.
6. Resume legacy traffic only after parity checks pass.

Rollback cannot make Telegram-only users work on the old Fanvue path. They must remain safely paused on retained core data until the core path is corrected.

## 11. Validation Plan

### 11.1 Environments and preflight

Run the eventual migration first against a disposable PostgreSQL 17 restore of `fanvue_backup.dump`, then a production-like sanitized snapshot. Capture server version, schema/search path, roles/privileges, extensions, row counts, constraints, and exact table columns. The earlier audit could not invoke `pg_restore` from the current shell, so implementation must also document the PostgreSQL tool path/environment rather than assuming it is globally available.

Preflight gates:

- no unexpected existing neutral table/function names;
- no duplicate or orphan Fanvue canonical users;
- every memory/thread/message owner is classified;
- every buyer row is classified without guessing;
- no pending migration has applied the obsolete Fanvue-dependent `telegram_identity_map`;
- sufficient disk/lock budget and a tested transaction timeout;
- backup and restore rehearsal completed;
- behavioral golden fixtures captured before changes.

### 11.2 Migration validation

- Exact source-to-map-to-core cardinality.
- All foreign keys validate after backfill.
- All uniqueness and check constraints reject invalid fixtures.
- Re-running the backfill creates no additional core users or external identities.
- Concurrent first Telegram-identity transactions converge to one core user.
- A Telegram-only core user can own memory, a thread, messages, relationship state, and zero buyer state without any Fanvue row.
- Revocation/deactivation retains intelligence and blocks delivery.
- No schema object relies on an uncontrolled `search_path`.

### 11.3 Data parity

For memory, chat, and buyer records compare:

- row counts by source/core owner;
- null and orphan counts;
- canonicalized field hashes excluding only new identity/audit fields;
- thread/message ordering and reply links;
- buyer totals, counts, tier, and timestamps without recalculation;
- relationship and intimacy fields exactly;
- legacy/core lookup results for every backfilled user in the disposable restore.

### 11.4 Behavioral parity

Replay fixed inbound fixtures through legacy and neutral context loading. Compare:

- selected DecisionEngine route;
- safety and suppression decisions;
- offer eligibility/timing;
- memory update keys and values;
- buyer/relationship state deltas;
- prompt context excluding deliberate identity-label changes;
- generated response under deterministic/mock model output.

Any behavior drift blocks rollout even when database counts match.

### 11.5 Rollback validation

- Feature flags return legacy users to identical legacy reads.
- No legacy column/value was deleted or overwritten.
- Canary-window writes are present through both key domains on the same rows.
- Workers and queued jobs do not address mixed identities after rollback.
- Telegram-only users remain retained and paused, not deleted or remapped.
- A second forward attempt is idempotent after rollback.

### 11.6 Acceptance gates

Proceed to the next phase only with zero unexplained duplicates, zero deterministic-source orphans, zero memory/conversation ownership mismatch, fully classified buyer rows, validated constraints, behavioral fixture parity, and a timed rollback rehearsal. Quarantined legacy commerce data may remain only if it is explicitly excluded from authoritative buyer state and approved by the owner.

## 12. Risks

| Risk | Severity | Control |
|---|---:|---|
| Buyer text ID interpreted in the wrong domain | Critical | Classification query; quarantine ambiguity |
| Duplicate core users created on rerun/concurrency | Critical | Durable source uniqueness, identity uniqueness, transactional creation |
| Telegram-only users fabricated as Fanvue users | Critical | No Fanvue FK in neutral identity; explicit integration test |
| DecisionEngine behavior changes during plumbing work | Critical | Immutable `UserContext`, golden route/memory fixtures |
| Memory split into legacy and Telegram rows | Critical | One row, one core owner, unique core-memory index |
| Message and thread owners diverge | Critical | Thread-first backfill, composite consistency constraint |
| Cross-account legacy records merged as one person | Critical | One core user per source row; verified merge only later |
| Provider identity reassigned after revocation | High | Uniqueness includes inactive rows; operator audit |
| Rollback deletes neutral-only intelligence | Critical | Retain neutral tables; pause Telegram-only users |
| Unvalidated FK creates long lock/outage | High | Add `NOT VALID`, backfill, validate deliberately |
| Generic nullable scope bypasses uniqueness | High | PostgreSQL `NULLS NOT DISTINCT` uniqueness |
| KVIQA/Fanvue becomes canonical again through context | High | Optional provider references; core-only consumer contracts |
| Legacy global memory uniqueness blocks new rows | High | Review/retire only after core authority; no destructive early change |
| Merged-user chains/cycles | High | Operator workflow, cycle guard, canonical target resolution |
| Consent inferred from legacy activity | High | Separate consent lifecycle; no invented backfill facts |
| Obsolete Telegram migration applied accidentally | High | Mark superseded and block in deployment preflight |

## 13. Recommended Next Task

The next task should be a **Core Identity Migration Implementation Plan and Test Matrix**, still without Telegram transport or commerce implementation.

It should:

1. Reinspect the live/disposable PostgreSQL schema and lock down exact existing column names and constraints.
2. Turn this specification into ordered forward and rollback migration files, but only after explicit implementation authorization.
3. Define the lifecycle audit table and verified merge/recovery workflow.
4. Specify repository methods for atomic core-user/external-identity creation and idempotent Fanvue backfill.
5. Specify memory, conversation, and buyer shadow-read comparison telemetry.
6. Build the complete unit, PostgreSQL integration, concurrency, parity, and rollback test matrix.
7. Define how the obsolete Fanvue-dependent Telegram identity migration and related code are retired without applying it.
8. Establish migration ledger, roles/grants, deployment timeout, batching, and operator runbook requirements.

Do not implement Telegram transport, DropFans, KVIQA, commerce normalization, or DecisionEngine behavior in that task. Neutral identity persistence and behavioral parity must be proven first.
