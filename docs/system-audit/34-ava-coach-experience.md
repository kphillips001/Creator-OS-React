# Ava Coach Experience

Ava Coach is the dedicated operator workspace for deterministic conversation
analysis. Creator Intelligence shows only a compact Latest Coach Summary and
links here for detailed evidence and review.

## Evidence and analysis

Analysis reads persisted conversation messages and creates an immutable
snapshot. Conversation Health, strengths, behavior insights, and emerging
topics are derived from that snapshot. Evidence remains expandable and reports
sample size and confidence. Topic trends are intentionally unavailable until
two comparable analysis periods exist.

Running analysis is guarded against duplicate clicks and reports the actual
conversation and message counts when complete. Phase 1 makes no paid AI call.

## Recommendation lifecycle

Recommendations begin as `PENDING`. An operator may edit their title and
description, reject or dismiss them, or approve them for the proposed
personality version.

Approval means `APPROVED_FOR_VERSION`. It does not mutate prompts, conversation
logic, memory, or Ava's live behavior. `ACTIVATED` is reserved for a future,
explicit personality-version activation workflow. Existing legacy `APPROVED`
and `APPLIED` records are migrated safely to `APPROVED_FOR_VERSION`.

The current baseline is Ava v1.0. Ava v1.1 is a `DRAFT`; approved
recommendations remain inert until explicit future activation.

## Responsibility boundary

Creator Intelligence owns platform health and a compact summary containing the
latest analysis time and recommendation counts. Ava Coach owns detailed
conversation intelligence, positive observations, evidence, recommendation
review, and personality evolution history.

Neither workspace sends Telegram messages or changes Commerce, Creator Agent,
Developer Agent, or live conversation behavior.
