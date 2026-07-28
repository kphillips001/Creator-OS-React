# Legacy migration status

The React repository is authoritative. `C:\Creator-OS` is a historical Streamlit application with substantially overlapping backend code. The current repository still contains `app/dashboard/` and root `start.py` starts Streamlit, so migration cleanup is incomplete.

| Capability | Legacy | React/current | Status / cleanup |
|---|---|---|---|
| Shell/navigation | Streamlit custom navigation | React Router/AppShell | Migrated; retire legacy launcher after operational replacement. |
| Content Studio | Large Streamlit page | React Content Studio + FastAPI | Migrated core; compare rare legacy controls before deletion. |
| Generation Library | Streamlit/JSON workflows | React + FastAPI | Migrated; remove/label Vite 18-item adapter discrepancy. |
| Edit/Photoshoot | Streamlit pages/services | React pages + same evolved services | Migrated and expanded. |
| Asset Library | Streamlit staging | React typed staging/registration | Migrated. |
| Product catalog | Streamlit management | React read-only Products plus new Commerce | Partial/intentionally superseded by Commercial Offerings. |
| Publishing queue/wall scheduler | Streamlit operational pages | specific Generation publish, Commerce vault, Operations | Partial; generic React Publishing is placeholder. |
| Creator/Developer agents | Streamlit pages | React placeholders | Meaningful UI remains unported or intentionally deferred. |
| System health/settings | Streamlit pages | Operations/Admin plus placeholders | Partial. |
| Mass PPV/delayed messages | Streamlit dashboards | workers/Operations projections | Backend retained; direct React management reduced. |
| Fanvue auth | Streamlit callback/page | React Provider Connections | Migrated, legacy callback retained. |
| Pricing playground | Streamlit | Commerce pricing/authoring | Old playground not directly ported. |
| Metadata stripping | Streamlit utility | no dedicated React route found | Missing or intentionally retired; owner decision needed. |

Duplicate implementations in the React repository include Streamlit dashboards, legacy Product/commerce models, `/callback`, JSON generation adapter, and older social/publishing services beside newer domain services. Deletion is unsafe until usage telemetry/import searches and operator sign-off confirm retirement.

Evidence: `app/dashboard/navigation.py`, `app/dashboard/pages/`, `frontend/src/app/router/router.tsx`, root `start.py`; comparison paths under `C:\Creator-OS\app\dashboard`.

