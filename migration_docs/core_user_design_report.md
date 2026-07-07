# Platform-Neutral Core User Design

**Status:** Planning only  
**Primary conversational identity:** Telegram  
**Canonical intelligence owner:** Platform-neutral core user

## 1. Executive Summary

The system should introduce a platform-neutral `core_user` as the sole owner of conversational intelligence. Telegram should be the authoritative external identity for users entering the conversational system, but the raw Telegram user ID should not become the primary key of memory, buyer intelligence, or conversations.

The central invariant should be:

```text
one person
  -> one core_user_id
  -> one shared intelligence profile
  -> zero or more verified external identities
       Telegram (primary conversation identity)
       Fanvue (optional commerce identity)
       DropFans (optional commerce identity)
       KVIQA (optional CRM identity)
       future providers/channels
```

A Telegram user must be able to create a core user, own memory, start conversations, build a relationship profile, receive offers, and accumulate engagement history without a Fanvue user, DropFans customer, or KVIQA contact.

Recommended database identity:

- `core_users.id`: internally generated `BIGINT`, immutable and semantically neutral.
- Telegram numeric user ID: required verified external identity for Telegram-originated users.
- Provider IDs: optional mappings, never substituted for `core_user_id`.
- Creator/persona context: separate from user identity and commerce-provider accounts.

The existing FanvueChatbot intelligence should be preserved behaviorally. Its identity access must be adapted because `DecisionEngine`, `MemoryService`, repositories, conversations, queues, buyer state, and ownership currently use Fanvue-shaped keys. The transition should be additive, use dual-read/write only within explicit phases, and retain legacy identifiers until parity and rollback are proven.

The aligned Telegram Identity Foundation provides reusable patterns—typed models, native UUID handling, schema qualification, integrity constraints, exception translation, rollback scripts, and disposable-database testing. Its Fanvue-required data model is superseded and must remain unapplied.

## 2. Core User Design

### 2.1 Purpose

`core_user` represents the person whose conversational intelligence the application owns. It is independent of communication channel, CRM, payment processor, vault, creator-commerce account, username, and checkout status.

It is the parent identity for:

- memory and relationship state;
- buyer intelligence and cross-provider value;
- conversation history;
- engagement, offer, and content history;
- entitlements and ownership;
- outbound eligibility and consent;
- CRM and provider mappings;
- audit and merge history.

### 2.2 Logical schema

This is a proposed logical design, not an authorized migration:

```text
core_users
  id                       BIGINT generated identity, primary key
  status                   pending | active | suspended | merged | deleted
  merged_into_core_user_id nullable self-reference
  created_at               timestamptz
  activated_at             timestamptz nullable
  suspended_at             timestamptz nullable
  deleted_at               timestamptz nullable
  updated_at               timestamptz
```

Optional operational fields such as consent version, locale, or safety status should live in dedicated profile/consent records unless they are true identity lifecycle fields. Avoid turning `core_users` into a replacement monolithic user profile.

### 2.3 Ownership

The FanvueChatbot core database owns `core_user_id`. Telegram, Fanvue, DropFans, and KVIQA may prove or reference external identities but may not create a second intelligence owner outside the core-user lifecycle.

No provider identifier may be copied into `core_users.id`, and no provider deletion should automatically delete the core user.

### 2.4 Creation rules

A core user may be created through:

1. A new Telegram identity after an authenticated supported private interaction and the approved onboarding/consent gate.
2. Backfill from one existing canonical `fanvue_users` row during migration.
3. A controlled identity import with explicit provenance and verification.

Creation must be atomic with the initiating external identity. It must never create a core user without either:

- a verified external identity; or
- a migration/import source reference.

For concurrent first Telegram messages, a unique Telegram identity constraint decides the winner. The losing transaction reloads the existing core user instead of creating a duplicate.

### 2.5 Lifecycle

| State | Meaning | Intelligence behavior |
|---|---|---|
| `pending` | Minimal identity exists but activation/consent is incomplete | No normal DecisionEngine processing; limited retention |
| `active` | User may converse and own intelligence | Normal processing |
| `suspended` | Safety, consent, operator, or compliance hold | Retain state; block defined processing/delivery |
| `merged` | Identity was consolidated into another core user | No new writes; redirect reads through merge resolution |
| `deleted` | User deletion/anonymization lifecycle completed or underway | No conversational processing; retention policy governs evidence |

