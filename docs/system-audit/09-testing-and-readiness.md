# Testing and readiness

## Test topology

- Backend unit/API/repository/worker tests: `app/test_*.py`.
- React component/navigation/API tests: colocated `*.test.ts(x)`.
- Database/migration and schema certification tests.
- Provider contract tests use fakes/mocks; explicitly named live validation scripts must not be part of routine execution.
- Conversation, Sales Brain, selector, Purchase Intent, webhook, publication, supervisor, safety and launch-blocker suites exist.
- No single browser E2E suite proves the complete React → provider → persisted result path.

## Strong coverage

Asset Library/API, photoshoot curation, worker orchestration, commercial offerings/publications, Fanvue executor/reconciliation, customer commerce idempotency, purchase intent transitions, unified chat composition, runtime/safety guards, developer authorization, and main React pages.

## Weak/conditional coverage

Real provider schema drift; OAuth consent/redirect registration; actual Telegram session longevity; real Fanvue purchase-to-offering attribution; multi-process crash/restart under load; filesystem/database divergence; complete operator journey; accessibility/responsive visual regression; X_Auto boundary.

## Safe validation commands

```powershell
python -m compileall -q app
cd frontend
npm run typecheck
npm run lint
npm test -- --run
cd ..
git diff --check -- docs/system-audit
```

Focused backend tests should be selected by domain and reviewed first to ensure no external writes. Never run “live,” “production validation,” provider upload, or paid generation scripts without explicit authorization and isolated credentials.

## Audit run (2026-07-25)

| Command | Result |
|---|---|
| `python -m compileall -q app` | Passed |
| `python -m pytest -q app/test_content_destination_foundation.py app/test_commercial_offerings.py app/test_commercial_publications.py app/test_customer_commerce_intelligence.py app/test_purchase_intent_lifecycle.py app/test_customer_sales_brain.py app/test_commercial_offering_selector.py app/test_webhook_signature_service.py app/test_worker_launcher_supervision.py` | 87 passed |
| `npm run typecheck` | Passed |
| `npm run lint` | Passed |
| `npm test -- --run` | 38 files, 182 tests passed |
| `git diff --check -- docs/system-audit` | Passed |

These checks made no live provider calls and are not a claim that every backend test or an end-to-end production workflow passed.

## Readiness verdict

The architecture is **ready with conditions for controlled live testing**, not autonomous production. A controlled test requires:

- supported React/FastAPI launcher and consistent ports;
- applied/verified migrations and unique constraints;
- developer key and private developer routes;
- resolved creator/Fanvue/Telegram identities;
- READY AI_CHAT offering and LIVE authoritative delivery URL;
- healthy reconciliation and transport workers;
- OBSERVE-mode rehearsal;
- fixture proof for duplicate webhook, retry, expiration, exactly-once acknowledgement;
- explicit rollback/stop procedure and operator present.

Application code presence or green unit tests alone does not satisfy these conditions.
