# Troubleshooting runbook

| Symptom | Diagnose | Safe recovery |
|---|---|---|
| Backend will not start | `python -m uvicorn app.fanvue_callback_server:app --port 8001`; inspect traceback and port | Fix missing package/config; do not change DB blindly. |
| Frontend will not start | `cd frontend; npm run typecheck; npm run dev` | Install declared dependencies; verify Node version and 5174. |
| Port occupied | `Get-NetTCPConnection -LocalPort 5174,8001 -State Listen`; inspect owning PID | Stop only verified Creator_OS process; never mass-kill Python/Node. |
| API 404 | Check `/openapi.json`, exact `/api/v1` path and Vite proxy | Start correct FastAPI app on 8001; avoid legacy port 8000 confusion. |
| UI stale | Check browser network/server output | Hard refresh; restart Vite after verifying correct worktree. |
| Image missing | Request media endpoint; verify local path/file and ownership | Restore file/path metadata from backup; do not fabricate Asset records. |
| Generation pending | Inspect generation run endpoint/provider error | Confirm key/model/network; retry only after job state understood. |
| Registration stuck | Inspect Asset status and analysis job | Start orchestrator/stage worker; repair cause before retry. |
| Stale lease | Check worker heartbeat/job lease/attempt | Ensure old worker is dead; use repository/service stale recovery. |
| Content absent from inventory | Verify READY, creator, canonical protection, destination | Correct through supported destination/registration service. |
| Destination cannot change | Check immutable commitment/history | Expected for PHOTOSET/TELEGRAM_WALL; owner decision, not direct SQL. |
| Photoshoot continuity wrong | Compare canonical identity vs latest approved continuity | Pause session; select correct seed/approved shot through UI. |
| Fanvue disconnected | Provider Connections status/scopes/token expiry | Reconnect with exact registered redirect and PKCE. |
| OAuth redirect mismatch | Compare encoded URI with Builder entry | Register `http://localhost:8001/api/v1/administration/providers/fanvue/callback` exactly for local use. |
| Publication stuck | Status, upload checkpoints, provider resource state, worker log | Reconcile first; retry only if idempotency state proves safe. |
| Telegram not ready | session/API IDs/channel IDs, worker heartbeat, switches | Keep OFFLINE; re-auth/session setup; OBSERVE before LIVE. |
| Sends disabled | Runtime/master/module/deployment guard reason | Do not bypass; satisfy every gate deliberately. |
| Migration missing | Schema certification/history/checksum | Apply only reviewed pending migration with rollback; back up first. |
| Tests pass/runtime stale | Compare PID command line, HEAD/worktree, server start time | Clean stop verified processes and restart intended tree. |

Useful read-only commands:

```powershell
git branch --show-current
git status --short
Get-NetTCPConnection -State Listen | Where-Object LocalPort -in 5174,8001
Get-Content logs/runtime/launcher.log -Tail 100
python -m compileall -q app
```

Safety: return runtime OFFLINE before diagnosis of sends/publication; preserve events/checkpoints; never delete queue rows or reset provider IDs as a first response.

