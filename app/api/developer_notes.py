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
    title: str | None = None
    completed: bool | None = None
    note: str | None = None


class SubnoteWrite(BaseModel):
    title: str
    content: str = ""


class SubnoteCompletionPatch(BaseModel):
    completed: bool


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


def _subnote_payload(row):
    def iso(value):
        return value.isoformat() if isinstance(value, (date, datetime)) else value
    return {
        "id": row["subnote_id"], "todoId": row["todo_id"],
        "title": row["title"], "content": row["content"],
        "completed": bool(row.get("is_completed", False)),
        "createdAt": iso(row["created_at"]), "updatedAt": iso(row["updated_at"]),
    }


def _todo_payload(repository, creator_profile_id, row):
    item = _payload(row)
    item["subnotes"] = [
        _subnote_payload(subnote)
        for subnote in repository.list_subnotes_for_todo(creator_profile_id, row["todo_id"])
    ]
    return item


@router.get("/todos")
def list_todos():
    creator_profile_id, _ = _context()
    repository = DeveloperTodoRepository()
    subnotes_by_todo = {}
    for row in repository.list_subnotes_for_creator(creator_profile_id):
        subnotes_by_todo.setdefault(row["todo_id"], []).append(_subnote_payload(row))
    items = []
    for row in repository.list_for_creator(creator_profile_id):
        item = _payload(row)
        item["subnotes"] = subnotes_by_todo.get(row["todo_id"], [])
        items.append(item)
    return {"items": items}


@router.patch("/todos/{todo_id}")
def update_todo(todo_id: str, body: TodoPatch):
    creator_profile_id, _ = _context()
    repository = DeveloperTodoRepository()
    fields=body.model_fields_set
    title = body.title.strip() if body.title is not None else None
    if "title" in fields and not title:
        raise HTTPException(status_code=422, detail="TODO title is required.")
    note=body.note.strip() if body.note and body.note.strip() else None
    row = repository.update(creator_profile_id,todo_id,title=title,update_title="title" in fields,completed=body.completed,update_completed="completed" in fields,notes=note,update_notes="note" in fields)
    if row is None:
        raise HTTPException(status_code=404, detail="Developer TODO not found.")
    return _todo_payload(repository, creator_profile_id, row)


@router.post("/todos",status_code=201)
def create_todo(body: TodoCreate):
    creator_profile_id,_=_context(); title=body.title.strip()
    if not title: raise HTTPException(status_code=422,detail="TODO title is required.")
    note=body.note.strip() if body.note and body.note.strip() else None
    row = DeveloperTodoRepository().create(creator_profile_id,title,note)
    payload = _payload(row)
    payload["subnotes"] = (
        [_subnote_payload(row["created_subnote"])] if row.get("created_subnote") else []
    )
    return payload


@router.delete("/todos/{todo_id}", status_code=204)
def delete_todo(todo_id: str):
    creator_profile_id, _ = _context()
    if not DeveloperTodoRepository().delete(creator_profile_id, todo_id):
        raise HTTPException(status_code=404, detail="Developer TODO not found.")


@router.post("/todos/{todo_id}/subnotes", status_code=201)
def create_subnote(todo_id: str, body: SubnoteWrite):
    creator_profile_id, _ = _context()
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Subnote title is required.")
    row = DeveloperTodoRepository().create_subnote(
        creator_profile_id, todo_id, title, body.content.strip(),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Developer TODO not found.")
    return _subnote_payload(row)


@router.patch("/todos/{todo_id}/subnotes/{subnote_id}")
def update_subnote(todo_id: str, subnote_id: str, body: SubnoteWrite):
    creator_profile_id, _ = _context()
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Subnote title is required.")
    row = DeveloperTodoRepository().update_subnote(
        creator_profile_id, todo_id, subnote_id,
        title=title, content=body.content.strip(),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Developer subnote not found.")
    return _subnote_payload(row)


@router.patch("/todos/{todo_id}/subnotes/{subnote_id}/completion")
def update_subnote_completion(todo_id: str, subnote_id: str, body: SubnoteCompletionPatch):
    creator_profile_id, _ = _context()
    row = DeveloperTodoRepository().set_subnote_completed(
        creator_profile_id, todo_id, subnote_id, body.completed,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Developer subnote not found.")
    return _subnote_payload(row)


@router.delete("/todos/{todo_id}/subnotes/{subnote_id}", status_code=204)
def delete_subnote(todo_id: str, subnote_id: str):
    creator_profile_id, _ = _context()
    if not DeveloperTodoRepository().delete_subnote(creator_profile_id, todo_id, subnote_id):
        raise HTTPException(status_code=404, detail="Developer subnote not found.")
