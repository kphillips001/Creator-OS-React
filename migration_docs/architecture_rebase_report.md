# Telegram-Primary Architecture Rebase Report

**Status:** Architecture analysis only  
**New premise:** Telegram is the primary user identity; commerce and vault providers are replaceable integrations

## 1. Executive Summary

The migration architecture must be rebased. The previous roadmap assumed that every Telegram user would map to an existing `fanvue_users` row and that Fanvue remained the source of truth for identity, purchases, ownership, and hosted media. That assumption is now invalid.

The target architecture should be:

```text
Telegram user
  -> platform-neutral core user
  -> FanvueChatbot intelligence and memory
  -> optional CRM projection in KVIQA
  -> replaceable commerce provider
       - Fanvue
       - DropFans
       - future providers
  -> provider-neutral entitlement
  -> replaceable vault/media provider
```

Telegram should become the **authoritative external identity** for conversational users. However, raw `telegram_user_id` should not become the database-wide primary key. The system should introduce a platform-neutral `core_user_id` as the canonical internal identity and require one active Telegram identity for Telegram-originated users. This distinction matters:

- Telegram determines who the conversational user is.
- `core_user_id` owns memory, relationship state, buyer intelligence, conversations, and entitlements.
- Commerce providers attach optional customer identities and transactions to that core user.
- KVIQA attaches an optional CRM identity and may own CRM workflow fields.
- Vault providers attach assets and delivery references, not user identity.

This allows a user to exist, converse, build memory, and receive offers without ever having a Fanvue account. A Fanvue or DropFans identity may appear only after checkout, and unresolved commerce events can be quarantined until attribution is proven.

The existing FanvueChatbot intelligence remains valuable and should be preserved behaviorally. Its identity plumbing cannot remain unchanged: the DecisionEngine, memory repositories, chat repositories, buyer/ownership stores, and service contracts currently assume Fanvue-shaped keys. The rebase requires a controlled identity decoupling—not a rewrite of the behavioral engine.

The aligned Telegram Identity Foundation remains useful as validated engineering work, but its current invariant is obsolete. Its UUID handling, constraint discipline, exception translation, rollback support, repository patterns, and disposable-database tests should be reused. Its requirement that Telegram resolve to `fanvue_accounts + fanvue_users` should be retired, and its migration should **not** be applied to the application database.

## 2. Revised Identity Architecture

### 2.1 Canonical identity decision

**Should Telegram User ID become the canonical identity?**

It should become the canonical **external conversational identity**, but not the canonical database primary key.

Recommended identity layers:

| Layer | Recommended identity | Authority |
|---|---|---|
| Internal person | `core_user_id` | FanvueChatbot core database |
| Primary conversational identity | Telegram numeric user ID | Telegram |
| Conversation destination | Telegram chat ID | Telegram transport metadata |
| CRM identity | KVIQA contact/customer ID | KVIQA mapping |
| Commerce customer identity | Provider + external customer ID | Fanvue, DropFans, or another provider |
| Vault identity | Provider + external asset ID | KVIQA/Fanvue/other vault |

Using `telegram_user_id` directly as every foreign key would replace Fanvue coupling with Telegram coupling. A neutral internal key allows future identity recovery, merges, deletion, another communication channel, and multiple commerce providers without rewriting memory again.

### 2.2 Recommended logical model

The following are logical architecture concepts, not authorized table definitions:

#### Core user

```text
core_user
  id                     platform-neutral internal key
  status                 active / suspended / merged / deleted
  created_at
  updated_at
```

This record may be created when a Telegram user first passes the approved onboarding/consent gate. It must not require a Fanvue, DropFans, or KVIQA record.

#### External identity

```text
external_identity
  core_user_id
  provider               telegram / fanvue / dropfans / kviqa / future
  provider_user_id       provider-native immutable identifier
  provider_account_ref   optional managed account context
  status
  verified_at
  verification_method
  metadata               mutable display data only
```

For the current single-Ava system, this does not require SaaS tenancy, a creator registry, or multi-creator provisioning. Provider/account scope may still be retained where an external API needs it, but it must not own the user.

#### Telegram identity

Telegram identity should be a constrained specialization of external identity or a narrow transport table containing:

```text
core_user_id
telegram_user_id         required, stable numeric identity
telegram_chat_id         current outbound destination
is_active
created_at
updated_at
```

