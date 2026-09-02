import { developerNotesApi } from "../../infrastructure/api/developerNotesApi";
import { PersistentChecklistPage } from "../checklist-notes/PersistentChecklistPage";

const copy = {
  pageTitle: "Developer Notes",
  pageDescription: "Keep track of future Creator_OS development work.",
  sectionTitle: "TODO",
  sectionDescription: "A simple persistent development checklist.",
  newButton: "+ New TODO",
  addButton: "Add TODO",
  detailsLabel: "Note",
  singular: "TODO",
  plural: "TODOs",
  completedVerb: "complete",
  incompleteVerb: "open",
  completedDateLabel: "Completed",
  emptyTitle: "No TODOs yet.",
  emptyDescription: "Use + New TODO to capture future development work.",
};

export function DeveloperNotesPage() {
  return <PersistentChecklistPage api={developerNotesApi} copy={copy} />;
}
