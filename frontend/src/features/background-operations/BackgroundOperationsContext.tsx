import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
  type ReactNode,
} from "react";

import { environment } from "../../infrastructure/config/environment";

export type BackgroundOperation = {
  operationId: string;
  operationType: string;
  originatingWorkspace: string;
  subjectType: string;
  subjectId: string;
  status: "QUEUED" | "RUNNING" | "WAITING_EXTERNAL" | "SUCCEEDED" | "PARTIAL" | "FAILED" | "CANCEL_REQUESTED" | "CANCELLED";
  progressCurrent: number;
  progressTotal: number;
  progressPercent: number;
  currentStage: string | null;
  stageMessage: string | null;
  createdAt: string;
  startedAt: string | null;
  completedAt: string | null;
  resultLocation: string | null;
  resultReference: string | null;
  errorCode: string | null;
  errorMessage: string | null;
  cancellationSupported: boolean;
  metadata: Record<string, unknown>;
};

type ContextValue = {
  active: BackgroundOperation[];
  recent: BackgroundOperation[];
  activeCount: number;
  initialized: boolean;
  refresh: () => Promise<void>;
  cancel: (operationId: string) => Promise<void>;
  retry: (operationId: string) => Promise<void>;
  byWorkspace: (workspace: string) => BackgroundOperation[];
  bySubject: (type: string, id: string) => BackgroundOperation[];
};

const emptyContext: ContextValue = {
  active: [], recent: [], activeCount: 0, initialized: false,
  refresh: async () => undefined, cancel: async () => undefined, retry: async () => undefined,
  byWorkspace: () => [], bySubject: () => [],
};
const BackgroundOperationsContext = createContext<ContextValue>(emptyContext);

async function load(status: "active" | "recent"): Promise<BackgroundOperation[]> {
  const response = await fetch(`${environment.apiBaseUrl}/background-operations?status=${status}`);
  const payload = await response.json() as { success: boolean; operations?: BackgroundOperation[]; error?: string };
  if (!response.ok || !payload.success) throw new Error(payload.error || "Background Operations unavailable");
  return payload.operations ?? [];
}

export function BackgroundOperationsProvider({ children, pollMilliseconds = 1500 }: {
  children: ReactNode;
  pollMilliseconds?: number;
}) {
  const [active, setActive] = useState<BackgroundOperation[]>([]);
  const [recent, setRecent] = useState<BackgroundOperation[]>([]);
  const [initialized, setInitialized] = useState(false);
  const mounted = useRef(true);
  const refreshing = useRef(false);

  const refresh = useCallback(async () => {
    if (refreshing.current) return;
    refreshing.current = true;
    try {
      const [nextActive, nextRecent] = await Promise.all([load("active"), load("recent")]);
      if (mounted.current) { setActive(nextActive); setRecent(nextRecent); setInitialized(true); }
    } catch {
      // Preserve the last known operation state during transient API unavailability.
    } finally {
      refreshing.current = false;
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    void refresh();
    const timer = window.setInterval(() => void refresh(), pollMilliseconds);
    return () => { mounted.current = false; window.clearInterval(timer); };
  }, [pollMilliseconds, refresh]);

  const mutate = useCallback(async (operationId: string, action: "cancel" | "retry") => {
    const response = await fetch(
      `${environment.apiBaseUrl}/background-operations/${operationId}/${action}`, { method: "POST" },
    );
    if (!response.ok) {
      const payload = await response.json() as { error?: string };
      throw new Error(payload.error || `Unable to ${action} operation`);
    }
    await refresh();
  }, [refresh]);

  const value = useMemo<ContextValue>(() => ({
    active, recent, activeCount: active.length, initialized, refresh,
    cancel: (id) => mutate(id, "cancel"), retry: (id) => mutate(id, "retry"),
    byWorkspace: (workspace) => [...active, ...recent].filter(
      (operation) => operation.originatingWorkspace === workspace),
    bySubject: (type, id) => [...active, ...recent].filter(
      (operation) => operation.subjectType === type && operation.subjectId === id),
  }), [active, initialized, mutate, recent, refresh]);

  return <BackgroundOperationsContext.Provider value={value}>{children}</BackgroundOperationsContext.Provider>;
}

// The provider and its colocated hook intentionally form one runtime boundary.
// eslint-disable-next-line react-refresh/only-export-components
export function useBackgroundOperations() {
  return useContext(BackgroundOperationsContext);
}
