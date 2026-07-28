# Commerce Recommendation Engine — Session 2

Implementation date: 2026-07-25  
Repository: `C:\Creator-OS-React`  
Branch: `react-migration`  
Baseline HEAD: `76b3c71`

## Outcome

The Session 1 parity engine was upgraded to deterministic, explainable
intelligent ranking:

```text
commerce_recommendation_v2_intelligent
```

The selector remains the only eligibility and commercial-safety authority.
The engine receives only eligible `RecommendationCandidate` values and has no
repository, database, provider, LLM, mutation, delivery, or Purchase Intent
write dependency.

## Architecture

```text
Telegram / Developer Test Chat
→ ConversationGateway
→ CustomerSalesBrainService
→ CommercialOfferingSelectorService
   → attributed-purchase exclusion read
   → bounded recommendation-history read
   → enriched eligible-candidate read
   → all existing eligibility checks
→ CommerceRecommendationEngine
   → active-intent override
   → semantic match
   → customer affinity
   → freshness
   → diversification
   → recent offer history
→ ChatCommerceService
→ existing Purchase Intent and delivery workflow
```

Newly activated offerings remain visible on the next selector call. There is
no recommendation cache, index, embedding job, or reindex operation.

## Candidate and context data

### Candidate projection

The existing Commercial Fulfillment query now includes two correlated,
set-based intelligence projections:

- `asset_intelligence_profiles.profile_data` for all offering member Assets;
- the hero Asset's approved Photoshoot membership and corresponding
  `photoshoot_intelligence_profiles.profile_data`, when present.

The projection contains no blobs or raw provider payloads. Candidate
intelligence is normalized into deterministic tuples covering title,
description, offering type, themes, keywords, activity, setting, environment,
location, clothing, pose, mood, atmosphere, emotional tone, visual style,
content summary, suggested collections, and available Photoshoot fields.

### Customer context

Ranking uses:

- the current message;
- media type extracted by the existing `ChatCommerceService` parser;
- at most three recent user messages from the supplied chat history;
- up to ten Purchase Intents from the last 30 days;
- themes/types from `PURCHASED` plus `ATTRIBUTED` history only.

UNKNOWN or otherwise unverified purchases never create affinity. Handles,
display names, protected provider payloads, and inferred sensitive attributes
are not ranking inputs.

## Query behavior

A normal no-active-intent selection performs:

1. one attributed-purchase exclusion query;
2. one bounded buyer recommendation-history query;
3. one enriched candidate query.

Strategies perform zero queries. There are no per-candidate reads. An active
Purchase Intent preserves the earlier narrow path: purchase exclusion read
plus one candidate lookup, with no history query.

## Normalization

`RecommendationTextNormalizer` lowercases, removes harmless punctuation,
normalizes whitespace, removes a small commerce/chat filler stopword set,
deduplicates tokens, and retains deterministic two- and three-token phrases.
It does not stem, fuzz, embed, or call external NLP.

## Strategies and formulas

### Semantic Match

Token matches use the highest matching field weight:

| Field group | Score |
|---|---:|
| title | 1.00 |
| offering type | 0.95 |
| search phrase | 0.90 |
| theme | 0.88 |
| activity | 0.86 |
| keyword | 0.76 |
| setting/environment/location | 0.74 |
| wardrobe/outfit/clothing | 0.72 |
| description/content/Photoshoot summary | 0.58 |
| mood/style/atmosphere/emotional tone | 0.38–0.40 |

The token score is the sum of each query token's best field match divided by
the number of meaningful query tokens. Exact normalized two-/three-token
phrase matches add up to 0.20. The result is capped at 1.0. No meaningful
query returns neutral 0.5.

### Customer Affinity

Only verified attributed-purchase tags and offering types are used:

```text
score = tag_overlap_ratio × 0.80
      + verified_offering_type_match × 0.20
```

No verified history returns neutral 0.5.

### Freshness

Authoritative publication age is linearly interpolated between:

```text
≤1 day  1.00
7 days  0.90
30 days 0.70
90 days 0.50
180 days 0.30
365+ days floor 0.15
```

Missing publication time receives 0.15. The ranking context clock controls all
tests and calculations.

### Diversification

The most recent ten presentations within 30 days are considered. The largest
applicable similarity penalty is used:

- same offering: 1.00;
- same Photoshoot/collection: 0.75;
- intelligence-token overlap: up to 0.60;
- same offering type: 0.15.

```text
score = 1 - maximum_similarity_penalty
```

Absent history returns 1.0.

### Recent Offer History

For the same offering:

```text
≤1 day  0.05
≤3 days 0.30
≤7 days 0.55
≤30 days 0.80
older / never 1.00
```

## Weights and final ordering

`RecommendationWeights` is frozen, injectable, rejects negative/out-of-range
values, and requires a total of exactly 1.0 within floating tolerance.

Defaults:

```text
Semantic Match       0.45
Customer Affinity    0.25
Freshness            0.15
Diversification      0.10
Recent Offer History 0.05
```

```text
final_score = Σ(raw_strategy_score × configured_weight)
```

Scores and contributions are rounded to eight decimal places. Ordering is:

1. eligible active Purchase Intent override;
2. final score descending;
3. publication timestamp descending;
4. offering UUID ascending.

## Active Purchase Intent

Behavior is unchanged. The selector considers only the active intent's
offering. If eligible, it is reused regardless of weighted score. If missing
or ineligible, no fallback offering is selected. Ranking never mutates intent
state.

## Cold start

- No verified customer history: affinity is 0.5.
- No semantic request: semantic score is 0.5.
- No presentation history: diversity and recent-history scores are 1.0.
- No structured Asset Intelligence: title, description, and offering type
  remain available.
- Equal intelligent scores: Session 1 publication recency and UUID ordering
  remains the tie-break.
- One eligible candidate: it is selected.

## Trace

Each ranked item includes rank, offering identity/type, publication time,
final score, raw scores, weighted contributions, safe evidence, explanations,
tie-break data, selected status, summary, and engine version.

Example:

```json
{
  "recommendationEngineVersion": "commerce_recommendation_v2_intelligent",
  "recommendationSummary": "Selected \"Coastal Sunset Photoset\" using semantic match, customer affinity, freshness.",
  "recommendationTrace": [{
    "rank": 1,
    "offeringId": "00000000-0000-0000-0000-000000000001",
    "finalScore": 0.789,
    "components": [{
      "key": "semantic_match",
      "rawValue": 0.82,
      "weightedContribution": 0.369,
      "evidence": {
        "matchedTokens": ["beach", "sunset"],
        "matchedFields": ["title", "themes"]
      }
    }],
    "selected": true
  }]
}
```

The trace contains no OAuth data, provider payloads, secrets, or raw
conversation history.

## Known limitations and Session 3 extension points

- No React recommendation-debug UI or persistent trace exists.
- Affinity is limited to hard-attributed purchases within the bounded history
  projection.
- Recent user messages contribute only when transports supply chat history.
- Photoshoot identity is resolved through approved hero membership.
- There is no click/impression event beyond Purchase Intent presentation.
- No embeddings, fuzzy semantics, conversion optimization, revenue score,
  inventory balancing, dynamic pricing, or model learning exists.

Session 3 can expose the existing safe trace through developer diagnostics
without changing ranking or adding a second recommendation path.

