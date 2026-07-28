# Commercial catalog and Sales Brain synchronization audit

Audit date: 2026-07-25  
Repository: `C:\Creator-OS-React`  
Branch: `react-migration`  
HEAD: `76b3c71`

## Executive conclusion

Once an owner deliberately creates an AI_CHAT Commercial Offering and its Fanvue publication has reached the complete sellable state, the offering is visible to the Sales Brain on its next catalog query. No restart, cache flush, worker copy, legacy Product, reindex, embedding, or model retraining is required.

The authoritative runtime reads current PostgreSQL rows every time `CommercialOfferingSelectorService.select()` runs:

```text
commercial_offerings
→ commercial_offering_assets
→ asset_content_destinations
→ commercial_publications
```

The offering must be `READY`, use `AI_CHAT`, have a `LIVE` publication whose provider resource is `PRESENT`, expose a non-empty Media Link URL, have a valid price, belong to the current creator, use the correct committed destination, and not already be attributed as purchased by that buyer.

This means “known to the catalog” is immediate, but “sold in this turn” remains subject to Customer Sales Brain controls: identity, conversation buying intent/readiness, recent-purchase cooldown, payment state, active Purchase Intent waiting/nudge state, and other safety policy.

**Confidence: High** that an owner-approved offering can traverse the supported activation workflow and enter the autonomous catalog without developer intervention. Once a valid offering has the complete durable sellable state, discoverability is immediate.

The Commercial Consistency Hardening pass resolved the two catalog-integrity
gaps identified by this audit:

1. `CommercialOfferingService.create()` is now the sole owner of PHOTOSET
   commitment. Photoshoot curation leaves canonical members in
   `AVAILABLE_INVENTORY`; offering creation validates and atomically creates
   the ordered offering, changes each member to `PHOTOSET`, and records the
   normal destination history. Publication finalization verifies this
   invariant without performing a second PHOTOSET assignment.
2. `CommercialOfferingService.validate_pricing_update()` is now the single
   publication-aware pricing policy used by both generic and Commerce
   authoring updates. `LIVE` prices are rejected before any database price
   write with `LIVE_PRICE_LOCKED`; `PUBLISHING` is also locked. DRAFT,
   READY_TO_PUBLISH, FAILED, and ARCHIVED publication states remain editable.

Membership, channel, and offering status remain creation-time fields except
for archive. That is an intentional immutable-catalog boundary, not a second
catalog.

Archiving removes an offering from selector eligibility, but it does not
return its members to `AVAILABLE_INVENTORY`. A PHOTOSET commitment remains
immutable after offering creation; reusing those Assets in a second offering
would violate commercial exclusivity.

## 1. Authoritative catalog definition

### 1.1 Authoritative records

The runtime sales catalog is the fulfillment projection built from:

- `public.commercial_offerings`
- `public.commercial_offering_assets`
- `public.asset_content_destinations`
- `public.commercial_publications`
- attributed purchased offerings derived through `PurchaseIntentRepository`

Evidence:

- `app/repositories/commercial_fulfillment_repository.py`
  - `list_candidates()`
  - `_select()`
  - `_fulfillable_having()`
- `app/repositories/commercial_offering_selector_repository.py`
  - `list_candidates()`
  - `list_purchased_offering_ids()`
- `app/services/commercial_offering_selector_service.py`
  - `select()`
  - `_evaluate()`

`commercial_offerings` is the authored catalog root, but a row alone is not sellable. The publication and committed member destinations are integral parts of the effective catalog.

### 1.2 Commerce Library terminology

| React location | Meaning | Authoritative for selling? |
|---|---|---|
| `/business/commerce-library` | Registered Business Assets, intelligence readiness and destinations | No; source material/readiness projection |
| `/inventory/available` | Active, non-test, non-archived Assets assigned to AVAILABLE_INVENTORY | No; offering source pool |
| `/commerce` | Current owner-facing authoring and publication workspace | UI over authoritative records |
| `/commerce/offerings` | Lower-level Commercial Offering/publication detail workspace | UI over authoritative records |
| Commercial Fulfillment projection | Current offering + publication + destination eligibility | Yes, for Sales Brain candidates |