State transitions must be audited and must not be inferred from provider account status alone.

### 2.6 Deletion rules

Deletion is a controlled privacy and retention workflow, not a raw cascading `DELETE`:

1. Disable all active communication identities and outbound delivery.
2. Revoke consent and pending jobs.
3. Remove or anonymize personal metadata and message content according to policy.
4. Retain legally required financial/audit evidence in pseudonymized form.
5. Notify CRM/vault/commerce adapters of provider-specific deletion obligations where applicable.
6. Preserve a nonreversible tombstone sufficient to prevent accidental recreation/reattachment where policy permits.

Commerce-provider deletion must not silently erase cross-provider entitlements or accounting evidence.

### 2.7 Merge rules

Merges are exceptional, operator-controlled, and based on verified evidence. Never merge through username, display name, approximate purchase timing, or model inference.

Merge behavior:

- choose one target `core_user_id`;
- mark the source `merged` with `merged_into_core_user_id`;
- move external identities under uniqueness constraints;
- reparent memory, conversations, provider bindings, deliveries, and CRM mappings;
- deduplicate transactions by provider transaction/event identity;
- union entitlements by asset/grant rules;
- recompute buyer aggregates instead of naively adding possibly duplicated totals;
- preserve immutable merge audit evidence;
- serialize all writes for both users during the operation.

An automatic “unmerge” is unsafe after new writes. Recovery should use a separately reviewed corrective migration.

### 2.8 Recovery rules

- A returning Telegram user with the same numeric ID resolves the same core user even if username/profile metadata changed.
- A deactivated Telegram identity may be reactivated after policy checks without creating a new core user.
- A new Telegram account is a new external identity and must not inherit an old core user without verified recovery evidence.
- Recovery evidence may include an operator-approved CRM workflow, signed account-link token, or verified commerce identity. It must not rely on name matching.
- Lost or compromised identities remain inactive and retained for audit.

## 3. External Identity Design

### 3.1 Purpose

`external_identity` links a provider-native identity to one core user. It describes identity and verification; it does not own memory or business intelligence.

### 3.2 Logical schema

```text
external_identities
  id                       BIGINT generated identity
  core_user_id             FK -> core_users.id
  provider                 telegram | fanvue | dropfans | kviqa | future
  provider_account_key     nullable provider account/connection reference
  external_user_id         provider-native immutable ID represented safely
  status                   observed | pending | active | suspended | revoked
  verification_method      telegram_update | signed_link | provider_event |
                           operator_verified | migration_backfill | other
  verified_at              timestamptz nullable
  last_seen_at             timestamptz nullable
  metadata                 jsonb, presentation data only
  created_at
  updated_at
```

Recommended uniqueness:

```text
UNIQUE(provider, provider_account_key, external_user_id)
```

Provider IDs with a stronger native type may use a dedicated detail table. Telegram should retain `BIGINT` values rather than losing type safety in generic text.

### 3.3 Telegram specialization

```text
telegram_identities
  external_identity_id     PK/FK -> external_identities.id
  telegram_user_id         BIGINT unique, positive
  telegram_chat_id         BIGINT nonzero
  is_primary               boolean
  can_receive_messages     boolean
  last_update_at
```

For the current one-Ava runtime, one active Telegram identity is the primary conversation identity for a core user. This is not a multi-creator or SaaS registry.

### 3.4 Provider identity semantics

| Provider | Identity meaning | Required for core user? |
|---|---|---|
| Telegram | Authenticated conversational account | Yes for Telegram-originated users |
| Fanvue | Fanvue customer/fan identity | No |
| DropFans | DropFans customer identity | No |
| KVIQA | CRM contact identity | No |
| Future channel | Provider-native communication identity | No unless that channel creates the user |

### 3.5 Verification and activation

- Telegram: verified from an authenticated platform update received by the managed Ava account/bot; user initiation and consent handled separately.
- Commerce: verified by signed provider webhook, provider API lookup, or signed checkout-link correlation.
- KVIQA: verified through API-created contact correlation or signed webhook; manual linking requires audit evidence.
- Migration: verified from a deterministic legacy-row backfill and recorded as such.

