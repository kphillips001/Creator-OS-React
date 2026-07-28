# Administration and operations

## Runtime controls

`RuntimeMode` is OFFLINE, OBSERVE, or LIVE. OFFLINE blocks decisions/sends; OBSERVE permits evaluation and records suggestions without external delivery; LIVE may allow replies/offers/delivery only when module switches, deployment permits, configuration, and global send guards also agree. An operator switch is not itself deployment authorization.

Evidence: `app/models/runtime_control.py`, `runtime_control_service.py`, `global_send_execution_guard_service.py`, `module_switches_service.py`, `app/api/operations.py`.

The Operations API exposes overview, runtime, workers, queues, publishing, failures, module switches, and PATCH for a module. Readiness cards intentionally sanitize environment details. Do not treat green UI alone as proof of provider reachability.

## Worker catalog

| Worker | Switch | Purpose |
|---|---|---|
| Telegram | `CREATOR_OS_LAUNCH_TELEGRAM` | Telethon inbound/outbound transport |
| Outreach | `...OUTREACH` | queued outreach |
| Delayed Messages | `...DELAYED_MESSAGES` | scheduled follow-up |
| Mass PPV | `...MASS_PPV` | campaign sends |
| Wall Worker | `...WALL_WORKER` | wall queue |
| NudeNet Analysis | `...NUDENET_ANALYSIS` | local safety/nudity stage |
| Analysis Orchestrator | `...ANALYSIS_ORCHESTRATOR` | advances asset stages |
| Vision Analysis | `...VISION_ANALYSIS` | visual structured analysis |
| Grok Analysis | `...GROK_ANALYSIS` | semantic analysis |
| Content Intelligence Merge | `...CONTENT_INTELLIGENCE_MERGE` | authoritative profile merge |
| Photoshoot Analysis | `...PHOTOSHOOT_ANALYSIS` | deliverable/member analysis |
| Photoshoot Auto Run | `...PHOTOSHOOT_AUTO_RUN` | session automation |
| READY Asset Chat Registration | `...READY_ASSET_CHAT_REGISTRATION` | compatibility chat registration |
| Fanvue Publications | `...FANVUE_COMMERCIAL_PUBLICATIONS` | provider execution/recovery |
| Commerce Reconciliation | `...COMMERCE_RECONCILIATION` | webhook/payment reconciliation and intent expiry |

The supervisor refuses duplicate matching processes, requires healthy heartbeats, records PID/instance state under `logs/runtime`, performs graceful process-tree shutdown, and escalates only when needed. Evidence: `worker_launcher_supervision_service.py`.

## Fanvue administration

React authorization begins at `POST /api/v1/administration/providers/fanvue/authorize`; callback is `/api/v1/administration/providers/fanvue/callback`. PKCE/state are persisted in a short-lived local OAuth session; `FanvueOAuthService` exchanges and `FanvueTokenService` persists tokens. The legacy `/callback` still redirects to Streamlit and exists for compatibility. Redirect URI registration must match character-for-character.

Provider Connections shows status, identity, requested/granted/missing scopes, Media Link capability, and readiness. Never display tokens/client secret. Evidence: `provider_connections.py`, `ProviderConnectionsPage.tsx`, `fanvue_oauth_service.py`.

## Safety

- Developer routes use `developer_authorization.py`; production should set `CREATOR_OS_DEVELOPER_KEY`.
- `/webhooks/fanvue` remains public but validates `x-fanvue-signature`.
- Provider writes require explicit endpoints/workers and configuration; API explorers are GET-only.
- Telegram sends pass execution guards/runtime decisions.
- Fanvue publication checkpoints preserve uploaded media/link identifiers across failure.
- Master OFFLINE is necessary but operators should also disable worker launch switches for maintenance.

