from datetime import date, datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.api.background_operations import _context
from app.repositories.developer_todo_repository import DeveloperTodoRepository

router = APIRouter(prefix="/api/v1/developer-notes", tags=["developer-notes"])


class TodoCreate(BaseModel):
    title: str
    note: str | None = None


class TodoPatch(BaseModel):
    completed: bool | None = None
    note: str | None = None


def _payload(row):
    def iso(value):
        return value.isoformat() if isinstance(value, (date, datetime)) else value
    return {
        "id": row["todo_id"],
        "title": row["title"],
        "createdAt": iso(row["created_at"]),
        "completed": bool(row["completed"]),
        "completedAt": iso(row.get("completed_at")),
        "note": row.get("notes"),
    }


@router.get("/todos")
def list_todos():
    creator_profile_id, _ = _context()
    return {"items": [_payload(row) for row in DeveloperTodoRepository().list_for_creator(creator_profile_id)]}


@router.patch("/todos/{todo_id}")
def update_todo(todo_id: str, body: TodoPatch):
    creator_profile_id, _ = _context()
    fields=body.model_fields_set
    note=body.note.strip() if body.note and body.note.strip() else None
    row = DeveloperTodoRepository().update(creator_profile_id,todo_id,completed=body.completed,update_completed="completed" in fields,notes=note,update_notes="note" in fields)
    if row is None:
        raise HTTPException(status_code=404, detail="Developer TODO not found.")
    return _payload(row)


@router.post("/todos",status_code=201)
def create_todo(body: TodoCreate):
    creator_profile_id,_=_context(); title=body.title.strip()
    if not title: raise HTTPException(status_code=422,detail="TODO title is required.")
    note=body.note.strip() if body.note and body.note.strip() else None
    return _payload(DeveloperTodoRepository().create(creator_profile_id,title,note))