Evidence:

- `frontend/src/app/router/router.tsx`
- `frontend/src/features/business-assets/BusinessAssetsPage.tsx`
- `frontend/src/features/available-inventory/AvailableInventoryPage.tsx`
- `frontend/src/features/commerce/CommercePage.tsx`
- `frontend/src/features/commercial-offerings/CommercialOfferingsPage.tsx`

The owner's mental model is substantially correct:

```text
Generation Library
→ owner curation
→ Asset Library registration
→ Commerce Library readiness
→ owner creates Commercial Offering
→ owner publishes
→ Sales Brain queries it immediately
```

The terminology difference is that “Commerce Library” is analyzed content, while the active sales catalog is Commercial Offerings plus their live publication state.

### 1.3 Duplicate catalogs

The repository also contains:

- legacy Products/Product assets;
- `chat_commerce_registrations`;
- `business_asset_registrations`;
- JSON learning and generation stores;
- READY Asset Chat Registration worker output.

None is queried by the authoritative Commercial Offering Selector. They can become stale relative to Commercial Offerings, but they cannot make an offering visible or invisible to the configured authoritative Telegram/Test Chat path.

Evidence:

- `ChatCommerceService.AUTHORITATIVE_MODE`
- `ChatCommerceService.recommend()`, which blocks compatibility fallback without an authoritative decision
- `CommerceSalesService.recommend_best()`, documented as compatibility-only
- `CommercialOfferingSelectorRepository`, which has no Product/chat-registration dependency

## 2. Runtime request trace

### 2.1 Telegram

```text
Telethon inbound event
→ TelegramInboundAdapter
→ ConversationGateway.process()
→ CustomerSalesBrainService.evaluate_for_buyer()
→ CommercialOfferingSelectorService.select()
→ CommercialOfferingSelectorRepository.list_candidates()
→ CommercialFulfillmentRepository.list_candidates()
→ fresh PostgreSQL SELECT
→ CustomerSalesDecision
→ DecisionEngine/GPT response composition
→ ChatCommerceService.recommend(authoritative decision)
→ CommerceSalesService.resolve_recommended_offering()
→ fresh eligible offering resolution
→ TelegramPurchaseIntentService / PurchaseIntentService
→ TelegramDeliveryExecutor
```

Composition evidence:

- `app/integrations/telegram/telethon_runtime.py`
  - constructs `ConversationGateway`
  - injects `CustomerSalesBrainService()`
  - uses `ChatCommerceService.AUTHORITATIVE_MODE`
- `app/services/telegram_inbound_adapter.py`
- `app/services/conversation_gateway.py`
- `app/services/customer_sales_brain_service.py`
- `app/services/chat_commerce_service.py`
- `app/services/telegram_delivery_executor.py`

### 2.2 Developer Test Chat

```text
POST /api/v1/developer/test-chat/turns
→ TestChatService
→ ConversationGateway
→ CustomerSalesBrainService
→ CommercialOfferingSelectorService
→ same fulfillment repository/query
→ ChatCommerceService in AUTHORITATIVE_MODE
→ response diagnostics; external send disabled
```

Evidence:

- `app/api/test_chat.py`
- `app/services/test_chat_service.py`
  - injects `CustomerSalesBrainService()`
  - constructs `ChatCommerceService` in `AUTHORITATIVE_MODE`

Test Chat and Telegram therefore use the same catalog authority and selector. They differ at transport/delivery, not at catalog selection.

### 2.3 Inputs and outputs by step

