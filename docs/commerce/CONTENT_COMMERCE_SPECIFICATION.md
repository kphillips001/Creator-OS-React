# Creator OS Content-Commerce Specification

Status: Authoritative  
Applies to: Creator OS content, commerce, recommendation, fulfillment, publishing, and chat workflows  
Change policy: Normative changes require an intentional update to this document

## 1. Purpose

This specification defines the authoritative boundary between canonical media, content commitment, customer-facing Products, provider artifacts, fulfillment, recommendation, and runtime delivery in Creator OS.

Its central rule is:

> A canonical Asset is either Available Inventory or committed to exactly one Content Destination. It must never be committed to two Content Destinations simultaneously.

This document governs future implementation. It records verified current behavior, identifies compatibility gaps, and defines target invariants without prescribing a final database schema.

Analysis, registration, upload, publication, recommendation, and runtime send permission are separate states. No generic `READY` value may collapse them into one concept.

## 2. Authoritative terminology

### Canonical Asset

A canonical Asset is one individual photo, video, story component, or other media item represented by Creator OS canonical media identity, currently `content_items`.

An Asset owns:

- canonical identity;
- creator ownership;
- local media identity;
- creative and generation provenance;
- analysis and safety intelligence;
- provider-media identity after upload;
- archive state.

An Asset is not sellable merely because it is generated, approved, canonical, registered, analyzed, or analysis-ready.

### Available Inventory

Available Inventory is the user-facing name for active canonical Assets that have no authoritative Content Destination commitment.

Available Inventory is a derived view, not a second canonical inventory system. An available Asset:

- may be registered and analyzed;
- may retain generation or Photoshoot provenance;
- is not sellable;
- is not recommendation eligible;
- is not chat deliverable;
- is not automatically uploaded or published;
- may later be committed to exactly one Content Destination.

### Content Destination

A Content Destination answers:

> Where has this Asset been permanently or commercially committed?

Initial categories are:

- `PHOTOSET`
- `VIDEOSET`
- `STORY_SET`
- `TELEGRAM_WALL`
- `TEASER`
- `SINGLE_PPV`
- `BUNDLE`

The domain may add destination types deliberately. It must not use an unbounded generic type system where explicit policy is required.

### Content commitment

A content commitment is the single authoritative association between an Asset and one Content Destination. Provenance, product composition, provider media, publishing jobs, and fulfillment records may reference the same Asset, but those references do not create additional commitments.

### Product

A Product is a customer-facing commercial offer. It answers:

> What can the customer purchase, on what terms, and how is that purchase fulfilled?

A Product is not a Content Destination and does not own canonical media identity.

### Provider media

Provider media is the remote identity assigned to an uploaded binary. Provider-media identity remains asset-scoped because each binary is independently uploaded and processed.

### Media Link

A Media Link is a provider fulfillment artifact. Its authoritative scope may be a destination or Product depending on verified provider semantics. It is not itself canonical media, a content commitment, or a Product.

### Provenance, commitment, commercial lock, archive, and deletion

- **Provenance** records where content came from. It never grants reuse permission.
- **Commitment** assigns an Asset to exactly one Content Destination.
- **Commercial lock** prevents composition changes after a policy-defined business event.
- **Archive** removes an item from active use while preserving identity, commitment, history, and auditability.
- **Deletion** removes data under an explicit deletion policy. It must not erase required sales, entitlement, delivery, or commitment history.

## 3. Current verified architecture

### Generation Library

`GeneratedImageRecord` and `GenerationLibraryService` own generated-output workflow state before staging or creative handoff. Records are persisted in `data/generation_library/generated_images.json`; media is routed through `ContentArchiveService`.

Moving a normal generation to Asset Library changes the existing record from `active` to `staged_asset_library`. It does not create a canonical Asset, copy the file, or create a Business Asset registration.

Generation Library also routes content to Photoshoot Studio, Edit Studio, publishing, and Removed Content. A successful direct publish archives and removes the live generation record; it does not require canonical registration today.

### Asset Library

The current Asset Library is a mixed operational surface over:

- staged `GeneratedImageRecord` records;
- canonical `content_items`;
- typed `photoshoot_commerce_deliverables`;
- archive and restore projections.

It is not one authoritative inventory table. Its standalone staging boundary is a workflow-status projection. Its standalone Register action creates or reuses canonical and Business Asset records. Its Photoshoot Register action promotes an existing aggregate.

