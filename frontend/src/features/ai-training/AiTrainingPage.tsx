import { aiTrainingApi } from "../../infrastructure/api/aiTrainingApi";
import { PersistentChecklistPage, type PersistentChecklistApi } from "../checklist-notes/PersistentChecklistPage";

const api: PersistentChecklistApi = {
  list: async () => {
    const value = await aiTrainingApi.list();
    return { items: value.items.map((item) => ({ id: item.id, title: item.title, createdAt: item.createdAt, completed: item.integrated, completedAt: item.integratedAt, note: item.details, subnotes: item.subnotes })) };
  },
  create: async (title, details) => {
    const item = await aiTrainingApi.create(title, details);
    return { id: item.id, title: item.title, createdAt: item.createdAt, completed: item.integrated, completedAt: item.integratedAt, note: item.details, subnotes: item.subnotes };
  },
  update: async (id, changes) => {
    const item = await aiTrainingApi.update(id, { title: changes.title, integrated: changes.completed, details: changes.note });
    return { id: item.id, title: item.title, createdAt: item.createdAt, completed: item.integrated, completedAt: item.integratedAt, note: item.details, subnotes: item.subnotes };
  },
  delete: (id) => aiTrainingApi.delete(id),
  createSubnote: (noteId, title, content) => aiTrainingApi.createSubnote(noteId, title, content),
  updateSubnote: (noteId, subnoteId, title, content) => aiTrainingApi.updateSubnote(noteId, subnoteId, title, content),
  updateSubnoteCompletion: (noteId, subnoteId, completed) => aiTrainingApi.updateSubnoteCompletion(noteId, subnoteId, completed),
  deleteSubnote: (noteId, subnoteId) => aiTrainingApi.deleteSubnote(noteId, subnoteId),
};

const copy = {
  pageTitle: "AI Developer Notes",
  pageDescription: "Capture ideas, examples, and implementation notes for future Creator_OS AI development.",
  sectionTitle: "AI DEVELOPMENT NOTES",
  sectionDescription: "A persistent AI development checklist. These notes do not affect live AI behavior.",
  newButton: "+ New AI Developer Note",
  addButton: "Add AI Developer Note",
  detailsLabel: "Details",
  singular: "AI Developer Note",
  plural: "AI developer notes",
  completedVerb: "integrated",
  incompleteVerb: "not integrated",
  completedDateLabel: "Integrated",
  emptyTitle: "No AI developer notes yet.",
  emptyDescription: "Use + New AI Developer Note to capture a future AI improvement.",
};

export function AiTrainingPage() {
  return <PersistentChecklistPage api={api} copy={copy} />;
}
