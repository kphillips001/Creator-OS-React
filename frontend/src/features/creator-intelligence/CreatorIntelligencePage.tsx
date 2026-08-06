import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Bot,
  Clipboard,
  HeartPulse,
  Radar,
  X,
} from "lucide-react";
import { Link, useLocation } from "react-router-dom";

import { operationsApi } from "../business-operations/api";
import type { OperationsModuleSwitches } from "../business-operations/types";
import {
  useDeveloperAgentExecutions,
  type AutonomousResolution,
  type DeveloperAgentTask,
  type DeveloperExecution,
} from "../developer-agent/DeveloperAgentExecutionContext";
import { loadCreatorIntelligence } from "./api";
import type {
  CreatorIntelligence,
  HealthStatus,
} from "./types";
import "./creator-intelligence.css";

type CommerceMode = "OFF" | "RELATIONSHIP" | "LIVE";
type DiagnosticIssue = {
  component: string;
  status: string;
  severity: HealthStatus;
  summary: string;
  evidence: string | Array<Record<string, unknown>>;
  classification?: string;
  root_cause?: string;
  confidence?: number;
  automatic_resolution?: boolean;
  resolution_reason?: string;
  recommended_action?: string;
  affected_components?: string[];
  diagnostic?: Record<string, unknown>;
  timestamp: string;
  destination?: { label: string; path: string };
};

const evidenceText = (value: DiagnosticIssue["evidence"]) =>
  typeof value === "string" ? value : JSON.stringify(value, null, 2);

const title = (value: string) =>
  value
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
const displayValue = (value: string | number) =>
  value === "Untracked" ? "No data collected yet." : value;
const statusClass = (status: HealthStatus) =>
  status === "Healthy"
    ? "is-healthy"
    : status === "Warning"
      ? "is-warning"
      : "needs-attention";

// Exported for boundary testing of browser-local time ranges.
// eslint-disable-next-line react-refresh/only-export-components
export function localGreeting(now = new Date()) {
  const hour = now.getHours();
  if (hour >= 5 && hour < 12) return "☀️ Good Morning, Kevin.";
  if (hour >= 12 && hour < 18) return "🌤️ Good Afternoon, Kevin.";
  return "🌙 Good Evening, Kevin.";
}

// eslint-disable-next-line react-refresh/only-export-components
export function localDate(now = new Date()) {
  return new Intl.DateTimeFormat(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  }).format(now);
}

const commerceLabel = (mode: CommerceMode) =>
  mode === "RELATIONSHIP"
    ? "🌱 Relationship Mode"
    : mode === "LIVE"
      ? "💰 Commerce Live"
      : "OFF";

function operatingState(mode: CommerceMode, runtime: string) {
  if (runtime === "OFFLINE" || mode === "OFF") {
    return {
      status: "Maintenance",
      focus: "Maintenance",
      explanation: "Commerce is off while Creator_OS remains available for operational review.",
    };
  }
  if (mode === "LIVE") {
    return {
      status: "Commerce Enabled",
      focus: "Commerce Live",
      explanation: "Approved offerings may be presented when the Sales Brain authorizes them.",
    };
  }
  return {
    status: "Relationship Building",
    focus: "Relationship Building",
    explanation: "Ava is learning from conversations while commercial offers remain suppressed.",
  };
}

function observedOpportunities(data: CreatorIntelligence) {
  const observations: string[] = [];
  if ((data.contentPipeline.readyOfferings ?? 0) === 0) {
    observations.push("No READY offerings currently exist.");
  }
  if (data.relationshipMode.wouldHaveSoldToday > 0) {
    observations.push(`Would Have Sold events: ${data.relationshipMode.wouldHaveSoldToday}`);
  }
  if (data.relationshipMode.highInterestCustomers > 0) {
    observations.push(`High interest customers: ${data.relationshipMode.highInterestCustomers}`);
  }
  return observations;
}

function diagnosticDestination(component: string) {
  const normalized = component.toLowerCase();
  if (normalized.includes("telegram") || normalized.includes("fanvue") || normalized.includes("provider")) {
    return { label: "Open Provider Connections", path: "/administration/providers" };
  }
  if (normalized.includes("recommendation")) {
    return { label: "Open Recommendation Diagnostics", path: "/developer/recommendations" };
  }
  return { label: "Open Operations", path: "/business/operations" };
}

function diagnosticMarkdown(issue: DiagnosticIssue, investigation = false) {
  return [
    `# ${investigation ? "Creator Agent Investigation Package" : "Diagnostic Summary"}`,
    "",
    "## Issue",
    issue.component,
    "",
    "## Status",
    issue.status,
    "",
    "## Severity",
    issue.severity,
    "",
    "## Summary",
    issue.summary,
    "",
    "## Root Cause",
    issue.root_cause ?? "Root cause is unknown because the diagnostic source did not provide one.",
    "",
    "## Classification",
    issue.classification ?? "UNKNOWN",
    "",
    "## Affected Components",
    ...(issue.affected_components ?? [issue.component]).map((item) => `- ${item}`),
    "",
    "## Evidence",
    evidenceText(issue.evidence),
    "",
    "## Recent Events",
    "No related event stream is included in the current dashboard response.",
    "",
    "## Suggested Investigation Scope",
    `Review ${issue.component} diagnostics and verify the recorded evidence without changing production state.`,
    "",
    "## Suggested Resolution",
    `Use ${issue.destination?.label ?? "the relevant diagnostics workspace"} to determine the required operator action.`,
    "",
    "## Timestamp",
    issue.timestamp,
  ].join("\n");
}