The current canonical-Asset grid does not consistently exclude Assets that are approved Photoshoot members. As a result, one Photoshoot may appear as a typed card while its members also appear as ordinary image cards.

### Photoshoot Studio and Photoshoot deliverables

Photoshoot Studio currently:

- starts from a Generation Library seed;
- approves or rejects generated candidates;
- creates canonical Assets during shot approval;
- accepts or declines the full set;
- includes the seed plus all approved shots in an accepted set;
- creates ordered `photoshoot_asset_memberships`;
- creates one `photoshoot_commerce_deliverables` aggregate with a hero Asset;
- stages that aggregate in Asset Library.

Current accepted-set UI does not allow approved non-seed shots to remain unselected. Declined-session salvage may stage selected approved shots individually, but that is not the future accepted-Photoset split workflow.

### Canonical Assets and Business Assets

`content_items` is the canonical media identity. `business_asset_registrations` stores individual Business Asset registration, intelligence lifecycle, destination-routing compatibility fields, publishing readiness, fulfillment readiness, provenance, and archive state.

Standalone Asset Library registration creates or reuses:

1. a canonical `content_items` row;
2. an intelligence profile;
3. a `business_asset_registrations` row.

The Business Asset repository already excludes approved Photoshoot members from ordinary standalone listings. This is useful compatibility behavior, but it is not yet a universal exactly-one commitment authority.

### Products and `product_assets`

Products currently own offer fields including type, status, approval metadata, price, currency, availability-related state, fulfillment strategy, and legacy `media_link`/fulfillment status.

`product_assets` directly relates Products to ordered Assets. Current composition can be replaced while editing. Existing Product types include single image, single video, photo set, video set, story, bundle, session, and custom.

This direct Asset composition predates authoritative Content Destinations. Future paid validation must ensure every Product member belongs to the same sellable destination represented by that Product. Product composition must not create or override commitment.

### Fulfillment registrations

`business_asset_fulfillment_registrations` and `FulfillmentRegistrationService` track provider-neutral, asset-scoped fulfillment progress, including:

- upload routing;
- provider media identifiers;
- provider processing;
- missing, submitted, and verified Media Links;
- fulfillment readiness;
- retry and failure state.

These records are technical readiness projections. They do not grant sales eligibility or destination commitment.

### Chat commerce registrations

`chat_commerce_registrations` currently stores asset-scoped chat availability, fulfillment readiness, recommendation eligibility, delivery eligibility, Product references, provider media, and Media Links.

This is a compatibility model. Future chat eligibility must validate destination policy and, for paid delivery, the Product backed by that destination. An asset-scoped chat row must not independently authorize a sale or delivery.

### Publishing jobs

Publishing jobs are durable execution records and may be asset- or Product-scoped. They track upload, provider media IDs, provider processing, Media Link requirements, completion, failure, and retries.

Publishing jobs execute transport/provider work. They do not own Product approval, commitment, entitlement, or runtime send permission.

### Telegram Wall

Current Generation Library publishing can post directly to Telegram Wall or Telegram Chat through `GenerationLibraryPublishingService` and `SocialPublishingService`. That route can act on an active generation without an authoritative commitment record.

Future Telegram Wall behavior must commit content before transport. A successful or failed post is operational history; it does not create, remove, or transfer commitment.

### Fanvue upload and Media Links

Fanvue upload services create one remote media identity per uploaded binary. Photoshoot upload currently iterates completed Photoshoot records and uploads each member independently.

The repository has manual Media Link submission and verification paths in Product, fulfillment, publishing, and chat compatibility layers. Fanvue upload exists, but automatic Media Link creation is not an established general capability.

## 4. Target business rules

1. Every active canonical Asset is either Available Inventory or committed to exactly one Content Destination.
2. No workflow may create a second commitment for an already committed Asset.
3. Registration and analysis do not commit content.
4. Commitment does not imply technical delivery readiness.
5. Technical readiness does not imply Product eligibility.
6. Product eligibility does not imply runtime send permission.
7. Provenance and remote provider references never count as additional destinations.
8. Destination policy determines whether composition is permanently immutable or editable until a commercial lock.
9. Archiving never silently releases a commitment.
10. Runtime or provider failure never releases a commitment.
11. A derivative or intentionally cloned canonical Asset is a new identity and may receive its own destination. The original remains committed.
12. Historical sales, entitlements, deliveries, and publications must preserve the exact committed composition used at the time.

