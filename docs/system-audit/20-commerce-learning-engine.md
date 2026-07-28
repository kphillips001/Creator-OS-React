# Commerce Learning Engine

## Scope

Session 3 extends `commerce_recommendation_v2_intelligent`; it does not replace
the selector, eligibility rules, Sales Brain, Purchase Intent lifecycle, or
commercial safety boundary. The recommendation engine remains stateless,
deterministic, provider-free, and read-only while ranking.

## Learning model

`CustomerCommerceLearningProfile` is the persisted projection for one
creator/Fanvue-account/buyer tuple. It contains:

- observed theme, activity, location, clothing/wardrobe/outfit, collection,
  and photoshoot preferences;
- preferred offering/media type and observed purchase price range;
- average purchase price and interval;
- repeat-purchase frequency;
- outcome counts, evidence count, confidence, and last observation time.

The profile is rebuilt deterministically from the append-only outcome ledger.
It is a projection, not a second source of event truth.

## Observed evidence

The authoritative vocabulary is `PRESENTED`, `OPENED`, `PURCHASED`, `IGNORED`,
`EXPIRED`, `DECLINED`, `ABANDONED`, and `REFUNDED`.

Learning never uses an inferred conversion. Current automatic observations are:

- successful Telegram delivery: `PRESENTED`;
- an explicitly recorded click: `OPENED`;
- hard-attributed verified payment: `PURCHASED`;
- Purchase Intent expiration: `EXPIRED`;
- failed Telegram delivery after intent creation: `ABANDONED`.

`IGNORED`, `DECLINED`, and `REFUNDED` are supported by the canonical outcome
service, but are recorded only when an authoritative producer supplies that
event. Absence of an event does not create learning. This deliberately avoids
turning silence or ambiguous provider data into a preference.

Each event has a unique source key, so retries rebuild the same profile without
double-counting. Recommendation trace and offering evidence are retained with
the event.

## Outcome processing

`CommerceLearningService` enriches an observed event from the selected
Commercial Offering and its canonical assets:

- Commercial Offering type and price;
- photoshoot membership;
- Asset Intelligence themes, activity, location, wardrobe/outfit, and
  suggested collections.
- matched conversation-theme tokens from the selected v2 recommendation trace.
  Only tokens that were actually present in the customer request and matched
  the selected offering are retained.

Evidence effects are deterministic:

| Outcome | Net effect |
| --- | ---: |
| Presented | 0.00 |
| Opened | +0.20 |
| Purchased | +1.00 |
| Ignored | -0.10 |
| Expired | -0.08 |
| Declined | -0.20 |
| Abandoned | -0.12 |
| Refunded | -1.00 |

Repeated purchases add repeated positive evidence and increase profile
confidence. Negative observed outcomes reduce preference strength. With no
history the profile is empty and neutral.

## Adaptive ranking

`CustomerAffinityStrategy` consumes the persisted profile supplied by
`CommercialOfferingSelectorService`. It no longer needs to reconstruct the
customer profile during every rank operation.

Explainable matches cover collection, activity, location, outfit, offering
type, photoshoot, and price range. The component records matched profile
values, applied deterministic boosts, learning confidence, evidence count, and
the `COMMERCE_LEARNING_PROFILE` source marker. The existing verified-purchase
context remains a rollout fallback only when no learning profile exists.

Eligibility, creator ownership, publication readiness, delivery URL checks,
already-purchased exclusions, active-intent behavior, and Customer Sales Brain
authorization are unchanged.

## Recommendation trace

The v2 trace continues to expose every ranked candidate and weighted component.
The customer-affinity component now includes:

- observed preference matches and their score/confidence;
- preferred offering type, price-band, and photoshoot boosts;
- profile confidence and evidence count;
- the selected candidate, final score, deterministic reason, and engine
  version.

The selected trace is copied into Purchase Intent metadata and retained on
subsequent observed outcomes. This makes a future result reproducible without
changing the ranker into a stateful service.

## Diagnostics

Developer Tools now includes **Commerce Learning**, a protected read-only page
that shows:

- observed preferences and confidence;
- evidence and outcome counts;
- preferred offering type;
- recent outcomes and recommendation history/trace returned by the API.

There are no mutation controls. The endpoints are protected by the existing
developer authorization dependency.

## Persistence and performance

Migration `20260725_010_commerce_recommendation_learning.sql` adds:

- append-only `commerce_recommendation_outcomes`, with a unique source-event
  key and customer/time index;
- one `customer_commerce_learning_profiles` projection per
  creator/account/buyer.

The migration has a rollback and is not applied by this implementation
session. At selection time the incremental database cost is one indexed profile
lookup. Ranking remains in-memory over the already bounded eligible candidate
set. Profile rebuild work occurs only when an observed outcome is recorded,
not on every recommendation.

## Tests

Focused coverage includes:

- purchase, repeat purchase, ignored, expired, and refunded learning;
- cold start/no history;
- deterministic and idempotent persistence;
- persisted-profile ranking improvement and explainable trace evidence;
- Purchase Intent lifecycle observation;
- developer diagnostics rendering;
- existing recommendation, selector, Sales Brain, conversation, and Commerce
  safety regression suites.

No live provider, Telegram, Fanvue, paid model, or production database call is
required.