Observed/unverified identities may be retained minimally for reconciliation but cannot merge users, inherit memory, or receive sensitive data.

Deactivation disables resolution/delivery through that identity. It does not delete the core user or other provider identities.

## 4. Telegram User Lifecycle

### 4.1 New Telegram-only user

```text
Authenticated Telegram private update
  -> validate supported account/chat/update
  -> deduplicate by managed Telegram account + update/message ID
  -> lookup telegram_user_id
     -> not found
  -> begin transaction
     -> create pending or active core_user
     -> create verified Telegram external_identity
     -> create telegram_identity details/chat destination
     -> initialize core-owned memory root
     -> create/get channel-neutral conversation thread
  -> commit
  -> load core user context
  -> invoke intelligence gateway
  -> persist response and delivery state
```

No step queries, creates, or requires `fanvue_users`.

If activation requires explicit consent, the first transaction creates a minimal `pending` user and identity. Only approved onboarding behavior runs until activation. The policy must define whether the triggering message is retained or minimized.

### 4.2 Returning user

```text
telegram_user_id
  -> active Telegram identity
  -> core_user_id
  -> shared memory + relationship + buyer state
  -> channel thread/history
  -> intelligence gateway
```

Username changes refresh metadata only. A changed chat destination is validated and updated without changing the user.

### 4.3 Commerce added later

When the Telegram-only user opens a checkout:

1. Create a core-owned checkout session linked to `core_user_id`.
2. Generate signed correlation metadata/link.
3. Receive the verified provider event.
4. Link the provider customer identity to the same core user.
5. Create normalized transaction and entitlement records.
6. Recompute/update core buyer intelligence.

The user remains valid if no provider customer identity is returned; the checkout correlation may still prove transaction ownership.

### 4.4 Failure behavior

- Duplicate first messages: unique constraint and transaction retry return one core user.
- Suspended identity: no DecisionEngine invocation; policy response only if allowed.
- Ambiguous external link: quarantine; do not merge.
- Database failure: acknowledge nothing as processed until durable identity/message state exists.
- Provider outage: conversation remains functional; commerce action returns structured unavailability.

## 5. Memory Ownership Design

### 5.1 Target ownership

`core_user_id` is the only person key for memory. Memory is shared across communication channels and enriched by commerce/CRM projections, but no provider owns it.

Target invariant:

```text
one core_user_id -> one active intelligence memory root
```

Channel-specific recent history may remain attached to a conversation thread, while durable relationship and behavioral memory remains core-user-owned.

### 5.2 Existing state

Current `user_memory` is addressed by:

```text
fanvue_account_id + text(fanvue_users.id)
```

`MemoryService` parses a Fanvue-shaped composite key. New Telegram-only users cannot use this path without a fabricated Fanvue row, which is prohibited.

### 5.3 Compatibility strategy

Use an additive migration of the existing memory store rather than a second Telegram memory table:

1. Add nullable `core_user_id` with a foreign key.
2. Create one core user for every valid legacy memory owner.
3. Backfill memory through `(fanvue_account_id, local fanvue_users.id)`.
4. Validate one memory root per core user and no ambiguous/orphan mappings.
5. Add a unique constraint for the active core memory root.
6. Introduce core-user repository methods and a neutral `UserContext`.
7. During a bounded compatibility phase, dual-read and compare; dual-write only if the exact field semantics are identical.
8. Permit new memory rows with `core_user_id` and null legacy Fanvue ownership.
9. Make `core_user_id` required after all active rows are backfilled.
10. Retire legacy ownership columns only in a later cleanup migration.

### 5.4 DecisionEngine compatibility

The current engine cannot fully support Telegram-only users while requiring `account_id:user_id` and a `fanvue_users` lookup. The identity boundary must be adapted, but behavioral logic should remain unchanged.

Recommended neutral contract:

```text
UserContext
  core_user_id
  creator_profile_id / Ava context
  memory
  relationship profile
  buyer profile
  entitlements
  active channel context
  optional provider identities
```

The gateway/repositories should supply this context. Commerce provider account IDs must not substitute for creator/persona context.

### 5.5 Relationship continuity

Relationship, intimacy, emotional, whale, dependency, recovery, and engagement fields remain part of the same memory/related core-owned profile. Their values are backfilled without recalculation unless a field is proven corrupt. Golden fixtures should compare memory deltas before and after identity adaptation.

