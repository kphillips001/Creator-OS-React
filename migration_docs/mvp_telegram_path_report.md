# MVP Telegram Path Report

**Status:** Analysis only  
**Objective:** Telegram -> Ava Brain -> Fanvue Media Link -> Sale  
**Scope:** One Ava identity, one Telegram bot, one Fanvue account

## 1. Executive Summary

The fastest credible MVP is a thin Telegram Bot API worker inside the FanvueChatbot runtime. It should receive private text messages, convert the Telegram user ID into a deliberately temporary legacy-compatible engine key, call the existing synchronous `DecisionEngine.process_message()`, and send the returned response. When the engine authorizes a close and selects content with a verified Fanvue Media Link, the worker sends that exact link through Telegram.

This path does **not** require the Core User migration, KVIQA, DropFans, multi-channel abstractions, Telegram-specific intelligence, or a second chatbot brain. It also should not import the reference Telegram repository's funnel, GPT, timing, or database logic. Those systems compete with Ava's existing brain.

The minimum revenue loop is:

```text
User starts Ava bot and sends private text
  -> Telegram long-polling worker
  -> validate, normalize, and serialize per Telegram user
  -> temporary engine key: <AVA_FANVUE_ACCOUNT_ID>:<negative Telegram user ID>
  -> existing MemoryService + DecisionEngine
  -> response text + engine-authorized offer
  -> verified, pre-created Fanvue Media Link
  -> Telegram reply
  -> user completes purchase on Fanvue
```

The repository already provides the difficult middle: persona loading, message classification, memory mutation, relationship/intimacy behavior, offer timing, content selection, pricing guidance, safety gates, and response generation. The MVP work is primarily transport glue, a bounded compatibility identity, deterministic Media Link handling, and tests.

Two limitations must be accepted explicitly:

1. A new Telegram user has no existing Fanvue customer identity, subscriber state, purchase history, or cross-platform buyer continuity. They begin as a cold/unknown user while still receiving the existing behavioral logic.
2. A completed Fanvue sale is not automatically attributable back to the temporary Telegram memory key. First-sale validation can use a dedicated Media Link and Fanvue reporting/manual reconciliation. Automatic post-purchase memory updates require a later signed attribution/mapping design.

Estimated effort is **2-3 engineering days for a controlled happy-path demo** and **5-8 engineering days for an allowlisted, revenue-capable MVP** with failure handling and tests. A generally available production service is larger and should not be confused with this experiment.

## 2. Recommended MVP Architecture

### 2.1 Runtime shape

Use one process boundary within the FanvueChatbot project:

```text
Telegram Bot API (one Ava bot)
        |
        | private inbound text/update
        v
Telegram MVP worker
  - bot-token authentication
  - long polling
  - allowlist/consent gate
  - update filtering
  - per-user lock
  - retry/error handling
        |
        | engine_user_id + message
        v
Existing FanvueChatbot
  MemoryService
        -> DecisionEngine.process_message()
        -> creator profile / Ava persona
        -> classifiers, relationship and offer logic
        -> ContentService
        -> GPTService
        |
        | response + offer/content metadata
        v
Telegram response formatter
  - plain text
  - approved Fanvue URL only when authorized
  - no paid media file delivery
        |
        v
Fanvue Media Link checkout -> sale
```

Long polling is the minimum operational path for one bot and one worker. It avoids public webhook infrastructure during hypothesis validation. Bot Token authentication remains preferable to copying the Telethon user-session login because it has a smaller credential/recovery surface and a clearer automation posture. The user must initiate the bot conversation.

### 2.2 Message flow

