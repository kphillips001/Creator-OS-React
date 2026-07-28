# Explainable Diagnostics

Creator Intelligence diagnostics use one machine-actionable contract:

- status and summary
- classification and root cause
- structured evidence
- confidence
- automatic-resolution authorization and reason
- recommended action
- affected components
- last-updated timestamp

Unknown values are explicit and explain why evidence is unavailable. A bare
`FAIL` is never sufficient for autonomous execution.

Schema Certification distinguishes pending migrations, checksum mismatches,
migration-order violations, schema drift, missing tables, missing indexes,
failed verification, and unknown internal failures. Its evidence preserves the
pending migration list, drift messages, missing objects, and certification
evidence.

Backend and Operations diagnostics expose the health score and the underlying
provider, worker, and database deductions. Provider configuration remains an
operator-controlled action; repository/runtime defects may authorize automatic
repair.

Autonomous Issue Resolution consumes `classification`,
`automatic_resolution`, `resolution_reason`, and `recommended_action`
directly. It does not infer repairability from summary text. Cached, stale, or
projection-mismatch classifications suppress Developer Agent execution and
require a fresh diagnostic re-evaluation.

## Schema Certification request path

The authoritative path is:

`PostgreSQL catalogs + schema_migrations`
→ `SchemaManagerService.discover_schema()/applied_migrations()`
→ `SchemaManagerService.certify()`
→ `CreatorIntelligenceService.dashboard()`
→ `ExplainableDiagnosticService.schema()`
→ `GET /api/v1/creator-intelligence`
→ `loadCreatorIntelligence()` with `cache: no-store`
→ the Creator Intelligence Schema Certification card.

Creator Intelligence does not read a persisted certification cache. A mismatch
between direct certification and the HTTP response therefore indicates a stale
application process or stale client projection. The response carries a fresh
dashboard `generatedAt` value and certification `checked_at` evidence so those
observations can be compared. Restart or reload the application process when it
predates the loaded diagnostic implementation.