## 6. Buyer Intelligence Design

### 6.1 Target ownership

Buyer intelligence belongs to `core_user_id` and aggregates verified activity across providers. It is a derived intelligence profile, not a provider customer record.

```text
core_user_id
  -> buyer profile
  -> normalized transactions from Fanvue/DropFans/future providers
  -> normalized tips/subscriptions/refunds
  -> provider-neutral entitlements
```

### 6.2 Recommended separation

| Record | Owner/source of truth |
|---|---|
| Provider checkout state | Commerce provider |
| Provider payment/refund status | Commerce provider |
| Raw verified event | Provider adapter/event store |
| Normalized transaction | Core commerce layer |
| Cross-provider spend/tier | Core buyer intelligence |
| Content entitlement | Core entitlement layer |
| Provider customer ID | External identity/binding |

### 6.3 Normalized transaction requirements

Each normalized commerce record should carry:

- `core_user_id` or unresolved/quarantine status;
- provider and provider account reference;
- provider transaction and event IDs;
- internal checkout-session correlation;
- normalized event type and status;
- amount, currency, and conversion policy;
- product/content/offer reference;
- occurred/received/processed timestamps;
- refund/reversal relationships;
- idempotency and raw-evidence reference.

Unique provider event/transaction keys prevent webhook and polling reconciliation from double-counting spend.

### 6.4 Buyer-profile updates

- Recompute totals from normalized ledger semantics where practical.
- Refunds and chargebacks reduce eligible spend according to policy.
- Cross-currency aggregation requires an explicit conversion source/time; do not sum unlike currencies blindly.
- Provider-specific statuses do not leak into tier logic.
- A Telegram-only nonbuyer has a valid zero-state buyer profile or lazily initialized core-owned state.
- Provider outages do not erase or downgrade prior verified intelligence.

### 6.5 Existing data migration

Current buyer data is split between `fanvue_users`, `buyer_intelligence`, `user_memory`, monetization events, purchases, and content usage. The backup showed ambiguous identity domains. Migration must:

1. Classify each row as local-ID, external-UUID, synthetic/test, unresolved, or invalid.
2. Resolve only deterministic rows to a core user.
3. Quarantine ambiguity rather than guess.
4. Preserve raw Fanvue event evidence.
5. Reconcile totals against a trusted current provider export before making cross-provider buyer state authoritative.

## 7. Conversation Ownership Design

### 7.1 Target model

Conversations are owned by `core_user_id`; channels own delivery addresses and external message identities.

```text
conversation_thread
  id
  core_user_id
  channel                 telegram / future
  channel_account_ref
  external_thread_id
  status
  timestamps

conversation_message
  id
  thread_id
  core_user_id
  channel
  external_message_id
  external_reply_to_id
  direction / sender role
  content/media metadata
  occurred_at
  delivery status/correlation
```

### 7.2 Rules

- Deduplicate inbound messages by channel account, external conversation, and external message ID before intelligence mutation.
- Serialize processing per thread/core user to prevent stale memory and out-of-order replies.
- Persist generation separately from delivery attempts.
- Sender usernames are presentation metadata, never ownership keys.
- Multiple channels may have separate threads but share durable memory through `core_user_id`.
- Channel deletion does not delete the core user or other channel history unless privacy policy requires it.
- Merge operations reparent threads with an immutable audit trail.

### 7.3 Legacy history

Existing `chat_threads` and `chat_messages` already point to local `fanvue_users.id`. Backfill `core_user_id` through the legacy mapping, retain Fanvue external IDs as channel metadata, and verify row counts/order/hashes before switching reads.

Fanvue-specific raw chat tables may remain archived/provider-specific. They should not receive new Telegram rows.

## 8. KVIQA Ownership Design

### 8.1 KVIQA should own

- CRM tags and segmentation authored in KVIQA;
- operator notes;
- tasks and follow-up assignments;
- campaign membership/configuration where KVIQA executes CRM workflows;
- CRM lifecycle fields explicitly designated as KVIQA-owned;
- vault binaries and provider-native vault metadata if KVIQA is selected as vault;
- KVIQA contact and asset identifiers.

### 8.2 KVIQA should not own

