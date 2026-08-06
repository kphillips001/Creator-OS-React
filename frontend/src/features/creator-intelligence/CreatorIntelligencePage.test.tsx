import type { ReactElement } from "react";
import { act, fireEvent, render as renderLibrary, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  CreatorIntelligencePage,
  diagnosticResolved,
  localDate,
  localGreeting,
} from "./CreatorIntelligencePage";
import { DeveloperAgentExecutionProvider } from "../developer-agent/DeveloperAgentExecutionContext";

function render(ui: ReactElement) {
  return renderLibrary(<DeveloperAgentExecutionProvider>{ui}</DeveloperAgentExecutionProvider>);
}

const intelligence = {
  generatedAt: "2026-07-25T12:00:00Z",
  relationshipMode: {
    mode: "RELATIONSHIP",
    customersMet: 12,
    returningVisitors: 4,
    wouldHaveSoldToday: 3,
    mostRequestedOffering: "PHOTOSET",
    customersReadyForCommerce: 5,
    highInterestCustomers: 5,
  },
  systemHealth: [
    {
      label: "Database", status: "Healthy", summary: "Connection passed.",
      classification: "HEALTHY", root_cause: "Database connection check passed.",
      evidence: [{ kind: "database_check", value: "connected" }],
      confidence: 1, automatic_resolution: false,
      resolution_reason: "No repair is required.",
      recommended_action: "No action required.",
      affected_components: ["Database"],
    },
    { label: "Telegram", status: "Warning", evidence: "Connection delayed." },
  ],
  today: {
    activeConversations: null,
    waitingReplies: null,
    purchaseIntentsWaiting: 1,
    offers: 4,
    purchases: 1,
    revenueMinor: 999,
    conversionRate: 25,
    recommendations: 1,
    learningEvents: 3,
  },
  recommendations: [
    { title: "Package inventory", why: "Five assets are available.", action: "/commerce" },
  ],
  commerceLearning: {
    profiles: 2,
    eventsToday: 3,
    confidence: "75%",
    trend: "Tracked",
    signals: [{ label: "Content types", value: "IMAGE" }],
  },
  contentPipeline: {
    generationLibrary: 4,
    availableInventory: 5,
    commercialOfferings: 1,
    readyOfferings: 1,
  },
  customerOpportunities: [{ label: "Repeat buyers", value: 1 }],
  revenueOpportunities: [{ label: "READY offerings", value: 1 }],
  problems: [
    { title: "Worker attention", detail: "One worker is stale.", severity: "Warning" },
  ],
};

const controls = (mode: "OFF" | "RELATIONSHIP" | "LIVE" = "RELATIONSHIP") => ({
  scope: { creatorProfileId: "7", moduleConfiguration: "config" },
  globalStatus: {
    globalAutomation: true,
    globalSends: false,
    manualPause: false,
    runtimeMode: "LIVE",
    heartbeatSummary: {},
    workerHealthSummary: {},
    effectiveSafety: "ACTIVE",
    reason: null,
  },
  masterControl: {
    key: "global_automation",
    label: "Autonomous Sales & Messaging",
    configured: true,
    effective: "ACTIVE",
    reason: null,
    lastChanged: null,
    editable: true,
  },
  runtime: {
    configuredMode: "LIVE",
    effectiveMode: "LIVE",
    status: "LIVE",
    lastChanged: null,
    reason: null,
    editable: true,
  },
  commerceMode: {
    configuredMode: mode,
    effectiveMode: mode,
    description: mode === "RELATIONSHIP" ? "Conversation continues. Commerce disabled." : "Mode description",
    editable: true,
  },
  cards: { Messaging: [], Sales: [], Publishing: [], AI: [] },
  deploymentReadiness: [],
});

const json = (body: unknown) =>
  Promise.resolve(new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  }));

