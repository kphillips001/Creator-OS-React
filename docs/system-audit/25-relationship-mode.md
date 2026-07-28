# Relationship Mode

## Purpose

Relationship Mode lets Creator_OS participate in live conversations while
commercial execution is intentionally unavailable before launch. It is an
independent `CommerceMode`; it does not overload `RuntimeMode` or OBSERVE.

The supported modes are `OFF`, `RELATIONSHIP`, and `LIVE`. `LIVE` remains the
compatibility default when no explicit configuration exists.

## Architecture

For every Relationship Mode turn, the normal conversation path continues:

```text
Inbound conversation
→ Conversation Gateway
→ Customer Sales Brain
→ Commercial Offering Selector
→ Recommendation Engine
→ Decision Engine / response generation
→ relationship-only response
```

The gateway converts a would-be `PRESENT_OFFER` execution policy to
`PRE_LAUNCH` before response generation. It then enforces
`COMMERCE_DISABLED_FOR_TURN` at the final authorization boundary.

No delivery URL, commercial offering copy, Purchase Intent, fulfillment, or
provider operation is exposed.

## Learning and Would Have Sold

The selected Commercial Offering and exact recommendation trace remain
available internally. A suppressed sale is recorded as the idempotent
`WOULD_HAVE_SOLD` Commerce Learning outcome with:

- selected offering and timestamp
- semantic, affinity, and freshness evidence
- `would_have_sold=true`
- `suppression_reason=RELATIONSHIP_MODE`

This outcome can improve observed-interest learning but is never treated as a
purchase, payment, delivery, fulfillment, or revenue event.

## Customer stage

A non-buyer whose sale is suppressed advances to
`PRE_LAUNCH_INTEREST`. This means the customer requested commercial content
while commerce was intentionally unavailable. It is distinct from purchased,
waiting-payment, and attributed-payment states.

## Creator workflow

Operations owns the explicit Commerce Mode control and requires confirmation
before changes. In Relationship Mode it states: “Conversation continues.
Commerce disabled.”

Creator Intelligence exposes customers met, returning visitors, would-have-sold
activity, requested offering evidence, and high-interest/pre-launch customers.
Recommendation Diagnostics exposes suppressed outcomes and confirms that no
Purchase Intent was created.

## Launch transition

Changing Commerce Mode from `RELATIONSHIP` to `LIVE` activates only the final
commercial execution boundary. Conversation personality, memory, relationship
scoring, customer ranking, Sales Brain evaluation, recommendation selection,
and learning remain on the same code path.
