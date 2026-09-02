import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { developerFetch } from "../../infrastructure/api/developerFetch";

export type DeveloperExecutionState =
  | "QUEUED" | "STARTING" | "RUNNING" | "WAITING_FOR_INPUT" | "TESTING"
  | "COMPLETED" | "FAILED" | "CANCELLED" | "INTERRUPTED";

export type DeveloperAgentTask = {
  task_id: string;
  issue_identifier: string;
  investigation_package: string;
  implementation_task: string;
  repository_path: string;
  expected_branch: string;
  status: "AWAITING_APPROVAL" | "APPROVED" | "REJECTED";
  approved_at: string | null;
};

export type DeveloperExecutionReport = {
  status: string;
  summary: string;
  rootCause: string;
  actionsPerformed: unknown[];
  filesModified: string[];
  databaseMigrationsApplied: string;
  commandsExecuted: unknown[];
  tests: unknown[] | string;
  validation: Record<string, unknown>;
  remainingWarnings: string[];
  telemetryDegraded?: boolean;
  commitCreated: boolean;
  commitHash: string | null;
  executionDurationMs: number;
  codexSessionId: string;
  gitStatusShort: string;
  gitDiffStat: string;
  gitDiff: string;
};

export type DeveloperExecution = {
  execution_id: string;
  task_id: string;
  issue_identifier: string;
  implementation_task: string;
  repository_path: string;
  expected_branch: string;
  status: DeveloperExecutionState;
  codex_session_id: string | null;
  started_at: string | null;
  completed_at: string | null;
  failure_reason: string | null;
  cancellation_reason: string | null;
  final_report: DeveloperExecutionReport | null;
  review_status: "PENDING" | "ACKNOWLEDGED" | "REJECTED" | "ARCHIVED";
  events: Array<{ event_id: number; event_type: string; message: string; created_at: string }>;
};

export type DeveloperNotification = {
  notification_id: string;
  task_id: string | null;
  execution_id: string | null;
  title: string;
  detail: string;
  created_at: string;
  is_read: boolean;
};

export type DeveloperAgentReadiness = {
  cliDetected: boolean;
  sdkDetected: boolean;
  authenticationAvailable: boolean;
  appServerReachable: boolean;
  repositoryAccessible: boolean;
  expectedBranchActive: boolean;
  executionWorkerAvailable: boolean;
  persistenceAvailable: boolean;
  overallReadiness: "READY" | "DEGRADED" | "UNAVAILABLE";
  reason: string;
};

export type AutonomousResolution = {
  resolution_id: string;
  issue_identifier: string;
  issue_snapshot: Record<string, unknown>;
  decision: "AUTO_FIX" | "USER_ACTION_REQUIRED" | "CONFIGURATION_REQUIRED" | "NOT_FIXABLE" | "ALREADY_RESOLVED";
  decision_reason: string;
  required_action: string | null;
  destination_path: string | null;
  developer_agent_task_id: string | null;
  developer_agent_execution_id: string | null;
  validation_status: "PENDING" | "RUNNING" | "PASSED" | "FAILED" | "NOT_REQUIRED";
  validation_evidence: Record<string, unknown>;
  outcome: "IN_PROGRESS" | "RESOLVED" | "PARTIALLY_RESOLVED" | "COULD_NOT_RESOLVE" | "USER_ACTION_REQUIRED" | "ALREADY_RESOLVED";
  resolved_at: string | null;
  created_at: string;
};

type ExecutionContextValue = {
  readiness: DeveloperAgentReadiness | null;
  notifications: DeveloperNotification[];
  recentExecutions: DeveloperExecution[];
  recentResolutions: AutonomousResolution[];
  manualApprovalRequired: boolean;
  setManualApprovalRequired: (value: boolean) => void;
  recheck: () => Promise<void>;
  refreshNotifications: () => Promise<void>;
  refreshExecutions: () => Promise<void>;
  refreshResolutions: () => Promise<void>;
  resolveIssue: (
    issue: Record<string, unknown>, investigation: string, task: string,
  ) => Promise<{ resolution: AutonomousResolution; task: DeveloperAgentTask | null; execution: DeveloperExecution | null }>;
  validateResolution: (id: string) => Promise<AutonomousResolution>;
  createTask: (issue: string, investigation: string, task: string) => Promise<DeveloperAgentTask>;
  dispatchTask: (
    issue: string, investigation: string, task: string,
  ) => Promise<{ task: DeveloperAgentTask; execution: DeveloperExecution | null }>;
  approveTask: (id: string) => Promise<DeveloperAgentTask>;
  rejectTask: (id: string) => Promise<DeveloperAgentTask>;
  submitTask: (id: string) => Promise<DeveloperExecution>;
  getExecution: (id: string) => Promise<DeveloperExecution>;
  cancel: (id: string) => Promise<void>;
  review: (id: string, state: "ACKNOWLEDGED" | "REJECTED" | "ARCHIVED") => Promise<void>;
  markRead: (id: string) => Promise<void>;
};

