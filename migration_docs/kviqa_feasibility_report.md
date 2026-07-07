# KVIQA Integration Feasibility Report

**Status:** Analysis only  
**Assessment date:** June 19, 2026  
**Architectural constraint:** Telegram -> Transport Layer -> FanvueChatbot Brain -> optional KVIQA CRM/Vault/Commerce layer

## 1. Executive Summary

KVIQA should **not be integrated before or during the Telegram MVP**. The repository's existing MVP plan deliberately excludes KVIQA from the minimum conversation-to-Fanvue-Media-Link revenue loop, and no publicly documented KVIQA customer/CRM API was found that would justify adding it to that critical path. The MVP should first prove the existing FanvueChatbot brain through a thin Telegram transport and verified Fanvue Media Links.

After that proof, KVIQA is worth a bounded integration discovery as **CRM + Vault, with commerce attribution where verified**. It presents credible operational value in unified inboxes, creator/chatter operations, partner vault browsing, paid-link delivery, and sales attribution. It should not be the primary customer platform or the conversational brain. KVIQA's own canonical description calls it an operational/CRM layer above payment rails and says it is not a content host or payment processor.

The ownership boundary should remain:

```text
Telegram user
  -> FanvueChatbot Transport Layer
  -> FanvueChatbot Brain
       conversation, memory, relationship intelligence, safety,
       content/offer selection, offer timing
  -> optional KVIQA adapter (post-MVP)
       operational contact projection, tags/segments if supported,
       vault lookup/link creation, delivery attribution, sales events
  -> Fanvue/DropFans/other payment rail
```

The public evidence is strong enough to justify vendor discovery, but not implementation. KVIQA exposes public **partner integration documentation** for payment and vault providers; this is not the same as a general API through which FanvueChatbot can create/update contacts, notes, tags, or events. The authenticated dashboard could not be evaluated without credentials. Undocumented items in this report are therefore marked **unverified**, not assumed absent.

### Decision

| Question | Finding |
|---|---|
| Integrate when? | **After Telegram MVP** |
| Best-fit category | **CRM + Vault**, optionally commerce attribution after API validation |
| Use KVIQBOT? | **No for the initial integration**; it overlaps the canonical brain and its public automation descriptions are inconsistent |
| Primary customer platform? | **No**; FanvueChatbot must retain canonical intelligence and identity boundaries |
| Immediate next task | Vendor/API validation and a read-only post-MVP integration contract |

## 2. API Findings

### Publicly demonstrated surface

