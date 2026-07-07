# FanvueChatbot Identity Discovery Report

**Scope:** Current identity behavior and the safest Telegram mapping insertion point  
**Status:** Analysis only; no code, schema, or Telegram implementation changes

## 1. Executive Summary

FanvueChatbot does not have one transport-neutral user identifier. Its effective canonical user identity is the pair:

```text
(fanvue_account_id, fanvue_users.id)
```

`fanvue_users.id` is the local database primary key for a fan. `fanvue_account_id` is the creator/account scope and must travel with it even though some repository methods query the local ID alone. The DecisionEngine serializes this pair as `"<fanvue_account_id>:<fanvue_users.id>"`. The memory system stores the local user ID as text and addresses memory using the same account/local-user pair.

The external Fanvue identity is a different value:

```text
(fanvue_account_id, fanvue_users.fanvue_user_uuid)
```

Fanvue API synchronization and webhooks identify users with this external UUID. `user_repository.py` and `realtime_decision_trigger_service.py` resolve that UUID to `fanvue_users.id` before invoking the DecisionEngine. That lookup is the existing identity bridge between Fanvue transport and the internal intelligence profile.

The most important discovery is that the name `fanvue_user_id` is overloaded:

- In the DecisionEngine, memory, chat threads, and many repositories, it means local `fanvue_users.id`.
- In monetization webhook processing, buyer intelligence, content unlocks, and some raw event records, it appears to mean the external Fanvue user UUID carried by the webhook.
- `buyer_memory_sync_repository.py` joins `buyer_intelligence.fanvue_user_id` directly to `user_memory.fanvue_user_id`, despite those values potentially belonging to different identifier domains.
- `decision_engine.py` writes the composite engine key into the `fanvue_user_uuid` field of the send log, which is a third semantic use of a Fanvue-named identifier.

This ambiguity is already a continuity risk and becomes critical when Telegram is introduced. Telegram must not be mapped directly to `user_memory`, buyer rows, usernames, conversation IDs, or the overloaded `fanvue_user_id` label.

The safest insertion point is a dedicated identity resolution boundary after a Telegram event has been authenticated, normalized, and deduplicated but before any conversation row is created or `DecisionEngine.process_message()` is called. It should resolve the stable Telegram numeric user ID to one existing canonical identity and return all three values explicitly:

```text
fanvue_account_id
local_fanvue_user_id       = fanvue_users.id
external_fanvue_user_uuid  = fanvue_users.fanvue_user_uuid
```

For Ava's single-account target, `fanvue_account_id` may be configured rather than dynamically selected, but it must remain part of every repository key. A Telegram contact without a verified Fanvue linkage must fail closed or remain pending; creating a second Telegram-only memory profile would break relationship, purchase, and ownership continuity.

## 2. Primary Identity Model

### 2.1 Identifier hierarchy

| Identifier | Domain | Current role | Canonical status |
|---|---|---|---|
| `fanvue_accounts.id` | Local database integer | Ava/creator account scope | Required scope, not a fan identity by itself |
| `fanvue_users.id` | Local database integer | Fan row primary key | Primary internal fan identifier |
| `fanvue_users.fanvue_user_uuid` | External Fanvue UUID/text | Fanvue API/webhook user identity | Primary external commerce identifier |
| Engine `user_id` | String `account_id:local_user_id` | DecisionEngine and MemoryService input | Serialized internal identity, not a database key |
| `username` / `display_name` | Mutable presentation data | Display and relationship sync metadata | Never safe for identity |
| `subscriber_id` | Not observed as a canonical key | Subscription state is attached to user/memory | Not an identity root |
| `chat_threads.id` | Local integer | Conversation/thread ownership | Conversation key, not person key |
| `fanvue_chat_uuid` | External Fanvue identifier | Fanvue conversation correlation | Transport conversation key only |
| `fanvue_message_uuid` | External Fanvue identifier | Fanvue message correlation/deduplication | Transport message key only |

### 2.2 Local user creation and resolution

`app/repositories/user_repository.py` establishes the principal identity behavior:

1. `get_user_by_account_and_fanvue_uuid()` resolves an external Fanvue UUID within a creator account.
2. `create_user()` inserts the account ID and external UUID and returns a row containing local `id`.
3. `get_or_create_user_with_memory()` creates or retrieves the user and ensures a `user_memory` row exists for `(fanvue_account_id, user["id"])`.
4. `get_user_by_account_and_id()` resolves the local pair used by the DecisionEngine.
5. `upsert_fan_relationship()` treats `(fanvue_account_id, fanvue_user_uuid)` as the external uniqueness boundary.

`app/services/realtime_decision_trigger_service.py` demonstrates the live conversion:

```text
webhook fanvue_user_id (external UUID)
  + fanvue_account_id
  -> SELECT fanvue_users.id
  -> engine key "fanvue_account_id:local_user_id"
  -> DecisionEngine.process_message()
```

This confirms that webhook `fanvue_user_id` and engine/local `fanvue_user_id` are not necessarily the same value, despite sharing a name.

### 2.3 DecisionEngine identity

`DecisionEngine._parse_engine_user_id()` splits the engine key into two integers. The engine then:

- loads creator configuration by `fanvue_account_id`;
- retrieves the user with `get_user_by_account_and_id(account_id, local_user_id)`;
- supplies the pair to memory, content, offer, ownership, relationship, and logging paths.

The engine therefore cannot accept a Telegram user ID directly. It requires the existing local user row and the Ava Fanvue account scope.

### 2.4 Primary identity conclusion

The practical primary identity is not `fanvue_user_uuid`, Telegram ID, subscriber ID, or conversation ID. It is:

```text
Canonical intelligence identity = fanvue_account_id + fanvue_users.id
Canonical commerce identity     = fanvue_account_id + fanvue_users.fanvue_user_uuid
```

Both must resolve to the same `fanvue_users` row. Telegram should be an additional external identity pointing at that row, not a replacement primary key.

## 3. Memory Identity Model

### 3.1 Memory ownership key

`app/repositories/memory_repository.py` addresses `user_memory` with:

```text
fanvue_account_id = integer account scope
fanvue_user_id    = string representation of fanvue_users.id
```

`_memory_user_id()` converts the supplied local ID to text. Reads, increments, updates, resets, and allowed-field mutations all filter by `fanvue_account_id` plus `fanvue_user_id = %s::text`.

`app/services/memory_service.py` receives the composite engine key, parses the two components, and delegates to the memory repository. This makes the engine key an address envelope around the real memory key rather than a new identity record.

### 3.2 State owned by that memory key

The single `user_memory` row owns or summarizes:

- inbound/outbound counts and last-message state;
- intent, engagement, routing, and behavior history;
- subscriber/follower and relationship state;
- buyer tier, PPV activity, average spend, and silent-buyer state;
- offer lifecycle, price resistance, and sales timing;
- content preferences, seen tags, outcomes, and session state;
- outreach state and buyer-session continuity;
- relationship and intimacy inputs consumed by downstream services.

Many relationship services are stateless evaluators over the loaded memory dictionary. They do not establish an independent person key. Preserving the memory row therefore preserves most relationship intelligence.

### 3.3 Relationship identity

Relationship identity is split across two synchronized locations:

- `fanvue_users` stores current Fanvue relationship facts such as `relationship_status`, `is_subscriber`, and `is_follower` on the local user row.
- `user_memory` stores corresponding conversational relationship fields under the account/local-user memory key.

`fanvue_relationship_sync_service.py` builds its upstream map by external `fanvue_user_uuid`. `upsert_fan_relationship()` then resolves/upserts the local user row under the account. During a decision, the engine reloads that local row and injects current relationship facts into memory behavior.

Telegram continuity therefore requires mapping to the existing local user, not reproducing relationship flags in a Telegram-specific record.

### 3.4 Memory preservation requirement

The Telegram mapping must yield the same engine key already used for that fan:

```text
telegram_user_id
  -> existing fanvue_users row
  -> "fanvue_account_id:fanvue_users.id"
  -> existing user_memory row
```

A new engine key based on Telegram ID would create or address a different profile and lose all accumulated relationship and sales context.

## 4. Buyer Intelligence Identity Model

### 4.1 Two buyer representations

