"""PostgreSQL checkpoints for resumable provider uploads."""
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.database import get_db_connection
from app.models.commercial_publication_upload import CommercialPublicationUpload

class CommercialPublicationUploadRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def get(self, publication_id: UUID, asset_id: int, provider: str = "FANVUE"):
        return self._one(
            "SELECT * FROM public.commercial_publication_uploads WHERE publication_id=%s AND asset_id=%s AND provider=%s",
            (publication_id, asset_id, provider),
        )

    def list_for_publication(self, publication_id: UUID):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM public.commercial_publication_uploads WHERE publication_id=%s ORDER BY created_at,asset_id",
                    (publication_id,),
                )
                rows = cursor.fetchall()
        return tuple(self._from_row(row) for row in rows)

    def initialize(self, *, publication_id, asset_id, fanvue_account_id, media_type,
                   content_hash, file_size_bytes):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO public.commercial_publication_uploads
                       (publication_upload_id,publication_id,asset_id,provider,fanvue_account_id,
                        media_type,content_hash,file_size_bytes,started_at)
                       VALUES (%s,%s,%s,'FANVUE',%s,%s,%s,%s,now())
                       ON CONFLICT (publication_id,asset_id,provider) DO UPDATE
                       SET updated_at=now()
                       RETURNING *""",
                    (uuid4(), publication_id, asset_id, fanvue_account_id, media_type,
                     content_hash, file_size_bytes),
                )
                row = cursor.fetchone()
        return self._from_row(row)

    def save_session(self, publication_upload_id, *, media_uuid, upload_id,
                     part_size, total_parts):
        return self._update(
            publication_upload_id,
            """provider_media_uuid=%s,provider_upload_id=%s,part_size_bytes=%s,
               total_parts=%s,upload_status='uploading',last_error=NULL""",
            (media_uuid, upload_id, part_size, total_parts),
        )

    def save_part(self, publication_upload_id, *, part_number, etag):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE public.commercial_publication_uploads
                       SET uploaded_parts=uploaded_parts || %s::jsonb,updated_at=now()
                       WHERE publication_upload_id=%s RETURNING *""",
                    (json.dumps({str(part_number): etag}), publication_upload_id),
                )
                row = cursor.fetchone()
        return self._from_row(row)

    def mark_uploaded(self, publication_upload_id, processing_status="processing"):
        return self._update(
            publication_upload_id,
            "upload_status='uploaded',processing_status=%s,last_error=NULL",
            (processing_status,),
        )

    def mark_processing(self, publication_upload_id, status, error=None):
        terminal = ",completed_at=now()" if status in {"ready", "error"} else ""
        return self._update(
            publication_upload_id,
            f"processing_status=%s,last_error=%s{terminal}",
            (status, error),
        )

    def mark_failed(self, publication_upload_id, error):
        return self._update(
            publication_upload_id,
            "upload_status='failed',last_error=%s,retry_count=retry_count+1",
            (str(error),),
        )

    def _update(self, identifier, assignments, params):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""UPDATE public.commercial_publication_uploads
                        SET {assignments},updated_at=now()
                        WHERE publication_upload_id=%s RETURNING *""",
                    (*params, identifier),
                )
                row = cursor.fetchone()
        return self._from_row(row)

    def _one(self, sql, params):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                row = cursor.fetchone()
        return self._from_row(row) if row else None

    @staticmethod
    def _from_row(row):
        parts = row.get("uploaded_parts") or {}
        if isinstance(parts, str):
            parts = json.loads(parts)
        return CommercialPublicationUpload(
            publication_upload_id=UUID(str(row["publication_upload_id"])),
            publication_id=UUID(str(row["publication_id"])), asset_id=int(row["asset_id"]),
            provider=row["provider"], fanvue_account_id=int(row["fanvue_account_id"]),
            provider_media_uuid=row.get("provider_media_uuid"),
            provider_upload_id=row.get("provider_upload_id"), media_type=row["media_type"],
            content_hash=row["content_hash"], file_size_bytes=int(row["file_size_bytes"]),
            part_size_bytes=row.get("part_size_bytes"), total_parts=row.get("total_parts"),
            uploaded_parts=dict(parts), processing_status=row["processing_status"],
            upload_status=row["upload_status"], retry_count=int(row.get("retry_count") or 0),
            last_error=row.get("last_error"), started_at=row.get("started_at"),
            completed_at=row.get("completed_at"),
        )