## 5. Content Destination definitions

### PHOTOSET

- Created through Photoshoot Studio final curation.
- Contains selected approved Photoshoot Assets.
- Keeps the seed as hero and first member unless an explicit later feature changes that rule.
- Becomes immutable when finalized.
- Members cannot later enter any other Photoset, Telegram Wall, Teaser, Single PPV, or Bundle.
- The creative Photoshoot session remains provenance.
- The durable Photoshoot deliverable represents the collection.

### VIDEOSET

- Future curated-video equivalent of a Photoset.
- Becomes immutable when finalized.
- Video Studio behavior is deferred.

### STORY_SET

- Future curated-story equivalent of a Photoset.
- Becomes immutable when finalized.
- Story Studio behavior is deferred.

### TELEGRAM_WALL

- Commits Assets permanently to free Wall publication.
- Members are non-resellable and cannot enter chat offers, PPVs, Bundles, Photosets, or Teasers.
- Commitment precedes and is separate from posting.
- Posting retries or failures do not release commitment.

### TEASER

- Commits one Asset as a free chat-deliverable preview or conversion aid.
- Is not a paid Product and is never sellable.
- Cannot later become PPV, Bundle, Photoset, Story Set, Video Set, or Telegram Wall content.
- Delivery requires provider artifacts, fulfillment readiness, Chat Eligibility, and Runtime Send Permission.

### SINGLE_PPV

- A sellable destination containing exactly one Asset.
- May be editable before commercial use.
- Becomes immutable after the first completed sale, active entitlement, publication dependency, or equivalent durable commercial-history event.
- Requires a valid active Product and price before recommendation.

### BUNDLE

- A sellable destination containing multiple Assets selected only from Available Inventory.
- Cannot contain members committed elsewhere.
- May be editable while draft.
- Becomes immutable after activation, first sale, active entitlement, publication dependency, or another explicit commercial lock event.

## 6. Lifecycle diagrams

### Standalone Asset

```text
Generated
→ staged
→ registered/canonical
→ analyzed
→ Available Inventory
→ committed to exactly one Content Destination
→ provider/fulfillment preparation
→ destination-appropriate eligibility
→ delivered or published when runtime permits
```

Registration and analysis may occur in a different operational order, but Available Inventory begins only after canonical identity exists and no commitment exists.

### Photoset

```text
Generation Library seed
→ Photoshoot creative session
→ candidate generation
→ approve/reject shots
→ final review
   ├─ selected seed + selected approved shots
   │  → finalized immutable PHOTOSET commitment
   │  → typed Photoshoot deliverable
   │  → Asset Library aggregate registration
   │  → member and aggregate analysis
   │  → optional Product and fulfillment preparation
   └─ approved but unselected shots
      → canonical Assets with Photoshoot provenance
      → Available Inventory

Rejected shots → excluded/junked
```

The approved-but-unselected branch is target behavior and is not current behavior.

### Paid destination and Product

```text
Available Inventory
→ SINGLE_PPV or BUNDLE/collection commitment
→ destination composition validated
→ Product created or linked
→ Product approved, priced, and activated
→ provider media prepared
→ Media Link/fulfillment verified
→ Product Eligible
→ Chat Eligible for paid recommendation
→ Runtime Send Permitted
→ offer, sale, entitlement, and delivery
→ commercial lock preserved
```

### Telegram Wall

```text
Available Inventory
→ TELEGRAM_WALL commitment
→ provider media preparation if required
→ Runtime Send Permitted
→ post attempt
   ├─ success → publication history
   └─ failure → retry/error history

Commitment remains in both branches.
```

### Teaser

```text
Available Inventory
→ TEASER commitment
→ provider media/fulfillment preparation
→ Chat Eligible for free delivery
→ Runtime Send Permitted
→ free delivery history
```

## 7. Eligibility dimensions

