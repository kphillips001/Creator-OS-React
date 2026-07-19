import type { OperationsFailures, OperationsModuleSwitches, OperationsOverview, OperationsPublishing, OperationsQueues, OperationsRuntime, OperationsWorkers } from "./types";

async function read<T>(section: string, signal?: AbortSignal): Promise<T> { const response = await fetch(`/api/v1/operations/${section}`, { cache: "no-store", signal }); const body = await response.json() as T & { detail?: string }; if (!response.ok) throw new Error(body.detail || "Unable to load Operations workspace."); return body; }
async function patch<T>(section: string, value: boolean | string): Promise<T> { const response = await fetch(`/api/v1/operations/${section}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ value }) }); const body = await response.json() as T & { detail?: string }; if (!response.ok) throw new Error(body.detail || "Unable to update module switch."); return body; }
export const operationsApi = {
  overview: (signal?: AbortSignal) => read<OperationsOverview>("overview", signal),
  runtime: (signal?: AbortSignal) => read<OperationsRuntime>("runtime", signal),
  workers: (signal?: AbortSignal) => read<OperationsWorkers>("workers", signal),
  queues: (signal?: AbortSignal) => read<OperationsQueues>("queues", signal),
  publishing: (signal?: AbortSignal) => read<OperationsPublishing>("publishing", signal),
  failures: (signal?: AbortSignal) => read<OperationsFailures>("failures", signal),
  module_switches: (signal?: AbortSignal) => read<OperationsModuleSwitches>("module-switches", signal),
  updateModuleSwitch: (module: string, value: boolean | string) => patch<OperationsModuleSwitches>(`module-switches/${module}`, value),
};
