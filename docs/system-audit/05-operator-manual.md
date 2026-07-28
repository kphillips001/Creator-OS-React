# Operator manual

## Start safely

Prerequisites: Python environment with `requirements.txt`, Node dependencies under `frontend`, PostgreSQL reachable through `DATABASE_URL`, required provider credentials, and migrations applied by the supported migration tooling.

The checked-in `start.py` is legacy: it launches FastAPI on 8000 and Streamlit on 8501. For the React runtime, use two terminals:

```powershell
cd C:\Creator-OS-React
python -m uvicorn app.fanvue_callback_server:app --host 127.0.0.1 --port 8001
```

```powershell
cd C:\Creator-OS-React\frontend
npm run dev
```

Open `http://127.0.0.1:5174`. Verify `http://127.0.0.1:8001/openapi.json` and Operations runtime cards. Stop with Ctrl+C in each owning terminal. Closing a terminal normally stops its foreground process; only supervised/background processes outlive it. Never kill an unknown PID.

Workers do not all start with FastAPI. `WorkerLauncherSupervisionService` starts only workers whose `CREATOR_OS_LAUNCH_*` switches are true. Observe `/business/operations`, heartbeat records, and `logs/runtime/*.log`.

## First-time setup

1. Populate `.env` from `.env.example` without committing secrets.
2. Configure database and run the project migration verifier before migration application.
3. Open Administration → Provider Connections; connect Fanvue with PKCE and verify required scopes.
4. Establish creator profile and active canonical reference in Reference Library.
5. Configure OpenAI/xAI and desired generation provider keys/models.
6. Configure Telegram API/session/channel IDs, but leave runtime OFFLINE.
7. Configure X only if Creator_OS-side publishing is used; broader automation belongs to X_Auto.
8. Set developer authorization for developer endpoints.
9. Review Operations module switches and deployment readiness. Begin OFFLINE, then OBSERVE.
10. Enable analysis workers individually and verify heartbeats before enabling commerce/reply workers.

## Daily supported workflow

1. Open Content Studio and confirm the active canonical reference.
2. Enter Creative Direction; use planner/manual/Prompt Workshop paths.
3. Select planner ideas and run Enhance & Generate. Planner generation is sequential and one image per selected idea.
4. Review persistent results and Generation Library.
5. Edit chosen media in Edit Studio or send a seed to Photoshoot Studio.
6. In Photoshoot Studio, approve/reject candidates and confirm final curation.
7. Move standalone generations or the photoshoot deliverable into Asset Library.
8. Register. Registration does **not** publish or sell.
9. Wait for analysis workers; review READY state in Commerce Library.
10. Confirm destination and Available Inventory eligibility.
11. Open Commerce; create an offering, set hero/assets, price, currency, and AI_CHAT or TELEGRAM_WALL channel.
12. Mark READY only after validation. Create a publication record.
13. Execute Fanvue publication only in an authorized controlled operation; otherwise leave READY_TO_PUBLISH.
14. For Telegram Content Vault, ensure an active provider-backed Media Link exists, then publish through Commerce.
15. Use Developer Test Chat before any live chat activation.
16. Monitor Operations, Customer Commerce, Purchase Intents, webhook monitor, sales and failures.

Unsupported/conditional: Video Studio and generic Publishing are placeholders; full unattended publication/sales should not be assumed; Story Studio is partial.

## Photoshoot guide

- Seed from Generation Library; do not substitute the canonical reference for continuity.
- Approve establishes the next continuity reference. Reject does not join the set.
- Regenerate preserves the shot intent; Edit Prompt changes it.
- At finish, review every approved image. Seed selection is mandatory.
- Confirm once membership is correct: photoset commitment is intended to be immutable.
- Register the deliverable in Asset Library and observe analysis. Never sell a member standalone merely because its file remains visible.

## Asset management

- **Staged:** visible in registration workspace, not canonical commerce inventory.
- **Registered:** canonical Asset created/linked; analysis starts.
- **READY:** analysis complete.
- **Available:** destination is AVAILABLE_INVENTORY and other eligibility checks pass.
- **Assigned/committed:** one non-available destination; reuse is restricted.
- **Archived:** hidden from active workflows, retained/restorable where API supports it.

Canonical references are protected and excluded from ordinary inventory. A failed worker stage is not fixed by repeatedly registering; inspect its job/error and worker health.

## Safe chat activation

1. Test representative turns in Developer Test Chat; external send is disabled.
2. Confirm Sales Brain reason, selector result, authoritative URL, and Purchase Intent.
3. Set runtime OBSERVE: calculate/log, do not send.
4. Validate Telegram session, identity map, READY offering, LIVE publication, master/module switches, and worker heartbeat.
5. Move to LIVE only for a controlled window.
6. On unexpected behavior, return OFFLINE, disable reply/commerce switches, retain logs/events, and diagnose before restart.