| Dimension | Authoritative question | Must not imply |
|---|---|---|
| Analysis Ready | Has local analysis and required safety intelligence completed? | Commitment, sale, upload, or send permission |
| Destination Committed | Has the creator assigned this Asset to exactly one destination? | Technical or commercial readiness |
| Technically Deliverable | Do required remote media, links, and fulfillment artifacts exist and verify? | Product approval, recommendation, or runtime permission |
| Product Eligible | Is the paid Product active, approved, correctly priced, available, and backed by valid committed deliverables? | Runtime permission |
| Chat Eligible | May chat select this candidate for its permitted paid or free behavior? | Permission to execute now |
| Runtime Send Permitted | Do runtime mode, global automation safety, module switches, deployment permits, credentials, and transport state allow execution now? | Content eligibility or commitment changes |

Each dimension requires its own state and reason codes. UI summaries may aggregate them but must preserve their individual truth.

## 8. Product and fulfillment boundaries

Products remain separate from Content Destinations.

Products own:

- title and description;
- price and currency;
- status, approval, and availability;
- customer entitlement terms;
- fulfillment strategy;
- commercial presentation.

A Product may represent `PHOTOSET`, `VIDEOSET`, `STORY_SET`, `SINGLE_PPV`, or `BUNDLE`. `TELEGRAM_WALL` and `TEASER` are not paid Products.

Product composition must be validated against one destination:

- every member must belong to that destination;
- no member may be borrowed from another destination;
- Product edits must not mutate immutable destination membership;
- paid recommendation must validate both Product state and actual committed deliverables.

Current `product_assets` and legacy `products.legacy_content_item_id` can reference Assets without a first-class destination authority. Current Product `media_link` also mixes provider fulfillment state into Product core. These are compatibility facts, not target authorization rules.

Fulfillment creates and verifies provider artifacts. It must never choose content, create commitment, activate a Product, or grant runtime send permission.

## 9. Photoshoot integration

Photoshoot Studio is the authoritative Photoset curation point. A separate post-Photoshoot collection builder must not ask the creator to repeat member selection.

Current behavior:

- approve/reject individual shots;
- accept or decline the whole set;
- accepted set includes seed plus all approved shots;
- finalization creates one typed Photoshoot deliverable;
- Asset Library later registers the aggregate.

Target behavior:

- final review permits selection among approved non-seed shots;
- seed remains required hero/first member;
- selected Assets receive immutable `PHOTOSET` commitment;
- approved unselected Assets remain Available Inventory;
- rejected shots remain excluded/junked;
- finalization is idempotent and auditable.

Canonical member creation during shot approval is provenance and identity creation, not commitment. Commitment occurs at finalized curation.

## 10. Available Inventory definition

An Asset is Available Inventory only when all of the following are true:

- it has canonical identity;
- it belongs to the active creator;
- it is not deleted and is eligible for active inventory display;
- it has no authoritative Content Destination commitment.

Registration, analysis state, Photoshoot provenance, provider upload state, and historical Generation Library state do not by themselves determine availability.

Committed Assets must not appear as available standalone cards, registration candidates, Product-composition candidates, recommendation candidates, or alternate-destination candidates.

Available Inventory should eventually be computed from canonical Assets plus authoritative commitment records and archive policy. It must not be represented by a second competing canonical Asset table.

## 11. Immutability and locking matrix

| Destination | Composition before finalization/lock | Lock event | After lock |
|---|---|---|---|
| PHOTOSET | Selected during final Photoshoot curation | Photoset finalization | Permanently immutable |
| VIDEOSET | Selected during future video curation | Videoset finalization | Permanently immutable |
| STORY_SET | Selected during future story curation | Story Set finalization | Permanently immutable |
| TELEGRAM_WALL | Selected before commitment | Wall commitment finalization | Permanently immutable/non-resellable |
| TEASER | Selected before commitment | Teaser commitment finalization | Permanently immutable/non-sellable |
| SINGLE_PPV | Editable while draft and unused | First sale, entitlement, publication dependency, or equivalent history | Immutable |
| BUNDLE | Editable while draft and unused | Activation, first sale, entitlement, publication dependency, or explicit lock | Immutable |

Archive does not unlock composition. Provider failure, revoked links, or missing remote media do not unlock composition. Any exceptional administrative reversal must be explicit, audited, policy-controlled, and must preserve historical truth; it must never be inferred from archive or readiness state.

## 12. Chat behavior matrix