- `core_user_id` or identity merges;
- Telegram authentication/user identity;
- raw conversational memory or DecisionEngine state;
- relationship/intimacy/engagement decisions;
- cross-provider buyer totals or tiers;
- payment/refund truth;
- global entitlements;
- offer eligibility/content-selection logic;
- message idempotency or delivery truth.

### 8.3 Synchronization model

Map `core_user_id` to a KVIQA contact external identity. Define field ownership individually:

- Core -> KVIQA: identity reference, consent status, Telegram lifecycle summary, buyer/relationship summaries approved for CRM use.
- KVIQA -> Core: operator tags, tasks, campaign eligibility, and approved notes.
- Conflicts: owner wins; never whole-record last-write-wins.
- Outages: queue/retry synchronization without blocking Telegram conversations.
- Deletion: propagate according to field owner, privacy rules, and retention obligations.

KVIQA vault IDs belong in vault bindings linked to internal content assets, not in user or offer primary keys.

## 9. Commerce Ownership Design

### 9.1 Commerce providers should own

- provider account credentials and capabilities;
- provider customer ID;
- checkout/payment-session state;
- payment authorization/capture state;
- provider transaction ID;
- refunds, disputes, chargebacks, and provider subscription state;
- signed raw event payloads and provider reconciliation responses;
- provider-hosted media/link availability where applicable.

### 9.2 Commerce providers should not own

- canonical person identity;
- Telegram conversation eligibility;
- memory or relationship profile creation;
- cross-provider buyer classification;
- conversation history;
- global content entitlement;
- DecisionEngine offer eligibility;
- CRM lifecycle;
- creator/persona identity.

### 9.3 Core commerce ownership

The core owns:

- checkout correlation to `core_user_id` and offer;
- provider selection/capability policy;
- normalized transaction ledger;
- unresolved-event quarantine;
- cross-provider buyer projection;
- entitlement grants/revocations;
- idempotency and reconciliation status;
- provider-neutral reporting supplied to intelligence.

Fanvue, DropFans, and future adapters implement the same contract without provider branching inside the DecisionEngine.

## 10. Fanvue Dependency Inventory

The inventory below is based on current source references to `fanvue_user_id`, `fanvue_user_uuid`, and `fanvue_account_id`, plus the audited PostgreSQL schema.

### 10.1 Repositories

| Disposition | Repositories | Required direction |
|---|---|---|
| **Replace identity root** | `user_repository.py`, `telegram_identity_repository.py` | Introduce core user/external identity repositories; retire mandatory Telegram-to-Fanvue mapping |
| **Adapt to core user** | `memory_repository.py`, `buyer_intelligence_repository.py`, `buyer_memory_sync_repository.py`, `realtime_buyer_repository.py`, `chat_message_repository.py`, `chat_reset_repository.py`, `content_ownership_repository.py`, `content_unlock_repository.py`, `content_usage_repository.py`, `send_log_repository.py`, `automated_reaction_repository.py`, `delayed_message_queue_repository.py`, `outreach_log_repository.py`, `outreach_queue_repository.py`, `qualification_ppv_repository.py` | Replace person ownership with `core_user_id`; retain legacy columns during transition |
| **Adapt campaign/delivery scope** | `mass_ppv_campaign_repository.py`, `ppv_broadcast_repository.py` | Separate target core user/channel from provider execution and creator context |
| **Keep as provider adapter/legacy source** | `fanvue_account_repository.py`, `fanvue_user_repository.py`, `fanvue_message_repository.py`, `fanvue_message_sync_repository.py`, `realtime_chat_sync_repository.py`, `monetization_event_repository.py`, `cms_fanvue_upload_repository.py`, `wall_post_repository.py` | Isolate Fanvue fields; use for provider operations, raw events, or backfill—not canonical identity |
| **Adapt account scope** | `content_repository.py`, `creator_profile_repository.py`, `webhook_event_repository.py` | Separate Ava/creator scope, vault provider, webhook provider, and commerce account concepts |

This covers every repository currently found carrying Fanvue identity/account fields.

### 10.2 Services—core intelligence and orchestration

These services should retain behavior but receive `core_user_id`/neutral context instead of Fanvue person keys:

