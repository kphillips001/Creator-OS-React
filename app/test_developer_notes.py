from datetime import datetime, timezone
from pathlib import Path
from app.api import developer_notes


class FakeRepository:
    def __init__(self): self.items=[{"todo_id":"add-photoshoot-bundle-support","title":"Add Photoshoot Bundle Support","created_at":datetime(2026,8,7,12,tzinfo=timezone.utc),"completed":False,"completed_at":None,"notes":None}]
    def list_for_creator(self,_): return self.items
    def create(self,creator,title,notes):
        row={"todo_id":"new-id","title":title,"created_at":datetime(2026,8,7,14,tzinfo=timezone.utc),"completed":False,"completed_at":None,"notes":notes};self.items.append(row);return row
    def update(self,creator,todo_id,**changes):
        row=next((item for item in self.items if item["todo_id"]==todo_id),None)
        if not row:return None
        if changes["update_completed"]:row["completed"]=changes["completed"];row["completed_at"]=datetime.now(timezone.utc) if changes["completed"] else None
        if changes["update_notes"]:row["notes"]=changes["notes"]
        return row


def setup(monkeypatch):
    repository=FakeRepository();monkeypatch.setattr(developer_notes,"_context",lambda:(7,None));monkeypatch.setattr(developer_notes,"DeveloperTodoRepository",lambda:repository);return repository


def test_initial_todo_completion_note_and_reopen(monkeypatch):
    setup(monkeypatch);listed=developer_notes.list_todos()
    assert listed["items"][0]["note"] is None
    completed=developer_notes.update_todo("add-photoshoot-bundle-support",developer_notes.TodoPatch(completed=True))
    assert completed["completed"] is True and completed["completedAt"] is not None
    noted=developer_notes.update_todo("add-photoshoot-bundle-support",developer_notes.TodoPatch(note="Bundle details"));assert noted["note"]=="Bundle details"
    cleared=developer_notes.update_todo("add-photoshoot-bundle-support",developer_notes.TodoPatch(note=""));assert cleared["note"] is None
    reopened=developer_notes.update_todo("add-photoshoot-bundle-support",developer_notes.TodoPatch(completed=False));assert reopened["completedAt"] is None


def test_create_todo(monkeypatch):
    setup(monkeypatch);created=developer_notes.create_todo(developer_notes.TodoCreate(title=" Future work ",note=" Details "))
    assert created["id"]=="new-id" and created["title"]=="Future work" and created["note"]=="Details" and created["completed"] is False


def test_seed_and_notes_migrations_are_idempotent_and_additive():
    repository=Path("app/repositories/developer_todo_repository.py").read_text(encoding="utf-8")
    first=Path("migrations/forward/20260807_041_developer_todos.sql").read_text(encoding="utf-8")
    second=Path("migrations/forward/20260807_042_developer_todo_notes.sql").read_text(encoding="utf-8")
    assert "ON CONFLICT (creator_profile_id, todo_id) DO NOTHING" in repository
    assert "PRIMARY KEY (creator_profile_id, todo_id)" in first and "ADD COLUMN notes" in second
    assert "ORDER BY completed ASC, created_at DESC" in repository