Username, display name, and phone visibility are metadata and never identity evidence.

### 2.3 Intelligence ownership

These systems should ultimately reference `core_user_id`:

- user memory;
- relationship and intimacy state;
- buyer intelligence;
- engagement and offer history;
- conversation threads/messages;
- content preferences;
- entitlements and ownership;
- outreach/follow-up state;
- delivery and attribution records.

Existing Fanvue-linked data must be backfilled to a core user through the current `fanvue_users.id` and external UUID. New Telegram-only users receive a core user and core-owned intelligence without a fabricated Fanvue row.

### 2.4 Transition strategy

The safest transition is additive:

1. Introduce a neutral core user identity.
2. Map each existing `fanvue_users` row to one core user.
3. Attach the Fanvue UUID as an optional commerce identity.
4. Add `core_user_id` to identity-dependent stores while preserving legacy columns temporarily.
5. Backfill and validate memory, history, buyer, and ownership records.
6. Route new Telegram users directly to core users.
7. Move reads/writes to core identity behind compatibility services.
8. Retire Fanvue-required keys only after parity and rollback gates pass.

Do not manufacture Fanvue users or UUIDs for Telegram-only contacts. Do not key new memory by Telegram ID alone.

## 3. Revised Commerce Architecture

### 3.1 Commerce boundary

Commerce must become an adapter layer with a provider-neutral contract. The intelligence engine decides **whether and what to offer**. A commerce orchestrator decides **which configured provider can sell it and how to create or retrieve checkout**.

```text
DecisionEngine offer decision
  -> provider-neutral offer request
  -> commerce orchestrator
  -> selected provider adapter
       Fanvue / DropFans / future
  -> checkout reference or payment link
  -> Telegram delivery
  -> provider webhook or reconciliation
  -> normalized commerce event
  -> entitlement and buyer-state update for core_user_id
```

### 3.2 Provider-neutral concepts

The core should own these concepts independently of a provider:

- `offer_id`: the commercial proposition selected by intelligence;
- `product_id` or `content_asset_id`: what is being sold;
- `checkout_session_id`: internal attempt/correlation identity;
- `commerce_provider`: Fanvue, DropFans, or another adapter;
- `provider_checkout_id` and URL: provider-specific references;
- `transaction_id`: internal normalized transaction;
- `provider_event_id`: provider idempotency key;
- `entitlement_id`: durable internal ownership/access result;
- `core_user_id`: the person receiving buyer and ownership state.

Provider URLs, media UUIDs, event payloads, statuses, and customer IDs stay inside provider adapters or provider binding records. They must not leak into DecisionEngine identity.

### 3.3 Commerce adapter contract

Each provider adapter should eventually support only the capabilities it actually offers:

- create or resolve checkout/payment link;
- attach internal correlation metadata where supported;
- verify webhook authenticity;
- normalize purchase, refund, subscription, tip, and cancellation events;
- resolve provider customer identity;
- fetch/reconcile transaction state;
- expose provider capability flags;
- return structured retryable/permanent failures.

Capability differences should be explicit. The core must not assume that DropFans implements Fanvue media links, that every provider supports tips/subscriptions, or that every webhook contains the same customer fields.

### 3.4 Attribution and identity

A commerce customer identity is optional and subordinate to `core_user_id`.

Preferred attribution sequence:

1. Create an internal checkout session for `core_user_id` and offer.
2. Generate a short-lived signed correlation token or provider metadata reference.
3. Send the provider checkout URL through Telegram.
4. Receive and verify the provider event.
5. Match the provider checkout/event to the internal checkout session.
6. Attach or verify the provider customer identity.
7. Create the normalized transaction and entitlement idempotently.
8. Update core-owned buyer intelligence.

If attribution is ambiguous, quarantine the event. Never merge by username, display name, or purchase timing alone.

### 3.5 Commerce source of truth

- The provider is authoritative for its payment status and refunds.
- The core is authoritative for normalized checkout correlation, cross-provider buyer intelligence, and entitlements used by the chatbot.
- No single provider is authoritative for the user's identity or total relationship.

## 4. Revised Vault Architecture

### 4.1 Vault ownership decision