| Step | Input | Output | Persistence/cache/failure |
|---|---|---|---|
| Conversation Gateway | message, identity, history | diagnostics, current-turn readiness, reply context | conversation repositories; no offering cache |
| Customer Sales Brain | creator/account/buyer/Telegram IDs, signal, context | immutable decision including selected offering IDs/URL | reads customer profile and Purchase Intents each evaluation; blocks on unresolved/unknown/payment/cooldown states |
| Selector | creator, buyer profile, active intent, channel | `SelectedOfferingResult` | opens repository query on each call; no candidate cache |
| Fulfillment repository | creator/channel | candidate row set | PostgreSQL query; up to 1,000 candidates; current rows |
| Chat Commerce | authoritative decision | resolved `CommerceSale` | resolves selected offering again; no independent selection in authoritative mode |
| Purchase Intent | offering/publication/provider/URL/price/customer | immutable CREATED/PRESENTED record | durable PostgreSQL snapshot; delivery failure becomes ABANDONED |
| Delivery | reply + offering URL | Telegram message/send outcome | runtime/send guards; failures surfaced and intent preserved |

## 3. Scenario findings

### Scenario A — new single-image offering

When Commerce authoring creates the offering, it uses initial status `READY`. It begins with an AVAILABLE_INVENTORY image. Fanvue execution uploads the member and, during LIVE finalization, commits its destination to `SINGLE_PPV`.

After the publication transaction persists:

- publication status `LIVE`;
- provider resource `PRESENT`;
- external provider/Media Link ID;
- `publication_metadata.media_link.url`;
- `published_at`;
- Asset destination `SINGLE_PPV`;

the next selector query includes it. No copy or restart occurs.

Evidence:

- `CommerceAuthoringService.create()`
- `CommercialPublicationService.mark_live()`
- `CommercialPublicationService._commit_offering_assets()`
- `CommercialPublicationRepository.finalize_live()`

### Scenario B — new photoset

The final selector behavior is correct for an already-valid photoset: the fulfillment projection returns ordered member Asset IDs, hero ID, price, URL and publication state, and the next selector query sees it without synchronization.

However, the supported creation sequence is internally contradictory:

```text
Photoshoot curation
→ selected members committed to PHOTOSET
→ CommercialOfferingService.create()
→ rejects every member because it is not AVAILABLE_INVENTORY
```

The reverse sequence also fails:

```text
create PHOTOSET offering while members are AVAILABLE_INVENTORY
→ publication reaches LIVE finalization
→ rejects members because they are not already PHOTOSET
```

Therefore Scenario B is **not verified end to end** through the current services. An already-existing, correctly persisted PHOTOSET offering is immediately discoverable, but normal owner workflow cannot reliably create that state without bypassing a domain rule.

Evidence:

- `CommercialOfferingService._validate_shape()`
- `CommercialOfferingService.create()` and its unconditional `is_available_inventory()` check
- `CommercialPublicationService._commit_offering_assets()`
- `CommercialFulfillmentRepository._select()`
- `CommercialOfferingSelectorService._destination_reason()`
- `PhotoshootCurationService.confirm()` for PHOTOSET commitment

### Scenario C — offering updates

| Change | Supported path | Next-query behavior | Qualification |
|---|---|---|---|
| Title/description | Commerce authoring PATCH or generic offering PATCH | Immediate | Existing Purchase Intent identifies offering but retains its original delivery/price snapshot; response resolution reads current title/description. |
| Price | Commerce authoring PATCH | Immediate for non-LIVE | Correctly blocked while publication LIVE. |
| Price via generic endpoint | `/commercial-offerings/{id}/pricing` | Immediate DB change | **Unsafe gap:** no LIVE publication check; provider Media Link price may remain old. |
| Hero Asset | generic metadata PATCH | Immediate | Must already be a member; Commerce authoring edit UI does not expose it. |
| Membership | No supported update endpoint | Not applicable | Recreate offering; do not edit DB directly. |
| Channel | No supported update endpoint | Not applicable | Creation-time field. A durable change would be seen immediately. |
| Status | Archive supported; no general READY/DRAFT transition endpoint | Archive immediate | Commerce authoring creates READY; generic creation creates DRAFT. |
| Publication URL | Executor metadata/finalization | Immediate | No operator URL-edit API; reconcile/provider execution owns it. |
| Provider resource state | reconciliation repository update | Immediate | Worker timing determines how quickly remote deletion/drift is learned. |

