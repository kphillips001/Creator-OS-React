import { environment } from "../config/environment";

export type DeveloperTodo = {
  id: string;
  title: string;
  createdAt: string;
  completed: boolean;
  completedAt: string | null;
  note: string | null;
};

const base = `${environment.apiBaseUrl}/developer-notes`;
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${base}${path}`, init);
  if (response.status === 204) return undefined as T;
  const value = await response.json().catch(() => null) as T & { detail?: string };
  if (!response.ok) throw new Error(value?.detail || "Unable to load Developer TODOs.");
  return value;
}

export const developerNotesApi = {
  list: () => request<{ items: DeveloperTodo[] }>("/todos", { cache: "no-store" }),
  create: (title: string, note: string) => request<DeveloperTodo>("/todos", {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ title, note }),
  }),
  update: (id: string, changes: { completed?: boolean; note?: string | null }) => request<DeveloperTodo>(`/todos/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(changes),
  }),
  delete: (id: string) => request<void>(`/todos/${encodeURIComponent(id)}`, { method: "DELETE" }),
};
