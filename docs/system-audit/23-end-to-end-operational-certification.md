# Session 6 — End-to-End Operational Certification

Certification date: 2026-07-25  
Repository: `C:\Creator-OS-React`  
Branch / HEAD: `react-migration` / `76b3c71a3c884098173a419c788ed51ba5dba2fc`

## Scope and result

This was a local, fixture-based certification. Telegram transports, Fanvue
clients, clocks, repositories, and worker processes were mocked where the
existing tests provide injection boundaries. No provider write, paid AI call,
message, publication, or purchase occurred.

**Classification: CONDITIONAL PASS.** The internal deterministic commerce
path, safety gates, persistence contracts, retry claims, attribution rules,
catalog reads, and learning rules pass their safe suites. The current machine
must not be switched LIVE yet: it has no Telegram identity mapping, no READY
AI_CHAT offering, no LIVE Commercial Publication, Telegram and Commerce
Reconciliation workers are disabled, and the master switch is OFF. Those are
explicit controlled-launch prerequisites rather than defects in the certified
internal path.

## Authoritative runtime architecture

The supported FastAPI entry point is `app.fanvue_callback_server:app`.
The supported native entry point is `Creator_OS.exe`, which delegates to
`tools/launcher/launch_creator_os.ps1`. That launcher is the current source of
truth:

- FastAPI: `127.0.0.1:8001`
- React/Vite: `127.0.0.1:5174`
- worker supervision: `WorkerLauncherSupervisionService`
- process state: `logs/runtime/launcher_state.json`
- persisted liveness: `worker_heartbeats`

Root `start.py` remains a contradictory legacy launcher for FastAPI `8000` and
Streamlit `8501`. It is not the supported React launch path. The situation is
**safe only with documented launcher use**: operators must use
`Creator_OS.exe` / `tools/launcher/launch_creator_os.ps1`, never `start.py`.
Removing legacy Streamlit support was outside this certification.

The configured runtime was observed as OFFLINE. Autonomous Sales & Messaging
was OFF. Telegram deployment readiness and webhook signing configuration were
READY; Fanvue, Mass PPV, and reaction live permits remained blocked where
applicable. The launcher state showed Telegram, Fanvue Commercial Publications,
and Commerce Reconciliation disabled.

## Schema certification

`20260721_009_photoshoot_seed_covers.sql` is a data correction that aligns each
Photoshoot deliverable hero with the first approved ordered member. Before
application:

- SHA-256: `3853a1c2e14c9059a281ad1e31991199a47644f3d6fe41b1adac1e8ac3b55d66`
- migration history row: absent
- correction predicate mismatches: `0`
- deliverables inspected: `4`
- memberships inspected: `16`
- rollback: intentionally non-destructive (`SELECT 1`) because the old,
  incorrect reference identity cannot be safely reconstructed
- later dependency requiring a mismatched hero: none found

It was applied with the supported checksum-guarded
`SchemaManagerService.reconcile_one()` operation. The SQL was idempotent for
the current rows and its exact checksum was recorded.

**Schema certification: PASS.** Missing migrations: none. Drift: none.

## Scenario certification