function implementationTask(issue: DiagnosticIssue) {
  return [
    "Implement the following Creator_OS diagnostic resolution.",
    "",
    "Repository:",
    "C:\\Creator-OS-React",
    "",
    "Branch:",
    "react-migration",
    "",
    "## Objective",
    `Investigate and resolve the reported ${issue.component} issue using verified repository evidence.`,
    "",
    "## Scope",
    `Limit changes to the components responsible for ${issue.component}.`,
    "",
    "## Diagnostic Evidence",
    evidenceText(issue.evidence),
    "",
    "## Constraints",
    "- Do not infer a root cause without repository evidence.",
    "- Do not modify unrelated Commerce, Ava, Recommendation Engine, or Telegram behavior.",
    "- Preserve existing production behavior outside the verified defect.",
    "- Do not create a git commit.",
    "",
    "## Acceptance Criteria",
    `- The verified ${issue.component} warning is resolved or its exact blocker is documented.`,
    "- Existing behavior has no regression.",
    "- Any changed behavior has focused tests.",
    "",
    "## Validation",
    "- Run focused tests for affected components.",
    "- Run static validation appropriate to changed files.",
    "- Run git diff --check.",
    "",
    "## Final Report",
    "- Root cause",
    "- Files modified",
    "- Implementation summary",
    "- Tests and validation",
    "- Remaining warnings",
    "- Whether a commit was created",
  ].join("\n");
}

// Exported for deterministic diagnostic-resolution testing.
// eslint-disable-next-line react-refresh/only-export-components
export function diagnosticResolved(
  issue: Pick<DiagnosticIssue, "component">,
  refreshed: Pick<CreatorIntelligence, "problems" | "systemHealth">,
) {
  const normalized = issue.component.toLowerCase();
  const stillProblem = refreshed.problems.some(
    (problem) => problem.title.toLowerCase() === normalized,
  );
  const matchingHealth = refreshed.systemHealth.find(
    (item) => item.label.toLowerCase() === normalized,
  );
  return !stillProblem && (!matchingHealth || matchingHealth.status === "Healthy");
}

