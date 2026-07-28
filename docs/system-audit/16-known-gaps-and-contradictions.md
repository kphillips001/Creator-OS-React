# Known gaps and contradictions

1. **Port/launcher conflict (high):** Vite proxies `/api/v1` to 8001, Provider Connections uses an 8001 callback, but `start.py` launches FastAPI on 8000 and Streamlit on 8501. Decide and ship one React launcher.
2. **Generation pagination conflict:** FastAPI/React use 20; the Vite development adapter hard-codes 18 and JSON storage. Remove or clearly isolate the adapter.
3. **Two UI generations:** React is authoritative, but `app/dashboard` and Streamlit launch remain. Imports/operators can reach superseded flows.
4. **Placeholder navigation:** labels for Video, Publishing, agents, Settings and Diagnostics sound functional but render generic placeholders.
5. **Story mismatch:** Story types/models exist and Story page is real, but there is no dedicated backend Story workflow comparable to Photoshoot.
6. **Product vs Offering:** legacy Product/catalog intelligence coexists with authoritative Commercial Offering selection; compatibility callers can still create conceptual confusion.
7. **Destination vocabulary:** old `commerce_destination` and newer `content_destination` coexist. New code must use `ContentDestinationService`.
8. **Mixed persistence:** Generation/creative/social JSON stores coexist with canonical PostgreSQL records, creating stale/missing visibility risks.
9. **Worker activation:** fifteen supervised worker definitions exist, but all depend on environment switches; UI capability does not prove execution.
10. **Purchase attribution:** official Fanvue events lack Media Link/offering ID. Hard matching can return UNKNOWN; this is correct but blocks fully automatic ownership.
11. **Security boundary:** developer-key protection is not complete user authentication/RBAC. Localhost assumptions must not be exposed directly.
12. **Fanvue scope/runtime drift:** Builder scopes, redirect URI, account identity and token metadata are external state; tests cannot prove them.
13. **Generic publishing:** Generation Broadcast and Commerce Content Vault work as separate paths; generic React Publishing remains placeholder.
14. **X boundary:** an X provider exists, but autonomous workflow ownership partly belongs to separate X_Auto. Define the integration contract and source of truth.
15. **Service-enforced rules:** some immutability/state transitions live in services rather than database constraints; direct repository use may bypass them.
16. **No comprehensive E2E:** extensive unit/component tests do not prove the full operator journey or live restart/retry behavior.

## Owner decisions

- Retire or support Streamlit?
- Make a single launcher/service manager authoritative?
- Retire legacy Products for new sales, or define their lasting role?
- Is Story Studio intended for near-term completion?
- Which Telegram transport owns replies versus channel publication?
- What manual-review SLA applies to UNKNOWN purchases?
- What authentication/deployment topology is required beyond localhost?
- Should JSON domains migrate to PostgreSQL or gain reconciliation?

No capability in this report should be promoted to production-ready until its contradiction is resolved and the controlled readiness checklist passes.