1. Receive a Bot API update and accept only a user-initiated private text message.
2. Reject bots, groups, channels, empty messages, unsupported media, edits, and stale/duplicate updates.
3. Read the stable numeric `from.id`; treat username/display name as metadata only.
4. Acquire a per-Telegram-user lock so two messages cannot mutate memory concurrently.
5. Resolve the configured Ava Fanvue account and verify an active creator profile exists.
6. Derive the temporary engine key and call `MemoryService.get_or_create_user_memory()`.
7. Run blocking `DecisionEngine.process_message()` outside the async event loop with a timeout.
8. Validate the engine result and extract `response`, `send_offer`, and `offer.content.fanvue_link`.
9. Send the conversational response. Include/send the approved link only under the Media Link rules in section 7.
10. Record delivery outcome and commit the polling offset only after the update has reached its defined terminal state.

The worker must not call `OneOnOnePPVSendService` for Telegram. That service creates a paid Fanvue chat payload and calls Fanvue's `/chats/{user_uuid}/message` endpoint; it does not create a Telegram-deliverable Media Link.

### 2.3 MVP boundaries

In scope:

- private text conversation with Ava;
- one configured bot and creator profile;
- existing DecisionEngine and memory behavior;
- existing offer/content selection;
- delivery of verified Fanvue Media Links;
- allowlisted rollout, logging, and safe shutdown.

Out of scope:

- Core User schema/backfill;
- Fanvue/Telegram account linking;
- post-purchase automatic buyer-memory synchronization;
- direct paid media delivery in Telegram;
- proactive outreach or cold messaging;
- Telegram groups, media ingestion, voice, edits, reactions, or commands beyond onboarding/help;
- KVIQA, DropFans, multi-creator support, and transport abstraction frameworks.

## 3. Components To Reuse

### 3.1 FanvueChatbot: reuse directly

| Component | MVP use | Notes |
|---|---|---|
| `app/engine/decision_engine.py` | Canonical conversation, relationship, safety, and offer decisions | Call `process_message(user_id, message, chat_history=[])`; do not duplicate logic in Telegram |
| `app/services/memory_service.py` | Create/load/update the existing memory row | Requires the temporary `account_id:user_id` key |
| `app/repositories/memory_repository.py` | Existing durable memory persistence | Its account scope is useful; its Fanvue-named user field is accepted temporarily only |
| `app/services/gpt_service.py` | Ava response generation and existing offer-link prompt injection | Already reads selected content's `fanvue_link` |
| `app/services/content_service.py` | Select eligible tease/VIP/premium content | Requires `fanvue_account_id` and a truthy legacy user ID in memory |
| Existing classifiers and relationship/intimacy services | Preserve Ava behavior | No Telegram forks |
| Creator profile repository/configuration | Load Ava persona | `DecisionEngine` blocks without an active creator profile |
| Existing content catalog/CMS selection | Source offer copy, price, and link metadata | Only records with verified live Media Links are MVP-eligible |
| Global safety/config services | Preserve current kill switches and send policy | Telegram must add its own delivery allowlist/rate controls |

The existing buyer and relationship algorithms can operate for Telegram users, but a new Telegram identity starts without verified Fanvue purchase/subscriber facts. “Reuse buyer intelligence” means reuse its rules and memory fields, not invent historical commerce data.

### 3.2 Telegram reference repository: reuse as patterns only

Useful patterns from `C:\Telegram Chatbot`:

- stable numeric sender ID rather than username;
- private-message filtering;
- one long-lived listener with reconnect lifecycle;
- typing-action concept;
- separation between receiving, generating, and sending;
- Windows event-loop awareness if the MVP is operated on Windows;
- outbound success/failure logging.

Do not transplant the reference repository wholesale:

| Reference component | Decision |
|---|---|
| `listener_amanda.py` | Adapt listener shape only; replace Amanda, Telethon user session, and all downstream business calls |
| `login_amanda.py` | Reject for the recommended Bot Token path |
| `logic.py` | Reject; competing funnel, sentiment, heat, CTA, and relationship logic |
| `gpt.py` and `grok.py` | Reject; competing response generation |
| `timing.py` | Reject for first MVP; existing engine/send policy plus a small Telegram rate limiter is enough |
| `database.py` | Reject; creates Telegram-specific users, messages, and funnel memory |
| `config.py` | Do not reuse directly; it defines bot tokens but the listener imports undefined `TG_API_ID`/`TG_API_HASH`, so the checked-in reference path is internally inconsistent |

