import { environment } from "../config/environment";

export type DeveloperTodo = {
  id: string;
  title: string;
  createdAt: string;
  completed: boolean;
  completedAt: string | null;
  note: string | null;
  subnotes: DeveloperTodoSubnote[];
};

export type DeveloperTodoSubnote = {
  id: string;
  todoId: string;
  title: string;
  content: string;
  completed: boolean;
  createdAt: string;
  updatedAt: string;
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
  update: (id: string, changes: { title?: string; completed?: boolean; note?: string | null }) => request<DeveloperTodo>(`/todos/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(changes),
  }),
  delete: (id: string) => request<void>(`/todos/${encodeURIComponent(id)}`, { method: "DELETE" }),
  createSubnote: (todoId: string, title: string, content: string) => request<DeveloperTodoSubnote>(`/todos/${encodeURIComponent(todoId)}/subnotes`, {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ title, content }),
  }),
  updateSubnote: (todoId: string, subnoteId: string, title: string, content: string) => request<DeveloperTodoSubnote>(`/todos/${encodeURIComponent(todoId)}/subnotes/${encodeURIComponent(subnoteId)}`, {
    method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ title, content }),
  }),
  updateSubnoteCompletion: (todoId: string, subnoteId: string, completed: boolean) => request<DeveloperTodoSubnote>(`/todos/${encodeURIComponent(todoId)}/subnotes/${encodeURIComponent(subnoteId)}/completion`, {
    method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ completed }),
  }),
  deleteSubnote: (todoId: string, subnoteId: string) => request<void>(`/todos/${encodeURIComponent(todoId)}/subnotes/${encodeURIComponent(subnoteId)}`, { method: "DELETE" }),
};
