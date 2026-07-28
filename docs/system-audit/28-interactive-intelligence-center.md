# Interactive Creator Intelligence Center

## Purpose

Creator Intelligence Center now supports an operator drill-down from every
System Health summary and persisted Needs Attention item. The interaction stays
read-only: it explains the evidence already returned by diagnostics and links to
the existing workspace that owns deeper investigation.

## Diagnostic drawer

Selecting a health or attention item opens a side drawer containing:

- status and severity;
- the reported summary and evidence;
- affected component;
- explicit disclosure when no root cause was reported;
- a non-mutating investigation direction;
- the dashboard evidence timestamp.

The drawer deliberately does not infer causes, query providers, or attempt a
repair. Component-aware links open Operations, Provider Connections, or
Recommendation Diagnostics, while View Logs opens the existing Diagnostics
workspace.

## Diagnostic export

`Copy Diagnostic Summary` creates a clean Markdown report from the selected
issue and copies it through the browser clipboard. The report contains only the
data already present in the page response plus explicit statements where data is
not available.

## Creator Agent boundary

`Investigate with Creator Agent` currently generates a local, read-only
investigation package. The package is displayed for review and future use; no
Creator Agent request, AI call, repair, migration, test run, provider operation,
or production mutation occurs.

Future action placeholders are visible but disabled:

- Create Fix Plan
- Implement Fix
- Run Tests
- Open Pull Request

This keeps the interaction contract extensible without implying that autonomous
execution exists today.