- `memory_service.py`
- `buyer_classification_service.py`, `buyer_memory_sync_service.py`, `buyer_momentum_service.py`, `buyer_session_service.py`, `hot_buyer_detection_service.py`, `spend_intelligence_service.py`
- `content_delivery_guard_service.py`, `content_gating_service.py`, `content_ownership_service.py`, `content_payload_builder_service.py`, `content_send_service.py`, `content_service.py`, `content_usage_service.py`
- `dynamic_intimacy_service.py`, `intimacy_context_service.py`, `intimacy_eligibility_service.py`, `intimacy_memory_service.py`, `intimacy_profile_service.py`, `intimacy_routing_service.py`, `intimacy_safety_service.py`, `emotional_continuity_service.py`, `whale_protection_service.py`
- `follower_monetization_service.py`, `follower_welcome_service.py`, `free_user_boundary_service.py`, `subscriber_monetization_service.py`, `subscriber_negotiation_service.py`, `subscriber_reentry_service.py`
- `outreach_service.py`, `outreach_scheduler_service.py`, `outreach_runner.py`, `delayed_followup_scheduler_service.py`, `delayed_message_worker_service.py`, `premium_followup_queue_service.py`
- `reaction_buyer_session_protection_service.py`, `reaction_duplicate_guard_service.py`, `reaction_execution_service.py`, `reaction_safety_gate_service.py`
- `automated_reaction_duplicate_protection_service.py`, `automated_reaction_message_builder_service.py`, `automated_reaction_persistence_service.py`, `automated_reaction_target_safety_service.py`
- `realtime_buyer_session_refresh_service.py`, `realtime_buyer_state_service.py`, `realtime_buyer_update_service.py`, `decisionengine_refresh_hook_service.py`
- `gpt_service.py` and `payload_builder_service.py` where Fanvue identity/account context is injected.

### 10.3 Services—commerce, provider, and delivery boundaries

| Disposition | Services |
|---|---|
| **Replace current identity entry** | `realtime_decision_trigger_service.py`, `realtime_message_event_service.py`, `telegram_identity_service.py` |
| **Normalize provider events to core user** | `monetization_event_normalizer_service.py`, `realtime_monetization_event_service.py`, `thank_you_message_executor_service.py`, `tip_reward_executor_service.py`, `subscriber_welcome_executor_service.py` |
| **Isolate as Fanvue adapter** | `fanvue_api_service.py`, `fanvue_oauth_service.py`, `fanvue_media_upload_service.py`, `fanvue_message_sync_service.py`, `fanvue_outbound_reaction_service.py`, `fanvue_relationship_sync_service.py`, `fanvue_relationship_sync_orchestrator.py`, `fan_insights_sync_service.py`, `cms_fanvue_media_sync_service.py`, `cms_fanvue_upload_link_service.py` |
| **Adapt provider/channel targeting** | `content_media_delivery_service.py`, `mass_ppv_content_service.py`, `mass_ppv_scheduler_service.py`, `mass_ppv_send_service.py`, `mass_ppv_suppression_signal_service.py`, `mass_ppv_targeting_service.py`, `mass_ppv_worker_service.py`, `one_on_one_ppv_send_service.py`, `ppv_broadcast_service.py`, `ppv_targeting_service.py`, `qualification_cooldown_service.py`, `qualification_escalation_service.py`, `wall_scheduler_service.py`, `wall_worker_service.py` |

### 10.4 Engine, runtime, and dashboards

- `app/engine/decision_engine.py`: replace Fanvue composite parsing/user lookup with neutral `UserContext`; preserve behavioral decisions.
- `app/main.py`: stop creating/simulating users through Fanvue identity; compose neutral identity services.
- `app/outreach_worker.py` and `app/run_daily_relationship_sync.py`: remove hard-coded Fanvue account/user targeting.
- Dashboard files carrying Fanvue keys—`main.py`, `approval_queue.py`, `chat_console.py`, `cms_upload.py`, `creator_profile.py`, `delayed_messages_dashboard.py`, `fanvue_auth.py`, `mass_ppv_dashboard.py`, `relationship_sync.py`, `wall_scheduler_dashboard.py`—must separate core-user, creator, channel, and provider contexts. Fanvue administration may remain provider-specific.

### 10.5 Tables

