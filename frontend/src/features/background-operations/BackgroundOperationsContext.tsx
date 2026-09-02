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

const DETAIL_CACHE_LIMIT = 100;
const detailCache = new Map<string, { etag: string; operation: BackgroundOperation }>();

function operationEqual(left: BackgroundOperation, right: BackgroundOperation) {
  return left.operationId === right.operationId
    && left.operationType === right.operationType
    && left.originatingWorkspace === right.originatingWorkspace
    && left.subjectType === right.subjectType
    && left.subjectId === right.subjectId
    && left.status === right.status
    && left.progressCurrent === right.progressCurrent
    && left.progressTotal === right.progressTotal
    && left.progressPercent === right.progressPercent
    && left.currentStage === right.currentStage
    && left.stageMessage === right.stageMessage
    && left.createdAt === right.createdAt
    && left.startedAt === right.startedAt
    && left.completedAt === right.completedAt
    && left.resultLocation === right.resultLocation
    && left.resultReference === right.resultReference
    && left.errorCode === right.errorCode
    && left.errorMessage === right.errorMessage
    && left.cancellationSupported === right.cancellationSupported
    && metadataEqual(left.metadata, right.metadata);
}

function metadataEqual(left: Record<string, unknown>, right: Record<string, unknown>) {
  const leftKeys = Object.keys(left);
  const rightKeys = Object.keys(right);
  if (leftKeys.length !== rightKeys.length) return false;
  return leftKeys.every((key) => {
    if (!(key in right)) return false;
    const a = left[key]; const b = right[key];
    if (Object.is(a, b)) return true;
    if (Array.isArray(a) && Array.isArray(b)) {
      return a.length === b.length && a.every((value, index) => Object.is(value, b[index]));
    }
    return false;
  });
}

function reconcileOperations(current: BackgroundOperation[], incoming: BackgroundOperation[]) {
  if (current.length !== incoming.length) return incoming;
  let changed = false;
  const reconciled = incoming.map((next, index) => {
    const previous = current[index];
    if (previous && operationEqual(previous, next)) return previous;
    changed = true;
    return next;
  });
  return changed ? reconciled : current;
}

function cacheDetail(operationId: string, value: { etag: string; operation: BackgroundOperation }) {
  detailCache.delete(operationId);
  detailCache.set(operationId, value);
  while (detailCache.size > DETAIL_CACHE_LIMIT) {
    const oldest = detailCache.keys().next().value as string | undefined;
    if (!oldest) break;
    detailCache.delete(oldest);
  }
}

async function loadDetail(operationId: string): Promise<BackgroundOperation | null> {
  const cached = detailCache.get(operationId);
  if (cached) { detailCache.delete(operationId); detailCache.set(operationId, cached); }
  const response = await fetch(`${environment.apiBaseUrl}/background-operations/${operationId}`, {
    headers: cached?.etag ? { "If-None-Match": cached.etag } : undefined,
  });
  if (response.status === 304) return cached?.operation ?? null;
  const payload = await response.json() as { success: boolean; operation?: BackgroundOperation };
  const operation = response.ok && payload.success ? payload.operation ?? null : null;
  const etag = response.headers.get("etag");
  if (operation && etag) cacheDetail(operationId, { etag, operation });
  return operation;
}

export function BackgroundOperationsProvider({ children, pollMilliseconds }: {
  children: ReactNode;
  pollMilliseconds?: number;
}) {
  const [active, setActive] = useState<BackgroundOperation[]>([]);
  const [recent, setRecent] = useState<BackgroundOperation[]>([]);
  const [initialized, setInitialized] = useState(false);
  const mounted = useRef(true);
  const refreshing = useRef(false);
  const activeRef = useRef<BackgroundOperation[]>([]);
  const recentLoadedAt = useRef(0);

  useEffect(() => { activeRef.current = active; }, [active]);

  const refresh = useCallback(async () => {
    if (refreshing.current) return;
    refreshing.current = true;
    try {
      const activeSummaries = await load("active");
      const activeIds = new Set(activeSummaries.map((item) => item.operationId));
      const transitionedTerminal = activeRef.current.some((item) => !activeIds.has(item.operationId));
      const refreshRecent = recentLoadedAt.current === 0 || transitionedTerminal
        || Date.now() - recentLoadedAt.current >= (document.visibilityState === "hidden" ? 120_000 : 60_000);
      const recentSummaries = refreshRecent ? await load("recent") : null;
      const nextRecent = recentSummaries ? await Promise.all(recentSummaries.map(async (item) => (
        item.operationType === "content_studio_explicit_batch" && item.status === "PARTIAL"
          ? (await loadDetail(item.operationId)) ?? item
          : item
      ))) : null;
      const hydrated = await Promise.all(activeSummaries.map(async (item) => (await loadDetail(item.operationId)) ?? item));
      if (mounted.current) {
        activeRef.current = hydrated;
        setActive((current) => reconcileOperations(current, hydrated));
        if (nextRecent) {
          setRecent((current) => reconcileOperations(current, nextRecent));
          recentLoadedAt.current = Date.now();
        }
        setInitialized(true);
      }
    } catch {
      // Preserve the last known operation state during transient API unavailability.
    } finally {
      refreshing.current = false;
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    let timer = 0;
    const schedule = () => {
      const hidden = document.visibilityState === "hidden";
      const delay = pollMilliseconds ?? (hidden ? 60_000 : activeRef.current.length ? 1_500 : 15_000);
      timer = window.setTimeout(async () => { await refresh(); if (mounted.current) schedule(); }, delay);
    };
    const visible = () => { if (document.visibilityState === "visible") void refresh(); };
    void refresh().finally(schedule);
    document.addEventListener("visibilitychange", visible);
    return () => { mounted.current = false; window.clearTimeout(timer); document.removeEventListener("visibilitychange", visible); };
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