No candidate cache exists, so supported mutations need no invalidation.

### Scenario D — removal/deactivation

The selector re-evaluates current rows. It immediately excludes:

- offering `ARCHIVED`;
- any offering not `READY`;
- channel other than `AI_CHAT`;
- publication not `LIVE`, including ARCHIVED/FAILED/PUBLISHING;
- provider resource not `PRESENT`;
- missing delivery URL/provider;
- invalid price;
- invalid destinations;
- wrong creator;
- buyer-attributed prior purchase.

An already delivered Purchase Intent is a historical snapshot and remains durable. If its active offering becomes invalid, active-intent selection re-queries that offering and refuses to return it. The active intent can nevertheless hold the buyer in a wait/nudge lifecycle until expiry or supersession; it does not automatically switch to a different offering.

### Scenario E — restart

Catalog discoverability is restart-safe:

- offerings/members/publications/destinations/intents are PostgreSQL records;
- selectors construct repositories and query them on demand;
- no warmup, JSON rebuild, in-memory index, or model state is required;
- an application or Telegram worker restart creates fresh service instances that read the same durable rows.

The audit did not restart production-like processes. This conclusion is supported by source construction and isolated tests using repository-backed/fake durable candidates. There is no candidate cache to repopulate.

## 4. State eligibility matrix

| Offering | Channel | Publication | Provider resource | URL | Destination | Sales Brain eligible? | Reason |
|---|---|---|---|---|---|---|---|
| READY | AI_CHAT | LIVE | PRESENT | present | SINGLE_PPV for single/video | Yes | Complete candidate |
| READY | AI_CHAT | LIVE | PRESENT | present | PHOTOSET for photoset | Yes | Complete candidate |
| DRAFT | AI_CHAT | LIVE | PRESENT | present | valid | No | `OFFERING_NOT_ACTIVE` |
| ARCHIVED | AI_CHAT | LIVE | PRESENT | present | valid | No | `OFFERING_ARCHIVED` |
| READY | TELEGRAM_WALL | LIVE | PRESENT | present | valid | No | `SALES_CHANNEL_MISMATCH` |
| READY | AI_CHAT | READY_TO_PUBLISH | UNVERIFIED | absent | uncommitted | No | publication not live/resource missing/URL missing/destination invalid |
| READY | AI_CHAT | PUBLISHING | UNVERIFIED | absent | uncommitted | No | `PUBLICATION_NOT_LIVE` |
| READY | AI_CHAT | FAILED | UNVERIFIED | absent | uncommitted | No | publication/resource/URL failures |
| READY | AI_CHAT | ARCHIVED | MISSING | absent | valid | No | publication/resource/URL failures |
| READY | AI_CHAT | LIVE | MISSING | present or absent | valid | No | `PROVIDER_RESOURCE_NOT_PRESENT` |
| READY | AI_CHAT | LIVE | PRESENT | absent | valid | No | `DELIVERY_URL_MISSING` |
| READY | AI_CHAT | LIVE | PRESENT | present | AVAILABLE_INVENTORY | No | `DESTINATION_NOT_COMMERCIALLY_AVAILABLE` |
| READY | AI_CHAT | LIVE | PRESENT | present | wrong creator | No | `CREATOR_MISMATCH` |
| READY | AI_CHAT | LIVE | PRESENT | present | valid; buyer already owns | No | `OFFERING_ALREADY_PURCHASED` |

Commerce UI visibility is broader than selector eligibility. Authoring lists DRAFT/READY/LIVE-related records and can show publication failures. Archived offerings are excluded from the main offering list or shown only through summary/state-specific views. UI presence is not a promise of Sales Brain eligibility.