Buyer intelligence currently exists in at least two forms:

1. Buyer summary columns on `fanvue_users`, updated by `realtime_buyer_repository.py` using local `fanvue_users.id`.
2. The `buyer_intelligence` table, addressed by `(fanvue_account_id, fanvue_user_id)` where the repository accepts `fanvue_user_id` as a string.

Content ownership/unlock intelligence is also represented through `content_usage_log`, commonly addressed by `(fanvue_account_id, fanvue_user_id)`.

### 4.2 External UUID flow in monetization

`monetization_event_normalizer_service.py` copies `event["fanvue_user_id"]` directly into the normalized event and initializes `local_user_id` to `None`. `realtime_monetization_event_service.py` passes that unqualified value into:

- `buyer_intelligence_repository.py` for purchase, tip, and subscription state;
- `content_unlock_repository.py` for unlock ownership;
- `buyer_memory_sync_service.py` for synchronization into `user_memory`;
- reaction, follow-up, and persistence pipelines.

The webhook normalizer elsewhere treats this event field as the external Fanvue user identity. No local `fanvue_users.id` resolution is visible in this monetization path before those writes.

### 4.3 Identity-domain collision

`buyer_memory_sync_repository.py` performs this conceptual join:

```text
user_memory.fanvue_account_id = buyer_intelligence.fanvue_account_id
user_memory.fanvue_user_id    = buyer_intelligence.fanvue_user_id
```

But `user_memory.fanvue_user_id` is the local integer ID serialized as text, while `buyer_intelligence.fanvue_user_id` may contain an external UUID. If production rows follow those observed call paths, buyer state will not synchronize to the intended memory row.

A similar risk exists for ownership:

- DecisionEngine/content ownership checks commonly supply the local user ID.
- Realtime unlock logging appears to supply the webhook's external UUID.
- Both query/write the same `content_usage_log.fanvue_user_id` label.

This report does not assert the contents of the live database, but the source contracts are inconsistent and must be validated against real row values before Telegram linking is designed.

### 4.4 Purchase and ownership preservation requirement

To preserve purchases, ownership, buyer tier, and subsequent conversation behavior, an identity resolution result must carry both identifier domains explicitly:

| Required value | Used for |
|---|---|
| `fanvue_account_id` | Ava account scope everywhere |
| `local_fanvue_user_id` | DecisionEngine, memory, local chat, relationship row |
| `external_fanvue_user_uuid` | Fanvue API, purchase webhook correlation, Media Link commerce identity |

Before implementation, sampled production data should prove which identifier is actually stored in `buyer_intelligence.fanvue_user_id`, `content_usage_log.fanvue_user_id`, and `fanvue_monetization_events.fanvue_user_id`. Any Telegram mapping based on the column name alone is unsafe.

## 5. Repository Dependencies

### 5.1 Identity-critical repositories

| Repository | Identity used | Dependency/role |
|---|---|---|
| `user_repository.py` | Account + external UUID; account + local ID | Core external-to-local resolution and memory creation |
| `fanvue_user_repository.py` | Account + external UUID | Fanvue relationship/user synchronization |
| `memory_repository.py` | Account + local ID serialized as text | Authoritative conversation and relationship memory |
| `buyer_intelligence_repository.py` | Account + string `fanvue_user_id` | Purchase, tip, subscription, and buyer-tier state; identifier domain is ambiguous at callers |
| `buyer_memory_sync_repository.py` | Account + string `fanvue_user_id` | Joins buyer and ownership state into memory; vulnerable to local/UUID mismatch |
| `realtime_buyer_repository.py` | Local user ID only | Updates buyer summary columns on `fanvue_users`; lacks account filter |
| `content_ownership_repository.py` | Account + string `fanvue_user_id` | Checks owned content from usage log |
| `content_unlock_repository.py` | Account + string `fanvue_user_id` | Writes unlock/purchase ownership from monetization path |
| `content_usage_repository.py` | Account + user ID | Logs content targeting, delivery, and outcomes |
| `monetization_event_repository.py` | Account + event `fanvue_user_id` | Persists Fanvue commerce events and external event deduplication |
| `chat_message_repository.py` | Account + local user ID + thread ID | Canonical conversation threads and messages |
| `chat_reset_repository.py` | Fanvue account/user/chat identifiers | Resets conversation data using Fanvue-specific ownership |
| `realtime_chat_sync_repository.py` | Account + external user UUID + external message UUID | Raw/live Fanvue message ingestion and deduplication |
| `fanvue_message_repository.py` | Account + external user/message UUIDs | Fanvue-specific message persistence and latest-message lookup |
| `fanvue_message_sync_repository.py` | Fanvue account/user/thread/message identifiers | Fanvue message synchronization state |
| `send_log_repository.py` | Account + local ID + `fanvue_user_uuid` label | Decision/send audit; engine currently supplies composite key to UUID field |

