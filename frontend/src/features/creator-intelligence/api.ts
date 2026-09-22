import type { CreatorIntelligence, CurrentSalesStatus, PerformanceSnapshot, SnapshotDrillDown, SnapshotPeriod, XLinkPerformance } from "./types";
import { overviewQuery, peekOverviewQuery } from "./overviewQueryCache";

export const overviewKeys = {
  intelligence: "overview:intelligence",
  snapshot: (period: SnapshotPeriod) => `overview:snapshot:${period}`,
  salesStatus: "overview:sales-status",
  xLinks: (period: SnapshotPeriod) => `overview:x-links:${period}`,
};

const json = async <T>(url: string, signal?: AbortSignal): Promise<T> => {
  const response = await fetch(url, { cache: "no-store", signal });
  const body = await response.json() as T & { detail?: string };
  if (!response.ok) throw new Error(body.detail || "Unable to load Overview data.");
  return body;
};

export async function loadCreatorIntelligence(_signal?: AbortSignal): Promise<CreatorIntelligence> {
  return overviewQuery(overviewKeys.intelligence, () =>
    json<CreatorIntelligence>("/api/v1/creator-intelligence"));
}

export async function loadPerformanceSnapshot(period: SnapshotPeriod, _signal?: AbortSignal): Promise<PerformanceSnapshot> {
  return overviewQuery(overviewKeys.snapshot(period), () =>
    json<PerformanceSnapshot>(`/api/v1/creator-intelligence/snapshot?period=${period}`));
}

export async function loadCurrentSalesStatus(_signal?: AbortSignal): Promise<CurrentSalesStatus> {
  return overviewQuery(overviewKeys.salesStatus, () =>
    json<CurrentSalesStatus>("/api/v1/creator-intelligence/sales-status"));
}

export async function loadSnapshotDrillDown(period: SnapshotPeriod, metric: string, signal?: AbortSignal): Promise<SnapshotDrillDown> {
  const params = new URLSearchParams({ period, metric });
  const response = await fetch(`/api/v1/creator-intelligence/snapshot/drill-down?${params}`, { cache: "no-store", signal });
  const body = await response.json() as SnapshotDrillDown & { detail?: string };
  if (!response.ok) throw new Error(body.detail || "Unable to load metric details.");
  return body;
}

export async function loadXLinkPerformance(period: SnapshotPeriod, _signal?: AbortSignal): Promise<XLinkPerformance> {
  return overviewQuery(overviewKeys.xLinks(period), () =>
    json<XLinkPerformance>(`/api/v1/creator-intelligence/x-link-performance?period=${period}`));
}

export const cachedCreatorIntelligence = () =>
  peekOverviewQuery<CreatorIntelligence>(overviewKeys.intelligence, 60_000);
export const cachedPerformanceSnapshot = (period: SnapshotPeriod) =>
  peekOverviewQuery<PerformanceSnapshot>(overviewKeys.snapshot(period), 30_000);
export const cachedSalesStatus = () =>
  peekOverviewQuery<CurrentSalesStatus>(overviewKeys.salesStatus, 15_000);
export const cachedXLinkPerformance = (period: SnapshotPeriod) =>
  peekOverviewQuery<XLinkPerformance>(overviewKeys.xLinks(period), 120_000);
