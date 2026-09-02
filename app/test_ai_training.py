from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api import ai_training


class FakeRepository:
    def __init__(self):
        self.items = []
        self.subnotes = []

    def list_for_creator(self, _creator):
        return sorted(self.items, key=lambda row: (row["integrated"], -row["created_at"].timestamp()))

    def list_subnotes_for_creator(self, _creator):
        return self.subnotes

    def list_subnotes_for_note(self, _creator, note_id):
        return [row for row in self.subnotes if row["training_note_id"] == note_id]

    def create(self, creator, title, details):
        row = {
            "note_id": f"training-{len(self.items) + 1}", "creator_profile_id": creator,
            "title": title, "details": details, "integrated": False, "integrated_at": None,
            "created_at": datetime(2026, 8, 20, 12 + len(self.items), tzinfo=timezone.utc),
            "updated_at": datetime(2026, 8, 20, 12 + len(self.items), tzinfo=timezone.utc),
        }
        self.items.append(row)
        row["created_subnote"] = None
        if details:
            row["created_subnote"] = self.create_subnote(creator, row["note_id"], "Existing Note", details)
        return row

    def get(self, creator, note_id):
        return next((row for row in self.items if row["creator_profile_id"] == creator and row["note_id"] == note_id), None)

    def update(self, creator, note_id, **changes):
        row = self.get(creator, note_id)
        if row is None:
            return None
        if changes["update_title"]:
            row["title"] = changes["title"]
        if changes["update_integrated"]:
            row["integrated"] = changes["integrated"]
            row["integrated_at"] = datetime.now(timezone.utc) if changes["integrated"] else None
        if changes["update_details"]:
            row["details"] = changes["details"]
        row["updated_at"] = datetime.now(timezone.utc)
        return row

    def create_subnote(self, creator, note_id, title, content):
        if self.get(creator, note_id) is None: return None
        now=datetime.now(timezone.utc); row={"subnote_id":f"sub-{len(self.subnotes)+1}","training_note_id":note_id,"title":title,"content":content,"is_completed":False,"created_at":now,"updated_at":now}; self.subnotes.append(row); return row

    def update_subnote(self, creator, note_id, subnote_id, **changes):
        row=next((value for value in self.subnotes if value["training_note_id"]==note_id and value["subnote_id"]==subnote_id),None)
        if row is None:return None
        row.update(changes,updated_at=datetime.now(timezone.utc));return row

    def set_subnote_completed(self, creator, note_id, subnote_id, completed):
        row=next((value for value in self.subnotes if value["training_note_id"]==note_id and value["subnote_id"]==subnote_id),None)
        if row is None:return None
        row["is_completed"]=completed;row["updated_at"]=datetime.now(timezone.utc);return row

    def delete_subnote(self, creator, note_id, subnote_id):
        before=len(self.subnotes);self.subnotes=[value for value in self.subnotes if not(value["training_note_id"]==note_id and value["subnote_id"]==subnote_id)];return len(self.subnotes)==before-1

    def delete(self, creator, note_id):
        row = self.get(creator, note_id)
        if row is None:
            return False
        self.items.remove(row)
        self.subnotes=[value for value in self.subnotes if value["training_note_id"]!=note_id]
        return True


@pytest.fixture
def repository(monkeypatch):
    value = FakeRepository()
    monkeypatch.setattr(ai_training, "_context", lambda: (7, None))
    monkeypatch.setattr(ai_training, "AiTrainingNoteRepository", lambda: value)
    return value


