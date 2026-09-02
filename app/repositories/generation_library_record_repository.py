"""Full-fidelity canonical PostgreSQL persistence for generated image records."""
from __future__ import annotations

import json
from dataclasses import asdict

from app.database import get_db_connection


class GenerationLibraryRecordRepository:
    STORE_NAME = "generation_library"

    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def state(self):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT revision,imported_legacy_version FROM generation_library_canonical_state WHERE store_name=%s", (self.STORE_NAME,))
            row = cursor.fetchone()
        return (int(row["revision"]), row["imported_legacy_version"]) if row else (0, None)

    def count(self) -> int:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) total FROM generation_library_records")
            return int(cursor.fetchone()["total"])

    def list_payloads(self):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT record_payload FROM generation_library_records ORDER BY created_at,image_id")
            return tuple(dict(row["record_payload"]) for row in cursor.fetchall())

    def get_payload(self, image_id: str):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT record_payload FROM generation_library_records WHERE image_id=%s", (str(image_id),))
            row = cursor.fetchone()
        return dict(row["record_payload"]) if row else None

    def upsert(self, records) -> int:
        records = tuple(records)
        if not records:
            return self.state()[0]
        with self.connection_factory() as connection, connection.cursor() as cursor:
            revision = self._next_revision(cursor)
            cursor.executemany(
                """INSERT INTO generation_library_records(image_id,creator_profile_id,status,record_payload,record_revision,is_staged,staged_at)
                   VALUES(%s,%s,%s,%s::jsonb,%s,%s,%s)
                   ON CONFLICT(image_id) DO UPDATE SET creator_profile_id=EXCLUDED.creator_profile_id,
                   status=EXCLUDED.status,record_payload=EXCLUDED.record_payload,
                   record_revision=EXCLUDED.record_revision,is_staged=EXCLUDED.is_staged,
                   staged_at=EXCLUDED.staged_at,updated_at=NOW()""",
                [(item.image_id,int(item.creator_profile_id),item.status,json.dumps(asdict(item),default=str),revision,item.is_staged,item.staged_at) for item in records],
            )
        return revision

    def delete(self, image_ids) -> int:
        ids = tuple(dict.fromkeys(str(value) for value in image_ids))
        if not ids:
            return self.state()[0]
        with self.connection_factory() as connection, connection.cursor() as cursor:
            revision = self._next_revision(cursor)
            cursor.execute("DELETE FROM generation_library_records WHERE image_id=ANY(%s)", (list(ids),))
        return revision

    def replace_all(self, records, *, legacy_version: str | None = None, bootstrap: bool = False) -> int:
        if not bootstrap:
            raise RuntimeError("Canonical Generation Library replacement is bootstrap-only.")
        records = tuple(records)
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) total FROM generation_library_records")
            if int(cursor.fetchone()["total"]) != 0:
                raise RuntimeError("Canonical Generation Library bootstrap requires an empty store.")
            cursor.execute("SELECT COUNT(*) total FROM assembled_photoshoot_intake_members")
            if int(cursor.fetchone()["total"]) != 0:
                raise RuntimeError("Canonical Generation Library bootstrap is blocked by durable dependencies.")
            revision = self._next_revision(cursor)
            if records:
                cursor.executemany(
                    "INSERT INTO generation_library_records(image_id,creator_profile_id,status,record_payload,record_revision,is_staged,staged_at) VALUES(%s,%s,%s,%s::jsonb,%s,%s,%s)",
                    [(item.image_id,int(item.creator_profile_id),item.status,json.dumps(asdict(item),default=str),revision,item.is_staged,item.staged_at) for item in records],
                )
            if legacy_version is not None:
                cursor.execute("UPDATE generation_library_canonical_state SET imported_legacy_version=%s WHERE store_name=%s", (legacy_version,self.STORE_NAME))
        return revision

    def _next_revision(self, cursor) -> int:
        cursor.execute("""UPDATE generation_library_canonical_state SET revision=revision+1,updated_at=NOW()
                          WHERE store_name=%s RETURNING revision""", (self.STORE_NAME,))
        row = cursor.fetchone()
        if not row:
            cursor.execute("INSERT INTO generation_library_canonical_state(store_name,revision) VALUES(%s,1) RETURNING revision", (self.STORE_NAME,))
            row = cursor.fetchone()
        return int(row["revision"])
