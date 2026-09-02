from datetime import datetime, timezone
from pathlib import Path
from app.api import developer_notes


class FakeRepository:
    def __init__(self):
        self.items=[{"todo_id":"add-photoshoot-bundle-support","title":"Add Photoshoot Bundle Support","created_at":datetime(2026,8,7,12,tzinfo=timezone.utc),"completed":False,"completed_at":None,"notes":None}]
        self.subnotes=[]
    def list_for_creator(self,_): return self.items
    def list_subnotes_for_creator(self,_): return self.subnotes
    def list_subnotes_for_todo(self,_,todo_id): return [item for item in self.subnotes if item["todo_id"]==todo_id]
    def create(self,creator,title,notes):
        row={"todo_id":"new-id","title":title,"created_at":datetime(2026,8,7,14,tzinfo=timezone.utc),"completed":False,"completed_at":None,"notes":notes};self.items.append(row);return row
    def update(self,creator,todo_id,**changes):
        row=next((item for item in self.items if item["todo_id"]==todo_id),None)
        if not row:return None
        if changes["update_title"]:row["title"]=changes["title"]
        if changes["update_completed"]:row["completed"]=changes["completed"];row["completed_at"]=datetime.now(timezone.utc) if changes["completed"] else None
        if changes["update_notes"]:row["notes"]=changes["notes"]
        return row
    def delete(self,creator,todo_id):
        before=len(self.items);self.items=[item for item in self.items if item["todo_id"]!=todo_id];self.subnotes=[item for item in self.subnotes if item["todo_id"]!=todo_id];return len(self.items)==before-1
    def create_subnote(self,creator,todo_id,title,content):
        if not any(item["todo_id"]==todo_id for item in self.items):return None
        now=datetime.now(timezone.utc);row={"subnote_id":f"sub-{len(self.subnotes)+1}","todo_id":todo_id,"title":title,"content":content,"is_completed":False,"created_at":now,"updated_at":now};self.subnotes.append(row);return row
    def update_subnote(self,creator,todo_id,subnote_id,**changes):
        row=next((item for item in self.subnotes if item["todo_id"]==todo_id and item["subnote_id"]==subnote_id),None)
        if not row:return None
        row.update(changes,updated_at=datetime.now(timezone.utc));return row
    def delete_subnote(self,creator,todo_id,subnote_id):
        before=len(self.subnotes);self.subnotes=[item for item in self.subnotes if not(item["todo_id"]==todo_id and item["subnote_id"]==subnote_id)];return len(self.subnotes)==before-1
    def set_subnote_completed(self,creator,todo_id,subnote_id,completed):
        row=next((item for item in self.subnotes if item["todo_id"]==todo_id and item["subnote_id"]==subnote_id),None)
        if not row:return None
        row["is_completed"]=completed;row["updated_at"]=datetime.now(timezone.utc);return row


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


def test_update_todo_title_preserves_identity_state_and_subnotes(monkeypatch):
    repository=setup(monkeypatch)
    child=repository.create_subnote(7,"add-photoshoot-bundle-support","Child","Details")
    original=repository.items[0].copy()
    updated=developer_notes.update_todo("add-photoshoot-bundle-support",developer_notes.TodoPatch(title=" Renamed TODO "))
    assert updated["id"]==original["todo_id"] and updated["title"]=="Renamed TODO"
    assert updated["createdAt"]==original["created_at"].isoformat()
    assert updated["completed"]==original["completed"]
    assert updated["subnotes"][0]["id"]==child["subnote_id"]


def test_delete_todo_removes_only_selected_row_and_its_inline_note(monkeypatch):
    repository=setup(monkeypatch)
    repository.items.append({"todo_id":"keep","title":"Keep me","created_at":datetime.now(timezone.utc),"completed":False,"completed_at":None,"notes":"Keep note"})
    assert developer_notes.delete_todo("add-photoshoot-bundle-support") is None
    assert [item["todo_id"] for item in repository.items] == ["keep"]
    assert repository.items[0]["notes"] == "Keep note"
    assert [item["id"] for item in developer_notes.list_todos()["items"]] == ["keep"]


