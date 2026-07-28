# Commerce Recommendation Engine — Session 1

Audit and implementation date: 2026-07-25  
Repository: `C:\Creator-OS-React`  
Branch: `react-migration`  
Baseline HEAD: `76b3c71`

## Outcome

Session 1 extracted deterministic ranking into a dedicated, side-effect-free
`CommerceRecommendationEngine`. Eligibility and commercial safety remain
owned by `CommercialOfferingSelectorService`. Production ordering and public
selector results are unchanged.

Engine version:

```text
commerce_recommendation_v1_parity
```

No schema, provider, delivery, Purchase Intent, pricing, destination, or
publication behavior changed.

## Previous architecture

The configured Telegram and Developer Test Chat runtimes both entered
`ConversationGateway`, which evaluated `CustomerSalesBrainService`. The Sales
Brain called `CommercialOfferingSelectorService.select()`. That one method:

1. read attributed purchased offering IDs;
2. handled the active Purchase Intent branch;
3. fetched candidate fulfillment projections;
4. evaluated creator, status, channel, publication, provider resource,
   delivery URL, price, Content Destination, and prior-purchase eligibility;
5. sorted eligible projections by publication timestamp descending and
   offering UUID ascending;
6. returned `SelectedOfferingResult`.

`CommercialOfferingSelectorRepository` delegates candidate reads to
`CommercialFulfillmentRepository` and purchase exclusion reads to
`PurchaseIntentRepository`.

The exact pre-extraction active-intent behavior is conservative: if an active
intent exists, only its offering is considered. If that offering is absent or
ineligible, selection returns no offering rather than falling back.

`CommerceSalesService.recommend_best()` remains an explicitly labelled
compatibility selector. Authoritative configured conversation mode resolves
the Sales Brain's already-selected offering and blocks compatibility fallback.

## New architecture

```text
Telegram transport or Developer Test Chat
→ ConversationGateway
→ CustomerSalesBrainService
→ CommercialOfferingSelectorService
   → repository candidate and purchase reads
   → eligibility evaluation
   → eligible RecommendationCandidate projections only
→ CommerceRecommendationEngine.rank()
→ SelectedOfferingResult
→ ChatCommerceService resolves the authoritative selection
→ existing Purchase Intent and delivery workflow
```

There is one candidate query. The engine never queries a repository.

## Responsibility boundaries

### Commercial Offering Selector

The selector remains authoritative for:

- creator ownership;
- READY and non-archived offering state;
- AI_CHAT channel;
- LIVE publication;
- provider presence;
- provider resource `PRESENT`;
- delivery URL presence;
- valid price;
- type-specific committed Content Destination;
- attributed purchase exclusion;
- active Purchase Intent lifecycle behavior;
- construction of the existing selector result contract.

### Commerce Recommendation Engine

The engine receives only immutable candidates that already passed selector
eligibility. It ranks them and returns an immutable result and trace. It has no
database, provider, LLM, mutation, publication, delivery, destination, price,
or Purchase Intent dependency.

## Models

- `RecommendationContext`: creator, active-intent offering ID, evaluation
  time, and optional already-known media/conversation identifiers.
- `RecommendationCandidate`: the narrow eligible offering/publication
  projection needed for ranking and downstream trace.
- `RecommendationScoreComponent`: one strategy's raw value, lexicographic
  value, contribution, explanation, and ranking-effect flag.
- `RankedRecommendationCandidate`: rank, components, deterministic reason,
  and selected flag.
- `RecommendationResult`: ranked candidates, selected candidate, reason,
  version, candidate count, and selector-supplied rejection count.

All are frozen dataclasses.

## Parity strategies and ordering

`RecommendationRankingStrategy` is the small extension interface. Session 1
installs, in lexicographic order:

1. `ActivePurchaseIntentStrategy` — matching active intent first;
2. `PublicationRecencyStrategy` — `published_at` descending;
3. `StableOfferingTieBreakStrategy` — offering UUID string ascending.

This reproduces the former selector ordering. No weighted semantic score,
affinity, performance signal, or diversification rule exists.

Previously purchased offerings are removed by eligibility before the engine.
The active-intent selector branch remains unchanged: valid is reused; missing
or invalid yields no offering.

## Trace format

`SelectedOfferingResult.recommendation_result` carries the immutable internal
result. Existing selector metadata also includes a JSON-safe summary:

```json
{
  "recommendationEngineVersion": "commerce_recommendation_v1_parity",
  "recommendationTrace": [
    {
      "rank": 1,
      "offeringId": "00000000-0000-0000-0000-000000000001",
      "title": "Private Release",
      "publishedAt": "2026-07-26T00:00:00+00:00",
      "activeIntentMatch": false,
      "components": [
        {
          "key": "publication_recency",
          "rawValue": "2026-07-26T00:00:00+00:00",
          "explanation": "Newer publication timestamps rank first.",
          "affectedRanking": true
        }
      ],
      "reason": "Ranked by publication timestamp descending.",
      "selected": true
    }
  ]
}
```

No trace table or persistent recommendation log was added. A safe structured
log records version, candidate count, and selected offering ID.

## Runtime parity

Live Telegram composition and Developer Test Chat both construct
`CustomerSalesBrainService`, whose sole authoritative selector now owns the
same default `CommerceRecommendationEngine`. Neither transport has a separate
recommendation implementation. Developer Test Chat continues to omit Telegram
delivery services and cannot send externally.

## Files

Created:

- `app/models/commerce_recommendation.py`
- `app/services/commerce_recommendation_engine.py`
- `app/test_commerce_recommendation_engine.py`
- `docs/system-audit/18-commerce-recommendation-engine-session-1.md`

Modified:

- `app/models/commercial_offering_selection.py`
- `app/services/commercial_offering_selector_service.py`
- `app/test_commercial_offering_selector.py`
- `docs/system-audit/README.md`

## Session 2 extension points

Future ranking logic can add strategies to the engine without moving or
duplicating eligibility. Semantic matching, customer affinity, purchase
history, freshness policy, and diversification remain intentionally absent.
Any future strategy must consume explicit candidate/context data; it must not
query raw Assets, Generation Library records, providers, or databases itself.

## Behavioral-parity statement

Parity is established by engine unit tests, selector integration tests, Sales
Brain tests, Chat Commerce/Purchase Intent tests, and shared Telegram/Test Chat
runtime tests. The selected offering remains:

- the eligible active-intent offering when that branch applies;
- otherwise the newest eligible publication;
- UUID ascending when timestamps tie;
- no offering when none is eligible or the active-intent offering is invalid.

