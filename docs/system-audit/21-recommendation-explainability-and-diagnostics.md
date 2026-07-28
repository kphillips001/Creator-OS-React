# Recommendation Explainability and Diagnostics

## Migration activation

Session 4 inspected the configured PostgreSQL target without exposing its
connection string or credentials. The server is local (`::1`, port 5432) and
the database is `fanvue_chatbot`.

Migration `20260725_010_commerce_recommendation_learning.sql` was applied with
the new transactional, checksum-guarded
`SchemaManagerService.reconcile_one()` operation. This operation applies or
records exactly one named migration and refuses checksum drift, so the unrelated
pending `20260721_009_photoshoot_seed_covers.sql` was not applied.

The target migration checksum matches its migration-history record, its
rollback file exists, both learning tables and expected uniqueness constraints
exist, and the customer-history index exists. Target-table certification
passes. Overall repository schema certification remains `FAIL` solely because
`20260721_009_photoshoot_seed_covers.sql` is still absent from migration
history; that condition predates Session 4 and remains intentionally untouched.

## Exact trace propagation

The trace is created once by `CommerceRecommendationEngine` and projected by
`CommercialOfferingSelectorService`. It now travels unchanged through:

```text
CommerceRecommendationEngine
→ CommercialOfferingSelectorService.selector_metadata
→ CustomerSalesDecision.decision_metadata
→ ConversationGateway.diagnostic_metadata
→ Developer Test Chat response
```

The selector projection includes engine version, candidate/rejection counts,
selection reason, active Purchase Intent control, ranked candidates, offering
type and price, final scores, component raw values, configured weights,
weighted contributions, bounded evidence, and deterministic tie-break values.
Scores are displayed as ranking scores, never purchase probabilities.

For a successfully presented Telegram offer, the same trace is copied into
Purchase Intent metadata. A subsequent observed outcome stores that trace in
the append-only Commerce Learning outcome. Telegram customer response text does
not include diagnostic metadata.

## Developer Test Chat

Test Chat continues through the real Conversation Gateway, Customer Sales
Brain, Commercial Offering Selector, and Recommendation Engine. Its collapsible
**Recommendation Decision** section displays:

- sell authorization and Sales Brain reason;
- engine version and eligible count;
- selected offering and ranking score;
- active Purchase Intent override;
- exact component score/weight/contribution rows;
- the top five ranked candidates;
- current observed Commerce Learning preferences and confidence.

When no profile exists it states: “No observed commerce-learning history yet.”
The existing **External Sends Disabled** warning and transport-free harness are
unchanged.

## Recommendation Diagnostics workspace

The protected route `/developer/recommendations` is read-only. It provides:

- outcome and engine-version filters;
- outcome, learning-profile, purchase, and ignored/expired summary counts;
- paginated outcome-linked recommendation history;
- safe buyer identifiers;
- selected score, outcome, active-intent state, and engine version;
- exact captured candidate ranking and score breakdown;
- observed outcome evidence.

History is intentionally limited to actual outcomes whose recommendation trace
was persisted. Recommendations that produced no Purchase Intent or observed
outcome are available in the immediate Test Chat response and structured
runtime diagnostics, but are not duplicated into a second persistence model.

## APIs

- `GET /api/v1/developer/recommendations`
- `GET /api/v1/developer/recommendations/{outcome_id}`
- `GET /api/v1/developer/commerce-learning`
- `GET /api/v1/developer/commerce-learning/{buyer_uuid}`
- `GET /api/v1/developer/commerce-learning/outcomes`
- `GET /api/v1/developer/commerce-learning/outcomes/{outcome_id}`

All use the existing developer authorization dependency. List limits are
bounded, outcome history uses a single paginated query, and summary metrics use
aggregate queries rather than per-row lookups.

## Privacy and safety

- Buyer identifiers in Recommendation Diagnostics are deterministic,
  non-reversible hashes.
- Tokens, authorization headers, cookies, client secrets, Telegram sessions,
  and signatures are recursively removed from diagnostic projections.
- Strings and collections are bounded.
- No raw conversation history or provider payload is persisted by this layer.
- There are no edit, reset, delete, rerun, send, or provider controls.
- No provider, Telegram, Fanvue, LLM, generation, or embedding call is made.

## Operator workflow

1. Use Developer Test Chat to exercise the real brain without external sends.
2. Expand **Recommendation Decision** for the exact current-turn trace.
3. Use **Recommendation Diagnostics** for persisted outcome-linked history.
4. Open a decision to compare the trace captured at recommendation time with
   its later outcome evidence.
5. Use **Commerce Learning** for the current customer profile projection.

The trace-at-decision, later outcome, and current learning profile are separate
concepts and must not be presented as though they occurred simultaneously.

## Known limitations

- Overall schema certification remains blocked by the unrelated pending
  `20260721_009` history entry described above; the Session 3 learning schema
  itself is active and certified.
- Outcome-linked history begins only when the learning schema is active and an
  authoritative observed outcome is recorded.
- No separate decision-event table was added; no-outcome recommendations are
  deliberately not persisted to avoid noisy duplicate telemetry.
- The diagnostics workspace derives average-free summary values because the
  current schema does not persist a selected score as a relational column.

## Tests

Coverage includes protected and redacted diagnostic APIs, bounded pagination,
exact trace propagation, selector trace detail, Test Chat explainability and
cold-start behavior, diagnostics filters/detail/empty/error rendering, existing
ranking regression suites, TypeScript, ESLint, Python compilation, and frontend
regression tests.
