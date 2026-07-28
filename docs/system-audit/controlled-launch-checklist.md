# Controlled launch checklist

## Before startup

- [ ] Confirm repository `C:\Creator-OS-React`, branch `react-migration`.
- [ ] Preserve the dirty worktree; do not reset unrelated Session work.
- [ ] Take and verify a PostgreSQL backup.
- [ ] Run schema certification; require `PASS` and no checksum drift.
- [ ] Use `Creator_OS.exe` or `tools/launcher/launch_creator_os.ps1`.
- [ ] Do **not** use legacy root `start.py`.
- [ ] Verify required environment variables without printing secret values.
- [ ] Confirm Fanvue shows Connected, required scopes present, and token valid.
- [ ] Confirm the authenticated Telegram session and Telethon dependency.
- [ ] Confirm exact Telegram ↔ Fanvue identity mapping for the test customer.
- [ ] Confirm one READY AI_CHAT offering and one LIVE publication.
- [ ] Validate title, price, currency, hero, provider resource, and HTTPS URL.
- [ ] Confirm Telegram and Commerce Reconciliation workers are enabled/healthy.
- [ ] Begin with RuntimeMode OFFLINE and Autonomous Sales & Messaging OFF.
- [ ] Keep all unrelated publishing and outreach modules disabled.

## OBSERVE rehearsal

- [ ] Start FastAPI `8001`, React `5174`, and required workers.
- [ ] Verify Database, Workers, Schema, Fanvue, and Telegram health.
- [ ] Move the selected creator to OBSERVE; keep the master switch OFF.
- [ ] Send one controlled inbound message from the approved test identity.
- [ ] Inspect Customer Sales Brain decision.
- [ ] Inspect selected offering and exact Recommendation Diagnostics trace.
- [ ] Confirm no external reply, Purchase Intent presentation, or provider write.
- [ ] Confirm Operations and Creator Intelligence show evidence accurately.
- [ ] Confirm uninstrumented metrics remain `Untracked`.

## Controlled LIVE window

- [ ] Owner/operator remains present throughout.
- [ ] One creator account and one approved customer/test identity only.
- [ ] Set a short, written start/end time.
- [ ] Open Operations, Creator Intelligence, Purchase Intents, Customer
      Commerce, Recommendation Diagnostics, and Webhook Monitor.
- [ ] Enable only the required Telegram and reconciliation workers.
- [ ] Verify LIVE mode, master switch, module switch, deployment readiness,
      identity, worker health, offering eligibility, and LIVE publication.
- [ ] Send one controlled commercial-interest message.
- [ ] Capture correlation ID, offering ID, publication ID, intent ID, message
      ID, webhook event ID, transaction ID, and recommendation trace.
- [ ] Confirm exactly one offer, intent, payment, attribution, acknowledgement,
      and learning outcome.
- [ ] Return OFFLINE immediately after the window.

## Stop conditions

Stop immediately for:

- wrong or unexplained offering;
- duplicate reply, intent, acknowledgement, or delivery;
- missing or UNKNOWN purchase attribution;
- provider error or unexpected scope/authentication failure;
- worker heartbeat loss or stale unrecovered lease;
- database or migration error;
- unexpected external send or publication;
- mismatch in price, currency, media, delivery URL, or customer identity.

## Rollback

- [ ] Set RuntimeMode OFFLINE.
- [ ] Turn Autonomous Sales & Messaging OFF.
- [ ] Disable relevant module switches.
- [ ] Stop only verified Telegram/reconciliation worker PIDs through supervisor.
- [ ] Preserve logs, webhooks, intents, transactions, outcomes, and heartbeats.
- [ ] Do not delete or rewrite durable records.
- [ ] Record the last successful checkpoint and exact failure.
- [ ] Diagnose and add a regression fixture before any retry.