| Scenario | Result | Evidence |
| --- | --- | --- |
| A — non-commercial greeting | PASS | Readiness tests block PRESENT_OFFER for greetings; unified brain tests prove no catalog query and no intent-side workflow. |
| B — commercial interest | PASS (fixture) | Sales Brain is evaluated once; selector filters LIVE/PRESENT candidates; semantic/affinity ranking emits a versioned trace; Telegram purchase-intent wrapper creates before delivery and confirms only afterward. |
| C — active Purchase Intent | PASS | Active eligible offering is reused; invalid active offering fails closed without fallback; replacement supersedes history; structural partial unique index preserves one active intent. |
| D — verified purchase | PASS (contract/local integration) | Current webhook topics normalize; captured-format signatures validate in fixture tests; `external_event_id` is unique; official earnings reconciliation uses `transactionOrderIds`; one hard candidate attributes and records PURCHASED once; duplicates do not double-count. |
| E — ambiguous purchase | PASS | Multiple hard matches result in UNKNOWN, mark candidates unknown, and perform no fulfillment guess. |
| F — delivery | CONDITIONAL | Fake text transport and safety boundary pass. The authoritative Fanvue Media Link is the content-delivery resource. Purchase acknowledgement persistence is idempotent. A transport-success/local-ack crash window remains at-least-once for Telegram text because Telegram supplies no application idempotency key. |
| G — Commerce Learning | PASS | Outcomes are append-only/idempotent, attributed purchases rebuild verified affinities, and persisted learning changes future ranking with trace evidence. PRESENTED alone does not infer preference. |
| H — ignored/expired | PASS | Expiration is idempotent; negative outcomes apply documented small weights; recent-offer/diversification strategies suppress repetition. |
| I — refund | UNSUPPORTED LIVE TRANSPORT | The learning service supports idempotent REFUNDED outcomes and a strong negative adjustment. No verified current Fanvue refund webhook contract is wired into Session 20, so no live refund claim is made and no revocation is invented. |

The full provider-to-customer journey was not executed live. The result proves
internal contracts and failure behavior, not provider availability.

## Restart and idempotency checkpoints

| Checkpoint | Certification |
| --- | --- |
| Intent created before presentation | Durable CREATED record; delivery failure marks ABANDONED; one-active structural constraint prevents duplicates. |
| Webhook persisted before processing | Public handler queues only; worker claims durable rows; stale claims recover. |
| Transaction before attribution | Reconciliation ledger remains PENDING/VERIFIED and transaction uniqueness prevents double revenue. |
| Attribution before fulfillment | PURCHASED intent is durable; UNKNOWN never becomes eligible through guessing. |
| Provider send before local acknowledgement | External Telegram send is an honest at-least-once boundary. Purchase acknowledgement uses `COALESCE` and is restart-safe after the local write, but a crash after transport success and before that write can repeat acknowledgement text. Operate with one worker and monitor during controlled launch. |
| Outcome insert before profile rebuild | Source-event uniqueness makes outcome insertion idempotent; profile is rebuilt/upserted from observed outcomes. A rebuild failure is retryable through the owning event workflow. |
| Worker processing | Lease recovery, retry scheduling, graceful shutdown, restart, PID ownership, and heartbeat state pass fixture tests. |

No durable record is deleted during recovery. The Operations workspace exposes
webhook, queue, publication, worker, and delivery failures.

## OBSERVE rehearsal

`RuntimeControlService` tests prove OBSERVE records recommendations and returns
no execution intent. OFFLINE blocks runtime action. Global automation remains
a separate final boundary. Developer Test Chat is developer-authorized and
does not own an external transport.

Current configuration was not mutated into OBSERVE. Tomorrow's rehearsal:

1. Start only with the supported launcher.
2. Confirm schema PASS and healthy required workers.
3. Keep Autonomous Sales & Messaging OFF.
4. Select OBSERVE for the active creator.
5. Submit one controlled inbound fixture/test account message.
6. Inspect Sales Brain and Recommendation Diagnostics.
7. Confirm no Telegram outbound event and no Purchase Intent presentation.
8. Confirm Operations and Creator Intelligence reflect only persisted facts.

## LIVE safety chain

The effective sequence is:

`RuntimeMode → autonomy master → module switch → deployment permit → provider
credentials/identity → worker state → selector eligibility → LIVE publication
→ global send guard → transport`.

Tests prove OFFLINE and OBSERVE cannot execute sends, an OFF master switch
blocks before transport/queue mutation, deployment permits are not overridden
by the operator projection, invalid delivery URLs fail closed, and Test Chat
does not select a live transport. Missing selector eligibility returns a
reasoned no-offering result. No legacy Product or READY-asset registration
worker participates in the authoritative selector.

