"""PostgreSQL persistence for isolated Instagram competitor intelligence."""
from uuid import uuid4

from app.database import get_db_connection


class IgCompetitorIntelligenceRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def list(self, creator_profile_id: int, *, archived: bool = False):
        archive_condition = "IS NOT NULL" if archived else "IS NULL"
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""SELECT * FROM ig_intelligence.competitors
                   WHERE creator_profile_id=%s AND archived_at {archive_condition}
                   ORDER BY created_at DESC, id""",
                (creator_profile_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_by_username(self, creator_profile_id: int, username: str):
        return self._one("SELECT * FROM ig_intelligence.competitors WHERE creator_profile_id=%s AND LOWER(username)=LOWER(%s)", (creator_profile_id, username))

    def create(self, creator_profile_id: int, *, username: str, followers_count: int):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""INSERT INTO ig_intelligence.competitors
                (id,creator_profile_id,username,followers_count)
                VALUES(%s,%s,%s,%s) RETURNING *""",
                (uuid4(), creator_profile_id, username, followers_count))
            return dict(cursor.fetchone())

    def update_followers(self, creator_profile_id: int, competitor_id: str, followers_count: int):
        return self._update("""UPDATE ig_intelligence.competitors SET followers_count=%s,updated_at=NOW()
            WHERE creator_profile_id=%s AND id=%s AND archived_at IS NULL RETURNING *""", (followers_count, creator_profile_id, competitor_id))

    def archive(self, creator_profile_id: int, competitor_id: str):
        return self._update("""UPDATE ig_intelligence.competitors SET archived_at=COALESCE(archived_at,NOW()),updated_at=NOW()
            WHERE creator_profile_id=%s AND id=%s RETURNING *""", (creator_profile_id, competitor_id))

    def restore(self, creator_profile_id: int, competitor_id: str):
        return self._update("""UPDATE ig_intelligence.competitors SET archived_at=NULL,updated_at=NOW()
            WHERE creator_profile_id=%s AND id=%s RETURNING *""", (creator_profile_id, competitor_id))

    def _one(self, sql, values):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(sql, values); row = cursor.fetchone(); return dict(row) if row else None

    def _update(self, sql, values):
        return self._one(sql, values)
