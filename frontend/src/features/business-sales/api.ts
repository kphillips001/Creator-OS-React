import type { Page, SalesDecision, SalesLearning, SalesOffer, SalesOverview } from "./types";

async function read<T>(url: string, signal?: AbortSignal): Promise<T> { const response = await fetch(url, { cache: "no-store", signal }); const body = await response.json() as T & { detail?: string }; if (!response.ok) throw new Error(body.detail || "Unable to load Sales workspace."); return body; }
export const salesApi = {
  overview: (signal?: AbortSignal) => read<SalesOverview>("/api/v1/sales/overview", signal),
  decisions: (params: URLSearchParams, signal?: AbortSignal) => read<Page<SalesDecision>>(`/api/v1/sales/decisions?${params}`, signal),
  decision: (id: string) => read<SalesDecision>(`/api/v1/sales/decisions/${encodeURIComponent(id)}`),
  offers: (params: URLSearchParams, signal?: AbortSignal) => read<Page<SalesOffer>>(`/api/v1/sales/offers?${params}`, signal),
  learning: (signal?: AbortSignal) => read<SalesLearning>("/api/v1/sales/learning", signal),
};
