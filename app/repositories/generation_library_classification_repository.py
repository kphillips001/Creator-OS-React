"""Canonical manual content classification for Generation Library images."""
from __future__ import annotations

from app.database import get_db_connection


class GenerationLibraryClassificationRepository:
    AUTOMATIC_ORIGINS = ("autonomous_inspiration", "explicit_tags", "explicit_inspiration")
    MAX_BULK_SIZE = 100

    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def classify_unclassified(self, *, image_id: str, creator_profile_id: int, classification: str) -> dict | None:
        value = str(classification).upper()
        if value not in {"SFW", "NSFW"}:
            raise ValueError("Manual classification must be SFW or NSFW.")
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO public.generation_library_content_classifications(
                       image_id,content_classification,classification_source)
                   SELECT canonical.image_id,%s,'MANUAL'
                   FROM public.generation_library_records canonical
                   WHERE canonical.image_id=%s AND canonical.creator_profile_id=%s
                     AND COALESCE(canonical.record_payload->'generation_metadata'->'request_metadata'->>'workflow_origin','')
                         <> ALL(%s)
                     AND NOT EXISTS (
                       SELECT 1 FROM public.generation_library_content_classifications existing
                       WHERE existing.image_id=canonical.image_id)
                   ON CONFLICT(image_id) DO NOTHING
                   RETURNING image_id,content_classification,classification_source,created_at,updated_at""",
                (value, str(image_id), int(creator_profile_id), list(self.AUTOMATIC_ORIGINS)),
            )
            row = cursor.fetchone()
        return dict(row) if row else None

    def bulk_classify_unclassified(
        self, *, image_ids: tuple[str, ...], creator_profile_id: int, classification: str,
    ) -> tuple[dict, ...]:
        value = str(classification).upper()
        ids = tuple(str(image_id).strip() for image_id in image_ids)
        if value not in {"SFW", "NSFW"}:
            raise ValueError("Manual classification must be SFW or NSFW.")
        if not ids:
            raise ValueError("At least one image is required.")
        if len(ids) > self.MAX_BULK_SIZE:
            raise ValueError(f"Bulk classification supports at most {self.MAX_BULK_SIZE} images.")
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate image IDs are not allowed.")
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtext(image_id)) FROM unnest(%s::text[]) image_id ORDER BY image_id",
                (list(ids),),
            )
            cursor.execute(
                """SELECT canonical.image_id,canonical.creator_profile_id,
                          canonical.record_payload->'generation_metadata'->'request_metadata'->>'workflow_origin' workflow_origin,
                          manual.content_classification manual_classification
                   FROM public.generation_library_records canonical
                   LEFT JOIN public.generation_library_content_classifications manual
                     ON manual.image_id=canonical.image_id
                   WHERE canonical.image_id=ANY(%s)
                   FOR UPDATE OF canonical""",
                (list(ids),),
            )
            rows = {str(row["image_id"]): row for row in cursor.fetchall()}
            invalid = [image_id for image_id in ids if (
                image_id not in rows
                or int(rows[image_id]["creator_profile_id"]) != int(creator_profile_id)
                or rows[image_id]["manual_classification"] is not None
                or str(rows[image_id]["workflow_origin"] or "") in self.AUTOMATIC_ORIGINS
            )]
            if invalid:
                raise ValueError("Every selected image must exist, belong to the active creator, and still be Unclassified.")
            cursor.execute(
                """INSERT INTO public.generation_library_content_classifications(
                       image_id,content_classification,classification_source)
                   SELECT image_id,%s,'MANUAL' FROM unnest(%s::text[]) image_id
                   RETURNING image_id,content_classification,classification_source,created_at,updated_at""",
                (value, list(ids)),
            )
            return tuple(dict(row) for row in cursor.fetchall())