const Context = createContext<ExecutionContextValue | null>(null);

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await developerFetch(`/api/v1/developer-agent${path}`, {
    cache: "no-store",
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  const body = await response.json() as T & { detail?: string };
  if (!response.ok) throw new Error(body.detail || "Developer Agent request failed.");
  return body;
}

export function DeveloperAgentExecutionProvider({ children }: { children: React.ReactNode }) {
  const [readiness, setReadiness] = useState<DeveloperAgentReadiness | null>(null);
  const [notifications, setNotifications] = useState<DeveloperNotification[]>([]);
  const [recentExecutions, setRecentExecutions] = useState<DeveloperExecution[]>([]);
  const [recentResolutions, setRecentResolutions] = useState<AutonomousResolution[]>([]);
  const [manualApprovalRequired, setManualApprovalState] = useState(
    () => window.localStorage.getItem("developerAgent.requireManualApproval") === "true",
  );

  const recheck = useCallback(async () => {
    try {
      setReadiness(await request<DeveloperAgentReadiness>("/health"));
    } catch (reason) {
      setReadiness({
        cliDetected: false, sdkDetected: false, authenticationAvailable: false,
        appServerReachable: false, repositoryAccessible: false,
        expectedBranchActive: false, executionWorkerAvailable: false,
        persistenceAvailable: false,
        overallReadiness: "UNAVAILABLE",
        reason: reason instanceof Error ? reason.message : "Developer Agent backend unavailable.",
      });
    }
  }, []);

  const refreshNotifications = useCallback(async () => {
    try {
      const body = await request<{ items: DeveloperNotification[] }>("/notifications");
      setNotifications(Array.isArray(body.items) ? body.items : []);
    } catch {
      setNotifications([]);
    }
  }, []);

  const refreshExecutions = useCallback(async () => {
    try {
      const body = await request<{ items: DeveloperExecution[] }>("/history?limit=20");
      setRecentExecutions(Array.isArray(body.items) ? body.items : []);
    } catch {
      setRecentExecutions([]);
    }
  }, []);
  const refreshResolutions = useCallback(async () => {
    try {
      const body = await request<{ items: AutonomousResolution[] }>("/resolutions?limit=20");
      setRecentResolutions(Array.isArray(body.items) ? body.items : []);
    } catch {
      setRecentResolutions([]);
    }
  }, []);

  const setManualApprovalRequired = useCallback((value: boolean) => {
    window.localStorage.setItem(
      "developerAgent.requireManualApproval", String(value),
    );
    setManualApprovalState(value);
  }, []);

  useEffect(() => {
    void recheck();
    void refreshNotifications();
    void refreshExecutions();
    void refreshResolutions();
    const notificationsTimer = window.setInterval(() => {
      if (document.visibilityState === "visible") void refreshNotifications();
    }, 15_000);
    const historyTimer = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        void refreshExecutions();
        void refreshResolutions();
      }
    }, 60_000);
    const refreshVisible = () => {
      if (document.visibilityState !== "visible") return;
      void refreshNotifications();
      void refreshExecutions();
      void refreshResolutions();
    };
    document.addEventListener("visibilitychange", refreshVisible);
    return () => {
      window.clearInterval(notificationsTimer);
      window.clearInterval(historyTimer);
      document.removeEventListener("visibilitychange", refreshVisible);
    };
  }, [recheck, refreshExecutions, refreshNotifications, refreshResolutions]);

  const value = useMemo<ExecutionContextValue>(() => ({
    readiness,
    notifications,
    recentExecutions,
    recentResolutions,
    manualApprovalRequired,
    setManualApprovalRequired,
    recheck,
    refreshNotifications,
    refreshExecutions,
    refreshResolutions,
    resolveIssue: (issue, investigation, task) => request("/resolutions", {
      method: "POST",
      body: JSON.stringify({
        issue, investigation_package: investigation, implementation_task: task,
      }),
    }),
    validateResolution: (id) => request(`/resolutions/${id}/validate`, {
      method: "POST",
    }),
    createTask: (issue, investigation, task) => request("/tasks", {
      method: "POST",
      body: JSON.stringify({
        issue_identifier: issue,
        investigation_package: investigation,
        implementation_task: task,
      }),
    }),
    approveTask: (id) => request(`/tasks/${id}/approve`, { method: "POST" }),
    rejectTask: (id) => request(`/tasks/${id}/reject`, { method: "POST" }),
    dispatchTask: async (issue, investigation, task) => {
      const result = await request<{
        task: DeveloperAgentTask; execution: DeveloperExecution | null;
      }>("/tasks/dispatch", {
        method: "POST",
        body: JSON.stringify({
          issue_identifier: issue,
          investigation_package: investigation,
          implementation_task: task,
          require_manual_approval: manualApprovalRequired,
        }),
      });
      await Promise.all([refreshExecutions(), refreshNotifications()]);
      return result;
    },
    submitTask: (id) => request(`/tasks/${id}/executions`, { method: "POST" }),
    getExecution: (id) => request(`/executions/${id}`),
    cancel: async (id) => { await request(`/executions/${id}/cancel`, { method: "POST" }); },
    review: async (id, state) => { await request(`/executions/${id}/reviews/${state}`, { method: "POST" }); },
    markRead: async (id) => {
      await request(`/notifications/${id}/read`, { method: "POST" });
      await refreshNotifications();
    },
  }), [
    manualApprovalRequired, notifications, readiness, recentExecutions,
    recentResolutions, recheck, refreshExecutions, refreshNotifications,
    refreshResolutions,
    setManualApprovalRequired,
  ]);

  return <Context.Provider value={value}>{children}</Context.Provider>;
}

// The provider and hook intentionally share this context module.
// eslint-disable-next-line react-refresh/only-export-components
export function useDeveloperAgentExecutions() {
  const value = useContext(Context);
  if (!value) throw new Error("DeveloperAgentExecutionProvider is required.");
  return value;
}
