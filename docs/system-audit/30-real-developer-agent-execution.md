# Real Developer Agent Execution

## Official integration

Creator_OS uses the official OpenAI Codex Python SDK (`openai-codex==0.144.4`).
The SDK controls its pinned local Codex app-server over JSON-RPC and is the
server-side integration recommended for Python applications requiring coding
threads, streamed items, and persisted Codex session identifiers.

Requirements:

- Python 3.10 or later;
- installed `openai-codex` package;
- an authenticated local Codex session;
- access to the canonical `C:\Creator-OS-React` repository;
- active `react-migration` branch;
- applied Developer Agent persistence migration.

No credential, access token, cookie, or authorization header is stored in
Creator_OS or returned to React.

## Architecture

```text
Creator Intelligence diagnostic
→ persisted Developer Agent task
→ persisted operator approval
→ background DeveloperAgentExecutionService
→ official Codex Python SDK
→ local Codex app-server
→ repository evidence collection
→ persisted execution report and notification
→ React polling and notification deep link
```

The browser cannot select an arbitrary repository or submit shell commands.
The backend owns the fixed repository allowlist and generated task contract.

## Approval and execution lifecycle

Tasks use `AWAITING_APPROVAL`, `APPROVED`, and `REJECTED`. An execution endpoint
rejects any task without persisted approval.

The default single-operator workflow is:

```text
Investigate
â†’ Generate Implementation Task
â†’ Send to Developer Agent
â†’ persisted automatic owner approval
â†’ queued execution
```

There is no intermediate approval screen in the default mode. Manual approval
remains available under **Developer Agent Settings** through **Require manual
approval before execution**. The setting defaults to disabled and is retained
by the browser. When enabled, task creation stops at `AWAITING_APPROVAL` and
the existing persisted approval endpoints remain authoritative.

Executions use:

- `QUEUED`
- `STARTING`
- `RUNNING`
- `WAITING_FOR_INPUT`
- `TESTING`
- `COMPLETED`
- `FAILED`
- `CANCELLED`
- `INTERRUPTED`

`COMPLETED` is written only after the SDK returns terminal completion and
independent git evidence is collected. There are no timer-generated execution
states or reports.

## Repository safety

Before submission the service verifies:

- the canonical repository path exactly matches the allowlist;
- git metadata resolves for the linked worktree;
- `react-migration` is active;
- the task was approved;
- the SDK, authentication, app-server, persistence, and worker are ready.

The service captures initial branch, HEAD, and working-tree status. It never
resets, cleans, stashes, switches branches, force-checks out, pushes, deploys, or
creates a commit automatically. Generated tasks explicitly forbid commits.

## Evidence and events

SDK thread items are persisted as execution events. After terminal completion,
Creator_OS independently collects current branch, HEAD, `git status --short`,
`git diff --stat`, `git diff --check`, and `git diff`. Commands and test results
are reported only when present in SDK event evidence. Missing fields say `Not
reported` or `Not verified`.

SDK item-completion notifications are persisted while the turn is running and
classified into observable phases such as repository inspection, planning,
file modification, and test execution. The live view presents status, latest
event, repository, branch, elapsed time, execution ID, Codex session ID, and
recent persisted events. It does not display inferred percentages.

Terminal execution states refresh Creator Intelligence, Operations, schema
certification, Developer Agent readiness, execution history, and notification
counts. The active diagnostic is re-evaluated from the refreshed backend
projection. When its warning is absent and its health projection is healthy,
the drawer displays `Resolved`, its timestamp, and the execution identifier.
No browser refresh is required.

Creator Intelligence includes persisted **Recent Executions**. Selecting an
entry reopens its exact execution report.

## Notifications and review

Task approval, execution start, completion, and failure notifications are stored
in PostgreSQL with unread/read state. Notification selection reopens the exact
execution report. Result review is separate from execution approval and supports
`ACKNOWLEDGED`, `REJECTED`, and `ARCHIVED`.

## Cancellation and recovery

Queued work can be cancelled when the background future has not started. A
running SDK turn is not presented as cancellable when safe interruption cannot
be confirmed. On backend startup, non-terminal persisted executions that cannot
be reconciled to a live local process become `INTERRUPTED`; completion is never
inferred.

## Failure and disabled behavior

When any readiness check fails, submission is disabled and the UI shows the
observed reason, recheck control, task copy, and diagnostic copy. It never falls
back to simulated success.

To disable execution, uninstall or disable the local Codex SDK/CLI, remove local
Codex authentication, or leave the persistence migration unapplied. No separate
remote execution endpoint is enabled.