KVIQA may become the primary vault, but vault access must remain provider-neutral. Fanvue may still host media associated with a Fanvue checkout. Other assets may live in KVIQA or a future provider.

The core should own a neutral content catalog:

```text
content_asset
  internal asset ID
  classification and safety metadata
  content tags/themes/intensity
  monetization metadata
  active/retired state

vault_binding
  content_asset_id
  vault_provider
  provider_asset_id
  delivery capability
  preview reference
  status/version metadata
```

The DecisionEngine selects an internal asset or content class. A vault service resolves an eligible provider binding. It should not make relationship, offer, or buyer decisions.

### 4.2 Vault adapter responsibilities

- register/synchronize provider assets;
- fetch safe metadata and approved previews;
- resolve provider delivery or checkout references;
- validate asset availability;
- enforce access/entitlement requirements;
- avoid exposing paid originals directly through Telegram unless explicitly approved;
- report provider failures without changing intelligence state.

### 4.3 Entitlement separation

Vault location and purchase provider are independent dimensions. A Fanvue payment may grant access to a KVIQA-hosted asset, or a DropFans payment may grant an internal entitlement. The entitlement should point to the internal asset and transaction, with provider references retained as evidence.

This prevents provider-specific “ownership” tables from becoming the only access truth.

## 5. KVIQA Integration Strategy

### 5.1 Recommended ownership model

KVIQA may be the primary **CRM and vault platform**, but should not become the canonical identity or conversational intelligence database.

Recommended ownership:

| Data | Authority |
|---|---|
| Internal user identity | FanvueChatbot core (`core_user_id`) |
| Telegram identity and destination | Telegram identity adapter/core mapping |
| AI memory and relationship runtime | FanvueChatbot intelligence layer |
| CRM tags, tasks, segments, operator notes | KVIQA |
| Commerce payment state | Individual commerce provider |
| Cross-provider transactions/entitlements | FanvueChatbot core |
| Vault asset binaries/provider metadata | KVIQA or selected vault provider |
| Internal content classification/offer eligibility | FanvueChatbot core |

### 5.2 Integration pattern

Use a KVIQA adapter keyed by a mapping from `core_user_id` to KVIQA contact ID. Synchronize only explicitly owned fields:

- send core identity reference, Telegram lifecycle facts, buyer summaries, and consent state to KVIQA;
- receive operator-owned CRM tags, tasks, notes, and campaign eligibility from KVIQA;
- define conflict rules per field rather than “last write wins” across whole profiles;
- process KVIQA webhooks/events idempotently;
- tolerate KVIQA downtime without blocking inbound Telegram conversation or memory access.

KVIQA should receive summaries or projections where possible, not become a second message-level memory engine.

### 5.3 KVIQA vault strategy

Treat KVIQA vault support as one implementation of the vault adapter contract. Store KVIQA asset IDs in provider bindings. Do not embed KVIQA-specific asset IDs in offer logic or personas.

## 6. Fanvue Integration Strategy

Fanvue should be reduced to one or more optional adapters:

- commerce/payment adapter;
- checkout or Media Link adapter;
- payment webhook/reconciliation adapter;
- optional media/vault adapter while content remains hosted there.

Fanvue should no longer own:

- canonical user identity;
- Telegram onboarding eligibility;
- memory creation;
- relationship profile creation;
- conversation identity;
- cross-provider buyer tier;
- global content entitlement.

An existing Fanvue user UUID becomes an optional external commerce identity mapped to `core_user_id`. A Telegram user without one remains a fully valid user.

Existing Fanvue webhook verification, token management, Media Link creation, purchase normalization, and API clients may remain useful after isolation behind a provider adapter. Existing Fanvue chat ingestion/delivery should remain outside the target conversation path.

Fanvue-specific buyer and ownership tables cannot remain the only source for core behavior. Their validated data should be projected into provider-neutral transactions, entitlements, and buyer aggregates during transition.

## 7. DropFans Integration Strategy

DropFans should be introduced only through the same commerce-provider boundary. No DropFans capability should be assumed until its API, authentication, checkout, webhook, customer identity, refund, and media behavior are separately audited.

The eventual adapter should translate DropFans concepts into the same normalized contracts:

```text
create checkout request
provider checkout result
verified provider event
normalized transaction/refund/subscription event
provider customer binding
entitlement result
```