def test_create_list_update_reopen_and_delete_are_isolated(repository):
    first = ai_training.create_training_note(ai_training.TrainingNoteCreate(title=" Rule one ", details=" Example details "))
    second = ai_training.create_training_note(ai_training.TrainingNoteCreate(title="Rule two", details=None))
    assert first["title"] == "Rule one" and first["details"] == "Example details"
    assert [item["id"] for item in ai_training.list_training_notes()["items"]] == [second["id"], first["id"]]
    integrated = ai_training.update_training_note(first["id"], ai_training.TrainingNotePatch(integrated=True))
    assert integrated["integrated"] is True and integrated["integratedAt"] is not None
    assert len(ai_training.list_training_notes()["items"]) == 2
    reopened = ai_training.update_training_note(first["id"], ai_training.TrainingNotePatch(integrated=False, details="Updated"))
    assert reopened["integrated"] is False and reopened["integratedAt"] is None and reopened["details"] == "Updated"
    assert ai_training.delete_training_note(second["id"]) is None
    assert [item["id"] for item in ai_training.list_training_notes()["items"]] == [first["id"]]


def test_validation_and_missing_note(repository):
    with pytest.raises(HTTPException) as blank:
        ai_training.create_training_note(ai_training.TrainingNoteCreate(title=" "))
    assert blank.value.status_code == 422
    with pytest.raises(HTTPException) as missing:
        ai_training.update_training_note("missing", ai_training.TrainingNotePatch(integrated=True))
    assert missing.value.status_code == 404
    with pytest.raises(HTTPException) as delete_missing:
        ai_training.delete_training_note("missing")
    assert delete_missing.value.status_code == 404


def test_training_subnotes_are_persisted_independent_and_cascade_with_parent(repository):
    parent=ai_training.create_training_note(ai_training.TrainingNoteCreate(title="Parent"))
    first=ai_training.create_subnote(parent["id"],ai_training.SubnoteWrite(title="First",content="One"))
    second=ai_training.create_subnote(parent["id"],ai_training.SubnoteWrite(title="Second",content="Two"))
    assert [value["title"] for value in ai_training.list_training_notes()["items"][0]["subnotes"]]==["First","Second"]
    completed=ai_training.update_subnote_completion(parent["id"],first["id"],ai_training.SubnoteCompletionPatch(completed=True))
    assert completed["completed"] is True and repository.items[0]["integrated"] is False
    updated=ai_training.update_subnote(parent["id"],second["id"],ai_training.SubnoteWrite(title="Renamed",content="Changed"))
    assert updated["id"]==second["id"] and updated["createdAt"]==second["createdAt"] and updated["content"]=="Changed"
    assert ai_training.delete_subnote(parent["id"],first["id"]) is None
    ai_training.delete_training_note(parent["id"]);assert repository.subnotes==[]


def test_migration_and_repository_use_a_dedicated_domain_table():
    forward = Path("migrations/forward/20260820_074_ai_training_notes.sql").read_text(encoding="utf-8")
    rollback = Path("migrations/rollback/20260820_074_ai_training_notes.sql").read_text(encoding="utf-8")
    repository = Path("app/repositories/ai_training_note_repository.py").read_text(encoding="utf-8")
    assert "CREATE TABLE public.ai_training_notes" in forward
    assert "integrated BOOLEAN NOT NULL DEFAULT FALSE" in forward
    assert "REFERENCES public.creator_profiles(id) ON DELETE CASCADE" in forward
    assert "DROP TABLE IF EXISTS public.ai_training_notes" in rollback
    assert "public.ai_training_notes" in repository
    assert "developer_todos" not in repository
    subnotes = Path("migrations/forward/20260822_079_ai_training_subnotes.sql").read_text(encoding="utf-8")
    assert "ON DELETE CASCADE" in subnotes and "ON CONFLICT DO NOTHING" in subnotes
    assert "migrated_from_parent_details" in subnotes and "is_completed BOOLEAN NOT NULL DEFAULT FALSE" in subnotes


def test_router_is_registered_without_provider_dependencies():
    from app.fanvue_callback_server import app

    paths = {route.path for route in app.routes}
    assert "/api/v1/ai-training/notes" in paths
    assert "/api/v1/ai-training/notes/{note_id}" in paths
