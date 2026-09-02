"""PostgreSQL authority for the isolated AI Training checklist."""
from uuid import uuid4

from app.database import get_db_connection


class AiTrainingNoteRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def list_for_creator(self, creator_profile_id: int):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT note_id, title, details, integrated, integrated_at, created_at, updated_at
                   FROM public.ai_training_notes
                   WHERE creator_profile_id=%s
                   ORDER BY integrated ASC, created_at DESC, note_id DESC""",
                (creator_profile_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def list_subnotes_for_creator(self, creator_profile_id: int):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT subnote_id, training_note_id, title, content, is_completed, created_at, updated_at
                   FROM public.ai_training_subnotes
                   WHERE creator_profile_id=%s
                   ORDER BY created_at ASC, subnote_id ASC""",
                (creator_profile_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def list_subnotes_for_note(self, creator_profile_id: int, note_id: str):
        return [row for row in self.list_subnotes_for_creator(creator_profile_id) if row["training_note_id"] == note_id]

    def create(self, creator_profile_id: int, title: str, details: str | None = None):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            note_id = str(uuid4())
            cursor.execute(
                """INSERT INTO public.ai_training_notes
                   (note_id, creator_profile_id, title, details)
                   VALUES (%s, %s, %s, %s)
                   RETURNING note_id, title, details, integrated, integrated_at, created_at, updated_at""",
                (note_id, creator_profile_id, title, details),
            )
            note = dict(cursor.fetchone())
            note["created_subnote"] = None
            if details:
                cursor.execute(
                    """INSERT INTO public.ai_training_subnotes
                       (subnote_id, creator_profile_id, training_note_id, title, content, migrated_from_parent_details)
                       VALUES (%s, %s, %s, 'Existing Note', %s, TRUE)
                       RETURNING subnote_id, training_note_id, title, content, is_completed, created_at, updated_at""",
                    (str(uuid4()), creator_profile_id, note_id, details),
                )
                note["created_subnote"] = dict(cursor.fetchone())
            return note

    def get(self, creator_profile_id: int, note_id: str):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT note_id, title, details, integrated, integrated_at, created_at, updated_at
                   FROM public.ai_training_notes
                   WHERE creator_profile_id=%s AND note_id=%s""",
                (creator_profile_id, note_id),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def update(self, creator_profile_id: int, note_id: str, *, title=None, update_title=False, integrated=None, update_integrated=False, details=None, update_details=False):
        assignments = []
        values = []
        if update_title:
            assignments.append("title=%s")
            values.append(title)
        if update_integrated:
            assignments.extend(("integrated=%s", "integrated_at=CASE WHEN %s THEN NOW() ELSE NULL END"))
            values.extend((integrated, integrated))
        if update_details:
            assignments.append("details=%s")
            values.append(details)
        if not assignments:
            return self.get(creator_profile_id, note_id)
        assignments.append("updated_at=NOW()")
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""UPDATE public.ai_training_notes SET {', '.join(assignments)}
                    WHERE creator_profile_id=%s AND note_id=%s
                    RETURNING note_id, title, details, integrated, integrated_at, created_at, updated_at""",
                (*values, creator_profile_id, note_id),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def create_subnote(self, creator_profile_id: int, note_id: str, title: str, content: str):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO public.ai_training_subnotes
                   (subnote_id, creator_profile_id, training_note_id, title, content)
                   SELECT %s, %s, note_id, %s, %s FROM public.ai_training_notes
                   WHERE creator_profile_id=%s AND note_id=%s
                   RETURNING subnote_id, training_note_id, title, content, is_completed, created_at, updated_at""",
                (str(uuid4()), creator_profile_id, title, content, creator_profile_id, note_id),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_subnote(self, creator_profile_id: int, note_id: str, subnote_id: str, *, title: str, content: str):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE public.ai_training_subnotes SET title=%s, content=%s, updated_at=NOW()
                   WHERE creator_profile_id=%s AND training_note_id=%s AND subnote_id=%s
                   RETURNING subnote_id, training_note_id, title, content, is_completed, created_at, updated_at""",
                (title, content, creator_profile_id, note_id, subnote_id),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def set_subnote_completed(self, creator_profile_id: int, note_id: str, subnote_id: str, completed: bool):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE public.ai_training_subnotes SET is_completed=%s, updated_at=NOW()
                   WHERE creator_profile_id=%s AND training_note_id=%s AND subnote_id=%s
                   RETURNING subnote_id, training_note_id, title, content, is_completed, created_at, updated_at""",
                (completed, creator_profile_id, note_id, subnote_id),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def delete_subnote(self, creator_profile_id: int, note_id: str, subnote_id: str) -> bool:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """DELETE FROM public.ai_training_subnotes
                   WHERE creator_profile_id=%s AND training_note_id=%s AND subnote_id=%s""",
                (creator_profile_id, note_id, subnote_id),
            )
            return cursor.rowcount == 1

    def delete(self, creator_profile_id: int, note_id: str) -> bool:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM public.ai_training_notes WHERE creator_profile_id=%s AND note_id=%s",
                (creator_profile_id, note_id),
            )
            return cursor.rowcount == 1
