# Autonomy gap analysis

## Must complete before live autonomous operation

| Gap | Current evidence | Risk / missing capability | Recommendation | Complexity |
|---|---|---|---|---|
| Supported launcher | `start.py` targets 8000/8501; Vite targets 8001 | stale/wrong runtime | One supervised React+FastAPI+workers launcher with health/stop | Medium |
| Identity and launch data | services require exact Fanvue/Telegram mapping and live offering | wrong buyer/offer or no delivery | Provision and validate via supported flows; startup certification | Medium |
| End-to-end purchase attribution | provider omits Media Link ID; intent may be UNKNOWN | incorrect ownership/delivery | Keep hard matching, manual-review queue, never guess | Large |
| Access control | developer key, local operator assumptions | sensitive diagnostics exposed | production auth/RBAC, TLS, secret rotation | Large |
| Delivery/ack recovery | services/tests exist but live loop not broadly proven | duplicate or missing delivery | crash/restart/duplicate fixture campaign then controlled live proof | Medium |
| Monitoring/alerting | operations views/logs/heartbeats | silent failures | actionable alerts, SLOs, webhook/queue age alarms | Medium |
| Safety/compliance | guards/classifiers exist | policy or platform breach | auditable policy, age/consent controls, retention/privacy review | Very Large |

## Strongly recommended before scale

- Provider circuit breakers, budgets and degradation strategy (Medium).
- Queue backpressure and multi-worker concurrency/load validation (Medium).
- Unified PostgreSQL-backed media/catalog truth or explicit reconciliation for JSON stores (Large).
- Automated backup/restore rehearsal and orphan audits (Medium).
- Customer consent, export/deletion, least-privilege credentials, and audit access (Large).
- Human override/manual-review inbox for UNKNOWN attribution and failed sends (Medium).
- Analytics that distinguish intent, offer, payment, delivery, refund and retention outcomes (Large).

## Useful enhancements

Content planning automation, price experiments, richer segmentation, retention sequences, Story/Video authoring completion, generic publishing calendar, responsive/accessibility regression tests, and provider-quality scorecards.

## Current level by loop

Creation 3; intelligence 4 when enabled; planning 3; offer construction 2; pricing 2; segmentation 3; conversation intelligence 3; sales decisioning 4 constrained; messaging 3; payment confirmation 3; delivery 2–3; upsells/follow-ups 2; retention 1–2; analytics 2; operational resilience 3.

## Sequence

1. Runtime/port/auth/config certification.
2. Fixture-based restart/idempotency/security verification.
3. Populate minimum launch data and rehearse OBSERVE.
4. Controlled Telegram reply without sale.
5. Controlled offer/purchase/delivery with operator and rollback.
6. Add manual-review/alerts and privacy controls.
7. Gradually widen LIVE windows; only then add strategy automation.

This sequence reuses the existing Sales Brain, selector, Purchase Intent, reconciliation, and worker foundations.