### 5.2 User-targeted automation repositories

These repositories also depend on Fanvue account/local or ambiguously named user IDs and must receive resolved canonical identity rather than Telegram IDs:

- `automated_reaction_repository.py`
- `delayed_message_queue_repository.py`
- `outreach_log_repository.py`
- `outreach_queue_repository.py`
- `qualification_ppv_repository.py`
- `ppv_broadcast_repository.py`
- `mass_ppv_campaign_repository.py`

They affect proactive delivery, follow-ups, reaction history, targeting, and queue ownership. Even if initial Telegram scope is inbound text only, they must be inventoried before proactive messages are switched to Telegram.

### 5.3 Account-scoped repositories

The following repositories use Fanvue account identity primarily to scope creator content or operations rather than to identify a fan:

- `fanvue_account_repository.py`
- `creator_profile_repository.py`
- `content_repository.py`
- `cms_fanvue_upload_repository.py`
- `wall_post_repository.py`
- `webhook_event_repository.py`

They should continue using Ava's `fanvue_account_id`. Telegram transport should not replace this commerce/persona scope.

### 5.4 Conversation ownership

Conversation state currently has two parallel shapes:

- `fanvue_chat_messages` is Fanvue-transport-specific and uses account, external Fanvue user UUID, and Fanvue message UUID.
- `chat_threads` and `chat_messages` use account, local user ID, local thread ID, and optional Fanvue external chat/message IDs.

The latter is the safer intelligence-history anchor because it already points to the canonical local user. Telegram external chat and message IDs must not be placed into fields whose names and uniqueness semantics explicitly mean Fanvue UUIDs without a separately reviewed transport-neutral design.

## 6. Recommended Telegram Mapping Strategy

### 6.1 Mapping invariant

For the single Ava deployment, the required logical mapping is:

```text
(Ava Telegram account identity, telegram_user_id)
    -> exactly one fanvue_accounts.id
    -> exactly one fanvue_users.id
    -> exactly one fanvue_users.fanvue_user_uuid
```

Because there is one Telegram account and one Fanvue account, the managed Telegram account may be fixed configuration. The fan's stable numeric Telegram ID must still be the external key; username, display name, phone visibility, and chat title are not identity evidence.

### 6.2 Resolution result

The boundary should use explicit names rather than a generic `user_id`:

```text
telegram_user_id
telegram_chat_id
fanvue_account_id
local_fanvue_user_id
external_fanvue_user_uuid
engine_user_id = "fanvue_account_id:local_fanvue_user_id"
mapping_status
```

This naming prevents external UUIDs, local IDs, Telegram IDs, and composite engine keys from being silently substituted for one another.

### 6.3 Safest insertion point

Insert identity resolution in the future Telegram inbound flow at this point:

```text
Telegram update authentication
  -> event normalization
  -> inbound deduplication
  -> IDENTITY RESOLUTION
  -> resolve/create canonical conversation thread
  -> load normalized history
  -> DecisionEngine.process_message(engine_user_id, ...)
```

The resolver should sit outside the Telegram client and outside the DecisionEngine. It should not be embedded in `memory_repository.py`, because all intelligence repositories already assume that canonical identity resolution has occurred. It should not reuse `RealtimeDecisionTriggerService.trigger_for_inbound_message()` unchanged because that method expects a Fanvue webhook UUID and also owns Fanvue-specific persistence and sending.

### 6.4 Linking rules