export function CreatorIntelligencePage() {
  const location = useLocation();
  const {
    getExecution, recentExecutions, refreshExecutions, refreshNotifications,
    recentResolutions, recheck,
  } = useDeveloperAgentExecutions();
  const [data, setData] = useState<CreatorIntelligence | null>(null);
  const [controls, setControls] = useState<OperationsModuleSwitches | null>(null);
  const [pendingMode, setPendingMode] = useState<CommerceMode | null>(null);
  const [selectedIssue, setSelectedIssue] = useState<DiagnosticIssue | null>(null);
  const [reopenedExecution, setReopenedExecution] = useState<DeveloperExecution | null>(null);
  const [reopenedResolution, setReopenedResolution] = useState<AutonomousResolution | null>(null);
  const [resolution, setResolution] = useState<{
    executionId: string; resolvedAt: string;
  } | null>(null);
  const [savingMode, setSavingMode] = useState(false);
  const [error, setError] = useState("");

  const refreshDashboard = useCallback(async () => {
    const [intelligence, operations] = await Promise.all([
      loadCreatorIntelligence(),
      operationsApi.module_switches(),
    ]);
    setData(intelligence);
    setControls(operations);
    await Promise.all([
      recheck(), refreshExecutions(), refreshNotifications(),
    ]);
    return intelligence;
  }, [recheck, refreshExecutions, refreshNotifications]);

  useEffect(() => {
    void refreshDashboard().catch((reason: unknown) => {
      setError(reason instanceof Error ? reason.message : "Unable to load Creator Intelligence.");
    });
  }, [refreshDashboard]);
  useEffect(() => {
    const executionId = (location.state as { developerExecutionId?: string } | null)?.developerExecutionId;
    if (executionId) void getExecution(executionId).then(setReopenedExecution);
  }, [getExecution, location.state]);

  if (error) {
    return <main className="intelligence-page"><div className="intelligence-state" role="alert"><AlertTriangle />{error}</div></main>;
  }
  if (!data) {
    return <main className="intelligence-page"><div className="intelligence-state">Loading operational intelligence…</div></main>;
  }

  const commerceMode = controls?.commerceMode.configuredMode ?? data.relationshipMode.mode;
  const runtimeMode = controls?.runtime.effectiveMode ?? "Unavailable";
  const state = operatingState(commerceMode, runtimeMode);
  const opportunities = observedOpportunities(data);
  const relationshipPulse: Array<[string, string | number]> = [
    ["New conversations", data.today.activeConversations ?? "Untracked"],
    ["Returning visitors", data.relationshipMode.returningVisitors],
    ["High interest customers", data.relationshipMode.highInterestCustomers],
    ["PRE_LAUNCH_INTEREST customers", "Untracked"],
    ["Would Have Sold", data.relationshipMode.wouldHaveSoldToday],
    ["Average conversation length", "Untracked"],
    ["Relationship trend", data.commerceLearning.trend || "Untracked"],
  ];

  const confirmMode = async () => {
    if (!pendingMode) return;
    setSavingMode(true);
    setError("");
    try {
      setControls(await operationsApi.updateModuleSwitch("commerce_mode", pendingMode));
      setPendingMode(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to update Commerce Mode.");
    } finally {
      setSavingMode(false);
    }
  };

  return <main className="intelligence-page">
    <header className="intelligence-hero">
      <div className="intelligence-hero__heading">
        <p>Creator Intelligence Center</p>
        <h1>{localGreeting()}</h1>
        <time>{localDate()}</time>
      </div>
      <div className="intelligence-hero__status">
        <Status label="Runtime" value={runtimeMode} className={`mode-badge--${runtimeMode.toLowerCase()}`} />
        <Status label="Commerce" value={commerceLabel(commerceMode)} className={`mode-badge--${commerceMode.toLowerCase()}`} />
        <Status label="Status" value={state.status} />
      </div>
      <div className="intelligence-hero__focus">
        <span>Current Focus</span>
        <strong>{state.focus}</strong>
        <p>{state.explanation}</p>
      </div>
      <div className="intelligence-hero__modes" role="group" aria-label="Switch Commerce Mode">
        {(["OFF", "RELATIONSHIP", "LIVE"] as const).map((mode) =>
          <button className={commerceMode === mode ? "is-active" : ""} disabled={savingMode || commerceMode === mode} key={mode} onClick={() => setPendingMode(mode)} type="button">{commerceLabel(mode)}</button>,
        )}
      </div>
    </header>

    <div className="intelligence-primary-grid">
      <section aria-labelledby="pulse-heading">
        <Heading icon={<Radar />} id="pulse-heading" title="Relationship Pulse" />
        <div className="pulse-card">{relationshipPulse.map(([label, value]) => <Stat key={label} label={label} value={value} />)}</div>
      </section>
      <section aria-labelledby="health-heading">
        <Heading icon={<HeartPulse />} id="health-heading" title="System Health" />
        <div className="health-grid">{data.systemHealth.map((item) =>
          <button className="health-card" key={item.label} onClick={() => setSelectedIssue({
            component: title(item.label),
            status: item.status,
            severity: item.status,
            summary: item.summary ?? evidenceText(item.evidence),
            evidence: item.evidence,
            classification: item.classification,
            root_cause: item.root_cause,
            confidence: item.confidence,
            automatic_resolution: item.automatic_resolution,
            resolution_reason: item.resolution_reason,
            recommended_action: item.recommended_action,
            affected_components: item.affected_components,
            diagnostic: item as unknown as Record<string, unknown>,
            timestamp: data.generatedAt,
            destination: diagnosticDestination(item.label),
          })} type="button">
            <strong>{item.label}</strong>
            <span className={statusClass(item.status)}>{item.status}</span>
          </button>,
        )}</div>
      </section>
    </div>

    <div className="intelligence-observation-grid">
      <section aria-labelledby="coach-summary-heading">
        <Heading id="coach-summary-heading" title="🤖 Ava Coach" />
        {data.avaCoachSummary?.latest_analysis_at
          ? <div className="compact-list">
              <Stat label="Latest analysis" value={new Date(data.avaCoachSummary.latest_analysis_at).toLocaleString()} />
              <Stat label="Pending recommendations" value={data.avaCoachSummary.pending_recommendations} />
              <Stat label="Approved for version" value={data.avaCoachSummary.approved_for_version} />
            </div>
          : <div className="intelligence-empty">
              No coaching analysis has been run yet.<br />
              Run Ava Coach to generate the first coaching report.
            </div>}
        <div className="quick-actions">
          <Link to="/agents/ava-coach">🤖 Open Ava Coach <ArrowRight size={14} /></Link>
        </div>
      </section>
      <ObservationCard title="Opportunities" empty="No observed opportunities are available." items={opportunities} />
      <section aria-labelledby="attention-heading">
        <Heading icon={<AlertTriangle />} id="attention-heading" title="Needs Attention" />
        {!data.problems.length
          ? <Empty>No persisted operational problems were found.</Empty>
          : <div className="attention-list">{data.problems.map((problem) =>
            <button key={`${problem.title}-${problem.detail}`} onClick={() => setSelectedIssue({
              component: title(problem.title),
              status: "Needs Attention",
              severity: problem.severity,
              summary: problem.detail,
              evidence: problem.diagnostic?.evidence ?? problem.detail,
              classification: problem.diagnostic?.classification,
              root_cause: problem.diagnostic?.root_cause,
              confidence: problem.diagnostic?.confidence,
              automatic_resolution: problem.diagnostic?.automatic_resolution,
              resolution_reason: problem.diagnostic?.resolution_reason,
              recommended_action: problem.diagnostic?.recommended_action,
              affected_components: problem.diagnostic?.affected_components,
              diagnostic: problem.diagnostic as unknown as Record<string, unknown>,
              timestamp: data.generatedAt,
              destination: diagnosticDestination(problem.title),
            })} type="button">
              <span className={statusClass(problem.severity)}>{problem.severity}</span>
              <div><strong>{problem.title}</strong><p>{problem.detail}</p></div>
          </button>,
          )}</div>}
      </section>
    </div>

    <div className="intelligence-secondary-grid">
      <section>
        <Heading title="Content Pipeline" />
        <div className="compact-list">{Object.entries(data.contentPipeline).map(([label, value]) => <Stat key={label} label={title(label)} value={value} />)}</div>
      </section>
      <section>
        <Heading title="Commerce Learning" />
        <div className="compact-list">
          <Stat label="Customer profiles" value={data.commerceLearning.profiles} />
          <Stat label="Events today" value={data.commerceLearning.eventsToday} />
          <Stat label="Confidence" value={data.commerceLearning.confidence} />
          <Stat label="Trend" value={data.commerceLearning.trend} />
          {data.commerceLearning.signals?.map((item) => <Stat key={item.label} label={item.label} value={item.value} />)}
        </div>
      </section>
    </div>

    <section aria-label="Quick actions" className="quick-actions">
      <h2>Quick Actions</h2>
      {([
        ["/studio/content", "Content Studio"],
        ["/commerce", "Commerce"],
        ["/developer/recommendations", "Recommendation Diagnostics"],
        ["/developer/test-chat", "Developer Test Chat"],
        ["/business/operations", "Operations"],
        ["/administration/providers", "Provider Connections"],
        ["/library/references", "Reference Library"],
      ] as Array<[string, string]>).map(([path, label]) =>
        <Link key={path} to={path}>{label}<ArrowRight size={15} /></Link>,
      )}
    </section>

    <section aria-labelledby="recent-executions-heading">
      <Heading id="recent-executions-heading" title="Recent Executions" />
      {!recentExecutions.length
        ? <Empty>No Developer Agent executions have been recorded.</Empty>
        : <div className="recent-executions">{recentExecutions.map((execution) =>
          <button key={execution.execution_id} onClick={() => void getExecution(execution.execution_id).then(setReopenedExecution)} type="button">
            <strong>{execution.issue_identifier}</strong>
            <span>{execution.status}</span>
            <small>{execution.execution_id}</small>
            <small>Started: {execution.started_at ? new Date(execution.started_at).toLocaleString() : "Not started"}</small>
            <small>Completed: {execution.completed_at ? new Date(execution.completed_at).toLocaleString() : "In progress"}</small>
            <small>Duration: {execution.started_at && execution.completed_at
              ? `${Math.max(0, new Date(execution.completed_at).getTime() - new Date(execution.started_at).getTime())} ms`
              : "In progress"}</small>
          </button>,
        )}</div>}
    </section>
    <section aria-labelledby="recent-resolutions-heading">
      <Heading id="recent-resolutions-heading" title="Recent Resolutions" />
      {!recentResolutions.length
        ? <Empty>No autonomous resolutions have been recorded.</Empty>
        : <div className="recent-executions">{recentResolutions.map((item) =>
          <button key={item.resolution_id} onClick={() => setReopenedResolution(item)} type="button">
            <strong>{item.issue_identifier}</strong>
            <span>{title(item.outcome.toLowerCase())}</span>
            <small>Decision: {title(item.decision.toLowerCase())}</small>
            <small>{new Date(item.created_at).toLocaleString()}</small>
          </button>,
        )}</div>}
    </section>

    {pendingMode && <CommerceModeConfirmation mode={pendingMode} busy={savingMode} close={() => setPendingMode(null)} confirm={() => void confirmMode()} />}
    {selectedIssue && <DiagnosticDrawer
      issue={selectedIssue}
      resolution={resolution}
      close={() => { setSelectedIssue(null); setResolution(null); }}
      onRefresh={async () => { await refreshDashboard(); }}
      onExecutionComplete={async (execution) => {
        const refreshed = await refreshDashboard();
        if (diagnosticResolved(selectedIssue, refreshed)) {
          setResolution({
            executionId: execution.execution_id,
            resolvedAt: execution.completed_at ?? new Date().toISOString(),
          });
        }
      }}
    />}
    {reopenedExecution && <ExecutionReviewDrawer execution={reopenedExecution} close={() => setReopenedExecution(null)} />}
    {reopenedResolution && <ResolutionHistoryDrawer resolution={reopenedResolution} close={() => setReopenedResolution(null)} />}
  </main>;
}

function Status({ label, value, className = "" }: { label: string; value: string; className?: string }) {
  return <div><span>{label}</span><strong className={`mode-badge ${className}`}>{value}</strong></div>;
}

function CommerceModeConfirmation({ mode, busy, close, confirm }: { mode: CommerceMode; busy: boolean; close: () => void; confirm: () => void }) {
  const content = mode === "RELATIONSHIP"
    ? { title: "Enable Relationship Mode?", detail: <><p>Ava will:</p><ul><li>✓ Chat naturally</li><li>✓ Learn</li><li>✓ Build customer intelligence</li><li>✓ Suppress commercial offers</li></ul><p>No products or purchase links will be presented.</p></> }
    : mode === "LIVE"
      ? { title: "Enable Commerce Live?", detail: <p>Commercial offers will begin appearing whenever the Sales Brain determines an offer is appropriate.</p> }
      : { title: "Disable customer conversations?", detail: <p>Conversation processing will stop until Runtime is restored.</p> };
  return <div className="commerce-mode-dialog" role="dialog" aria-modal="true" aria-labelledby="commerce-mode-dialog-title"><div><header><h2 id="commerce-mode-dialog-title">{content.title}</h2><button aria-label="Close mode confirmation" disabled={busy} onClick={close} type="button"><X /></button></header>{content.detail}<footer><button disabled={busy} onClick={close} type="button">Cancel</button><button disabled={busy} onClick={confirm} type="button">{busy ? "Saving…" : "Confirm"}</button></footer></div></div>;
}

function Heading({ title: text, id, icon }: { title: string; id?: string; icon?: React.ReactNode }) {
  return <div className="section-heading">{icon}<h2 id={id}>{text}</h2></div>;
}
function Empty({ children }: { children: React.ReactNode }) {
  return <div className="intelligence-empty">{children}</div>;
}
function Stat({ label, value }: { label: string; value: string | number }) {
  return <div><span>{title(label)}</span><strong>{displayValue(value)}</strong></div>;
}
function ObservationCard({ title: text, icon, items, empty }: { title: string; icon?: React.ReactNode; items: string[]; empty: string }) {
  return <section><Heading icon={icon} title={text} />{items.length ? <ul className="observation-list">{items.map((item) => <li key={item}>{item}</li>)}</ul> : <Empty>{empty}</Empty>}</section>;
}

function DiagnosticDrawer({
  issue, close, resolution, onExecutionComplete, onRefresh,
}: {
  issue: DiagnosticIssue;
  close: () => void;
  resolution: { executionId: string; resolvedAt: string } | null;
  onExecutionComplete: (execution: DeveloperExecution) => Promise<void>;
  onRefresh: () => Promise<void>;
}) {
  const {
    readiness, recheck, dispatchTask, approveTask, rejectTask, submitTask,
    getExecution, cancel, review, manualApprovalRequired,
    setManualApprovalRequired, refreshExecutions, refreshNotifications,
    resolveIssue, validateResolution, refreshResolutions,
  } = useDeveloperAgentExecutions();
  const [copyState, setCopyState] = useState("");
  const [agentPackage, setAgentPackage] = useState("");
  const [task, setTask] = useState("");
  const [persistedTask, setPersistedTask] = useState<DeveloperAgentTask | null>(null);
  const [execution, setExecution] = useState<DeveloperExecution | null>(null);
  const [workflowError, setWorkflowError] = useState("");
  const [busy, setBusy] = useState(false);
  const [launchStartedAt, setLaunchStartedAt] = useState<number | null>(null);
  const [executionStartedLocally, setExecutionStartedLocally] = useState<number | null>(null);
  const [autonomousResolution, setAutonomousResolution] = useState<AutonomousResolution | null>(null);
  const [autonomousStage, setAutonomousStage] = useState<"IDLE" | "INVESTIGATING" | "IMPLEMENTING" | "VALIDATING" | "REFRESHING" | "DONE">("IDLE");
  const launchGuard = useRef(false);
  useEffect(() => {
    if (!execution || ["COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED"].includes(execution.status)) return;
    const timer = window.setInterval(() => {
      void getExecution(execution.execution_id).then((next) => {
        setExecution(next);
        if (["COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED"].includes(next.status)) {
          void Promise.all([refreshExecutions(), refreshNotifications()]);
          window.dispatchEvent(new CustomEvent("creator-os:diagnostics-invalidated", {
            detail: { executionId: next.execution_id, status: next.status },
          }));
          if (autonomousResolution) {
            setAutonomousStage("VALIDATING");
            void validateResolution(autonomousResolution.resolution_id)
              .then((validated) => {
                setAutonomousResolution(validated);
                setAutonomousStage("REFRESHING");
                return onExecutionComplete(next);
              })
              .then(() => refreshResolutions())
              .then(() => setAutonomousStage("DONE"))
              .catch((reason: unknown) => {
                setWorkflowError(reason instanceof Error ? reason.message : "Fresh validation failed.");
                setAutonomousStage("DONE");
              });
          } else {
            void onExecutionComplete(next);
          }
        }
      }).catch((reason: unknown) => {
        setWorkflowError(reason instanceof Error ? reason.message : "Unable to refresh execution.");
      });
    }, 1500);
    return () => window.clearInterval(timer);
  }, [
    autonomousResolution, execution, getExecution, onExecutionComplete,
    refreshExecutions, refreshNotifications, refreshResolutions,
    validateResolution,
  ]);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(diagnosticMarkdown(issue));
      setCopyState("Diagnostic summary copied.");
    } catch {
      setCopyState("Copy unavailable. Select the generated text manually.");
    }
  };
  return <div className="diagnostic-drawer-backdrop" role="presentation" onMouseDown={(event) => {
    if (event.currentTarget === event.target) close();
  }}>
    <aside className="diagnostic-drawer" role="dialog" aria-modal="true" aria-labelledby="diagnostic-title">
      <header>
        <div><span>Operational diagnostic</span><h2 id="diagnostic-title">{issue.component}</h2></div>
        <button aria-label="Close diagnostic details" onClick={close} type="button"><X /></button>
      </header>
      <dl className="diagnostic-fields">
        <div><dt>Status</dt><dd>{issue.status}</dd></div>
        <div><dt>Severity</dt><dd><span className={statusClass(issue.severity)}>{issue.severity}</span></dd></div>
        <div><dt>Summary</dt><dd>{issue.summary}</dd></div>
        <div><dt>Classification</dt><dd>{title((issue.classification ?? "unknown").toLowerCase())}</dd></div>
        <div><dt>Root Cause</dt><dd>{issue.root_cause ?? "Unknown because the diagnostic source did not provide root-cause evidence."}</dd></div>
        <div><dt>Affected Components</dt><dd>{(issue.affected_components ?? [issue.component]).join(", ")}</dd></div>
        <div><dt>Evidence</dt><dd><pre>{evidenceText(issue.evidence) || "No data collected yet."}</pre></dd></div>
        <div><dt>Confidence</dt><dd>{issue.confidence == null ? "Unknown — diagnostic source did not provide confidence." : `${Math.round(issue.confidence * 100)}%`}</dd></div>
        <div><dt>Automatic Repair</dt><dd>{issue.automatic_resolution == null ? "Unknown" : issue.automatic_resolution ? "YES" : "NO"}</dd></div>
        <div><dt>Reason</dt><dd>{issue.resolution_reason ?? "Unknown because the diagnostic source did not provide a resolution reason."}</dd></div>
        <div><dt>Suggested Remediation</dt><dd>{issue.recommended_action ?? "Collect additional evidence in the relevant diagnostic workspace."}</dd></div>
        <div><dt>Timestamp</dt><dd>{new Date(issue.timestamp).toLocaleString()}</dd></div>
      </dl>
      <div className="diagnostic-actions">
        <button className="resolve-issue-action" disabled={busy || autonomousStage !== "IDLE"} onClick={() => {
          setBusy(true);
          setWorkflowError("");
          setAutonomousStage("INVESTIGATING");
          const investigation = diagnosticMarkdown(issue, true);
          const generatedTask = implementationTask(issue);
          void resolveIssue(issue, investigation, generatedTask)
            .then((result) => {
              setAutonomousResolution(result.resolution);
              if (result.execution) {
                setAgentPackage(investigation);
                setTask(generatedTask);
                setPersistedTask(result.task);
                setExecutionStartedLocally(Date.now());
                setExecution(result.execution);
                setAutonomousStage("IMPLEMENTING");
              } else {
                setAutonomousStage("DONE");
                if (result.resolution.decision === "ALREADY_RESOLVED") {
                  void onRefresh().then(close);
                }
              }
              return refreshResolutions();
            })
            .catch((reason: unknown) => {
              setWorkflowError(reason instanceof Error ? reason.message : "Issue resolution could not start.");
              setAutonomousStage("DONE");
            })
            .finally(() => setBusy(false));
        }} type="button">✨ Resolve Issue</button>
        {issue.destination && <Link to={issue.destination.path}>{issue.destination.label}<ArrowRight size={14} /></Link>}
        <Link to="/diagnostics">View Logs<ArrowRight size={14} /></Link>
        <button onClick={() => void copy()} type="button"><Clipboard size={14} />Copy Diagnostic Summary</button>
      </div>
      <details className="diagnostic-advanced">
        <summary>Advanced</summary>
        <button onClick={() => {
          setAgentPackage(diagnosticMarkdown(issue, true));
          setCopyState("Investigation package generated locally. No Creator Agent request was sent.");
        }} type="button"><Bot size={14} />Investigate with Creator Agent</button>
      </details>
      {copyState && <p className="diagnostic-copy-status" role="status">{copyState}</p>}
      {resolution && <section className="diagnostic-resolved" role="status">
        <strong>Resolved</strong>
        <span>{new Date(resolution.resolvedAt).toLocaleString()}</span>
        <span>Execution ID: {resolution.executionId}</span>
      </section>}
      {autonomousStage !== "IDLE" && <section className="autonomous-resolution" role="status">
        <strong>{autonomousStage === "DONE"
          ? autonomousResolution?.outcome === "RESOLVED" ? "✅ Issue Resolved"
            : autonomousResolution?.outcome === "PARTIALLY_RESOLVED" ? "⚠ Partially Resolved"
              : autonomousResolution?.outcome === "USER_ACTION_REQUIRED" ? "⚠ This issue cannot be repaired automatically"
                : autonomousResolution?.outcome === "ALREADY_RESOLVED" ? "This issue has already been resolved"
                  : "❌ Could Not Resolve"
          : title(autonomousStage)}</strong>
        {autonomousStage !== "DONE" && <span className="autonomous-resolution__spinner" aria-hidden="true" />}
        <p>{autonomousResolution?.decision_reason ?? "Creator Agent is classifying the current diagnostic evidence."}</p>
        {autonomousResolution?.required_action && <p>{autonomousResolution.required_action}</p>}
        {autonomousResolution?.developer_agent_execution_id
          && <p>Execution ID: {autonomousResolution.developer_agent_execution_id}</p>}
        {autonomousResolution?.validation_status === "PASSED"
          && <p>Verification: Healthy. Validation completed successfully.</p>}
        {autonomousResolution?.destination_path && autonomousResolution.decision !== "AUTO_FIX"
          && <Link to={autonomousResolution.destination_path}>Open relevant workspace<ArrowRight size={14} /></Link>}
      </section>}
      {agentPackage && <section className="agent-workflow">
        <div className="agent-workflow__summary">
          <h3>Creator Agent investigation</h3>
          <Stat label="Issue" value={issue.component} />
          <Stat label="Root Cause" value="Not established by current diagnostics." />
          <Stat label="Impact" value={issue.summary} />
          <Stat label="Confidence" value="No confidence score available." />
          <Stat label="Estimated effort" value="Not estimated." />
          <Stat label="Recommended Fix" value="Repository investigation required before implementation." />
          <Stat label="Current Status" value={execution?.status ?? persistedTask?.status ?? (task ? "Task ready for review" : "Investigation complete")} />
        </div>
        <details><summary>View Investigation Package</summary><textarea aria-label="Creator Agent investigation package" readOnly rows={16} value={agentPackage} /></details>
        {!task && <button className="agent-primary-action" onClick={() => setTask(implementationTask(issue))} type="button">Generate Implementation Task</button>}
        {task && !execution && launchStartedAt === null && <section className="developer-task">
          <h3>Developer Agent task</h3><p>Review the generated task before sending it to the local Developer Agent.</p>
          <textarea aria-label="Developer Agent implementation task" disabled={Boolean(persistedTask)} onChange={(event) => setTask(event.target.value)} rows={18} value={task} />
          <details className="developer-agent-settings">
            <summary>Developer Agent Settings</summary>
            <label>
              <input
                checked={manualApprovalRequired}
                onChange={(event) => setManualApprovalRequired(event.target.checked)}
                type="checkbox"
              />
              Require manual approval before execution
            </label>
            <p>Disabled by default for single-operator installations.</p>
          </details>
          {!persistedTask && <DeveloperAgentReadiness readiness={readiness} recheck={() => void recheck()} />}
          {!persistedTask && <button className="agent-primary-action" disabled={busy} onClick={() => {
            if (readiness?.overallReadiness !== "READY") {
              setWorkflowError(
                `Developer Agent cannot start: ${readiness?.reason ?? "readiness has not completed. Recheck Developer Agent and try again."}`,
              );
              return;
            }
            if (launchGuard.current) return;
            launchGuard.current = true;
            const launchedAt = Date.now();
            setLaunchStartedAt(launchedAt);
            setExecutionStartedLocally(launchedAt);
            setBusy(true); setWorkflowError("");
            void dispatchTask(issue.component, agentPackage, task)
              .then((result) => {
                setPersistedTask(result.task);
                if (result.execution) {
                  setExecution(result.execution);
                  setLaunchStartedAt(null);
                } else {
                  setLaunchStartedAt(null);
                }
              })
              .catch((reason: unknown) => {
                setLaunchStartedAt(null);
                setExecutionStartedLocally(null);
                setWorkflowError(
                  `Developer Agent failed to start. ${reason instanceof Error ? reason.message : "Unable to send task."}`,
                );
              })
              .finally(() => {
                launchGuard.current = false;
                setBusy(false);
              });
          }} type="button">🚀 Send to Developer Agent</button>}
          {persistedTask?.status === "AWAITING_APPROVAL" && <div className="task-approval">
            <button disabled={busy} onClick={() => {
              setBusy(true);
              void approveTask(persistedTask.task_id).then(setPersistedTask)
                .catch((reason: unknown) => setWorkflowError(reason instanceof Error ? reason.message : "Approval failed."))
                .finally(() => setBusy(false));
            }} type="button">Approve Task</button>
            <button disabled={busy} onClick={() => void rejectTask(persistedTask.task_id).then(setPersistedTask)} type="button">Reject Task</button>
          </div>}
          {persistedTask?.status === "APPROVED" && !execution && <>
            <DeveloperAgentReadiness readiness={readiness} recheck={() => void recheck()} />
            {readiness?.overallReadiness !== "READY" && <button onClick={() => void navigator.clipboard.writeText(task)} type="button"><Clipboard size={14} />Copy Implementation Task</button>}
            <button className="agent-primary-action" disabled={busy || readiness?.overallReadiness !== "READY"} onClick={() => {
              if (launchGuard.current) return;
              launchGuard.current = true;
              const launchedAt = Date.now();
              setLaunchStartedAt(launchedAt);
              setExecutionStartedLocally(launchedAt);
              setBusy(true); setWorkflowError("");
              void submitTask(persistedTask.task_id)
                .then((accepted) => {
                  setExecution(accepted);
                  setLaunchStartedAt(null);
                })
                .catch((reason: unknown) => {
                  setLaunchStartedAt(null);
                  setExecutionStartedLocally(null);
                  setWorkflowError(
                    `Developer Agent failed to start. ${reason instanceof Error ? reason.message : "Submission failed."}`,
                  );
                })
                .finally(() => {
                  launchGuard.current = false;
                  setBusy(false);
                });
            }} type="button">🚀 Send Approved Task</button>
          </>}
          {workflowError && <p className="workflow-error" role="alert">{workflowError}</p>}
        </section>}
        {launchStartedAt !== null && <LaunchingExecution startedAt={launchStartedAt} />}
        {execution && <ExecutionStatus execution={execution} launchedAt={executionStartedLocally} cancel={() => void cancel(execution.execution_id)} retry={() => {
          setBusy(true);
          void submitTask(execution.task_id).then(setExecution).catch((reason: unknown) => setWorkflowError(reason instanceof Error ? reason.message : "Retry failed.")).finally(() => setBusy(false));
        }} review={(state) => {
          void review(execution.execution_id, state)
            .then(() => getExecution(execution.execution_id))
            .then(setExecution);
        }} />}
      </section>}
      {!agentPackage && <footer aria-label="Future diagnostic actions"><span>Future actions</span><button disabled type="button">Create Fix Plan</button><button disabled type="button">Implement Fix</button><button disabled type="button">Run Tests</button><button disabled type="button">Open Pull Request</button></footer>}
    </aside>
  </div>;
}