function mockRequests(
  mode: "OFF" | "RELATIONSHIP" | "LIVE" = "RELATIONSHIP",
  developerReady = true,
  dispatchOverride?: Promise<Response>,
) {
  return vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = String(input);
    if (url.includes("/developer-agent/health")) return json({
      cliDetected: true, sdkDetected: true, authenticationAvailable: true,
      appServerReachable: true, repositoryAccessible: true,
      expectedBranchActive: true, executionWorkerAvailable: true,
      persistenceAvailable: true,
      overallReadiness: developerReady ? "READY" : "DEGRADED",
      reason: developerReady
        ? "Developer Agent is ready."
        : "Codex CLI authentication is unavailable.",
    });
    if (url.includes("/developer-agent/notifications")) return json({ items: [] });
    if (url.includes("/developer-agent/history?")) return json({ items: [] });
    if (url.includes("/developer-agent/resolutions?")) return json({ items: [] });
    if (url.endsWith("/developer-agent/resolutions") && init?.method === "POST") {
      return json({
        resolution: {
          resolution_id: "resolution-1", issue_identifier: "Frontend",
          issue_snapshot: {}, decision: "USER_ACTION_REQUIRED",
          decision_reason: "Browser health requires an operator action.",
          required_action: "Open diagnostics.", destination_path: "/diagnostics",
          developer_agent_task_id: null, developer_agent_execution_id: null,
          validation_status: "NOT_REQUIRED", validation_evidence: {},
          outcome: "USER_ACTION_REQUIRED", resolved_at: "2026-07-26T12:00:00Z",
          created_at: "2026-07-26T12:00:00Z",
        },
        task: null, execution: null,
      });
    }
    if (url.includes("/developer-agent/tasks") && init?.method === "POST") {
      if (url.endsWith("/dispatch") && dispatchOverride) {
        return dispatchOverride;
      }
      if (url.endsWith("/dispatch") && JSON.parse(String(init?.body)).require_manual_approval) {
        return json({
          task: {
            task_id: "task-1", issue_identifier: "Database",
            investigation_package: "Package", implementation_task: "Task",
            repository_path: "C:\\Creator-OS-React", expected_branch: "react-migration",
            status: "AWAITING_APPROVAL", approved_at: null,
          },
          execution: null,
        });
      }
      if (url.endsWith("/dispatch")) return json({
        task: {
          task_id: "task-1", issue_identifier: "Database",
          investigation_package: "Package", implementation_task: "Task",
          repository_path: "C:\\Creator-OS-React", expected_branch: "react-migration",
          status: "APPROVED", approved_at: "2026-07-26T12:00:00Z",
        },
        execution: {
          execution_id: "execution-1", task_id: "task-1", issue_identifier: "Database",
          implementation_task: "Task", repository_path: "C:\\Creator-OS-React",
          expected_branch: "react-migration", status: "QUEUED", codex_session_id: null,
          started_at: null, completed_at: null, failure_reason: null,
          cancellation_reason: null, final_report: null, review_status: "PENDING",
          events: [{ event_id: 1, event_type: "EXECUTION_ACCEPTED", message: "Queued.", created_at: "2026-07-26T12:00:00Z" }],
        },
      });
      if (url.endsWith("/approve")) return json({ task_id: "task-1", status: "APPROVED", approved_at: "2026-07-26T12:00:00Z" });
      if (url.endsWith("/executions")) return json({
        execution_id: "execution-1", task_id: "task-1", issue_identifier: "Database",
        implementation_task: "Task", status: "QUEUED", codex_session_id: null,
        started_at: null, completed_at: null, failure_reason: null,
        cancellation_reason: null, final_report: null, review_status: "PENDING",
        events: [{ event_id: 1, event_type: "EXECUTION_ACCEPTED", message: "Execution accepted.", created_at: "2026-07-26T12:00:00Z" }],
      });
      return json({
        task_id: "task-1", issue_identifier: "Database",
        investigation_package: "Package", implementation_task: "Task",
        repository_path: "C:\\Creator-OS-React", expected_branch: "react-migration",
        status: "AWAITING_APPROVAL", approved_at: null,
      });
    }
    if (init?.method === "PATCH") return json(controls("LIVE"));
    return url.includes("/operations/module-switches")
      ? json(controls(mode))
      : json(intelligence);
  });
}

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe("Creator Intelligence operational homepage", () => {
  it.each([
    [new Date(2026, 0, 1, 5), "☀️ Good Morning, Kevin."],
    [new Date(2026, 0, 1, 11, 59), "☀️ Good Morning, Kevin."],
    [new Date(2026, 0, 1, 12), "🌤️ Good Afternoon, Kevin."],
    [new Date(2026, 0, 1, 17, 59), "🌤️ Good Afternoon, Kevin."],
    [new Date(2026, 0, 1, 18), "🌙 Good Evening, Kevin."],
    [new Date(2026, 0, 1, 4, 59), "🌙 Good Evening, Kevin."],
  ])("uses browser-local time for greeting boundaries", (time, expected) => {
    expect(localGreeting(time)).toBe(expected);
  });

  it("formats the displayed date from browser-local time", () => {
    expect(localDate(new Date(2026, 6, 26, 8))).toContain("July 26, 2026");
  });

  it("marks a diagnostic resolved only from refreshed healthy projections", () => {
    expect(diagnosticResolved(
      { component: "Database" },
      {
        problems: [],
        systemHealth: [{
          label: "Database", status: "Healthy", evidence: "Connection passed.",
        }],
      },
    )).toBe(true);
    expect(diagnosticResolved(
      { component: "Worker attention" },
      {
        problems: [{
          title: "Worker attention", detail: "One worker is stale.",
          severity: "Warning",
        }],
        systemHealth: [],
      },
    )).toBe(false);
  });

  it("renders Relationship Mode, Current Focus, pulse, observations, and attention", async () => {
    mockRequests();
    render(<MemoryRouter><CreatorIntelligencePage /></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: /Good (Morning|Afternoon|Evening), Kevin\./ })).toBeInTheDocument();
    expect(screen.getAllByText("🌱 Relationship Mode").length).toBeGreaterThan(0);
    expect(screen.getByText("Current Focus").parentElement).toHaveTextContent("Relationship Building");
    expect(screen.getByRole("heading", { name: "Relationship Pulse" })).toBeInTheDocument();
    expect(screen.getByText("PRE LAUNCH INTEREST Customers").parentElement).toHaveTextContent("No data collected yet.");
    expect(screen.getByRole("heading", { name: "🤖 Ava Coach" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open Ava Coach/ })).toHaveAttribute("href", "/agents/ava-coach");
    expect(screen.getByText(/No coaching analysis has been run yet/)).toBeInTheDocument();
    expect(screen.getByText(/Run Ava Coach to generate the first coaching report/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Needs Attention" })).toBeInTheDocument();
    expect(screen.getByText("Worker attention")).toBeInTheDocument();
    expect(screen.queryByText("Today's Objective")).not.toBeInTheDocument();
    expect(screen.queryByText("AI recommendations")).not.toBeInTheDocument();
  });

  it.each([
    ["OFF", "Maintenance"],
    ["LIVE", "Commerce Live"],
  ] as const)("renders the %s current focus", async (mode, focus) => {
    mockRequests(mode);
    render(<MemoryRouter><CreatorIntelligencePage /></MemoryRouter>);
    expect((await screen.findByText("Current Focus")).parentElement).toHaveTextContent(focus);
  });

  it("keeps all required quick actions including Reference Library", async () => {
    mockRequests();
    render(<MemoryRouter><CreatorIntelligencePage /></MemoryRouter>);
    await screen.findByText("Current Focus");
    for (const label of [
      "Content Studio",
      "Commerce",
      "Recommendation Diagnostics",
      "Developer Test Chat",
      "Operations",
      "Provider Connections",
      "Reference Library",
    ]) {
      expect(screen.getByRole("link", { name: new RegExp(label) })).toBeInTheDocument();
    }
  });

  it("confirms and updates through the existing Commerce Mode endpoint", async () => {
    const fetchMock = mockRequests("RELATIONSHIP");
    render(<MemoryRouter><CreatorIntelligencePage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: "💰 Commerce Live" }));
    expect(screen.getByRole("dialog", { name: "Enable Commerce Live?" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/operations/module-switches/commerce_mode",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ value: "LIVE" }),
      }),
    ));
  });

  it("uses a responsive grid with no prescriptive recommendation content", async () => {
    mockRequests();
    const { container } = render(<MemoryRouter><CreatorIntelligencePage /></MemoryRouter>);
    await screen.findByText("Current Focus");
    expect(container.querySelector(".intelligence-observation-grid")).toBeInTheDocument();
    expect(screen.queryByText("Package inventory")).not.toBeInTheDocument();
    expect(screen.queryByText(/you should/i)).not.toBeInTheDocument();
  });

  it("opens a diagnostic drawer from every clickable health summary", async () => {
    mockRequests();
    render(<MemoryRouter><CreatorIntelligencePage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: /Database Healthy/ }));
    const drawer = screen.getByRole("dialog", { name: "Database" });
    expect(drawer).toHaveTextContent("Connection passed.");
    expect(drawer).toHaveTextContent("Database connection check passed.");
    expect(drawer).toHaveTextContent("ClassificationHealthy");
    expect(drawer).toHaveTextContent("Automatic RepairNO");
    expect(drawer).toHaveTextContent("Affected Components");
    expect(drawer).toHaveTextContent("Suggested Remediation");
    expect(drawer).toHaveTextContent("Timestamp");
  });

  it("resolves an issue with one primary action and does not dispatch user actions", async () => {
    const fetchMock = mockRequests();
    render(<MemoryRouter><CreatorIntelligencePage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: /Telegram Warning/ }));
    fireEvent.click(screen.getByRole("button", { name: "✨ Resolve Issue" }));
    expect(await screen.findByText(/cannot be repaired automatically/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/developer-agent/resolutions",
      expect.objectContaining({ method: "POST" }),
    );
    expect(fetchMock.mock.calls.some(([input]) =>
      String(input).endsWith("/developer-agent/tasks/dispatch"),
    )).toBe(false);
  });

  it("opens persisted Needs Attention evidence and relevant navigation", async () => {
    mockRequests();
    render(<MemoryRouter><CreatorIntelligencePage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: /Worker attention/ }));
    expect(screen.getByRole("dialog", { name: "Worker Attention" })).toHaveTextContent("One worker is stale.");
    expect(screen.getByRole("link", { name: /Open Operations/ })).toHaveAttribute("href", "/business/operations");
    expect(screen.getByRole("link", { name: /View Logs/ })).toHaveAttribute("href", "/diagnostics");
  });

  it("copies a clean markdown diagnostic without invoking AI", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    mockRequests();
    render(<MemoryRouter><CreatorIntelligencePage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: /Database Healthy/ }));
    fireEvent.click(screen.getByRole("button", { name: /Copy Diagnostic Summary/ }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(expect.stringContaining("# Diagnostic Summary")));
    expect(writeText.mock.calls[0]?.[0]).toContain("## Classification\nHEALTHY");
    expect(writeText.mock.calls[0]?.[0]).toContain("\"database_check\"");
    expect(screen.getByRole("status")).toHaveTextContent("Diagnostic summary copied.");
  });

  it("generates a local Creator Agent investigation package without a request", async () => {
    const fetchMock = mockRequests();
    render(<MemoryRouter><CreatorIntelligencePage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: /Telegram Warning/ }));
    const requestCount = fetchMock.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: /Investigate with Creator Agent/ }));
    const report = screen.getByRole("textbox", { name: "Creator Agent investigation package" });
    expect((report as HTMLTextAreaElement).value).toContain("# Creator Agent Investigation Package");
    expect((report as HTMLTextAreaElement).value).toContain("## Suggested Investigation Scope");
    expect(screen.getByRole("status")).toHaveTextContent("generated locally");
    expect(fetchMock).toHaveBeenCalledTimes(requestCount);
    expect(screen.getByRole("link", { name: /Open Provider Connections/ })).toHaveAttribute("href", "/administration/providers");
  });

  it("auto-approves and immediately submits the reviewed implementation task", async () => {
    const fetchMock = mockRequests();
    render(<MemoryRouter><CreatorIntelligencePage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: /Database Healthy/ }));
    fireEvent.click(screen.getByRole("button", { name: /Investigate with Creator Agent/ }));
    fireEvent.click(screen.getByRole("button", { name: "Generate Implementation Task" }));
    const task = screen.getByRole("textbox", { name: "Developer Agent implementation task" });
    expect((task as HTMLTextAreaElement).value).toContain("C:\\Creator-OS-React");
    expect((task as HTMLTextAreaElement).value).toContain("react-migration");
    expect((task as HTMLTextAreaElement).value).toContain("## Acceptance Criteria");

    expect(screen.getByText("Developer Agent Settings")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Require manual approval before execution" })).not.toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: /Send to Developer Agent/ }));
    expect(await screen.findByRole("heading", { name: "Queued" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/developer-agent/tasks/dispatch",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining('"require_manual_approval":false'),
      }),
    );
    expect(screen.getByText("C:\\Creator-OS-React")).toBeInTheDocument();
    expect(screen.getByText("execution-1")).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(screen.queryByText(/simulation/i)).not.toBeInTheDocument();
  });

  it("retains optional manual approval mode in Developer Agent Settings", async () => {
    mockRequests();
    render(<MemoryRouter><CreatorIntelligencePage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: /Database Healthy/ }));
    fireEvent.click(screen.getByRole("button", { name: /Investigate with Creator Agent/ }));
    fireEvent.click(screen.getByRole("button", { name: "Generate Implementation Task" }));
    const approval = screen.getByRole("checkbox", {
      name: "Require manual approval before execution",
    });
    fireEvent.click(approval);
    fireEvent.click(screen.getByRole("button", { name: /Send to Developer Agent/ }));
    expect(await screen.findByRole("button", { name: "Approve Task" })).toBeInTheDocument();
    expect(window.localStorage.getItem("developerAgent.requireManualApproval")).toBe("true");
  });

  it("surfaces the exact readiness blocker instead of silently ignoring launch", async () => {
    mockRequests("RELATIONSHIP", false);
    render(<MemoryRouter><CreatorIntelligencePage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: /Database Healthy/ }));
    fireEvent.click(screen.getByRole("button", { name: /Investigate with Creator Agent/ }));
    fireEvent.click(screen.getByRole("button", { name: "Generate Implementation Task" }));
    fireEvent.click(screen.getByRole("button", { name: /Send to Developer Agent/ }));
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Developer Agent cannot start: Codex CLI authentication is unavailable.",
    );
  });

  it("shows an immediate optimistic launch card before the request resolves", async () => {
    let resolveDispatch: (response: Response) => void = () => undefined;
    const deferred = new Promise<Response>((resolve) => {
      resolveDispatch = resolve;
    });
    const fetchMock = mockRequests("RELATIONSHIP", true, deferred);
    render(<MemoryRouter><CreatorIntelligencePage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: /Database Healthy/ }));
    fireEvent.click(screen.getByRole("button", { name: /Investigate with Creator Agent/ }));
    fireEvent.click(screen.getByRole("button", { name: "Generate Implementation Task" }));
    const send = screen.getByRole("button", { name: /Send to Developer Agent/ });
    fireEvent.click(send);
    fireEvent.click(send);

    expect(screen.getByRole("status", { name: "Developer Agent launching" })).toHaveTextContent("Launching...");
    expect(screen.getByLabelText("Launching Developer Agent")).toBeInTheDocument();
    expect(screen.getByText("00:00")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Launching Developer Agent/ })).toBeDisabled();
    expect(screen.queryByRole("button", { name: /Send to Developer Agent/ })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([input]) =>
      String(input).endsWith("/developer-agent/tasks/dispatch"),
    )).toHaveLength(1);

    await act(async () => resolveDispatch(new Response(JSON.stringify({
      task: {
        task_id: "task-1", status: "APPROVED", approved_at: "2026-07-26T12:00:00Z",
      },
      execution: {
        execution_id: "execution-1", task_id: "task-1", issue_identifier: "Database",
        implementation_task: "Task", repository_path: "C:\\Creator-OS-React",
        expected_branch: "react-migration", status: "QUEUED", codex_session_id: null,
        started_at: null, completed_at: null, failure_reason: null,
        cancellation_reason: null, final_report: null, review_status: "PENDING",
        events: [{ event_id: 1, event_type: "EXECUTION_ACCEPTED", message: "Queued.", created_at: "2026-07-26T12:00:00Z" }],
      },
    }), { status: 200 })));
    expect(await screen.findByRole("heading", { name: "Queued" })).toBeInTheDocument();
    expect(screen.getByLabelText("Developer Agent running")).toBeInTheDocument();
  });

  it("stops launching, surfaces the backend error, and restores retry", async () => {
    mockRequests("RELATIONSHIP", true, Promise.resolve(new Response(JSON.stringify({
      detail: "Execution worker unavailable.",
    }), { status: 409, headers: { "Content-Type": "application/json" } })));
    render(<MemoryRouter><CreatorIntelligencePage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: /Database Healthy/ }));
    fireEvent.click(screen.getByRole("button", { name: /Investigate with Creator Agent/ }));
    fireEvent.click(screen.getByRole("button", { name: "Generate Implementation Task" }));
    fireEvent.click(screen.getByRole("button", { name: /Send to Developer Agent/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Developer Agent failed to start. Execution worker unavailable.",
    );
    expect(screen.queryByLabelText("Launching Developer Agent")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Send to Developer Agent/ })).toBeEnabled();
  });

  it("removes the spinner and shows completed elapsed state at terminal completion", async () => {
    Object.defineProperty(Element.prototype, "scrollIntoView", {
      configurable: true,
      value: vi.fn(),
    });
    mockRequests("RELATIONSHIP", true, Promise.resolve(new Response(JSON.stringify({
      task: { task_id: "task-1", status: "APPROVED", approved_at: "2026-07-26T12:00:00Z" },
      execution: {
        execution_id: "execution-1", task_id: "task-1", issue_identifier: "Database",
        implementation_task: "Task", repository_path: "C:\\Creator-OS-React",
        expected_branch: "react-migration", status: "COMPLETED", codex_session_id: "session-1",
        started_at: "2026-07-26T12:00:00Z", completed_at: "2026-07-26T12:01:42Z",
        failure_reason: null, cancellation_reason: null, review_status: "PENDING",
        events: [{ event_id: 2, event_type: "EXECUTION_COMPLETED", message: "Completed.", created_at: "2026-07-26T12:01:42Z" }],
        final_report: {
          status: "COMPLETED", summary: "Done", rootCause: "Verified",
          actionsPerformed: [], filesModified: [], databaseMigrationsApplied: "None",
          commandsExecuted: [], tests: [], validation: {}, remainingWarnings: [],
          telemetryDegraded: true,
          commitCreated: false, commitHash: null, executionDurationMs: 102000,
          codexSessionId: "session-1", gitStatusShort: "", gitDiffStat: "", gitDiff: "",
        },
      },
    }), { status: 200 })));
    render(<MemoryRouter><CreatorIntelligencePage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: /Database Healthy/ }));
    fireEvent.click(screen.getByRole("button", { name: /Investigate with Creator Agent/ }));
    fireEvent.click(screen.getByRole("button", { name: "Generate Implementation Task" }));
    fireEvent.click(screen.getByRole("button", { name: /Send to Developer Agent/ }));
    expect(await screen.findByRole("heading", { name: /Completed/ })).toBeInTheDocument();
    expect(screen.getByText("Completed in")).toBeInTheDocument();
    expect(screen.getByText("01:42")).toBeInTheDocument();
    expect(screen.queryByLabelText("Developer Agent running")).not.toBeInTheDocument();
    expect(screen.getByText("Telemetry degraded; the repository operation still completed.")).toBeInTheDocument();
  });
});
