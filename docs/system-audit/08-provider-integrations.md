# Provider integrations

| Provider | Capability | Readiness/failure behavior | Evidence |
|---|---|---|---|
| OpenAI | Conversation response, intent/vision paths | Requires key/model; failures surface through services; test clients mocked | `openai_provider.py`, `gpt_service.py`, `OPENAI_*` |
| xAI/Grok | Prompt Planner/creative Q&A, captions, semantic analysis | `GROK_MODEL`, `GROK_VISION_MODEL`; analysis worker retries; planner refusals/model behavior are provider-dependent | `grok_anything_service.py`, `grok_analysis_worker_service.py` |
| Seedream | Image generation | model/key/transport-dependent; registry adapter persists output | `seedream_provider.py`, `SEEDREAM_MODEL` |
| Nano Banana | Image/edit generation with references | model/provider transport-dependent | `nano_banana_provider.py`, `NANO_BANANA_MODEL` |
| WAN | Video-generation foundation | adapter exists; React Video Studio is placeholder | `wan_provider.py`, `WAN_MODEL` |
| NudeNet | Local nudity/safety analysis | Local inference worker; no paid external call; failed state/retry | `nudenet_analysis_worker_service.py` |
| Fanvue official API | OAuth, media upload/poll, Media Links, read diagnostics, webhook/reconciliation | Requires exact redirect, scopes, account identity; checkpoints/retries; writes guarded | `fanvue_official_client.py`, `fanvue_media_link_publication_executor.py` |
| Telegram | Telethon user runtime, Bot API/channel publishing, content vault | Requires API/session/bot/channel configuration, module/runtime permit | `app/integrations/telegram`, `telegram_provider.py` |
| X | Creator_OS-side social publishing/callback | Credentials and live guard required; broader autonomous X operation belongs to `C:\X_Auto` | `x_provider.py`, `social_publishing_service.py` |
| ImgBB/hosted reference | Temporary hosted reference fallback | Optional key; retry/backoff; avoid making it canonical storage | `hosted_asset_reference*`, `IMGBB_API_KEY` |

## Fanvue sequence

Offering → publication → multipart upload → processing poll → ready media UUID → POST Media Link → persist media/link UUID and URL → LIVE → reconciliation. Price is stored in minor currency units. No “Product” creation is required for the implemented Media Link path.

OAuth uses Bearer tokens, refresh handling, PKCE, state, and stored account identity. Requested/granted scopes are surfaced; missing write scopes block capability. Webhook signatures read `x-fanvue-signature` in `t=...,v0=...` form and must use the configured signing secret; verification must never be bypassed.

The official purchase payload/earnings path supplies buyer and transaction/payment data but not a deterministic offering identifier. Purchase Intent narrows attribution; ambiguity is persisted as UNKNOWN.

## External-side-effect controls

Read explorers never call write endpoints. Fanvue execute/retry and Commerce Telegram Vault POST endpoints are dangerous live boundaries. Telegram additionally requires runtime LIVE, module enablement, credentials, and send guards. Generation calls can incur cost. Tests mock providers and should never inherit production write permits.