### 3.3 Media Link capability already present

The DecisionEngine returns an `offer` object and selected content; `ContentService` carries `fanvue_link`; `GPTService` can include the link in close mode. This is the correct seam. The MVP should not use Fanvue paid-chat sending or direct Telegram file delivery.

The checked-in `data/content_catalog.json` contains `fanvue_link` values, but source inspection cannot prove that they are live, purchasable, correctly priced Media Links. They are prerequisites to validate against Fanvue before implementation.

## 4. Components To Build

Build only the following narrow pieces:

### 4.1 Bot configuration

- one Ava Bot Token loaded from environment/secret storage;
- one explicit `AVA_FANVUE_ACCOUNT_ID`;
- QA/allowlisted Telegram user IDs;
- polling timeout, engine timeout, and delivery retry limits;
- allowed Fanvue host/path policy;
- master enable/disable switch.

Do not add creator registries, provider registries, or generic channel configuration.

### 4.2 Telegram polling worker

- Bot API long polling with graceful reconnect/backoff;
- private text/update filtering;
- update offset handling;
- sender/chat extraction;
- per-user serialization;
- typing action if desired;
- text delivery with explicit link-preview behavior;
- structured delivery result and safe logging;
- graceful shutdown.

A maintained Bot API library is reasonable, but selecting it is an implementation decision. FanvueChatbot currently has no Telegram dependency in `requirements.txt`.

### 4.3 Brain gateway

A tiny synchronous/async boundary that:

- derives the temporary engine user ID;
- verifies/creates memory;
- calls `DecisionEngine.process_message()` in a worker thread;
- imposes a timeout and per-user lock;
- normalizes the result into `text`, `offer_authorized`, `offer_link`, and diagnostic status;
- never embeds Telegram policy in DecisionEngine.

No generic transport interface is required for this MVP.

### 4.4 Response and link guard

- escape/format text safely for the chosen Telegram parse mode, or use plain text;
- cap/split responses to Telegram limits;
- accept links only from the selected engine offer;
- require HTTPS and an allowlisted Fanvue hostname;
- remove/block unexpected model-generated URLs;
- prevent duplicate link delivery for the same engine turn;
- record which content tag/link was delivered.

### 4.5 Minimal observability and tests

- update ID, Telegram user ID, temporary engine key, latency, route, offer decision, content tag, and delivery status;
- never log Bot Tokens, full sensitive prompts, or private Media Link secrets;
- unit tests for identity derivation, filtering, result normalization, and link allowlisting;
- mocked Bot API/DecisionEngine integration tests;
- one allowlisted live conversation-to-checkout smoke test.

Durable cross-restart deduplication is desirable, but a new database subsystem is not necessary for a controlled one-worker MVP. Use the Bot API polling offset correctly and keep the rollout allowlisted. If retries demonstrate duplicate brain mutation, a tiny durable update ledger becomes a launch gate rather than broad identity redesign.

## 5. Temporary Identity Strategy

### 5.1 Recommended compatibility identity

For the MVP only:

```text
telegram_user_id = positive Telegram BIGINT
temporary_legacy_user_id = -telegram_user_id
engine_user_id = "<AVA_FANVUE_ACCOUNT_ID>:<temporary_legacy_user_id>"
```

Example:

```text
Telegram user 123456789
-> legacy-compatible user component -123456789
-> engine key "<ava_account_id>:-123456789"
```

This is the minimum strategy because:

