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

    def create(self, creator_profile_id: int, title: str, notes: str | None = None):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO public.developer_todos
                   (todo_id, creator_profile_id, title, notes)
                   VALUES (%s, %s, %s, %s)
                   RETURNING todo_id, title, created_at, completed, completed_at, notes""",
                (str(uuid4()), creator_profile_id, title, notes),
            )
            return dict(cursor.fetchone())

    def update(self, creator_profile_id: int, todo_id: str, *, completed=None, update_completed=False, notes=None, update_notes=False):
        assignments=[]; values=[]
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
