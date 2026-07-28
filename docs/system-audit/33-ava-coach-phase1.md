# Ava Coach Phase 1 — Conversation Intelligence

Ava Coach is an observational workspace built from persisted `chat_threads` and
`chat_messages`. It uses deterministic measurements and never calls an AI
provider, changes prompts, writes conversation memory, or modifies Telegram
behavior.

The analysis snapshot records the reviewed message IDs and method. Overview
metrics describe conversation volume, length, returning activity, topics,
endings, questions, and continuation. Insights and recommendations are emitted
only when their deterministic thresholds have supporting message/thread IDs.

Recommendations target `Ava v1.1` while `Ava v1.0` remains the baseline.
Approve, Reject, and Dismiss are operator decisions. Approval creates an
Applied Improvement history record; Phase 1 does not activate the target
version or change runtime behavior.

Persistence:

- `ava_personality_versions`
- `ava_coach_snapshots`
- `ava_conversation_insights`
- `ava_coaching_recommendations`
- `ava_applied_improvements`

Request path:

`chat_threads/chat_messages`
→ `AvaCoachRepository`
→ `AvaCoachService`
→ `/api/v1/ava-coach`
→ `AvaCoachPage`.