## 5. Synchronization requirements

| Mechanism | Required for a fully valid new offering to be discovered? | Notes |
|---|---|---|
| FastAPI restart | No | Next selector query reads DB. |
| Frontend restart | No | React lists use `cache: "no-store"`; chat catalog is backend-owned. |
| Telegram worker restart | No | Long-lived service still issues new DB queries. |
| Sales/commerce worker restart | No | Selector is synchronous/on-demand. |
| READY Asset Chat Registration worker | No | Legacy per-Asset chat registration path. |
| Catalog synchronization worker | No | None exists or is needed. |
| Cache invalidation | No | No authoritative candidate cache. |
| Search-index rebuild | No | Selector does not use search index. |
| JSON regeneration | No | Catalog is PostgreSQL. |
| legacy Product creation | No | Selector does not query Products. |
| chat Asset registration | No | Selector consumes Offering fulfillment. |
| embedding generation | No | Selector is deterministic relational SQL. |
| model retraining | No | No learned catalog index. |
| manual browser refresh | No for Sales Brain | Needed only to visually refresh an already-open UI screen. |
| publication reconciliation | Required for provider drift, not initial successful finalization | Executor finalization directly sets LIVE/PRESENT; reconciliation later detects missing/mismatched provider resources. |

## 6. READY Asset Chat Registration worker

`ReadyAssetChatRegistrationWorkerService`:

1. claims a READY-asset registration job;
2. resolves canonical Asset and runtime media;
3. loads legacy Business Asset registration;
4. calls `ChatCommerceRegistrationService.register_fulfilled_asset()`;
5. writes a chat-registration availability record.

Evidence:

- `app/workers/ready_asset_chat_registration.py`
- `app/services/ready_asset_chat_registration_worker_service.py`
- `app/services/chat_commerce_registration_service.py`
- `app/repositories/chat_commerce_registration_repository.py`

Findings:

1. It is not part of the authoritative Commercial Offering selector.
2. Disabling it does not prevent a READY/LIVE/PRESENT offering from selection.
3. It supports the older Asset/Product/chat-inventory compatibility architecture.
4. Its duplicate catalog can become stale, but authoritative mode does not read it.
5. It should be renamed to make “legacy asset chat registration” explicit, then deprecated after all non-authoritative consumers are inventoried. Immediate removal is unsafe because legacy delivery/inventory services still reference chat registrations.

Recommended name: `Legacy Ready Asset Chat Registration`. Recommended status: retained but disabled/clearly labeled compatibility-only until dependent legacy services are retired.

## 7. Create, publish, retry and reconciliation propagation

```text
CommercePage
→ POST /api/v1/commerce-authoring
→ CommerceAuthoringService.create()
→ CommercialOfferingService.create(initial_status=READY)
→ CommercialOfferingRepository.create()
```

Creation is transactional across offering and member inserts. Source Assets must be AVAILABLE_INVENTORY at creation.

```text
POST /commerce-authoring/{id}/publish
→ resolve/create Fanvue publication
→ READY_TO_PUBLISH
```

```text
POST /commercial-publications/{id}/execute or /retry
→ CommercialPublicationService / executor
→ upload checkpoints
→ Media Link
→ finalize_live()
→ LIVE + PRESENT + URL + external ID
→ destination commitment
```

```text
POST /commercial-publications/{id}/reconcile
or publication worker
→ provider read
→ record_reconciliation()
→ PRESENT/MISSING/MISMATCH/AMBIGUOUS
→ optionally archive invalid LIVE record
```

All selector-visible values are queried directly, so propagation occurs on commit.

Database constraint `UNIQUE (commercial_offering_id, provider)` prevents multiple Fanvue publication rows from producing ambiguous URLs. Only FANVUE is currently supported.

Evidence:

