# Configuration reference

No values are shown.

| Variable(s) | Purpose | Required/default | Live risk / secret |
|---|---|---|---|
| `DATABASE_URL`, `TEST_DATABASE_URL` | PostgreSQL connections | Runtime/test required | Secret |
| `VITE_API_BASE_URL` | React API origin | proxy default in dev | Public config |
| `CREATOR_OS_REACT_URL` | OAuth return UI | localhost:5174 default | No |
| `CREATOR_OS_RUNTIME_MODE` | OFFLINE/OBSERVE/LIVE | should default safe | Enables decisions; not sufficient alone |
| `CREATOR_OS_DEVELOPER_KEY` | developer endpoint authorization | required outside local fallback | Secret |
| `CREATOR_OS_VERSION` | diagnostics version | optional | No |
| `CREATOR_OS_LAUNCH_*` | individual worker launch | false unless enabled | May enable sends/provider writes |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | response/vision/intelligence | key required for use | Secret/cost |
| `GROK_API_KEY`, `XAI_API_KEY`, `GROK_BASE_URL`, `GROK_MODEL`, `GROK_VISION_MODEL` | xAI planner/caption/analysis | required per feature | Secret/cost |
| `SEEDREAM_MODEL`, `NANO_BANANA_MODEL`, `WAN_MODEL` | generation model selection | service defaults may apply | Cost/provider behavior |
| `WAVESPEED_TRANSPORT_TIMEOUT_SECONDS` | generation transport timeout | optional | No |
| `IMGBB_API_KEY`, hosted-reference retry vars | hosted reference fallback | optional | Key is secret |
| `FANVUE_CLIENT_ID`, `FANVUE_CLIENT_SECRET` | OAuth application | required | Secret except client ID |
| `FANVUE_REACT_REDIRECT_URI`, `FANVUE_REDIRECT_URI` | React/legacy callbacks | exact Builder match | No |
| `FANVUE_API_BASE_URL`, `FANVUE_API_KEY` | official client/legacy auth | OAuth preferred | Secret |
| `AVA_FANVUE_ACCOUNT_ID`, `AVA_FANVUE_URL` | creator account identity | required for scoped commerce | ID not secret |
| `ENABLE_REALTIME_FANVUE_SEND` | legacy live send permit | false by default | High risk |
| `FANVUE_WEB_COOKIE` | legacy/private browser credential | should not power official paths | Highly secret; misleading legacy |
| `TG_API_ID`, `TG_API_HASH`, `TG_SESSION_PATH` | Telethon runtime | required | Hash/session secret |
| `TELEGRAM_BOT_TOKEN*` | Bot API publishing | required per bot path | Secret |
| `TELEGRAM_CHANNEL_ID`, `TELEGRAM_VAULT_CHANNEL_ID`, URLs | target channels | required for publishing | IDs generally non-secret |
| `TELEGRAM_REPLIES_ENABLED` | reply module permit | false safest | Live send |
| `CONTENT_ROOT`, `CMS_ROOT` | filesystem vaults | project defaults | Local path |
| `COMMERCE_RECONCILIATION_INTERVAL_SECONDS` | worker poll interval | default in service | No |
| `DEFAULT_PERSONA`, `REQUIRE_CREATOR_PROFILE` | conversation identity rules | service defaults | Behavior-sensitive |
| `DMGATE_URL_AVA` | legacy delivery/link integration | optional/legacy | verify before use |

Worker switches are enumerated in `worker_launcher_supervision_service.WORKERS`, including Telegram, outreach, delayed messages, mass PPV, wall, all analysis stages, photoshoot, chat registration, Fanvue publication, and commerce reconciliation.

Potentially duplicated/misleading variables: `GROK_API_KEY` vs `XAI_API_KEY`; React vs legacy Fanvue redirect; OAuth vs `FANVUE_API_KEY`; multiple Telegram token/chat/channel forms; `FANVUE_WEB_COOKIE` is incompatible with the official-API-only architecture. Deprecation requires runtime telemetry before removal.