| Content state/type | Paid recommendation | Free delivery | Sellable | Required validation |
|---|---:|---:|---:|---|
| Available Inventory | No | No | No | Must first receive a destination |
| PHOTOSET Product | Yes | No | Yes | Destination, Product, fulfillment, chat, runtime |
| VIDEOSET Product | Yes | No | Yes | Destination, Product, fulfillment, chat, runtime |
| STORY_SET Product | Yes | No | Yes | Destination, Product, fulfillment, chat, runtime |
| SINGLE_PPV Product | Yes | No | Yes | Destination, Product, fulfillment, chat, runtime |
| BUNDLE Product | Yes | No | Yes | Destination, Product, fulfillment, chat, runtime |
| TEASER | No | Yes | No | Teaser commitment, fulfillment, chat, runtime |
| TELEGRAM_WALL | No | No | No | Wall publishing path only |

The recommendation engine reasons from destination and Product identity. Asset intelligence supports ranking, safety, description, and presentation but cannot authorize cross-destination reuse.

Chat must never sell or send uncommitted Assets, sell Teasers, sell Wall content, or deliver a candidate outside its destination policy.

## 13. Fanvue artifact rules

1. Each uploaded Asset binary receives its own provider-media identity.
2. Provider media references the canonical Asset and does not alter commitment.
3. Upload may be shared by multiple legitimate projections of the same committed content, but may not authorize a second destination.
4. A Single PPV may use one Asset and one commercial link.
5. A Photoset may require multiple provider-media records and one set-level Media Link if Fanvue supports multi-media links.
6. A Teaser may require provider media or another free-delivery artifact but must not require a paid Product.
7. Telegram Wall may require provider media but not a paid Media Link.
8. Media Link revocation removes technical eligibility; it does not release commitment.
9. Upload and Media Link creation must be explicit provider operations with idempotency and audit history.
10. Automatic Media Link creation must not be assumed from the existence of upload services.

Exact Fanvue Media Link scope, payload, pricing, currency handling, multi-media ordering, entitlement semantics, update behavior, revocation behavior, and idempotency must be verified against the official Fanvue API before implementation.

## 14. Runtime-safety separation

Content eligibility answers whether an action is allowed in principle. Runtime safety answers whether that allowed action may execute now.

Outbound execution must pass all applicable runtime gates:

- global automation safety;
- runtime mode;
- module-specific enablement;
- deployment permit;
- account and credential validity;
- provider availability;
- transport readiness;
- idempotency and duplicate-send protection.

A blocked runtime action must not mutate Product eligibility, destination commitment, Available Inventory, or commercial lock state. Conversely, an eligible item must remain unsent when runtime permission is absent.

## 15. Compatibility notes

Current code that conflicts with or predates the target model includes:

- Asset Library may show canonical Photoshoot members as standalone image cards.
- `business_asset_registrations` contains destination-routing fields but is not yet an authoritative exactly-one content commitment.
- `product_assets` directly composes Assets without mandatory destination validation.
- Products contain legacy provider/media-link fulfillment state.
- Fulfillment and chat registrations are primarily asset-scoped.
- Generation Library can publish directly without canonical registration or destination commitment.
- Telegram publishing treats transport as the primary operation rather than requiring prior Wall commitment.
- Current accepted Photoshoots contain all approved shots; no accepted-set Available Inventory split exists.
- Photoshoot membership persistence does not universally enforce that an Asset cannot belong to another commitment.
- Photoshoot registration requires member Business Asset registrations but does not itself create missing member registrations.
- Publishing jobs may be asset- or Product-scoped and do not encode authoritative destination ownership.

Compatibility adapters may remain during migration, but no adapter may be treated as a second commitment authority.

## 16. Explicitly deferred features

- Database schema and migration design.
- Final Photoshoot shot-selection UI.
- Available Inventory UI.
- Content Destination management UI.
- VIDEOSET and Video Studio behavior.
- STORY_SET and Story Studio behavior.
- Full Bundle builder.
- Commercial lock-event implementation.
- Historical entitlement integration.
- Automated Fanvue Media Link creation.
- Fanvue multi-media Media Link implementation.
- Destination-aware recommendation implementation.
- Telegram Wall commitment workflow.
- Teaser pool and free-delivery implementation.
- Administrative commitment reversal policy.

## 17. Implementation roadmap

The order below is normative at the dependency level, not a commitment to a particular schema.

1. **Establish commitment authority**
   - Define durable destination identity and exactly-one Asset commitment.
   - Add transactional conflict detection and audit provenance.