| Disposition | Current tables |
|---|---|
| **Add core ownership/backfill** | `user_memory`, `buyer_intelligence`, `chat_threads`, `chat_messages`, `content_usage_log`, `offers_sent`, `purchase_events`, `send_log`, `automated_reactions`, `delayed_message_queue`, `outreach_log`, `outreach_queue`, `qualification_ppv_events` |
| **Adapt campaign/channel/provider scope** | `mass_ppv_campaigns`, `mass_ppv_queue`, `ppv_broadcast_log`, `ppv_broadcast_logs` |
| **Keep as Fanvue provider/legacy tables** | `fanvue_accounts`, `fanvue_users`, `fanvue_chat_messages`, `fanvue_messages`, `fanvue_threads`, `fanvue_monetization_events`, `cms_fanvue_upload_links`, `wall_post_history`, `wall_post_queue` |
| **Adapt to neutral creator/content/provider model** | `content_catalog`, `content_items`, `creator_profiles`, `webhook_events` |

`fanvue_users` becomes a legacy/provider identity source, not a parent for new intelligence. Existing foreign keys are retained until neutral backfill and parity are proven.

### 10.6 Workflows

| Workflow | Disposition |
|---|---|
| Fanvue chat ingestion and delivery | Retire as primary conversation path; preserve only for rollback/archive until cutover |
| Fanvue relationship sync | Convert results to optional Fanvue provider/CRM facts; never create canonical user requirement |
| Telegram inbound identity resolution | Replace Fanvue-required mapping with lookup/create of core user |
| DecisionEngine invocation | Adapt identity/context boundary; preserve decisions |
| Memory reads/writes | Move to core ownership with validated compatibility phase |
| Fanvue monetization webhooks | Keep verification/raw evidence; normalize to core transactions/entitlements |
| Buyer-memory synchronization | Replace Fanvue-ID equality joins with normalized core-user projection |
| Content ownership suppression | Read provider-neutral entitlements by core user |
| Outreach, delayed messages, reactions | Preserve intelligence; resolve active channel destination from core user |
| Mass PPV/qualification/wall workflows | Split provider campaign execution from user intelligence and channel delivery |
| Dashboards/operations | Present core identity plus optional provider identities; never imply Fanvue is required |

## 11. Transition Strategy

### Phase 0 — Freeze and evidence

- Keep the Fanvue-dependent Telegram identity migration unapplied.
- Freeze DecisionEngine/memory golden fixtures and current row counts.
- Capture schema, FK, duplicate, orphan, and identifier-domain audits from the current database.
- Define the Ava creator/persona identifier independently of Fanvue account ID.

Rollback: documentation/evidence only.

### Phase 1 — Neutral identity foundation

- Add `core_users`, external identities, Telegram identity details, lifecycle audit, and migration provenance.
- Create repositories/services without changing live message processing.
- Validate schema and rollback on disposable restore.

Rollback: remove unused neutral tables; legacy behavior untouched.

### Phase 2 — Legacy core-user backfill

- Create exactly one core user per valid legacy `fanvue_users` row.
- Record Fanvue external identity and provenance.
- Detect duplicates/conflicts before constraints.
- Do not merge across Fanvue accounts without verified evidence.

Gates: counts, uniqueness, deterministic reruns, no intelligence mutation.

### Phase 3 — Additive intelligence ownership

- Add nullable `core_user_id` to memory, conversations, buyer state, ownership, logs, and queues.
- Backfill through deterministic legacy mappings.
- Quarantine ambiguous commerce/content rows.
- Add indexes and constraints after validation.

Rollback: disable neutral reads; additive columns remain inert or are reversed on a tested copy.

### Phase 4 — Neutral repositories and context

- Implement core-user repositories and `UserContext`.
- Dual-read legacy and neutral paths for legacy users and compare results.
- Preserve DecisionEngine behavior and memory deltas.
- No new Telegram users yet.

Gates: zero unexplained parity differences across representative states.

### Phase 5 — Core-owned writes

- Switch memory/history/buyer/ownership writes to `core_user_id` behind flags.
- If dual-writing, define one authoritative path and reconcile every write.
- Ensure retries cannot mutate intelligence twice.

Rollback: revert reads/writes together to avoid split-brain state.

### Phase 6 — Telegram-only lifecycle in QA

