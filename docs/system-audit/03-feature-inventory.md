# Feature inventory

| Domain | Status | Actual capability and evidence |
|---|---|---|
| App shell | Implemented | Responsive grouped navigation and nested router. Default `/library/generations`. `frontend/src/app/layout`, `app/navigation/navigation.ts`, `app/router/router.tsx`. |
| Generation Library | Implemented | Database/service-backed 20-item pagination, search/provider/sort, preview, edit, photoshoot, stage, publish, remove/restore/version actions. FastAPI is authoritative; Vite’s separate 18-item JSON adapter is development legacy. `GenerationLibraryPage.tsx`, `app/api/generation_library.py`, `generation_library_service.py`. |
| Content Studio | Implemented; provider-configured | Canonical context, creative tags, Prompt Workshop, Grok planner, sequential multi-select enhance/generate, aggregate progress, persistent results. `ContentStudioWorkflow.tsx`, `CanonicalPromptPlannerSection.tsx`, `app/api/content_studio.py`, `creative_director_service.py`. |
| Reference Library | Implemented | Active protected reference, creator scoping, media serving, startup recovery. `app/api/reference_library.py`, `canonical_reference_service.py`, `reference_library_service.py`. |
| Edit Studio | Implemented | Multi-reference upload/select, generation, candidates, approve/edit/discard, version archive and return. `EditStudioPage.tsx`, `app/api/edit_studio.py`, `edit_studio_service.py`. |
| Photoshoot Studio | Implemented | Planning, session, auto-run, continuity, approve/regenerate/edit/reject, curation and registration handoff. Workers are opt-in. `PhotoshootPage.tsx`, `app/api/photoshoot.py`, `photoshoot_*`. |
| Story Studio | Partial | Real React page/test but limited workflow compared with image/photoshoot; no dedicated Story API router. `StoryStudioPage.tsx`. |
| Video Studio | Placeholder | Navigation maps to generic `PlaceholderPage`; WAN provider foundation exists. |
| Asset Library | Implemented | Mixed staging/registration queue for standalone generations and typed photoshoot deliverables; archive/restore and registration mutate state. `AssetLibraryPage.tsx`, `app/api/asset_library.py`. |
| Asset analysis | Implemented but worker-dependent | NudeNet, vision, Grok, merge stages with leases/retries/heartbeats. `app/workers/*analysis*`, migrations `20260719_*`, `20260720_*`. |
| Commerce Library | Implemented | Read-oriented business asset/details/readiness/destination surface with archive mutations. `BusinessAssetsPage.tsx`, `app/api/business_assets.py`. |
| Content Destination | Implemented | Exactly one authoritative destination per asset plus history; default AVAILABLE_INVENTORY; immutable committed paths. `content_destination_service.py`, migration `20260723_001`. |
| Available Inventory | Implemented/read-focused | Eligible canonical READY/uncommitted assets with paging/search/filter/sort/selection; offering actions live elsewhere. `AvailableInventoryPage.tsx`, `available_inventory_repository.py`. |
| Commerce authoring | Implemented | Create/update/archive offerings, pricing, asset composition, publish record, Telegram vault action. Supports SINGLE_IMAGE, PHOTOSET, VIDEO in authoring service. |
| Commercial publications | Implemented; live guarded | Provider-neutral lifecycle plus Fanvue executor, retry and reconcile endpoints/worker. Credentials/scopes/data required. |
| Telegram Content Vault | Implemented; configuration-dependent | Offering cover/title/description + Unlock button to authoritative Media Link; separate from Generation Library broadcast. `commerce_telegram_vault_service.py`. |
| Products | Read-only legacy workspace | Product list/detail remains for compatibility; Commercial Offerings are authoritative for new commerce. |
| Customers | Read-only | Customer list/detail projections. Customer Commerce developer tool exposes verified purchase aggregates. |
| Sales | Read-only | Overview, decisions, offers, learning, and commerce-sales explorer. |
| Operations | Implemented | Runtime, worker, queue, publication, failure, and module-switch views; module switch PATCH mutates local operational state. |
| Test Chat | Implemented developer tool | Exercises unified conversation/sales decision path with external send disabled; session/reset endpoints mutate test state. |
| Fanvue API Explorer | Read-only developer tool | Official GET endpoints, redacted diagnostics, no persistence/provider writes. |
| Webhook Monitor | Read-only, process-local | Last requests with master/detail; captures are in memory when not persisted. |
| Publishing/Agents/Settings/Diagnostics | UI placeholders | Explicitly rendered by `PlaceholderPage`. |
| Legacy Streamlit | Superseded but retained | `app/dashboard/` remains importable; root launcher still starts it. Not authoritative for React workflows. |

## Content Studio details

The planner request is `POST /api/v1/content-studio/prompt-planner/ask`, assembled by `CreativeDirectorService` and xAI client configuration (`GROK_MODEL`). Generation is `POST /generations`, polled at `/generations/{run_id}`. The React planner holds selected ideas, processes sequentially, forces one image per planner idea without persisting the user batch setting, and feeds completed images into the normal results grid.

Provider registry evidence: `app/providers/generation/provider_registry.py`, `seedream_provider.py`, `nano_banana_provider.py`, `wan_provider.py`. Reference behavior and output ingestion are centralized in generation services rather than duplicated in the UI.

## Canonical reference

The canonical reference identifies the creator and is distinct from a photoshoot’s latest-approved continuity image. It is creator-scoped, protected from routine archive/reuse paths, selected through Reference Library, and recovered on FastAPI startup. IDs are records, not universal constants. Evidence: `canonical_reference_service.py`, `asset_repository.py`, `reference_library.py`.

## Registration semantics

Moving a generation to Asset Library changes workflow visibility/staging; it does not by itself make a commercial offering. Registering creates/links the canonical Asset and analysis workflow. READY means the intelligence pipeline completed, not “published” or “sold.” Destination answers where the Asset is committed; in-service/readiness are separate commerce states.