If DropFans lacks a required webhook, a bounded reconciliation worker may poll provider transaction state. That difference belongs inside the adapter and capability model, not in the DecisionEngine.

DropFans IDs must never be stored in columns named for Fanvue, and DropFans users must never require `fanvue_users` rows.

## 8. Components To Keep

### Intelligence and behavior

- DecisionEngine behavior, routing, engagement, offer timing, relationship shaping, safety, and response generation.
- Memory categories and continuity behavior.
- Buyer classification and value logic as provider-neutral business rules.
- Relationship, intimacy, whale, emotional, dependency, and recovery services.
- Persona and creator-profile behavior for Ava.
- Content selection and suppression logic, after identity/ownership inputs become neutral.

### Transport/reference mechanics

- Telegram stable numeric user ID usage.
- Private-message filtering, update normalization, reply correlation, reconnect lifecycle, typing, delivery results, and idempotency concepts.
- The narrow adapter boundary and rejection of the reference Telegram repository's competing business logic.
- Bot Token recommendation and explicit consent/security requirements, unless a separately approved policy review changes it.

### Engineering patterns from the Identity Foundation

- Immutable domain results with explicit identifier names.
- Repository/service separation.
- UUID normalization where providers use UUIDs.
- Schema qualification.
- Database uniqueness and integrity enforcement.
- Persistence-to-domain exception translation.
- Active/inactive lifecycle handling.
- Forward and rollback migrations.
- Disposable restore and real PostgreSQL integration tests.

### Commerce capabilities worth adapting

- Fanvue OAuth/token handling.
- Fanvue webhook authentication and idempotency.
- Media Link/checkout creation.
- Normalized purchase/tip/subscription semantics where they remain useful.
- Delivery guards, audit logging, and retry principles.

## 9. Components To Revise

### Identity Foundation

The current `telegram_identity_map` design must be superseded before application:

- remove the requirement for `fanvue_account_id`;
- remove the requirement for `local_fanvue_user_id`;
- remove the requirement for `external_fanvue_user_uuid`;
- map Telegram to `core_user_id` instead;
- make Fanvue identity a separate optional provider mapping;
- remove the trigger that requires a matching `fanvue_users` row;
- revise `CanonicalTelegramIdentity` so it does not contain mandatory Fanvue fields;
- revise repository/service duplicate rules around core identity.

The current migration has not been applied to `fanvue_chatbot`, which makes this rebase substantially safer. It should remain unapplied and be replaced through a reviewed migration plan rather than edited into production history after application.

### Intelligence identity plumbing

- `DecisionEngine._parse_engine_user_id()` and its Fanvue-shaped composite key.
- `MemoryService` parsing of `fanvue_account_id:fanvue_user_id`.
- memory ownership columns and repositories.
- user lookup through `fanvue_users` before every decision.
- creator/account resolution that conflates creator scope with commerce provider account.
- send logs containing Fanvue-named identity fields.

Behavior should remain stable while identity access is refactored behind a neutral context contract.

### Persistence and history

- `user_memory` must gain neutral ownership and allow Telegram-originated users.
- chat threads/messages must use `core_user_id` and transport-neutral external IDs.
- buyer intelligence must aggregate across providers by `core_user_id`.
- content usage and ownership must stop overloading `fanvue_user_id`.
- proactive queues and delivery records must route by channel/provider binding.

### Commerce and vault

- Fanvue monetization events must normalize into provider-neutral transactions.
- Fanvue ownership must become an entitlement projection, not global truth.
- offer/content records must reference internal product/asset IDs.
- vault lookup must use a provider adapter rather than Fanvue fields.
- post-purchase reactions must target the core user and active conversation channel.

### Prior reports superseded

The following earlier conclusions are explicitly retired:

- every Telegram user must map to an existing Fanvue user;
- no Telegram-only user may exist;
- `fanvue_users.id` remains the permanent canonical user;
- Fanvue remains the sole commerce/ownership source of truth;
- Fanvue Media Links are the only monetization path;
- identity implementation should precede a neutral core-user model.

Earlier audits remain valid as descriptions of the current code and as inventories of reusable intelligence and coupling.

## 10. Updated Migration Roadmap

### Phase 0 — Rebase freeze