def test_delete_missing_todo_returns_not_found(monkeypatch):
    from fastapi import HTTPException
    setup(monkeypatch)
    try:
        developer_notes.delete_todo("missing")
        assert False, "Expected a not-found response"
    except HTTPException as error:
        assert error.status_code == 404


def test_subnotes_are_independent_and_scoped_to_the_parent(monkeypatch):
    repository=setup(monkeypatch)
    first=developer_notes.create_subnote("add-photoshoot-bundle-support",developer_notes.SubnoteWrite(title=" First ",content=" One "))
    second=developer_notes.create_subnote("add-photoshoot-bundle-support",developer_notes.SubnoteWrite(title="Second",content="Two"))
    assert [item["title"] for item in developer_notes.list_todos()["items"][0]["subnotes"]] == ["First","Second"]
    updated=developer_notes.update_subnote("add-photoshoot-bundle-support",first["id"],developer_notes.SubnoteWrite(title="First updated",content="Changed"))
    assert updated["content"]=="Changed" and repository.subnotes[1]["content"]=="Two"
    assert developer_notes.delete_subnote("add-photoshoot-bundle-support",first["id"]) is None
    assert [item["subnote_id"] for item in repository.subnotes] == [second["id"]]


def test_parent_delete_cascades_fake_subnotes(monkeypatch):
    repository=setup(monkeypatch)
    developer_notes.create_subnote("add-photoshoot-bundle-support",developer_notes.SubnoteWrite(title="Child",content="Details"))
    developer_notes.delete_todo("add-photoshoot-bundle-support")
    assert repository.subnotes == []


def test_subnote_completion_is_persisted_and_independent_from_parent(monkeypatch):
    repository=setup(monkeypatch)
    child=developer_notes.create_subnote("add-photoshoot-bundle-support",developer_notes.SubnoteWrite(title="Child",content="Details"))
    assert child["completed"] is False
    completed=developer_notes.update_subnote_completion("add-photoshoot-bundle-support",child["id"],developer_notes.SubnoteCompletionPatch(completed=True))
    assert completed["completed"] is True
    assert repository.items[0]["completed"] is False
    assert developer_notes.list_todos()["items"][0]["subnotes"][0]["completed"] is True
    reopened=developer_notes.update_subnote_completion("add-photoshoot-bundle-support",child["id"],developer_notes.SubnoteCompletionPatch(completed=False))
    assert reopened["completed"] is False


def test_seed_and_notes_migrations_are_idempotent_and_additive():
    repository=Path("app/repositories/developer_todo_repository.py").read_text(encoding="utf-8")
    first=Path("migrations/forward/20260807_041_developer_todos.sql").read_text(encoding="utf-8")
    second=Path("migrations/forward/20260807_042_developer_todo_notes.sql").read_text(encoding="utf-8")
    assert "ON CONFLICT (creator_profile_id, todo_id) DO NOTHING" in first
    assert "ON CONFLICT (creator_profile_id, todo_id) DO NOTHING" not in repository
    assert "PRIMARY KEY (creator_profile_id, todo_id)" in first and "ADD COLUMN notes" in second
    assert "ORDER BY completed ASC, created_at DESC" in repository
    subnotes=Path("migrations/forward/20260822_077_developer_todo_subnotes.sql").read_text(encoding="utf-8")
    assert "ON DELETE CASCADE" in subnotes
    assert "ON CONFLICT DO NOTHING" in subnotes
    assert "migrated_from_parent_note" in subnotes
    completion=Path("migrations/forward/20260822_078_developer_todo_subnote_completion.sql").read_text(encoding="utf-8")
    assert "is_completed BOOLEAN NOT NULL DEFAULT FALSE" in completion


def test_historical_normalization_routes_are_retired():
    from app.fanvue_callback_server import app
    paths = {route.path for route in app.routes}
    assert not any("content-vault-normalization" in path for path in paths)
