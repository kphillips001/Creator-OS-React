# System architecture

## Runtime

- **Frontend:** React 19, React Router 7, TypeScript, Vite 6; entry routing in `frontend/src/app/router/router.tsx`.
- **Backend:** FastAPI application `app.fanvue_callback_server:app`; routers under `app/api/`.
- **Persistence:** PostgreSQL through repository modules and `DATABASE_URL`; JSON/filesystem stores remain for generation, creative sessions, archives, and social publishing.
- **Migrations:** ordered SQL in `migrations/forward`, corresponding recovery scripts in `migrations/rollback`, managed by `SchemaManagerService`.
- **Workers:** Python modules under `app/workers`, opt-in and supervised by `WorkerLauncherSupervisionService`; heartbeats persist health.
- **Media:** local vault/media files are streamed by API media endpoints; Vite also contains a legacy development-only generation-library adapter.

```mermaid
flowchart LR
  O[Operator] --> R[React/Vite :5174]
  R -->|/api/v1| F[FastAPI :8001 expected]
  T[Telegram] --> TI[Telethon runtime]
  FV[Fanvue webhooks] --> F
  F --> S[Services]
  TI --> G[Conversation Gateway]
  G --> S
  S --> Q[Repositories]
  Q --> P[(PostgreSQL)]
  S --> J[JSON/filesystem media]
  W[Supervised workers] --> S
  S --> X[Provider adapters]
  X --> EXT[OpenAI / xAI / generation / Fanvue / Telegram / X]
```

## Major components

```mermaid
flowchart TB
  CS[Content Studio] --> GE[Generation engine]
  GE --> GL[Generation Library]
  GL --> AL[Asset Library staging]
  GL --> PS[Photoshoot Studio]
  AL --> AR[Asset registration]
  PS --> AR
  AR --> AI[Asset intelligence workers]
  AI --> BA[Commerce Library / Business Assets]
  BA --> CD[Content Destination]
  CD --> INV[Available Inventory]
  INV --> CO[Commercial Offering]
  CO --> CP[Commercial Publication]
  CP --> ML[Fanvue Media Link]
  CO --> TV[Telegram Content Vault]
  CHAT[Telegram/Test Chat] --> SB[Customer Sales Brain]
  SB --> SEL[Offering Selector]
  SEL --> PI[Purchase Intent]
  PI --> DEL[Telegram delivery]
  WH[Fanvue webhook] --> CC[Customer Commerce/reconciliation]
```

## Asset registration

```mermaid
stateDiagram-v2
  [*] --> REGISTERED
  REGISTERED --> PENDING
  PENDING --> NUDENET_PENDING
  NUDENET_PENDING --> NUDENET_RUNNING
  NUDENET_RUNNING --> NUDENET_COMPLETE
  NUDENET_COMPLETE --> VISION_PENDING
  VISION_PENDING --> VISION_RUNNING
  VISION_RUNNING --> VISION_COMPLETE
  VISION_COMPLETE --> GROK_PENDING
  GROK_PENDING --> GROK_RUNNING
  GROK_RUNNING --> GROK_COMPLETE
  GROK_COMPLETE --> CONTENT_INTELLIGENCE_PENDING
  CONTENT_INTELLIGENCE_PENDING --> CONTENT_INTELLIGENCE_RUNNING
  CONTENT_INTELLIGENCE_RUNNING --> CONTENT_INTELLIGENCE_COMPLETE
  CONTENT_INTELLIGENCE_COMPLETE --> READY
```

Each provider stage has a FAILED state. Orchestration maps completion to the next pending state. Evidence: `app/models/asset_intelligence.py`, `app/services/business_asset_analysis_orchestrator.py`, worker/repository pairs named for each stage.

## Photoshoot workflow

```mermaid
flowchart LR
  Seed[Generation seed / Shot 1] --> Session[Photoshoot session]
  Canon[Canonical identity reference] --> Session
  Session --> Gen[Generate candidate]
  Gen --> Review{Approve?}
  Review -->|approve| Cont[Latest approved continuity]
  Review -->|regenerate/edit| Gen
  Review -->|reject| Rejected
  Cont --> Gen
  Cont --> Curate[Final curation]
  Curate --> Deliverable[Photoshoot deliverable]
  Deliverable --> Register[Asset Library registration]
  Register -->|selected members| Photo[PHOTOSET destination]
  Register -->|unselected approved| Available[AVAILABLE_INVENTORY]
```

Evidence: `app/api/photoshoot.py`, `app/services/photoshoot_curation_service.py`, `app/services/photoshoot_*`, migrations `20260721_*`.

## Commercial publication

```mermaid
flowchart LR
  O[READY offering] --> P[READY_TO_PUBLISH publication]
  P --> E[FanvueMediaLinkPublicationExecutor]
  E --> U[Multipart upload]
  U --> Poll[processing poll]
  Poll --> Link[Media Link]
  Link --> Persist[UUID + URL + metadata]
  Persist --> Live[LIVE]
  Live --> Reconcile[reconciliation worker]
```

The Telegram Content Vault is a separate marketing publication event and reuses the authoritative active Media Link; it is not the provider-backed `CommercialPublication`. Evidence: `app/services/fanvue_media_link_publication_executor.py`, `commerce_telegram_vault_service.py`, `social_publishing_service.py`.

## Autonomous conversation/sales

```mermaid
flowchart LR
  Msg[Telegram/Test Chat message] --> CG[ConversationGateway]
  CG --> CSB[CustomerSalesBrain]
  CSB --> Policy[Commerce execution policy]
  Policy --> DE[DecisionEngine]
  CSB --> OS[CommercialOfferingSelector]
  DE --> GPT[GPTService]
  GPT --> CC[ChatCommerceService]
  OS --> CC
  CC --> PI[PurchaseIntentService]
  PI --> TX[TelegramDeliveryExecutor]
  WH[Fanvue payment webhooks] --> CR[Commerce reconciliation]
  CR --> Profile[CustomerCommerceProfile]
  CR --> PI
```

`CustomerSalesBrainService` authorizes commerce; relationship, intent, safety, personality, and response generation remain in the Conversation Brain. Evidence: `app/services/conversation_gateway.py`, `customer_sales_brain_service.py`, `commerce_execution_policy.py`, `commercial_offering_selector_service.py`, `telegram_inbound_adapter.py`.

## Repository boundaries

`C:\Creator-OS-React` contains the current React UI and FastAPI runtime, plus legacy Streamlit modules retained under `app/dashboard`. `C:\Creator-OS` is historical only. X publishing adapter code is in this repository, but broader X automation belongs to the separate `C:\X_Auto` project and was not audited as part of this system.

