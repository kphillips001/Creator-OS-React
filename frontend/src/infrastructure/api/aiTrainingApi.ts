import { environment } from "../config/environment";

export type AiTrainingNote = {
  id: string;
  title: string;
  details: string | null;
  integrated: boolean;
  integratedAt: string | null;
  createdAt: string;
  updatedAt: string;
  subnotes: AiTrainingSubnote[];
};

export type AiTrainingSubnote = {
  id: string; todoId: string; title: string; content: string; completed: boolean; createdAt: string; updatedAt: string;
};

const base = `${environment.apiBaseUrl}/ai-training`;
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${base}${path}`, init);
  if (response.status === 204) return undefined as T;
  const value = await response.json().catch(() => null) as T & { detail?: string };
  if (!response.ok) throw new Error(value?.detail || "Unable to load AI Training notes.");
  return value;
}

export const aiTrainingApi = {
  list: () => request<{ items: AiTrainingNote[] }>("/notes", { cache: "no-store" }),
  create: (title: string, details: string) => request<AiTrainingNote>("/notes", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ title, details }),
  }),
  update: (id: string, changes: { title?: string; integrated?: boolean; details?: string | null }) => request<AiTrainingNote>(`/notes/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(changes),
  }),
  delete: (id: string) => request<void>(`/notes/${encodeURIComponent(id)}`, { method: "DELETE" }),
  createSubnote: (noteId: string, title: string, content: string) => request<AiTrainingSubnote>(`/notes/${encodeURIComponent(noteId)}/subnotes`, {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ title, content }),
  }),
  updateSubnote: (noteId: string, subnoteId: string, title: string, content: string) => request<AiTrainingSubnote>(`/notes/${encodeURIComponent(noteId)}/subnotes/${encodeURIComponent(subnoteId)}`, {
    method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ title, content }),
  }),
  updateSubnoteCompletion: (noteId: string, subnoteId: string, completed: boolean) => request<AiTrainingSubnote>(`/notes/${encodeURIComponent(noteId)}/subnotes/${encodeURIComponent(subnoteId)}/completion`, {
    method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ completed }),
  }),
  deleteSubnote: (noteId: string, subnoteId: string) => request<void>(`/notes/${encodeURIComponent(noteId)}/subnotes/${encodeURIComponent(subnoteId)}`, { method: "DELETE" }),
};
