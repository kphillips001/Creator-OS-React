# Autonomous Issue Resolution

Creator Intelligence exposes one primary **Resolve Issue** action for a persisted
diagnostic. The Creator Agent first classifies the evidence as `AUTO_FIX`,
`USER_ACTION_REQUIRED`, `CONFIGURATION_REQUIRED`, `NOT_FIXABLE`, or
`ALREADY_RESOLVED`.

Only `AUTO_FIX` dispatches the existing Developer Agent. The resolution record
links the immutable issue snapshot, decision, task, execution, validation
evidence, outcome, and completion time. Operator/configuration classifications
never execute repository changes.

After an autonomous execution reaches a terminal state, Creator OS requests a
new Creator Intelligence snapshot. `RESOLVED` is recorded only when the original
component is absent from current problems and its matching health check is
healthy. A completed execution without passing fresh diagnostics is
`PARTIALLY_RESOLVED`; failed or interrupted execution is
`COULD_NOT_RESOLVE`. This prevents an execution report from being treated as
proof of resolution.

The previous investigation, task review, approval, and manual dispatch workflow
remains available under **Advanced**. Recent resolution records can be reopened
from Creator Intelligence for review.