- Telegram's numeric ID is stable and directly reversible;
- the negative namespace separates MVP Telegram memory from normal positive local `fanvue_users.id` values;
- `MemoryService` already parses signed integers from the composite key;
- `user_memory.fanvue_user_id` is text and has no direct foreign key to `fanvue_users` in the audited schema;
- the engine can run without a matching `fanvue_users` row, defaulting relationship facts from memory, while still loading Ava's creator profile from the configured account.

### 5.2 Required safeguards

- Preflight must prove no existing memory/user-dependent row uses the reserved negative namespace.
- Reject Telegram IDs that cannot be safely represented as positive PostgreSQL `BIGINT` before negation.
- Use one configured Ava account; never derive it from user input.
- Never create a fake `fanvue_users` row or fake Fanvue UUID.
- Never expose the temporary key as a commerce identity.
- Restrict this key to the conversational memory/DecisionEngine path. Do not call services that require a real local Fanvue user or external Fanvue UUID.
- Tag/log the identity strategy version so a later Core User backfill can deterministically recognize these rows.

### 5.3 Accepted limitations

- `get_user_by_account_and_id()` returns no Fanvue user, so subscriber/follower/relationship fields are not refreshed from Fanvue.
- Existing Fanvue buyer rows cannot be automatically joined to the Telegram user.
- Some repositories assume the ID represents `fanvue_users.id`; those paths remain out of MVP scope.
- The field name remains misleading and must not become permanent architecture.

This compatibility namespace is technical debt with an explicit deletion date: migrate it to Core User identity before general availability or automatic cross-provider purchase continuity.

## 6. Temporary Memory Strategy

Use the existing single `user_memory` row under the temporary engine key. Do not create Telegram-specific memory, copy the reference repository's `users` table, or maintain a second funnel profile.

On first valid inbound message:

```text
derive engine key
-> MemoryService.get_or_create_user_memory(engine key)
-> initialize existing defaults
-> DecisionEngine.process_message(engine key, text, chat_history=[])
-> existing engine persists memory deltas
```

This preserves the current memory categories and relationship/buyer-session logic. The user begins with default/unknown Fanvue facts and accumulates Telegram conversation intelligence in the existing store.

For first-sale validation, pass an empty `chat_history` initially and rely on durable `user_memory`, including last-message and accumulated fields. A bounded in-process recent-message cache may improve conversational context, but it is optional and must not become a second durable memory system. Persisting full Telegram conversation history should wait for the Core User conversation design.

Operational rules:

- serialize calls per Telegram user;
- do not retry an engine call blindly after an uncertain timeout because it mutates memory;
- distinguish generation failure from delivery failure;
- on delivery failure, do not re-run DecisionEngine merely to regenerate the same reply;
- keep proactive outreach, broadcast, delayed-message workers, Fanvue chat sync, and post-purchase reactions disabled for temporary identities;
- support a manual memory reset for allowlisted QA users through an operator action, not a public command.

## 7. Media Link Strategy

### 7.1 Prerequisite: real links

Before listener implementation, create or identify a very small sellable Ava catalog—for example one low-price and one premium Fanvue Media Link. For each item verify in a clean browser/account:

- the URL is live HTTPS on the approved Fanvue domain;
- it opens the intended Ava offer/content;
- price and currency are correct;
- preview does not leak the paid original;
- checkout succeeds on mobile;
- the offer remains stable long enough for the experiment;
- Fanvue reporting can distinguish the MVP link/campaign.

Store only those verified links in the existing content source used by `ContentService`. Do not assume the sample catalog URLs are real checkout links.

### 7.2 Injection rule

The DecisionEngine remains the only authority for whether an offer is appropriate. The transport may deliver a link only when all of the following are true:

1. `result.send_offer` is true.
2. `result.offer.offer_type` is not `none`.
3. `result.offer.content.fanvue_link` is present.
4. The selected content is on the MVP verified-link allowlist.
5. The engine's close/offer state authorizes link delivery under existing behavior.
6. The same link was not already delivered for that engine turn.