- `app/api/commerce_authoring.py`
- `app/api/commercial_publications.py`
- `app/services/commercial_publication_service.py`
- `app/services/fanvue_media_link_publication_executor.py`
- `app/repositories/commercial_publication_repository.py`
- `migrations/forward/20260723_003_commercial_publications_foundation.sql`

## 8. Eligibility versus sales timing

The selector knows an offering exists when it appears among candidate evaluations. That does not authorize selling it.

The Customer Sales Brain can block or defer presentation because of:

- unresolved Telegram ↔ Fanvue identity;
- unsupported/unknown commerce state;
- payment pending;
- unacknowledged purchase;
- recent purchase cooldown;
- existing active Purchase Intent waiting period;
- current-turn readiness/buying intent;
- no eligible offering;
- conversation policy/safety;
- another active offering requiring a nudge rather than replacement.

Evidence:

- `CustomerSalesBrainService.evaluate_for_buyer()`
- `CustomerSalesBrainService.refine_for_readiness()`
- `ConversationGateway._customer_sales_decision()`
- `app/services/commerce_execution_policy.py`

Ranking among eligible offerings is:

1. active Purchase Intent’s offering;
2. exclude attributed previously purchased offerings;
3. `published_at` descending;
4. `offering_id` ascending for deterministic ties.

No featured flag, performance score or semantic ranking is implemented.

## 9. Metadata usage matrix

| Field | Selector projection | Actively used |
|---|---|---|
| Offering ID | Available | Selection, intent, resolution |
| Title | Available | Returned to Chat Commerce/GPT composition |
| Description | Available | Returned to response composition |
| Offering type | Available | Destination/type validation; response |
| Price/currency | Available | Eligibility, response and Purchase Intent snapshot |
| Primary channel | Available | Required AI_CHAT filter |
| Hero Asset | Available | Available to resolved sale/UI; not ranking |
| Member Asset IDs/order | Available | Destination and fulfillment structure |
| Publication date | Available | Primary ranking |
| Delivery URL | Available | Mandatory, Purchase Intent snapshot and delivery |
| Provider/resource ID | Available | Mandatory fulfillment/delivery |
| Content Destination | Available per member | Mandatory structural eligibility |
| Creator ownership | Available | Mandatory scoping |
| Purchase history | Separate query | Excludes attributed purchased offerings |
| Active Purchase Intent | Separate query | Reuses active offer and controls timing |
| Content Intelligence | Not in selector projection | Unused |
| Mood/theme/wardrobe/location/pose/activity | Not in projection | Unused |
| Keywords/search phrases/style/emotional tone | Not in projection | Unused |
| Photoshoot summary | Not in projection | Unused |
| Creator priority/featured | Not stored in selector schema | Unsupported; metadata reports `featuredSupported: false` |
| Freshness | Publication date available | Used as published-recency ordering |
| Performance/revenue/conversion | Not in projection | Unused/legacy learning only |

## 10. Purchase Intent snapshot behavior

`PurchaseIntent` preserves:

- offering and publication IDs;
- provider resource ID;
- delivery URL;
- expected price/currency;
- buyer/conversation/message correlation;
- presentation and expiration times.

Evidence: `app/models/purchase_intent.py`, `app/services/purchase_intent_service.py`.

This is desirable for historical attribution: an already-presented offer retains the terms sent to the buyer. New conversations resolve current offering data. A later price change should not rewrite an existing intent.

Race considerations:

- Updating/archiving after selector evaluation but before intent creation can race. `CommerceSalesService.resolve_recommended_offering()` revalidates the selected offering, reducing this window.
- Updating after intent creation preserves old terms intentionally.
- A provider URL/resource can change remotely before reconciliation; until provider state is refreshed, the database may remain PRESENT.
- Active invalidated intents can temporarily block selection of a replacement until expiry/supersession.

## 11. Failure-mode audit