- Create allowlisted Telegram-originated core users with no Fanvue/KVIQA/DropFans identities.
- Initialize memory and conversation history by core ID.
- Exercise DecisionEngine through the neutral context.
- Keep outbound transport or production sending disabled until separately approved.

Required proof:

```text
Telegram identity
  -> core user
  -> memory mutation
  -> relationship continuity
  -> conversation persistence
  -> no fanvue_users row created or required
```

### Phase 7 — Commerce normalization

- Introduce checkout correlation, normalized transactions, provider customer bindings, and entitlements.
- Extract Fanvue behind the provider contract.
- Reconcile trusted Fanvue data to core users.
- Add DropFans only after a separate capability audit.

### Phase 8 — KVIQA projection/vault

- Implement explicit CRM field ownership and retryable sync.
- Add vault bindings to internal assets.
- Verify KVIQA outage does not block conversation or memory.

### Phase 9 — Cutover and stabilization

- Make Telegram/core identity primary for approved users.
- Keep Fanvue payment webhooks while disabling Fanvue chat triggers.
- Monitor identity misses, duplicate core users, memory parity, transaction attribution, entitlement errors, and channel delivery.
- Delay destructive legacy cleanup until sustained success.

## 12. Risks

| Risk | Severity | Control |
|---|---:|---|
| Duplicate core users from concurrent Telegram arrival | Critical | Atomic create + unique Telegram identity + reload winner |
| Incorrect legacy backfill | Critical | Deterministic account/local-ID mapping, counts, conflicts quarantined |
| Memory split between legacy and core keys | Critical | One authoritative write path, parity checks, coordinated flags |
| DecisionEngine behavior regression | Critical | Neutral context boundary plus golden decision/memory fixtures |
| Fabricated Fanvue identity persists | Critical | Explicit invariant: Telegram-only user requires no provider mapping |
| Incorrect user merge | Critical | Verified evidence, operator approval, transactional merge audit |
| Commerce purchase misattribution | Critical | Signed checkout correlation, provider event verification, quarantine |
| Buyer double counting across webhooks/polling/providers | Critical | Provider transaction/event uniqueness and normalized ledger |
| Ownership loss or paid-content resale | Critical | Core entitlements, reconciliation, provider evidence retained |
| Conversation history loss/order changes | High | Row/hash/order validation and channel-neutral IDs |
| Dual-read/write drift | High | Bounded phase, metrics, reconciliation, explicit authority |
| KVIQA becomes accidental canonical store | High | Field-level ownership and outage-tolerant projection only |
| Provider account confused with Ava/persona scope | High | Separate creator context from commerce account references |
| Deletion violates financial retention or privacy | High | Policy-led anonymization/tombstone workflow |
| External identity takeover/recovery mistake | Critical | Strong verification; never name-based recovery |
| Ambiguous legacy commerce rows | High | Quarantine and trusted provider reconciliation |
| Existing unapplied mapping is applied accidentally | High | Mark superseded; replace migration plan and deployment checklist |
| Rollback reactivates two identity paths | High | Single coordinated feature mode and tested rollback drill |
| Future-channel coupling repeats Fanvue mistake | Medium-High | `core_user_id` only in intelligence; channel IDs at adapter boundary |

## 13. Recommended Next Task

The next task should be a **Core User Schema and Backfill Specification**, still planning-only.

It should produce:

1. Exact PostgreSQL DDL proposals for `core_users`, external identities, Telegram identity details, lifecycle audit, and migration provenance.
2. Constraint and index definitions, including duplicate-race behavior.
3. Exact additive `core_user_id` changes for `user_memory`, `chat_threads`, and `chat_messages` as the first intelligence stores.
4. A deterministic backfill query from `fanvue_users` and memory, with conflict/orphan reports.
5. A disposition/rollback plan for the unapplied Fanvue-dependent Telegram identity migration and its repository/service/models.
6. The neutral `UserContext` contract required by the gateway and DecisionEngine.
7. Read/write authority and feature-flag sequencing for every transition phase.
8. Disposable-database test cases proving a Telegram-only user can own memory and conversation history without any Fanvue row.
9. Current-database preflight queries and production rollback criteria.

Do not implement transport, KVIQA, commerce adapters, or DecisionEngine behavior during that task. The schema and backfill contract should be reviewed before any new migration is written.

