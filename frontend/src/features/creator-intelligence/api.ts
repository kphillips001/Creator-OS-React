import type { CreatorIntelligence, CurrentSalesStatus, PerformanceSnapshot, SnapshotDrillDown, SnapshotPeriod, XLinkPerformance } from "./types";

export async function loadCreatorIntelligence(signal?: AbortSignal): Promise<CreatorIntelligence> {
  const response = await fetch("/api/v1/creator-intelligence", { cache: "no-store", signal });
  const body = await response.json() as CreatorIntelligence & { detail?: string };
  if (!response.ok) throw new Error(body.detail || "Unable to load Creator Intelligence.");
  return body;
}

export async function loadPerformanceSnapshot(period: SnapshotPeriod, signal?: AbortSignal): Promise<PerformanceSnapshot> {
  const response = await fetch(`/api/v1/creator-intelligence/snapshot?period=${period}`, { cache: "no-store", signal });
  const body = await response.json() as PerformanceSnapshot & { detail?: string };
  if (!response.ok) throw new Error(body.detail || "Unable to load the performance snapshot.");
  return body;
}

export async function loadCurrentSalesStatus(signal?: AbortSignal): Promise<CurrentSalesStatus> {
  const response = await fetch("/api/v1/creator-intelligence/sales-status", { cache: "no-store", signal });
  const body = await response.json() as CurrentSalesStatus & { detail?: string };
  if (!response.ok) throw new Error(body.detail || "Unable to load current sales status.");
  return body;
}

export async function loadSnapshotDrillDown(period: SnapshotPeriod, metric: string, signal?: AbortSignal): Promise<SnapshotDrillDown> {
  const params = new URLSearchParams({ period, metric });
  const response = await fetch(`/api/v1/creator-intelligence/snapshot/drill-down?${params}`, { cache: "no-store", signal });
  const body = await response.json() as SnapshotDrillDown & { detail?: string };
  if (!response.ok) throw new Error(body.detail || "Unable to load metric details.");
  return body;
}

export async function loadXLinkPerformance(period: SnapshotPeriod, signal?: AbortSignal): Promise<XLinkPerformance> {
  const response = await fetch(`/api/v1/creator-intelligence/x-link-performance?period=${period}`, { cache: "no-store", signal });
  const body = await response.json() as XLinkPerformance & { detail?: string };
  if (!response.ok) throw new Error(body.detail || "Unable to load X Link Performance.");
  return body;
}