| Potential issue | Finding | Severity | Launch impact / smallest safe fix |
|---|---|---:|---|
| Stale in-memory candidate cache | Not found | None | DB queried every selection. |
| Selector uses Products | No | None | Authoritative Offering path verified. |
| Worker copies offerings to second catalog | No | None | READY chat worker is legacy-only. |
| Updates need cache invalidation | No | None | Current DB values queried. |
| Archived offering remains eligible | No | None | Explicit exclusion. |
| Publication changes delayed | Only remote drift waits for reconciliation | Medium | Keep reconciliation worker healthy and alert on stale `last_reconciled_at`. |
| Copied delivery URL stale | Intent snapshots URL intentionally; provider DB state may drift | Medium | Reconcile before new presentation; URL health validation. |
| Membership updates ignored | No supported update workflow | Medium | Keep immutable; create replacement offering or implement transactional revisioning. |
| Hero/description invisible | Visible on next resolution | Low | No fix. |
| Purchase exclusion wrong | Uses only hard-attributed purchased offering IDs | Medium | Correctly conservative; UNKNOWN purchases cannot safely exclude. |
| Active intent presents invalid offering | Selector revalidates and refuses it | Low–Medium | Supersede/expire invalid active intent promptly. |
| Cross-creator candidate | Explicit creator predicate/evaluation | Low | Preserve tests and DB ownership constraints. |
| Invalid destination leaks | Explicit destination validation | Low | Preserve service-only mutation boundary. |
| Restart loses catalog | No | None | Durable DB state. |
| Test Chat/live differ | Same gateway/Sales Brain/selector | Low | Preserve composition tests. |
| UI says active but selector rejects | Possible: UI reports READY/LIVE but can omit composite exclusion reason at card level | Medium | Surface selector/fulfillment eligibility and exact exclusion reasons consistently. |
| Reconciliation worker disabled | Does not block freshly finalized LIVE/PRESENT, but remote drift grows stale | **High operational** | Require healthy reconciliation heartbeat for LIVE launch certification. |
| LIVE with stale provider state | Possible until reconcile | **High operational** | Staleness threshold should exclude or warn before offers. |
| Multiple publication URLs | Prevented per offering/provider | Low | Unique constraint; only FANVUE. |
| Generic pricing bypasses LIVE lock | Resolved | None | Central service guard rejects LIVE/PUBLISHING before the repository update. |
| Generic metadata edit on LIVE | Allowed | Medium | Decide immutable publication/version policy; title/hero may diverge from provider presentation. |
| Generic DRAFT creation cannot be promoted | Confirmed API gap | Medium | Use `/commerce` authoring path or add explicit validated activation transition. |
| PHOTOSET creation/commitment ordering is impossible through supported rules | Resolved | None | Curation preserves AVAILABLE_INVENTORY; offering creation atomically commits PHOTOSET membership. |

The PHOTOSET ordering and LIVE price consistency blockers are resolved. A
healthy reconciliation worker remains the principal operational consistency
requirement for detecting remote provider drift.

## 12. Tests inspected and run

Inspected:

- `app/test_commercial_offerings.py`
- `app/test_commerce_authoring.py`
- `app/test_commercial_publications.py`
- `app/test_commercial_offering_selector.py`
- `app/test_customer_sales_brain.py`
- `app/test_customer_sales_brain_conversation_integration.py`
- `app/test_chat_commerce_service.py`
- `app/test_purchase_intent_lifecycle.py`
- `app/test_unified_conversation_brain.py`
- `app/test_telegram_brain_composition.py`
- `app/test_telethon_runtime.py`
- `app/test_test_chat.py`
- React Commerce, Offering Selector, Commercial Offerings and Test Chat tests

Commands:

```powershell
python -m pytest -q app/test_commercial_offerings.py app/test_commerce_authoring.py app/test_commercial_publications.py app/test_commercial_offering_selector.py app/test_customer_sales_brain.py app/test_customer_sales_brain_conversation_integration.py app/test_chat_commerce_service.py app/test_purchase_intent_lifecycle.py app/test_unified_conversation_brain.py app/test_telegram_brain_composition.py app/test_telethon_runtime.py app/test_test_chat.py
```