1. Link Telegram only to an existing `fanvue_users` row when continuity with Fanvue purchases and ownership is required.
2. Verify the external Fanvue identity through an explicit linking flow; never infer it from Telegram and Fanvue usernames.
3. Return pending/unmapped for unknown Telegram IDs and do not invoke the DecisionEngine under a fabricated Telegram-based engine key.
4. Fail closed on duplicate, conflicting, or incomplete mappings.
5. Preserve `fanvue_account_id` in every lookup even though Ava currently has only one account.
6. Confirm forward lookup for inbound Telegram messages and reverse lookup for approved outbound follow-ups.
7. Do not create separate Telegram memory, buyer, relationship, or ownership records.
8. Keep Fanvue commerce webhooks active and resolve their external UUID to the same local user before synchronizing buyer state.

### 6.5 Discovery required before schema design

Before any database proposal is approved:

- inspect constraints and data types for `fanvue_users`, `user_memory`, `buyer_intelligence`, `content_usage_log`, `chat_threads`, `chat_messages`, and `fanvue_monetization_events`;
- sample real values to determine whether each `fanvue_user_id` column contains a local integer-as-text or an external UUID;
- identify duplicate or orphaned `fanvue_users` and memory rows;
- prove `(fanvue_account_id, fanvue_user_uuid)` uniqueness;
- prove one memory row per `(fanvue_account_id, local user ID)`;
- test buyer/ownership-to-memory joins for known purchasers;
- identify how a Fanvue Media Link purchase proves the same person who initiated the Telegram conversation.

No table design should precede that validation.

## 7. Migration Risks

| Risk | Severity | Why it exists | Required control |
|---|---:|---|---|
| External/local ID collision | Critical | `fanvue_user_id` names both a local integer and external UUID | Explicit typed/named identity result; audit real data before design |
| Duplicate intelligence profile | Critical | Telegram ID used as a new engine/memory key | Map only to existing local user for preserved continuity |
| Incorrect identity merge | Critical | Username or weak linking connects two people | Verified link, immutable numeric Telegram ID, fail closed |
| Buyer-memory disconnect | Critical | Buyer table may use external UUID while memory uses local ID text | Resolve commerce UUID to local ID and validate joins |
| Ownership mismatch or resale | Critical | Unlock writes and ownership reads may use different ID domains | Normalize ownership identity contract and test known purchasers |
| Purchase attribution gap | Critical | Fanvue checkout knows Fanvue user, Telegram knows Telegram user | Verified bidirectional identity link before relying on sales continuity |
| Relationship fragmentation | High | New Telegram profile misses Fanvue subscriber/follower and memory state | Resolve existing `fanvue_users` row before every decision |
| Account-scope omission | High | Some methods query local ID alone | Require account/local pair at boundary and repository review |
| Conversation-history split | High | Telegram messages enter a separate or Fanvue-specific store | Anchor history to canonical local user and defined transport IDs |
| Duplicate event mutation | High | Telegram retries run the brain twice | Deduplicate before identity resolution/DecisionEngine invocation |
| Proactive delivery misrouting | High | Queues currently assume Fanvue user/channel | Defer channel switch until reverse identity and routing are proven |
| Send-log audit corruption | Medium-High | Composite engine key is logged as a Fanvue UUID | Treat audit fields as untrusted semantics until corrected design is reviewed |
| Mutable username reliance | High | Telegram/Fanvue usernames can change or collide | Metadata only; never use for identity matching |
| Unmapped Telegram fan | Medium-High | No verified Fanvue identity exists yet | Defined pending/onboarding behavior with no memory mutation |
| Live schema assumptions | High | Repository code does not prove deployed constraints/data domains | Read-only schema and production-data audit before migration design |

The highest-risk gate is not Telegram authentication or message receipt. It is proving that one Telegram fan, one local `fanvue_users` row, one memory row, and one Fanvue commerce UUID are the same person. Until that invariant is demonstrated against the actual database and purchase flow, Telegram must not invoke the live DecisionEngine or deliver sales offers tied to preserved buyer state.

No code was modified, no Telegram component was implemented, and no database table or column was created as part of this discovery.

