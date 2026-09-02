import type { OperationsFailures, OperationsModuleSwitches, OperationsOverview, OperationsPublishing, OperationsQueues, OperationsRuntime, OperationsWorkers, PurchaseRecoveryDetail, PurchaseRecoveryQueue, TelegramIdentityReadiness } from "./types";

async function read<T>(section: string, signal?: AbortSignal): Promise<T> { const response = await fetch(`/api/v1/operations/${section}`, { cache: "no-store", signal }); const body = await response.json() as T & { detail?: string }; if (!response.ok) throw new Error(body.detail || "Unable to load Operations workspace."); return body; }
async function patch<T>(section: string, value: boolean | string): Promise<T> { const response = await fetch(`/api/v1/operations/${section}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ value }) }); const body = await response.json() as T & { detail?: string }; if (!response.ok) throw new Error(body.detail || "Unable to update module switch."); return body; }
async function post<T>(section: string, body: unknown): Promise<T> { const response = await fetch(`/api/v1/operations/${section}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); const value = await response.json() as T & { detail?: string }; if (!response.ok) throw new Error(value.detail || "Unable to resolve purchase attribution."); return value; }
export const operationsApi = {
  overview: (signal?: AbortSignal) => read<OperationsOverview>("overview", signal),
  runtime: (signal?: AbortSignal) => read<OperationsRuntime>("runtime", signal),
  workers: (signal?: AbortSignal) => read<OperationsWorkers>("workers", signal),
  queues: (signal?: AbortSignal) => read<OperationsQueues>("queues", signal),
  publishing: (signal?: AbortSignal) => read<OperationsPublishing>("publishing", signal),
  failures: (signal?: AbortSignal) => read<OperationsFailures>("failures", signal),
  purchase_recovery: (signal?: AbortSignal) => read<PurchaseRecoveryQueue>("purchase-recovery", signal),
  telegram_identity_readiness: (signal?: AbortSignal) => read<TelegramIdentityReadiness>("telegram-identity-readiness", signal),
  verifyTelegramIdentity: (telegramUserId: string, localFanvueUserId: number, verificationNote: string) => post<{ success: boolean; idempotentReplay: boolean }>(`telegram-identity-readiness/${telegramUserId}/verify`, { localFanvueUserId, verificationNote }),
  purchaseRecoveryDetail: (id: string) => read<PurchaseRecoveryDetail>(`purchase-recovery/${id}`),
  attributePurchase: (id: string, purchaseIntentId: string, operatorNote: string) => post<{ success: boolean; idempotentReplay: boolean }>(`purchase-recovery/${id}/attribute`, { purchaseIntentId, operatorNote: operatorNote || null }),
  module_switches: (signal?: AbortSignal) => read<OperationsModuleSwitches>("module-switches", signal),
  updateModuleSwitch: (module: string, value: boolean | string) => patch<OperationsModuleSwitches>(`module-switches/${module}`, value),
};