The principal duplication is that runtime mode, the automation master, module
switches, and the global send guard overlap deliberately. They are defense in
depth, not contradictory bypasses. The stale `start.py` launcher is the only
operational contradiction found.

## Telegram certification

**Level: internally certified with mocked transport; configuration-readable;
not live-proven in this session.**

Covered: inbound validation and normalization, deterministic correlation,
identity adapter handoff, one gateway execution, unified Test Chat/Telegram
commerce decisions, offer text/link formatting, final safety boundary, fake
sync/async transport, persisted worker heartbeat, supervised restart, quiet
state and delayed-worker guards in the broader runtime suites.

Not proven here: a real Telethon session, real outbound delivery, provider
rate behavior, or true network retry. The local Python environment lacks the
optional `telethon` package, so transport module collection is an environment
prerequisite. The current database has zero Telegram identity mappings and
the Telegram worker is disabled.

## Fanvue certification

**Level: official-client contract tested and locally integrated; OAuth
connection previously established; no live call in this session.**

The selected account is connected, has a refresh token, has all required Media
Link scopes, and reports publication readiness. The stored Fanvue user UUID is
present; the creator UUID is absent. OAuth token values were not exposed.

Covered: account/token selection, required scope projection, documented API
version, upload/media-link checkpoints, LIVE/PRESENT selector requirements,
price/resource validation, current signature contract, webhook deduplication,
earnings reconciliation, hard attribution, UNKNOWN ambiguity, and worker retry
contracts.

Still required: resolve/persist the creator UUID through the supported account
flow if the verified event requires it, enable reconciliation, and perform one
operator-controlled Telegram/Fanvue journey. No purchase was made here.

## Catalog synchronization

The selector reads PostgreSQL on each query. There is no catalog cache,
reindex, model retraining, legacy Product dependency, or READY chat
registration worker in the authoritative path. READY offerings require an
eligible sales channel and LIVE/PRESENT provider resource. Updated fields are
visible on the next selector query; archived, mismatched, unavailable, or
non-LIVE records are immediately excluded. SINGLE_IMAGE and PHOTOSET paths are
covered by unified brain/selector fixtures. Test Chat and Telegram share the
same Conversation Gateway, Sales Brain, selector, and recommendation engine.

The current selected creator has `28` Available Inventory assets and `6`
READY analyses, but zero READY AI_CHAT offerings and zero LIVE publications.

## Commerce Learning and recommendations

Learning is based only on observed outcomes. Attributed purchases produce
affinity evidence; presentations alone do not. Duplicate source keys are
ignored, refunds reverse learned affinity, negative outcomes use bounded
weights, and semantic/affinity/freshness/diversification/history contributions
are exposed in deterministic traces. No paid model or embedding call is
required.

## Creator Intelligence Center

The homepage performs one read-only API request. Its database aggregate was
executed successfully against the certified schema. Health derives from
Operations and schema certification. Today metrics use persisted Purchase
Intents, transactions, and outcomes. Pipeline counts derive from canonical
assets, destinations, offerings, publications, and Generation Library state.
Operations failures include persisted delivery failures. Metrics lacking an
authoritative projection—active conversations, waiting replies, and
unstructured learning facets—remain labelled `Untracked`.

Current evidence: schema PASS, Operations critical/85, two healthy workers,
one stopped, seven untracked, and no provider configuration warnings.

## Operational failure matrix