2. **Build derived availability**
   - Define Available Inventory from canonical Assets minus commitments.
   - Exclude committed members consistently across all read models.
3. **Integrate Photoshoot finalization**
   - Select approved non-seed shots.
   - Commit selected members atomically to `PHOTOSET`.
   - Preserve approved unselected Assets as Available Inventory.
4. **Harden Product composition**
   - Bind Products to one sellable destination.
   - Validate that legacy `product_assets` cannot cross destination boundaries.
5. **Separate readiness dimensions**
   - Expose analysis, commitment, technical, Product, chat, and runtime states independently.
6. **Align fulfillment and provider artifacts**
   - Preserve asset-scoped provider media.
   - Verify and implement destination/Product Media Link scope.
7. **Gate recommendations and chat**
   - Build paid candidates from eligible Products and free candidates from Teasers.
   - Reject Available Inventory and cross-destination candidates.
8. **Add immutable commercial history**
   - Lock compositions on destination-specific events.
   - Preserve sales, entitlements, delivery, and publication snapshots.
9. **Migrate compatibility paths**
   - Gate direct Generation Library/Telegram publishing with destination policy.
   - Retire duplicate or ambiguous readiness authority only after read/write parity.

Every phase requires idempotency, creator ownership validation, transactional commitment enforcement, audit logging, and regression tests.

## 18. Non-negotiable invariants

1. One canonical Asset has at most one authoritative Content Destination.
2. Available Inventory means no commitment; it is never an independent canonical store.
3. Registration and analysis never make content sellable.
4. Committed Assets never appear as standalone available candidates.
5. Photoset, Videoset, Story Set, Wall, and Teaser membership is immutable after finalization.
6. Single PPV and Bundle composition is immutable after a commercial lock event.
7. Archiving never releases commitment.
8. Runtime and provider failure never releases commitment.
9. Provider media identity never creates another destination.
10. Products remain separate from destinations and cannot cross destination boundaries.
11. Paid recommendation requires both an eligible Product and valid committed deliverables.
12. Free chat delivery is limited to eligible Teasers.
13. Chat never sends or sells Available Inventory.
14. Telegram Wall and Teaser Assets are permanently non-resellable.
15. Runtime send permission remains independent from all eligibility dimensions.
16. Historical delivery and entitlement composition remains reproducible.
17. Commitment operations are creator-scoped, idempotent, transactional, and auditable.
18. A cloned or derivative canonical Asset is a new identity; the original commitment remains unchanged.

## 19. Open Fanvue API questions

These questions must be answered from current official Fanvue API documentation or an authorized provider test before implementation:

1. Is a Media Link scoped to one media UUID, several media UUIDs, a post, a message, or another provider object?
2. Does Fanvue support one paid link containing an ordered multi-image Photoset?
3. What are the exact create, read, update, deactivate, and revoke endpoints?
4. What payload fields define media ordering, title, description, price, currency, and availability?
5. Can an existing Media Link change media or price after use?
6. What event makes a link commercially immutable?
7. What entitlement or purchase records identify completed sales and active access?
8. Are idempotency keys supported, and what is their scope and retention period?
9. How are upload processing and Media Link creation failures retried safely?
10. Can free Teaser delivery reference provider media without a paid link?
11. Does Telegram Wall publication require Fanvue provider media at all?
12. How are remote deletions or revocations reported?
13. Are provider-media UUIDs reusable across links without duplicating upload?
14. Are preview and full media separate required identities?
15. What webhook or polling states establish media and link readiness?

Until these questions are verified, implementation must not infer automatic Media Link creation, set-level link scope, pricing behavior, or multi-media fulfillment from current UI or legacy fields.

## 20. Change control

This specification is the authoritative content-commerce contract for Creator OS.

Future implementation sessions must:

- cite this document when designing content commitment, inventory, Products, recommendation, fulfillment, publishing, or chat behavior;
- preserve all non-negotiable invariants;
- identify compatibility behavior explicitly;
- avoid creating a competing commitment or canonical inventory authority;
- update tests and documentation when implementing an approved rule.

Any deviation from this specification requires an intentional review and update to this document before or alongside implementation. Accidental divergence, compatibility shortcuts, provider-specific assumptions, and generic `READY` fields do not supersede this specification.

The specification should record the reason, decision owner, date, affected invariants, migration implications, and backward-compatibility plan for every normative change.
