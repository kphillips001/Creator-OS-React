# Creator_OS system audit

This directory is the evidence-based system map for the `react-migration` branch, audited on 2026-07-25. The React repository is authoritative; `C:\Creator-OS` was consulted only for migration history.

## Headline assessment

Creator_OS is a broad, locally operated creator-content and commerce platform with a React 19/Vite interface, FastAPI application, PostgreSQL repositories/migrations, filesystem media stores, supervised workers, and provider adapters. Content creation, libraries, registration, analysis, destinations, offerings, publication records, customer commerce, purchase intent, and a constrained conversation/sales brain all have real implementations. Operational activation remains conditional: launch configuration, identity/data prerequisites, worker enablement, access control, provider scopes, and end-to-end live proof are not uniformly complete.

**Overall maturity:** implemented platform in controlled pre-production activation, not unattended production.

**Autonomy:** Level 3 of 5 overall — automated workflows with human setup/oversight. Analysis is near Level 4 when workers run; content generation and publishing remain approval/configuration dependent; payment attribution, delivery recovery, monitoring, and live operational proof prevent Level 4 overall.

## Documents

- [Executive summary](01-executive-summary.md)
- [System architecture](02-system-architecture.md)
- [Feature inventory](03-feature-inventory.md)
- [Content lifecycle](04-content-lifecycle.md)
- [Operator manual](05-operator-manual.md)
- [Administration and operations](06-administration-and-operations.md)
- [API and data reference](07-api-and-data-reference.md)
- [Provider integrations](08-provider-integrations.md)
- [Testing and readiness](09-testing-and-readiness.md)
- [Legacy migration status](10-legacy-migration-status.md)
- [Autonomy gap analysis](11-autonomy-gap-analysis.md)
- [Troubleshooting runbook](12-troubleshooting-runbook.md)
- [Glossary](13-glossary.md)
- [Route catalog](14-route-catalog.md)
- [Configuration reference](15-configuration-reference.md)
- [Known gaps and contradictions](16-known-gaps-and-contradictions.md)
- [Commercial catalog and Sales Brain synchronization](17-commercial-catalog-sales-brain-sync.md)
- [Commerce Recommendation Engine — Session 1](18-commerce-recommendation-engine-session-1.md)
- [Commerce Recommendation Engine — Session 2](19-commerce-recommendation-engine-session-2.md)
- [Commerce Learning Engine](20-commerce-learning-engine.md)
- [Recommendation Explainability and Diagnostics](21-recommendation-explainability-and-diagnostics.md)
- [Creator Intelligence Center](22-creator-intelligence-center.md)
- [End-to-end operational certification](23-end-to-end-operational-certification.md)
- [Controlled launch checklist](controlled-launch-checklist.md)
- [Capability matrix](system-capability-matrix.csv)

## Status vocabulary

“Implemented” means an executable path exists, not that it is enabled or live-proven. “Production-ready” is reserved for paths with configuration, safety controls, persistence, recovery, and representative tests. “Read-only” means the page/API is observational. “Placeholder” means navigation exists but the router deliberately renders `PlaceholderPage`.

## Primary evidence

- `frontend/src/app/router/router.tsx`, `frontend/src/app/navigation/navigation.ts`
- `app/fanvue_callback_server.py`, `app/api/`
- `app/services/`, `app/repositories/`, `app/workers/`
- `app/services/worker_launcher_supervision_service.py`
- `migrations/forward/`, `migrations/rollback/`
- `app/test_*.py`, `frontend/src/**/*.test.tsx`