Result: **108 passed**.

```powershell
cd frontend
npm test -- --run src/features/commerce/CommercePage.test.tsx src/features/commercial-offerings/CommercialOfferingsPage.test.tsx src/features/offering-selector/CommercialOfferingSelectorPage.test.tsx src/features/test-chat/TestChatPage.test.tsx src/features/commerce-sales-explorer/CommerceSalesExplorerPage.test.tsx
```

Result: **5 files, 16 tests passed**.

All selected tests use fakes/mocks or isolated state. No live Fanvue, Telegram, LLM or generation operations were run. The suite verifies current-query selection, eligibility filters, active intent reuse, purchased-offering exclusion, deterministic newest ordering, authoritative runtime composition, and UI behavior. It does not simulate a real process restart against a production-like database.

## 13. Direct answers

1. **Once I create and activate a new AI_CHAT Commercial Offering, will the Sales Brain know on the next eligible conversation?**  
   Yes, if it satisfies the full READY/LIVE/PRESENT/URL/destination/price/ownership state.

2. **Does it require restarting Creator_OS?**  
   No.

3. **Does it require a background synchronization or registration worker?**  
   No catalog-sync worker. Fanvue execution must create the provider resource, and ongoing reconciliation is operationally required to detect drift.

4. **Does it require a legacy Product record?**  
   No.

5. **Does Test Chat use the same current catalog as live Telegram?**  
   Yes. Both inject Customer Sales Brain and AUTHORITATIVE Chat Commerce through Conversation Gateway.

6. **Do offering updates propagate immediately?**  
   Supported committed database updates do. Existing Purchase Intents retain their original snapshot. Membership/channel/status updates are not generally supported, and the generic price route has an unsafe LIVE-publication bypass.

7. **Do archived or invalid offerings disappear immediately?**  
   They are rejected on the next selector query. An existing active Purchase Intent remains historical and may delay replacement until expiry/supersession.

8. **What exact states must be true?**  
   Offering READY; creator matches; channel AI_CHAT; supported SINGLE_IMAGE/PHOTOSET/VIDEO structure; price 300–50,000 USD minor units; one LIVE FANVUE publication; resource PRESENT; provider/resource ID and Media Link URL present; member destinations SINGLE_PPV for single/video or PHOTOSET for photoset; not already attributed purchased.

9. **What can prevent sale at a given moment?**  
   No buying intent/current-turn readiness, unresolved identity, active offer wait/nudge, recent-purchase cooldown, payment pending/unknown, unacknowledged purchase, previous ownership, safety/runtime guard, or catalog ineligibility.

10. **Is Commerce Library the authoritative catalog?**  
    No. It is the analyzed Business Asset library. The authoritative sales catalog is Commercial Offerings evaluated through the Commercial Fulfillment projection and Sales Brain selector.

11. **Can the owner add new offerings daily without developer synchronization?**  
    Single-image offerings can follow that model once provider operation is healthy. PHOTOSET offerings cannot currently satisfy the supported creation and commitment rules in either order, so the statement is not yet true for the complete requested catalog.

12. **What must be fixed before that statement is unqualified?**  
    Fix the PHOTOSET creation/commitment transaction; close the generic LIVE price-update bypass; certify/monitor reconciliation freshness; surface composite selector eligibility in the Commerce UI; define a safe replacement/version policy for membership/channel changes and invalid active intents.

## Final confidence

> Confidence that an owner-approved, newly activated Commercial Offering becomes part of the autonomous sales catalog without restart or developer intervention: **Medium**

Catalog discovery from an already-valid durable state is high-confidence. The overall rating is Medium because the supported PHOTOSET workflow cannot currently produce that state consistently, and a legacy pricing endpoint can desynchronize LIVE terms.
