from datetime import date, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.background_operations import _context
from app.repositories.ai_training_note_repository import AiTrainingNoteRepository

router = APIRouter(prefix="/api/v1/ai-training", tags=["ai-training"])


class TrainingNoteCreate(BaseModel):
    title: str
    details: str | None = None


class TrainingNotePatch(BaseModel):
    title: str | None = None
    integrated: bool | None = None
    details: str | None = None


class SubnoteWrite(BaseModel):
    title: str
    content: str = ""


class SubnoteCompletionPatch(BaseModel):
    completed: bool


def _payload(row):
    def iso(value):
        return value.isoformat() if isinstance(value, (date, datetime)) else value

    return {
        "id": row["note_id"],
        "title": row["title"],
        "details": row.get("details"),
        "integrated": bool(row["integrated"]),
        "integratedAt": iso(row.get("integrated_at")),
        "createdAt": iso(row["created_at"]),
        "updatedAt": iso(row["updated_at"]),
    }


def _subnote_payload(row):
    def iso(value):
        return value.isoformat() if isinstance(value, (date, datetime)) else value
    return {
        "id": row["subnote_id"], "todoId": row["training_note_id"],
        "title": row["title"], "content": row["content"],
        "completed": bool(row.get("is_completed", False)),
        "createdAt": iso(row["created_at"]), "updatedAt": iso(row["updated_at"]),
    }


def _note_payload(repository, creator_profile_id, row):
    item = _payload(row)
    item["subnotes"] = [_subnote_payload(value) for value in repository.list_subnotes_for_note(creator_profile_id, row["note_id"])]
    return item


@router.get("/notes")
def list_training_notes():
    creator_profile_id, _ = _context()
    repository = AiTrainingNoteRepository()
    subnotes_by_note = {}
    for row in repository.list_subnotes_for_creator(creator_profile_id):
        subnotes_by_note.setdefault(row["training_note_id"], []).append(_subnote_payload(row))
    items = []
    for row in repository.list_for_creator(creator_profile_id):
        item = _payload(row); item["subnotes"] = subnotes_by_note.get(row["note_id"], []); items.append(item)
    return {"items": items}


@router.post("/notes", status_code=201)
def create_training_note(body: TrainingNoteCreate):
    creator_profile_id, _ = _context()
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Training note title is required.")
    details = body.details.strip() if body.details and body.details.strip() else None
    row = AiTrainingNoteRepository().create(creator_profile_id, title, details)
    payload = _payload(row)
    payload["subnotes"] = [_subnote_payload(row["created_subnote"])] if row.get("created_subnote") else []
    return payload


@router.patch("/notes/{note_id}")
def update_training_note(note_id: str, body: TrainingNotePatch):
    creator_profile_id, _ = _context()
    fields = body.model_fields_set
    title = body.title.strip() if body.title is not None else None
    if "title" in fields and not title:
        raise HTTPException(status_code=422, detail="Training note title is required.")
    details = body.details.strip() if body.details and body.details.strip() else None
    repository = AiTrainingNoteRepository()
    row = repository.update(
        creator_profile_id,
        note_id,
        title=title,
        update_title="title" in fields,
        integrated=body.integrated,
        update_integrated="integrated" in fields,
        details=details,
        update_details="details" in fields,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="AI Training note not found.")
    return _note_payload(repository, creator_profile_id, row)


@router.delete("/notes/{note_id}", status_code=204)
def delete_training_note(note_id: str):
    creator_profile_id, _ = _context()
    if not AiTrainingNoteRepository().delete(creator_profile_id, note_id):
        raise HTTPException(status_code=404, detail="AI Training note not found.")


@router.post("/notes/{note_id}/subnotes", status_code=201)
def create_subnote(note_id: str, body: SubnoteWrite):
    creator_profile_id, _ = _context(); title = body.title.strip()
    if not title: raise HTTPException(status_code=422, detail="Subnote title is required.")
    row = AiTrainingNoteRepository().create_subnote(creator_profile_id, note_id, title, body.content.strip())
    if row is None: raise HTTPException(status_code=404, detail="AI Training note not found.")
    return _subnote_payload(row)


@router.patch("/notes/{note_id}/subnotes/{subnote_id}")
def update_subnote(note_id: str, subnote_id: str, body: SubnoteWrite):
    creator_profile_id, _ = _context(); title = body.title.strip()
    if not title: raise HTTPException(status_code=422, detail="Subnote title is required.")
    row = AiTrainingNoteRepository().update_subnote(creator_profile_id, note_id, subnote_id, title=title, content=body.content.strip())
    if row is None: raise HTTPException(status_code=404, detail="AI Training subnote not found.")
    return _subnote_payload(row)


@router.patch("/notes/{note_id}/subnotes/{subnote_id}/completion")
def update_subnote_completion(note_id: str, subnote_id: str, body: SubnoteCompletionPatch):
    creator_profile_id, _ = _context()
    row = AiTrainingNoteRepository().set_subnote_completed(creator_profile_id, note_id, subnote_id, body.completed)
    if row is None: raise HTTPException(status_code=404, detail="AI Training subnote not found.")
    return _subnote_payload(row)


@router.delete("/notes/{note_id}/subnotes/{subnote_id}", status_code=204)
def delete_subnote(note_id: str, subnote_id: str):
    creator_profile_id, _ = _context()
    if not AiTrainingNoteRepository().delete_subnote(creator_profile_id, note_id, subnote_id):
        raise HTTPException(status_code=404, detail="AI Training subnote not found.")
