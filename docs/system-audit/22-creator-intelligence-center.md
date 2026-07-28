# Creator Intelligence Center

## Purpose

The Creator Intelligence Center is the default Creator OS landing page and a
read-only executive console. It summarizes persisted operational, commerce,
learning, customer, and content-pipeline evidence. It does not send messages,
publish content, call providers, run paid AI, or mutate production data.

## Request path

`CreatorIntelligencePage` makes one request to
`GET /api/v1/creator-intelligence`. `CreatorIntelligenceService` composes:

- one account-scoped aggregate query from `CreatorIntelligenceRepository`;
- the existing `OperationsWorkspaceService.overview()` projection;
- the existing Generation Library record source;
- `SchemaManagerService.certify()` for migration and schema evidence.

The aggregate repository uses scalar subqueries in one database round trip.
The page does not poll. Recommendations are deterministic rules over the
returned snapshot, and never invoke an AI provider.

## Evidence rules

Health cards always include their evidence source. An uninstrumented frontend
heartbeat is reported as a warning rather than inferred healthy. Worker status
comes from persisted Operations heartbeat evidence. Database and provider
status come from Operations. Schema status comes from schema certification.

The “Today” boundary is midnight UTC on the backend clock. Revenue is stored
and transported in minor currency units and formatted only in the browser.
Conversion rate is verified purchases divided by offers presented today, or
zero when there are no offers.

## Recommendations

The initial deterministic rules surface:

- available inventory with no READY offering;
- READY photosets never presented;
- publications waiting to publish;
- expired purchase intents;
- publishing records requiring attention;
- a non-passing schema certification.

Each recommendation links only to an existing Creator OS route. It performs no
action itself.

## Operational limitations

“Active conversations” and “waiting replies” are reported as untracked until
an authoritative conversation activity projection exists. Frontend process liveness is not independently
instrumented. Commerce-learning theme breakdowns are intentionally omitted
until a bounded aggregate query can expose them without interpreting free-form
JSON. These limitations are displayed conservatively rather than filled with
invented values.
