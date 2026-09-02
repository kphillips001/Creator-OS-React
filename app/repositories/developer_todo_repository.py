"""Small PostgreSQL authority for the Developer Notes checklist."""
from app.database import get_db_connection
from uuid import uuid4

class DeveloperTodoRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def list_for_creator(self, creator_profile_id: int):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT todo_id, title, created_at, completed, completed_at, notes
                   FROM public.developer_todos
                   WHERE creator_profile_id=%s
                   ORDER BY completed ASC, created_at DESC, todo_id DESC""",
                (creator_profile_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def list_subnotes_for_creator(self, creator_profile_id: int):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT subnote_id, todo_id, title, content, is_completed, created_at, updated_at
                   FROM public.developer_todo_subnotes
                   WHERE creator_profile_id=%s
                   ORDER BY created_at ASC, subnote_id ASC""",
                (creator_profile_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def list_subnotes_for_todo(self, creator_profile_id: int, todo_id: str):
        return [
            row for row in self.list_subnotes_for_creator(creator_profile_id)
            if row["todo_id"] == todo_id
        ]

    def create(self, creator_profile_id: int, title: str, notes: str | None = None):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            todo_id = str(uuid4())
            cursor.execute(
                """INSERT INTO public.developer_todos
                   (todo_id, creator_profile_id, title, notes)
                   VALUES (%s, %s, %s, %s)
                   RETURNING todo_id, title, created_at, completed, completed_at, notes""",
                (todo_id, creator_profile_id, title, notes),
            )
            todo = dict(cursor.fetchone())
            todo["created_subnote"] = None
            if notes:
                cursor.execute(
                    """INSERT INTO public.developer_todo_subnotes
                       (subnote_id, creator_profile_id, todo_id, title, content, migrated_from_parent_note)
                       VALUES (%s, %s, %s, 'Existing Note', %s, TRUE)
                       RETURNING subnote_id, todo_id, title, content, is_completed, created_at, updated_at""",
                    (str(uuid4()), creator_profile_id, todo_id, notes),
                )
                todo["created_subnote"] = dict(cursor.fetchone())
            return todo

    def update(self, creator_profile_id: int, todo_id: str, *, title=None, update_title=False, completed=None, update_completed=False, notes=None, update_notes=False):
        assignments=[]; values=[]
        if update_title:
            assignments.append("title=%s"); values.append(title)
        if update_completed:
            assignments.extend(("completed=%s", "completed_at=CASE WHEN %s THEN NOW() ELSE NULL END"))
            values.extend((completed, completed))
        if update_notes:
            assignments.append("notes=%s"); values.append(notes)
        if not assignments:
            return self.get(creator_profile_id, todo_id)
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""UPDATE public.developer_todos SET {', '.join(assignments)}
                    WHERE creator_profile_id=%s AND todo_id=%s
                    RETURNING todo_id, title, created_at, completed, completed_at, notes""",
                (*values, creator_profile_id, todo_id),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get(self, creator_profile_id: int, todo_id: str):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT todo_id, title, created_at, completed, completed_at, notes
                              FROM public.developer_todos WHERE creator_profile_id=%s AND todo_id=%s""",(creator_profile_id,todo_id))
            row=cursor.fetchone(); return dict(row) if row else None

    def delete(self, creator_profile_id: int, todo_id: str) -> bool:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """DELETE FROM public.developer_todos
                   WHERE creator_profile_id=%s AND todo_id=%s""",
                (creator_profile_id, todo_id),
            )
            return cursor.rowcount == 1

    def create_subnote(self, creator_profile_id: int, todo_id: str, title: str, content: str):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO public.developer_todo_subnotes
                   (subnote_id, creator_profile_id, todo_id, title, content)
                   SELECT %s, %s, todo_id, %s, %s
                   FROM public.developer_todos
                   WHERE creator_profile_id=%s AND todo_id=%s
                   RETURNING subnote_id, todo_id, title, content, is_completed, created_at, updated_at""",
                (str(uuid4()), creator_profile_id, title, content,
                 creator_profile_id, todo_id),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_subnote(self, creator_profile_id: int, todo_id: str, subnote_id: str, *, title: str, content: str):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE public.developer_todo_subnotes
                   SET title=%s, content=%s, updated_at=NOW()
                   WHERE creator_profile_id=%s AND todo_id=%s AND subnote_id=%s
                   RETURNING subnote_id, todo_id, title, content, is_completed, created_at, updated_at""",
                (title, content, creator_profile_id, todo_id, subnote_id),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def set_subnote_completed(self, creator_profile_id: int, todo_id: str, subnote_id: str, completed: bool):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE public.developer_todo_subnotes
                   SET is_completed=%s, updated_at=NOW()
                   WHERE creator_profile_id=%s AND todo_id=%s AND subnote_id=%s
                   RETURNING subnote_id, todo_id, title, content, is_completed, created_at, updated_at""",
                (completed, creator_profile_id, todo_id, subnote_id),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def delete_subnote(self, creator_profile_id: int, todo_id: str, subnote_id: str) -> bool:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """DELETE FROM public.developer_todo_subnotes
                   WHERE creator_profile_id=%s AND todo_id=%s AND subnote_id=%s""",
                (creator_profile_id, todo_id, subnote_id),
            )
            return cursor.rowcount == 1