`GPTService` currently includes the selected link naturally in close mode. The response guard should preserve that exact selected URL, remove/block any other generated URL, and append the selected link once if close mode authorized it but the model omitted it. The gateway may need to expose the existing close/response-strategy decision explicitly; it must not infer readiness from sexual intensity or Telegram metadata.

Prefer one concise Telegram message containing the engine text and URL, with link previews explicitly disabled unless the verified preview is safe. A second link-only message is acceptable if it materially improves tracking, but avoid duplicate notifications.

### 7.3 What not to send

- no original paid media file through Telegram;
- no `fanvue_media_uuid` or Fanvue chat PPV payload;
- no locally hosted paid asset;
- no link selected by Telegram-specific logic;
- no model-invented or user-supplied checkout URL;
- no Media Link when the engine is in chat, tension-building, suppression, cooldown, or safety-block mode.

### 7.4 Sale measurement

For the first experiment, use a dedicated verified Media Link/campaign and compare Telegram delivery logs with Fanvue's purchase reporting. Record at minimum link-delivered count, unique Telegram recipients, checkout visits if Fanvue exposes them, purchases, gross revenue, and time from link delivery to sale.

This validates “Telegram can produce a Fanvue sale.” It does not prove identity-level purchase attribution or post-purchase personalization. Those require a signed per-user checkout correlation or verified Fanvue identity link later.

## 8. Implementation Roadmap

### Phase 0 - Revenue-path preflight

- Confirm the Ava Fanvue account ID and active creator profile.
- Confirm DecisionEngine can process a negative temporary ID in a disposable/test database.
- Verify the global safety configuration permits controlled chat/offer generation.
- Validate two or three real Fanvue Media Links and content records.
- Create the Ava bot, store its token securely, and define an operator/QA allowlist.
- Define success: at least one verified Fanvue purchase from an MVP-specific link.

**Gate:** do not build the listener until a real sellable link works manually.

### Phase 1 - Offline brain spike

- Feed fixed Telegram-like messages into the temporary engine key.
- Verify memory creation, creator-profile load, response generation, offer progression, and content selection.
- Confirm no path tries to send a Fanvue chat PPV or requires a real `fanvue_users` row.
- Capture one deterministic/mocked flow that reaches a Media Link decision.

**Gate:** normal messages and an offer path complete without fake Fanvue identity.

### Phase 2 - Thin Bot API loop

- Add Bot Token dependency/configuration.
- Implement long polling, private-text filtering, per-user locking, and typing/text delivery.
- Run DecisionEngine outside the event loop with timeout handling.
- Enable only operator-owned QA Telegram IDs.

**Gate:** multi-turn Telegram conversation persists memory across process restart.

### Phase 3 - Media Link close path

- Normalize the engine result.
- Add strict Fanvue URL/content allowlisting and duplicate-link protection.
- Send the exact verified link only on an authorized close.
- Add delivery metrics and failure handling.

**Gate:** test user can move from conversation to the correct mobile Fanvue checkout without paid-media leakage.

### Phase 4 - First-sale trial

- Add a very small external-user allowlist.
- Observe conversations and intervene/disable quickly if needed.
- Reconcile link deliveries against Fanvue purchase reporting.
- Validate the sale and preserve evidence of the funnel outcome.

**Gate:** one confirmed purchase or a clearly diagnosed conversion failure.

### Phase 5 - Decide, do not expand automatically

If the hypothesis succeeds, choose the next constraint to solve: attribution/post-purchase continuity, Core User migration, durable Telegram conversations, or operational hardening. Do not grow the temporary negative-ID path into permanent architecture.

## 9. Estimated Effort

Assumes one engineer familiar with the repository, working Bot API credentials, reachable PostgreSQL/OpenAI services, an active Ava creator profile, and real Media Links available.