- Mark the previous Fanvue-primary identity roadmap as superseded.
- Do not apply `telegram_identity_map` in its current Fanvue-dependent form.
- Freeze behavioral regression fixtures for DecisionEngine and memory.
- Confirm the single-Ava, non-SaaS scope.

### Phase 1 — Neutral identity contract

- Define `core_user_id`, primary Telegram identity, optional provider identities, merge/deletion semantics, and consent lifecycle.
- Define creator/persona context separately from commerce account context.
- Define unknown Telegram user creation without Fanvue.
- Produce schema and transition design only.

### Phase 2 — Data ownership and compatibility map

- Inventory every Fanvue-shaped identity read/write.
- Define a neutral `UserContext`/identity result consumed by intelligence services.
- Map current `fanvue_users` rows to core users for backfill.
- Define additive changes to memory, chat, buyer, ownership, queues, and logs.
- Define rollback and dual-read/write boundaries.

### Phase 3 — Neutral identity persistence

- Create core users and provider identity mappings.
- Backfill existing Fanvue users and validate one-to-one relationships.
- Create Telegram-first user lifecycle.
- Do not run Telegram transport yet.

### Phase 4 — Intelligence ownership migration

- Add/backfill `core_user_id` across memory and conversation state.
- Adapt identity access around DecisionEngine while preserving behavioral outputs.
- Support a core user with no Fanvue mapping.
- Run golden behavior and memory-delta comparisons.

### Phase 5 — Provider-neutral commerce and entitlement contracts

- Define normalized checkout, transaction, refund, subscription, tip, customer-binding, and entitlement models.
- Build adapter interfaces and idempotency rules.
- Define unresolved-event quarantine and reconciliation.
- Keep existing providers disabled behind the new boundary initially.

### Phase 6 — Fanvue adapter extraction

- Wrap existing Fanvue payment/Media Link/webhook behavior behind the commerce contract.
- Normalize existing Fanvue customer identities to optional provider bindings.
- Prove purchase -> transaction -> entitlement -> buyer-memory continuity for a core user.

### Phase 7 — Vault and KVIQA integration design

- Establish neutral content assets and vault bindings.
- Define KVIQA CRM field ownership and synchronization.
- Implement KVIQA only after its API/reference audit and contract approval.

### Phase 8 — Telegram transport

- Implement selected Bot Token authentication and one Ava runtime.
- Receive/deduplicate private messages.
- Resolve or create the Telegram-primary core user.
- Invoke the neutral intelligence gateway.
- Deliver text and provider checkout links with delivery tracking.

### Phase 9 — Controlled commerce rollout

- Enable one provider and allowlisted users.
- Verify checkout attribution, provider event idempotency, entitlement creation, buyer updates, and next-message continuity.
- Prove rollback without losing Telegram identity or memory.

### Phase 10 — DropFans adapter

- Audit DropFans capabilities.
- Implement only the approved provider adapter.
- Run the same contract and reconciliation suite used for Fanvue.
- Enable provider selection through configuration/capabilities, not engine branching.

### Phase 11 — Cutover and cleanup

- Make Telegram the primary conversation channel.
- Retire Fanvue chat triggers without disabling payment webhooks.
- Remove legacy Fanvue identity requirements only after sustained parity.
- Treat destructive cleanup as a separate reviewed migration.

## 11. Recommended Next Task

The next task should be a **Platform-Neutral Core Identity and Data Ownership Design**—planning only.

It should deliver:

1. A proposed `core_user`, external identity, and Telegram identity schema.
2. Exact lifecycle rules for Telegram-first user creation, deactivation, merge, deletion, and recovery.
3. A field-by-field ownership map for memory, relationship, buyer, conversation, CRM, commerce, and vault data.
4. An inventory of every current repository/service keyed by Fanvue identity.
5. A compatibility contract for supplying neutral user context to DecisionEngine without changing behavior.
6. A backfill plan from `fanvue_users` and `user_memory` to core users.
7. A disposition plan for the unapplied Fanvue-dependent Telegram identity migration and related repository/service code.
8. Rollback, dual-read/write, and validation gates.
9. Explicit proof that a Telegram user with no Fanvue, DropFans, or KVIQA identity can own memory and complete a normal conversation.

Do not implement Telegram transport or a commerce provider during that task. The neutral identity contract must be settled first because it now determines every downstream memory, CRM, commerce, entitlement, and vault boundary.

