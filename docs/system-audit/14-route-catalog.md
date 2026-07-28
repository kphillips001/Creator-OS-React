# Route catalog

## React routes

| Route | Page/status | Mutates? |
|---|---|---|
| `/` | redirects to Generation Library | No |
| `/library/generations` | Generation Library | Yes |
| `/inventory/available` | Available Inventory | Primarily read |
| `/library/photoshoots` | Photoshoot Gallery | Add-to-library |
| `/studio/content` | Content Studio | Yes/provider cost |
| `/content/edit` | Edit Studio | Yes/provider cost |
| `/content/photoshoot` | Photoshoot Studio | Yes/provider cost |
| `/content/story` | Partial Story Studio | Limited |
| `/library/references` | Reference Library | Selection |
| `/library/assets` | Asset Library | Yes |
| `/business/commerce-library` | Commerce Library | Read + archive |
| `/commerce` | Commerce authoring | Yes |
| `/commerce/offerings` | Offering list/detail | Yes |
| `/business/assets` | redirect to Commerce Library | No |
| `/business/products` | legacy Products | Read |
| `/business/customers` | Customers | Read |
| `/business/sales` | Sales | Read |
| `/business/operations` | Operations | module switches |
| `/developer/*` | Test/diagnostic pages | Mostly read; Test Chat mutates isolated session |
| `/administration` | Administration | configuration |
| `/administration/providers` | Provider Connections | OAuth |
| `/system/archive/*` | archives/version/posted/removed | Some restore/delete |
| `/studio/video`, `/publishing`, `/agents/*`, `/settings`, `/diagnostics` | PlaceholderPage | No |
| `/administration/:section` | placeholder | No |

Evidence: `frontend/src/app/router/router.tsx`.

## Backend route groups

All paths below are under `/api/v1` unless noted.

| Domain | Endpoints | Service/side effects |
|---|---|---|
| Content Studio | GET context/config/archive/run; POST creative tags, workshop, preview, planner, generations | Creative/generation services; LLM/image provider calls |
| Generation Library | GET list/media/versions/removed; POST remove/restore/delete/stage/edit/photoshoot | GenerationLibraryService; filesystem/DB workflow mutations |
| Generation publish | GET publish context; POST captions/publish | Broadcast social provider; live side effect guarded |
| Edit Studio | context/references/media plus upload/generate/approve/discard | Edit services/provider/files |
| Photoshoot | context/planning/generate/status/review/finish/curation/auto-run | Photoshoot services/workers/provider |
| Asset Library | list/detail/media/archive; staged/photoshoot register; restore | AssetLibraryService/repositories |
| Business Assets | list/detail/photoshoot/archive | business asset query/archive |
| Available Inventory | GET `/available-inventory` | narrow read projection |
| Offerings | GET/POST/PATCH `/commercial-offerings`; pricing | CommercialOfferingService |
| Authoring | summary/list/create/update/archive/publish/vault | CommerceAuthoring/Telegram Vault; vault POST can send |
| Publications | list/get/create/update/execute/retry/reconcile | Fanvue write on execute/retry; reconcile reads |
| Fulfillments | list/get | read projection |
| Sales | `/commerce/sales`, `/sales/*` | read projections |
| Customers | `/customers/*` | read |
| Operations | overview/runtime/workers/queues/publishing/failures/switches | PATCH changes module switch |
| Developer | test-chat POSTs; explorers/commerce/signals/intents/brain/selector GETs | developer auth; Fanvue Explorer official GET only |
| Administration | Fanvue status/authorize | OAuth session and token exchange |
| Reference | active/image | read |
| Webhook | POST `/webhooks/fanvue` | public, signature verified, dedupe/persist/process |
| OAuth callback | GET `/api/v1/administration/providers/fanvue/callback` | state/PKCE/token persistence |
| Legacy callback | GET `/callback` | redirects to Streamlit |

Request/response models are Pydantic/dataclass contracts in each `app/api/*.py` and `app/models/*`. Router consumers are the matching `frontend/src/features/*/api.ts` modules. Full decorator inventory is source-authoritative; this grouped catalog avoids presenting implementation-only media routes as separate capabilities.

## Unused/duplicate risks

Vite defines `/api/generation-library` without `/v1`, reads JSON, uses 18 items, and returns 501 for actions; normal React uses FastAPI `/api/v1` and 20 items. The legacy `/callback` and Streamlit dashboard routes remain. Backend product/legacy operational services have no equivalent fully mutable React pages. See contradictions.