KVIQA publishes a [canonical public product reference](https://kviqa.com/llms-full.md) and a browser-rendered [Partner API guide](https://kviqa.com/developers/api-docs). The latter is an integration contract for **payment and vault partners connecting their systems to KVIQA**, not a general customer-facing CRM API.

The visible partner contract describes:

- partner-hosted REST endpoints including `GET /api/v1/me`, vault/folder/media endpoints, drops, drop status, and a transaction ledger;
- per-creator bearer API keys generated at the partner and pasted into KVIQA;
- partner-to-KVIQA sale webhooks at `/api/webhooks/v2/<partner-slug>/sale`;
- HMAC-SHA256 webhook authentication using `X-KV-Signature` and `X-KV-Timestamp`;
- test and live webhook secrets issued by KVIQA;
- timestamp/replay validation and event idempotency;
- per-partner rate limiting, `429`, `RateLimit-*`, and `Retry-After` behavior.

This establishes that KVIQA has an integration framework for vault and commerce providers. It does **not** establish that FanvueChatbot can call KVIQA to manage fans or CRM state.

### Capability determination

| API question | Finding | Confidence |
|---|---|---:|
| Public API | **Partial:** public partner spec exists for vault/payment providers; no public general CRM API verified | High |
| Private/internal API | The web app necessarily uses authenticated internal endpoints, but these are not a supported integration contract | High |
| Authentication | Partner REST uses per-creator bearer keys; inbound sale webhooks use KVIQA-issued HMAC secrets. KVIQA's Fanvue connection is advertised as supporting API-key and OAuth 2.0 paths | Medium-High |
| API documentation | Public partner guide exists; the `/dashboard` route is authentication-protected; no public OpenAPI artifact was found | High |
| Rate limits | Rate limiting and response headers are documented conceptually, but no stable public numeric quota was found | High |
| SDK availability | No official KVIQA SDK was found in the reviewed public material | Medium-High |
| CRM endpoints | No supported public contact/tag/note/custom-field/event endpoints were found | High |

### Integration consequence

FanvueChatbot should not use KVIQA's private browser endpoints or reverse-engineer its web client. A post-MVP integration requires a supported, versioned API or a vendor-approved webhook/export contract. If KVIQA only supports the partner direction, the viable model may be for FanvueChatbot to act as a vault/commerce partner—or to consume KVIQA-originated events—rather than treating KVIQA as a writable CRM.

## 3. CRM Findings

KVIQA clearly functions as an operational CRM in its own interface: it advertises a unified inbox across Telegram, WhatsApp, Fanvue, and OnlyFans; multi-account and multi-chatter operation; fan insights; team permissions; earnings attribution; saved replies; and per-conversation timelines. These are meaningful operations features.

However, the requested programmatic CRM capabilities are not established by the public partner API:

| Required capability | Product/UI evidence | Supported external API evidence | Determination |
|---|---|---|---|
| Create contacts | Conversations/fans appear through connected channels | None found | **Unverified** |
| Update contacts | Fan/channel records and insights exist in the product | None found | **Unverified** |
| Custom fields | No public schema or field-management contract found | None found | **Unverified** |
| Store Telegram IDs | Native Telegram conversations necessarily associate Telegram identities internally | No supported read/write identity endpoint found | **Product yes; integration unverified** |
| Store Fanvue references | Native Fanvue accounts, DMs, subscribers, and earnings are advertised | No general identity-mapping endpoint found | **Product yes; integration unverified** |
| Notes | Some internal-note UI is visible, but public docs do not establish fan-note semantics | None found | **Unverified** |
| Tags | Vault tags/stages are visible; general fan tags were not confirmed | None found | **Unverified** |
| Events | Conversation sales/unlocks and earnings timelines are advertised | Partner sale-webhook ingestion exists, but general custom events were not found | **Commerce events partial; custom events unverified** |

KVIQA therefore cannot yet be selected as the authoritative identity or memory store. At most, it should receive a **projection** of operational state after the canonical Telegram-to-Core-User identity contract is ready. Immutable platform identifiers—not usernames—must drive any future mapping, consistent with the repository's identity reports.

## 4. Vault Findings

Vault is KVIQA's strongest fit. Public product material and the visible app surface support:

- browsing partner vault content from the inbox;
- creator-specific vaults;
- folders, tags, descriptions, prices, media status, and pagination in the partner contract;
- partner vault connections using creator-scoped API keys;
- DropFans, UnlockBL, Fangate, and Fanvue vault/inbox UI paths;
- selecting vault content, setting a price, and sending a paid drop;
- Fanvue vault access and local media upload in the current product client;
- creation/delivery of Fanvue Paid Media Links through an early official API integration, according to KVIQA's June 19 announcement.

Important boundary: KVIQA's canonical reference says it is **not a content host**. “KVIQA Vault” is best understood as an operational catalog/bridge over partner-hosted media, even if some current UI supports upload staging. Payment partners or Fanvue remain authoritative for media hosting, checkout, compliance, and delivery.

| Vault question | Finding |
|---|---|
| Store media | Partner platforms/Fanvue appear to host authoritative media; KVIQA catalogs/bridges it. Native KVIQA hosting is not established |
| Organize media | **Yes in product:** folders, tags/stages, descriptions, creator association |
| Categorize media | **Yes in product:** tag/stage concepts are documented and visible |
| Expose media via API | **Yes in the partner-to-KVIQA direction:** partners expose their vault API to KVIQA. A KVIQA-to-FanvueChatbot vault API is not verified |
| Provide media URLs | Paid/unlock links and partner checkout links are supported; raw paid-media URLs should not be exposed |
| Manage paid content | **Yes operationally:** choose content, price/send drops, record unlocks and attribution; payment/fulfillment remains with the rail |

KVIQA is therefore a plausible **vault operations adapter**, but only after API direction and licensing are confirmed. For the Telegram MVP, the existing verified Fanvue Media Link in FanvueChatbot's content catalog remains the simpler and already-approved seam.

## 5. Sales Bot Findings

KVIQBOT is marketed as creator-trained AI that can qualify cold leads, draft replies, suggest vault content, time paid drops, use scripts/stages, operate across channels, and hand conversations to humans. These are useful capabilities for teams that lack a conversational system.

They substantially overlap FanvueChatbot's existing DecisionEngine, MemoryService, relationship/intimacy logic, safety gates, content selection, response generation, and offer timing. Running both decision systems in one conversation would create split authority, contradictory memory, duplicate sends, inconsistent offer timing, and unclear audit ownership.

There is also a material documentation inconsistency:

- the June 6 canonical reference says KVIQBOT runs alongside chatters, a human always reviews/sends, and it “does not send on its own”;
- newer product/blog material describes 24/7 handling, scripted or auto-sent PPVs, and warming fans before human handoff.

That may reflect a fast product change or multiple modes, but it must be resolved directly with KVIQA before relying on automation semantics.

| Dimension | KVIQBOT | FanvueChatbot Brain |
|---|---|---|
| Primary strength | Turnkey omnichannel operations, team handoff, vault/commerce proximity | Repository-owned persona, durable memory, relationship intelligence, safety, and offer policy |
| Conversation authority | Product-defined and not externally inspectable from public docs | Fully controlled in this repository |
| Memory/relationship model | Advertised training/history; exact model and exportability unverified | Existing explicit services and persistence |
| Offer timing | Advertised | Existing canonical DecisionEngine behavior |
| CRM integration | Native KVIQA integration | Requires adapter |
| Automation mode | Public descriptions conflict; vendor validation required | Known and testable |
| Portability/auditability | Vendor-dependent | Repository-owned |

**Recommendation:** do not use KVIQBOT in the FanvueChatbot conversation path. If evaluated later, restrict it to non-overlapping operational roles such as human reply suggestions, queue triage, or fallback coverage, with a single explicit authority per conversation.

## 6. Telegram Integration Strategy

### MVP path: no KVIQA dependency

```text
Telegram
  -> thin FanvueChatbot Transport Layer
  -> FanvueChatbot Brain
  -> verified Fanvue Media Link
  -> Fanvue checkout
```

This matches `mvp_telegram_path_report.md`: one Bot API worker, temporary compatibility identity for the controlled MVP, existing memory/DecisionEngine, and verified pre-created Media Links. Adding KVIQA here would introduce a second Telegram connection model, a second inbox, uncertain identity synchronization, and an unavailable public CRM contract before the basic hypothesis is proven.

### Post-MVP option

```text
Telegram inbound/outbound
  -> FanvueChatbot Transport Layer       (sole transport authority)
  -> FanvueChatbot Brain                 (sole decision authority)
  -> Integration outbox/adapter
       -> KVIQA contact projection       (only if supported)
       -> KVIQA vault/link request       (only if supported)
       -> KVIQA delivery/sale attribution
  -> Fanvue/DropFans checkout link
  <- signed purchase event
  -> canonical commerce mapping
  -> FanvueChatbot buyer memory update
```

Design rules:

1. Do not let both FanvueChatbot and KVIQA independently listen/send on the same conversation.
2. FanvueChatbot decides **what to say, what to offer, and when**.
3. KVIQA may resolve operational media/link metadata and record delivery/sale facts; it must not overwrite canonical memory.
4. Use stable Telegram numeric IDs and canonical Core User mappings; never merge by username.
5. Use an idempotent outbox/event contract so KVIQA downtime cannot block replies.
6. Keep raw media behind the commerce provider; send only an approved HTTPS checkout/unlock URL.
7. Inbound purchases must be signed, idempotent, attributable to content/link/user, and reconciled before updating buyer intelligence.

KVIQA's primary Telegram connection uses user-account MTProto sessions, whereas the repository recommends a Bot Token for the MVP. Those are different operational models. Replacing the chosen transport with KVIQA would be an architectural rebase, not a small CRM integration, and is not recommended.

## 7. Commerce Integration Strategy

KVIQA presents stronger commerce evidence than CRM API evidence. Its partner contract supports signed sale webhooks, transaction ledgers, drops, refunds/idempotency, and attribution metadata. Product materials claim real-time per-fan, per-chatter, per-creator, and per-platform attribution.

| Commerce capability | Finding |
|---|---|
| Fanvue purchases | KVIQA claims native Fanvue REST integration and near-real-time PPV purchase timelines. Fanvue Paid Media Link creation/attribution was announced June 19, with rollout language; production availability must be verified |
| DropFans purchases | Current guides/UI show DropFans vault/API-key and checkout integration, although the June 6 canonical reference still calls DropFans roadmap. Treat as fast-moving and verify tenant availability |
| Custom events | The partner sale schema supports defined commerce event types and idempotency; arbitrary custom business events are not documented |
| Checkout activity | Links, clicks, unlocks, purchases, refunds, and earnings are claimed for supported rails; exact event coverage/export API requires validation |

Recommended commerce contract after MVP:

- generate a unique immutable offer/delivery ID in FanvueChatbot;
- preserve canonical Telegram/Core User, content, creator account, rail, link, quoted price/currency, and decision-turn IDs;
- pass only approved attribution metadata supported by KVIQA/rail;
- ingest signed purchase/refund events through a supported webhook;
- deduplicate on the rail's event ID and reconcile uncertain events;
- update FanvueChatbot buyer memory only after identity and purchase verification;
- treat KVIQA analytics as an operational view, not the sole financial ledger.

Until KVIQA confirms an outbound webhook or supported read API for this use case, first-sale attribution should remain the MVP's dedicated Media Link plus Fanvue reporting/manual reconciliation.

## 8. Recommended Ownership Model

| Capability | Owner | Rationale |
|---|---|---|
| Telegram receive/send | FanvueChatbot Transport Layer | One transport authority; matches MVP |
| Conversation text and persona | FanvueChatbot Brain | Existing canonical behavior |
| Durable conversational memory | FanvueChatbot | Avoid split brain and vendor lock-in |
| Relationship/intimacy intelligence | FanvueChatbot | Existing proprietary capability |
| Safety and consent policy | FanvueChatbot | Must gate every response/offer locally |
| Offer timing and content selection | FanvueChatbot | Existing DecisionEngine responsibility |
| Canonical identity mapping | FanvueChatbot/Core User foundation | Cross-provider invariant; KVIQA is a projection |
| Unified human inbox/team shifts | KVIQA, optionally post-MVP | Clear operational product strength |
| Operational tags/segments/notes | KVIQA only if API-supported; otherwise local | External write contract not yet verified |
| Vault browsing/organization | KVIQA, optionally | Strongest fit across partner rails |
| Raw media hosting/compliance | Fanvue/DropFans/payment rail | KVIQA says it is not a content host/payment processor |
| Checkout link creation | KVIQA or rail, behind an adapter | Useful if supported; must not control offer decision |
| Delivery and sale attribution | KVIQA operationally + local canonical event | Preserve auditability and buyer memory continuity |
| Campaign/agency/chatter analytics | KVIQA | Clear team-operations value |
| AI sales conversation | FanvueChatbot Brain | KVIQBOT would duplicate core intelligence |

KVIQA should therefore be treated as an **optional downstream operations system**, never a synchronous prerequisite for generating or sending a Telegram reply.

## 9. MVP Recommendation

**Integrate KVIQA after the Telegram MVP.**

Reasons:

1. The approved MVP report explicitly excludes KVIQA and already defines the smallest revenue loop.
2. KVIQA adds no required capability for receiving a Telegram message, invoking the brain, or sending a verified pre-created Fanvue Media Link.
3. Its publicly documented API is oriented toward vault/payment partners, while required CRM write operations remain unverified.
4. KVIQA introduces a competing Telegram transport and potentially a competing AI decision system.
5. Identity and purchase continuity already have known repository readiness gates; another platform would multiply ambiguity.
6. KVIQA's Fanvue and Paid Media Link capabilities are extremely recent and described with rollout language, so production contracts should stabilize before dependency.

The appropriate trigger for post-MVP discovery is a successful allowlisted Telegram conversation-to-checkout test plus a stable canonical identity/commerce event design. KVIQA can then be evaluated for measurable operational value without placing the experiment at risk.

## 10. Risks

| Risk | Severity | Mitigation |
|---|---:|---|
| No verified general CRM API | Critical | Obtain supported endpoint/schema documentation before design |
| Split conversational authority | Critical | Disable KVIQBOT for integrated accounts; one brain per conversation |
| Duplicate Telegram transport/sends | Critical | Select one transport owner and document account/session topology |
| Identity mismatch across Telegram, KVIQA, Fanvue, and DropFans | Critical | Complete canonical Core User mapping; immutable IDs only |
| Purchase attribution cannot round-trip | High | Signed idempotent events plus controlled purchase test |
| Recent/fast-changing Fanvue features | High | Confirm GA status, tenant access, SLAs, and breaking-change policy |
| Public documentation contradictions | High | Vendor walkthrough and written capability matrix |
| Vendor lock-in/loss of intelligence | High | Keep memory, decisions, identity, and canonical commerce events local |
| Private API temptation | High | Use only documented/vendor-approved contracts |
| KVIQA outage blocks chat | High | Asynchronous optional adapter/outbox; graceful degradation |
| Vault link or price mismatch | High | Validate host, content, price, currency, creator, and expiration before send |
| Sensitive session/content exposure | High | Least privilege, encrypted secrets, no raw media in logs, documented deletion/export |
| Compliance responsibility ambiguity | High | Written data-processing, adult-content, retention, erasure, and incident terms |
| Product claims not independently verified | Medium-High | Treat marketing/blog statements as vendor claims until sandbox proof |
| Rate/SDK uncertainty | Medium | Obtain numeric quotas and versioning/support policy; implement backoff only after contract |

## 11. Recommended Next Task

After the Telegram MVP is proven, run a **KVIQA Vendor/API Validation and Read-Only Integration Contract** task. Do not begin implementation in that task.

Required outputs:

1. Obtain KVIQA sandbox/tenant access and a live vendor walkthrough.
2. Obtain the supported API specification, authentication scopes, numeric rate limits, versioning/deprecation policy, SDK status, webhook catalog, and support/SLA terms.
3. Prove or reject each CRM matrix item: contact create/update, external IDs, custom fields, notes, tags, and custom events.
4. Prove vault directionality: list/search media, folders/tags, price metadata, Fanvue Paid Media Link creation, URL lifetime, and sale callback.
5. Prove commerce round trips for one Fanvue Media Link and one DropFans purchase, including refunds, retries, attribution, and identity reconciliation.
6. Resolve in writing whether KVIQBOT drafts, sends autonomously, or supports both modes, and prove it can be disabled per account/conversation.
7. Define a read-only or write-minimal adapter contract with FanvueChatbot as the system of record.
8. Produce a go/no-go decision and measured success criteria before any code change.

### Evidence reviewed

Repository context:

- `migration_docs/mvp_telegram_path_report.md`
- `migration_docs/transport_strategy_review.md`
- `migration_docs/identity_discovery_report.md`
- `migration_docs/database_readiness_report.md`
- associated architecture, identity, and Telegram migration documents

KVIQA public sources:

- [KVIQA home/product metadata](https://kviqa.com/)
- [Canonical setup/product reference](https://kviqa.com/llms-full.md)
- [Partner API documentation](https://kviqa.com/developers/api-docs)
- [KVIQA + Fanvue integration announcement](https://kviqa.com/blog/kviqa-fanvue-integration.md)
- [Fanvue Paid Media Links announcement](https://kviqa.com/blog/kviqa-fanvue-paid-media-links.md)
- [KVIQBOT comparison](https://kviqa.com/blog/kviqbot-vs-substy.md)
- [PPV Buy Now buttons](https://kviqa.com/blog/ppv-buy-now-buttons.md)
- [Send Buttons setup guide](https://kviqa.com/blog/send-buttons.md)
- public sitemap, authenticated-route metadata, and the unauthenticated web application surface

Public claims were used as evidence of advertised capability, not independent proof of production behavior. The `/dashboard` content is authentication-protected and was not treated as verified documentation.