function ResolutionHistoryDrawer({
  resolution, close,
}: { resolution: AutonomousResolution; close: () => void }) {
  return <div className="diagnostic-drawer-backdrop" role="presentation" onMouseDown={(event) => {
    if (event.currentTarget === event.target) close();
  }}>
    <aside className="diagnostic-drawer" role="dialog" aria-modal="true" aria-labelledby="resolution-history-title">
      <header>
        <div><span>Resolution history</span><h2 id="resolution-history-title">{resolution.issue_identifier}</h2></div>
        <button aria-label="Close resolution history" onClick={close} type="button"><X /></button>
      </header>
      <dl className="diagnostic-fields">
        <div><dt>Decision</dt><dd>{title(resolution.decision.toLowerCase())}</dd></div>
        <div><dt>Reason</dt><dd>{resolution.decision_reason}</dd></div>
        <div><dt>Outcome</dt><dd>{title(resolution.outcome.toLowerCase())}</dd></div>
        <div><dt>Validation</dt><dd>{title(resolution.validation_status.toLowerCase())}</dd></div>
        <div><dt>Required Action</dt><dd>{resolution.required_action ?? "None"}</dd></div>
        <div><dt>Execution ID</dt><dd>{resolution.developer_agent_execution_id ?? "No execution created"}</dd></div>
        <div><dt>Created</dt><dd>{new Date(resolution.created_at).toLocaleString()}</dd></div>
        <div><dt>Resolved</dt><dd>{resolution.resolved_at ? new Date(resolution.resolved_at).toLocaleString() : "Not resolved"}</dd></div>
      </dl>
      <details><summary>Validation evidence</summary><pre>{JSON.stringify(resolution.validation_evidence, null, 2)}</pre></details>
    </aside>
  </div>;
}