| Failure | Detected? | Persisted? | Retry-safe? | Operator-visible? | Blocks launch? |
| --- | --- | --- | --- | --- | --- |
| Telegram disconnected | Yes, configuration/heartbeat | Launcher state + heartbeat | Supervisor restart is PID-safe | Operations | Yes |
| Invalid identity mapping | Yes, exact UUID lookup fails closed | Mapping absence is durable | Safe after corrected mapping | Test Chat/diagnostics | Yes |
| No eligible offering | Yes, filtering summary | Trace where diagnostics are recorded | Read-only retry | Recommendation diagnostics | Blocks commerce, not chat |
| Fanvue token expired | Yes | Account expiry metadata | OAuth refresh/reconnect path | Provider Connections | Yes for Fanvue work |
| Missing required scope | Yes | Granted scope metadata | Reauthorize | Provider Connections | Yes |
| Publication FAILED | Yes | `commercial_publications` | Claimed retry checkpoints | Commerce/Operations | Yes for that offer |
| Webhook invalid signature | Yes, HTTP 401 | Monitor is memory-only before acceptance | Provider may retry after secret fix | Webhook Monitor | Yes for purchase recognition |
| Duplicate webhook | Yes | Unique `external_event_id` | Yes; ignored idempotently | Webhook diagnostics | No |
| UNKNOWN purchase | Yes | Intent + reconciliation | Safe manual reconciliation | Purchase Intents/Customer Commerce | Blocks fulfillment |
| Delivery failure | Yes | Delivery event/failure evidence | Safe only before confirmed external success | Operations | Yes for that delivery |
| Worker crash | Yes | Heartbeat/launcher state | Yes | Operations | Yes when required |
| Stale lease | Yes | Lease owner/expiry | Recoverable | Operations | No if recovery succeeds |
| Database unavailable | Yes | Not while DB is unavailable | Process retry/restart | Health/logs | Yes |
| Learning rebuild failure | Yes through owning event failure | Event retry state | Idempotent source key | Webhook/worker diagnostics | No immediate send; blocks trusted learning |
| Pending migration | Yes | Migration ledger | Checksum-guarded reconciliation | Schema certification | Yes |

## Defect found and fixed

Three `TelegramDeliveryExecutor` unit tests instantiated the production safety
reader, so their result depended on the operator's real master switch. This
violated test isolation and made a fake-transport capability test fail when the
safe OFF configuration was active. The tests now inject an explicit
`AllowingSafetyService`; production code and safety behavior are unchanged.

## Unresolved blockers and live prerequisites

Internal launch blockers: none found in the fixture-certified path.

Prerequisites before a controlled LIVE window:

1. Use the supported launcher, not `start.py`.
2. Install/verify the declared Telethon runtime dependency and authenticated
   Telegram session.
3. Create and verify at least one Telegram-to-Fanvue identity mapping.
4. Resolve the stored Fanvue creator UUID if required by verified events.
5. Create at least one READY AI_CHAT Commercial Offering with a LIVE
   Commercial Publication and valid HTTPS delivery URL.
6. Enable and verify healthy Telegram and Commerce Reconciliation workers.
7. Complete OBSERVE rehearsal with zero external sends.
8. Enable LIVE/master/module gates only for the supervised window.
9. Accept and monitor the Telegram acknowledgement at-least-once crash
   boundary; stop immediately on duplicate output.
10. Perform one controlled live purchase only with explicit owner approval.

## Exact operator launch checklist

Use [controlled-launch-checklist.md](controlled-launch-checklist.md). The stop
control is OFFLINE plus Autonomous Sales & Messaging OFF, followed by stopping
the verified transport workers. Durable records must be preserved for
diagnosis.

## Validation results

- Focused safe backend certification: `275 passed`.
- React: TypeScript PASS, ESLint PASS, `187 passed`.
- `python -m compileall -q app`: PASS.
- `git diff --check`: PASS (line-ending notices only).
- Live read-only aggregate query for Creator Intelligence: PASS.
- Schema certification after guarded reconciliation: PASS.
- Repository-wide backend collection: `1832` tests collected, interrupted by
  `9` collection errors. Two are the missing optional `telethon` dependency,
  one is missing legacy dashboard `pandas`, and six are legacy CMS upload
  imports for repository functions no longer exported. These are reported
  separately from the authoritative commerce certification. Missing Telethon
  does affect real Telegram startup and is therefore an explicit launch
  prerequisite; the legacy CMS/Streamlit collection errors do not execute in
  the certified Conversation Gateway → Commercial Offering path.
