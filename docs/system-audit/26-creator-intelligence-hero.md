# Creator Intelligence Hero

## Purpose

The Creator Intelligence hero is the operator's morning command card. It
combines the browser-local greeting, effective RuntimeMode, configured
CommerceMode, today's objective, one evidence-backed insight, and the sole
CommerceMode editing control.

## Greeting behavior

The greeting is calculated in React from the browser clock using
`Date.getHours()`. Server time is not used:

- 05:00–11:59: Good Morning
- 12:00–17:59: Good Afternoon
- 18:00–04:59: Good Evening

It is recalculated whenever the page is loaded or refreshed.

## Hero architecture

Creator Intelligence loads its existing dashboard projection and the existing
Operations module-switch projection. The latter supplies the effective Runtime
and configured Commerce modes. No duplicate backend endpoint or mode logic was
introduced.

The highlighted insight is selected only from existing dashboard evidence:
would-have-sold events, returning visitors, or READY offering availability.
When none is meaningful, the hero reports no significant change.

## Commerce mode ownership

Creator Intelligence Center is the authoritative UI for changing CommerceMode.
It calls the existing:

```text
PATCH /api/v1/operations/module-switches/commerce_mode
```

Operations continues to display CommerceMode and its consequences, but the
projection is read-only and directs operators to Creator Intelligence.

## Mode switching

Every mode change opens a confirmation dialog explaining the operational
consequences:

- `OFF`: customer conversations are disabled for maintenance.
- `RELATIONSHIP`: conversation and learning continue while commercial offers
  are suppressed.
- `LIVE`: Sales Brain-authorized commercial offers can execute.

Cancel performs no mutation. Confirm delegates to the existing CommerceMode
service through the established Operations API.