function useElapsed(startedAt: number, completedAt?: number | null) {
  const [now, setNow] = useState(() => completedAt ?? Date.now());
  useEffect(() => {
    if (completedAt) {
      setNow(completedAt);
      return;
    }
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [completedAt]);
  const seconds = Math.max(0, Math.floor((now - startedAt) / 1000));
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

function LaunchingExecution({ startedAt }: { startedAt: number }) {
  const elapsed = useElapsed(startedAt);
  return <section className="execution-status execution-status--launching" aria-label="Developer Agent launching" role="status">
    <header><div><span>🤖 Developer Agent</span><h3>🟢 Launching...</h3></div><span aria-label="Launching Developer Agent" className="developer-agent-spinner" /></header>
    <p>Connecting to Codex...</p>
    <div className="execution-elapsed"><span>Elapsed</span><strong>{elapsed}</strong></div>
    <button disabled type="button">⏳ Launching Developer Agent...</button>
  </section>;
}

function ExecutionStatus({ execution, launchedAt, cancel, retry, review }: { execution: DeveloperExecution; launchedAt?: number | null; cancel: () => void; retry: () => void; review: (state: "ACKNOWLEDGED" | "REJECTED" | "ARCHIVED") => void }) {
  const terminal = ["COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED"].includes(execution.status);
  const latestEvent = execution.events?.at(-1);
  const startedAt = execution.started_at
    ? new Date(execution.started_at).getTime()
    : launchedAt ?? Date.now();
  const completedAt = execution.completed_at
    ? new Date(execution.completed_at).getTime()
    : null;
  const elapsed = useElapsed(startedAt, terminal ? completedAt ?? Date.now() : null);
  const reportRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (terminal && execution.final_report) {
      reportRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [execution.final_report, terminal]);
  return <section className="execution-status" aria-label="Developer Agent execution">
    <header><div><span>🤖 Developer Agent</span><h3>{execution.status === "COMPLETED" ? "✅ Completed" : execution.status === "FAILED" ? "❌ Failed" : title(execution.status.toLowerCase())}</h3></div>{!terminal && <span aria-label="Developer Agent running" className="developer-agent-spinner" />}</header>
    <p>{latestEvent?.message ?? "Waiting for the first authoritative execution event."}</p>
    <dl className="execution-status__facts">
      <div><dt>Status</dt><dd>{title(execution.status.toLowerCase())}</dd></div>
      <div><dt>Latest Event</dt><dd>{latestEvent ? title(latestEvent.event_type.toLowerCase()) : "Queued"}</dd></div>
      <div><dt>Repository</dt><dd>{execution.repository_path}</dd></div>
      <div><dt>Branch</dt><dd>{execution.expected_branch}</dd></div>
      <div><dt>Execution ID</dt><dd>{execution.execution_id}</dd></div>
      <div><dt>Codex Session ID</dt><dd>{execution.codex_session_id ?? "Connecting"}</dd></div>
    </dl>
    {execution.started_at && <p>Started {new Date(execution.started_at).toLocaleString()}</p>}
    <div className="execution-elapsed"><span>{terminal ? "Completed in" : "Elapsed"}</span><strong>{elapsed}</strong></div>
    <details open><summary>Recent Events</summary><ol>{execution.events?.slice(-12).reverse().map((event) => <li key={`recent-${event.event_id}`}><strong>🟢 {title(event.event_type.toLowerCase())}</strong> — {event.message}</li>)}</ol></details>
    <details><summary>View execution log</summary><ol>{execution.events?.map((event) => <li key={event.event_id}><strong>{title(event.event_type.toLowerCase())}</strong> — {event.message}</li>)}</ol></details>
    {!terminal && <button disabled type="button">⏳ Developer Agent Running...</button>}
    {!terminal && <button onClick={cancel} type="button">Cancel</button>}
    {execution.status === "FAILED" && <button onClick={retry} type="button">Retry Execution</button>}
    {execution.failure_reason && <p role="alert">{execution.failure_reason}</p>}
    {execution.final_report?.telemetryDegraded && <p role="status">Telemetry degraded; the repository operation still completed.</p>}
    {execution.final_report && <section ref={reportRef}><ExecutionReport execution={execution} review={review} /></section>}
  </section>;
}

function ExecutionReport({ execution, review }: { execution: DeveloperExecution; review: (state: "ACKNOWLEDGED" | "REJECTED" | "ARCHIVED") => void }) {
  const report = execution.final_report;
  if (!report) return null;
  return <section className="execution-report">
    <h3>Execution Report</h3>
    <Stat label="Summary" value={report.summary} />
    <Stat label="Root Cause" value={report.rootCause} />
    <Stat label="Files Modified" value={report.filesModified.length ? report.filesModified.join(", ") : "None"} />
    <Stat label="Tests" value={typeof report.tests === "string" ? report.tests : JSON.stringify(report.tests)} />
    <Stat label="Validation" value={JSON.stringify(report.validation)} />
    <Stat label="Warnings" value={report.remainingWarnings.length ? report.remainingWarnings.join(" ") : "None"} />
    <Stat label="Commit Created" value={report.commitCreated ? "Yes" : "No"} />
    <Stat label="Implementation Duration" value={`${report.executionDurationMs} ms`} />
    <div className="execution-report__links"><details><summary>Open Diff</summary><pre>{report.gitDiff || "No diff reported."}</pre></details><button disabled={!report.commitHash} type="button">Open Commit</button></div>
    <div className="execution-report__approval" aria-label="Result review">
      <button onClick={() => review("ACKNOWLEDGED")} type="button">Acknowledge</button>
      <button onClick={() => review("ARCHIVED")} type="button">Archive Report</button>
      <span>Review: {title(execution.review_status)}</span>
    </div>
  </section>;
}

function ExecutionReviewDrawer({ execution, close }: { execution: DeveloperExecution; close: () => void }) {
  const { review, getExecution, submitTask } = useDeveloperAgentExecutions();
  const [current, setCurrent] = useState(execution);
  return <div className="diagnostic-drawer-backdrop" role="presentation"><aside className="diagnostic-drawer" role="dialog" aria-modal="true" aria-labelledby="execution-review-title"><header><div><span>Developer Agent</span><h2 id="execution-review-title">{current.issue_identifier}</h2></div><button aria-label="Close execution report" onClick={close} type="button"><X /></button></header><ExecutionStatus execution={current} cancel={() => undefined} retry={() => { void submitTask(current.task_id).then(setCurrent); }} review={(state) => {
    void review(current.execution_id, state)
      .then(() => getExecution(current.execution_id))
      .then(setCurrent);
  }} /></aside></div>;
}

function DeveloperAgentReadiness({ readiness, recheck }: { readiness: ReturnType<typeof useDeveloperAgentExecutions>["readiness"]; recheck: () => void }) {
  if (!readiness) return <div className="developer-readiness">Checking Developer Agent…</div>;
  return <section className={`developer-readiness is-${readiness.overallReadiness.toLowerCase()}`}>
    <strong>Developer Agent {readiness.overallReadiness}</strong>
    <p>{readiness.reason}</p>
    <ul>
      <li>Codex CLI: {readiness.cliDetected ? "Detected" : "Unavailable"}</li>
      <li>Codex SDK: {readiness.sdkDetected ? "Detected" : "Unavailable"}</li>
      <li>Authentication: {readiness.authenticationAvailable ? "Available" : "Unavailable"}</li>
      <li>App-server: {readiness.appServerReachable ? "Reachable" : "Unavailable"}</li>
      <li>Repository: {readiness.repositoryAccessible ? "Accessible" : "Unavailable"}</li>
      <li>Expected branch: {readiness.expectedBranchActive ? "Active" : "Not active"}</li>
      <li>Execution worker: {readiness.executionWorkerAvailable ? "Available" : "Unavailable"}</li>
      <li>Persistence: {readiness.persistenceAvailable ? "Available" : "Migration required"}</li>
    </ul>
    {readiness.overallReadiness !== "READY" && <button onClick={recheck} type="button">Recheck Developer Agent</button>}
  </section>;
}