| Work | Estimate |
|---|---:|
| Preflight: account/profile/safety/link verification | 0.5-1 day |
| Offline DecisionEngine compatibility spike | 0.5-1 day |
| Bot Token long-polling listener and async boundary | 1-1.5 days |
| Temporary identity/memory guardrails | 0.5 day |
| Result normalization and Media Link guard | 0.5-1 day |
| Unit/integration tests, logging, retries, shutdown | 1-2 days |
| Allowlisted deployment and first-sale observation | 1 day |
| **Revenue-capable allowlisted MVP** | **5-8 engineering days** |

A happy-path operator demo can likely be assembled in **2-3 days**, but it should not accept uncontrolled users or be treated as reliable revenue infrastructure. General availability, durable deduplication, purchase attribution, monitoring, privacy workflows, and Core User migration likely add multiple weeks depending on acceptance criteria.

## 10. Risks

| Risk | Impact | MVP control |
|---|---|---|
| Catalog URL is not a real purchasable Media Link | No sale despite working chat | Verify real checkout before listener work |
| Temporary ID reaches a service expecting `fanvue_users.id` | Wrong query or failed send | Strict gateway allowlist; exclude Fanvue-targeted workers/services |
| Negative ID collides with existing data | Memory corruption | Preflight and reserved namespace invariant |
| Telegram sale cannot update the same buyer memory | Weak post-purchase continuity | Accept/manual reconcile for first sale; design attribution next |
| LLM omits or invents a URL | Lost sale or unsafe redirect | Deterministic selected-link allowlist and response guard |
| Link sent before true close readiness | Conversion/relationship harm | Preserve engine close state; no Telegram CTA logic |
| Duplicate update mutates memory/sends link twice | Poor experience and duplicate pressure | Correct polling offset, per-user lock, turn-level dedupe |
| Blocking engine stalls async listener | Backlog/timeouts | Worker thread, timeout, bounded concurrency |
| Engine timeout occurs after memory mutation | Unsafe retry | Mark outcome uncertain; do not blindly rerun |
| No matching Fanvue user suppresses subscriber/buyer facts | Less personalized offers | Treat Telegram user as cold-start; never fabricate facts |
| Reference Telegram code copied with competing logic | Two brains and divergent memory | Reuse transport patterns only |
| Reference authentication/config mismatch | Listener fails at startup | Fresh Bot Token config; do not copy session files |
| Bot cannot initiate first contact | Acquisition friction | User-start `t.me` link and clear onboarding |
| Paid media leaks through Telegram preview/file | Revenue/access loss | Links only; disable previews unless verified safe |
| Sensitive adult conversation/log exposure | Privacy/security harm | Data minimization, secret-safe logs, access controls |
| Bot/platform policy or age/consent issue | Account/reputational risk | Explicit onboarding, policy review, allowlisted trial, kill switch |
| Temporary architecture becomes permanent | Compounding identity debt | Defined exit gate and no expansion beyond MVP |

## 11. Recommendation

Proceed with a **single-Ava, Bot Token, long-polling MVP** that uses FanvueChatbot as the only brain and delivers only pre-verified Fanvue Media Links. Use the reversible negative Telegram ID as a temporary `MemoryService` compatibility key; do not create fake Fanvue users and do not implement Core User as part of this experiment.

The first implementation task should be a narrowly scoped **offline MVP compatibility spike**, not the listener itself:

1. Select the real Ava account and confirm its creator profile.
2. Verify at least one actual Fanvue Media Link through purchase checkout.
3. Run a negative-ID Telegram-only memory through `DecisionEngine.process_message()`.
4. Prove the result can progress to an authorized offer containing that exact link.
5. Identify every invoked service that assumes a real `fanvue_users` row and either prove it is harmless or keep it outside the MVP path.

If that spike passes, the Telegram transport is small and should follow immediately. If it fails, fix only the narrow compatibility seam needed for the revenue loop; do not restart the platform redesign. The success criterion is deliberately simple: **a user starts on Telegram, has a coherent Ava conversation, receives an engine-approved Fanvue Media Link, and completes a verified sale.**
