"""Transactional ownership and workspace lifecycle for Bundle Studio."""
from __future__ import annotations

from uuid import UUID, uuid4

from app.database import get_db_connection
from app.models.bundle_studio import BundleStudioBundle, BundleStudioMember


class BundleStudioConflict(ValueError):
    pass


class BundleStudioService:
    OWNER = "BUNDLE_STUDIO"

    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def active(self, *, creator_profile_id: int, create: bool = False,
               name: str = "Untitled Bundle") -> BundleStudioBundle | None:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            row = self._active_row(cursor, creator_profile_id)
            if row is None and create:
                bundle_id = uuid4()
                cursor.execute(
                    """INSERT INTO public.bundle_studio_bundles(bundle_id,creator_profile_id,name)
                       VALUES(%s,%s,%s) RETURNING *""",
                    (bundle_id, int(creator_profile_id), self._name(name)),
                )
                row = cursor.fetchone()
            return self._bundle(cursor, row) if row else None

    def move_images(self, *, creator_profile_id: int, image_ids,
                    bundle_name: str = "Untitled Bundle") -> BundleStudioBundle:
        ids = self._ids(image_ids)
        if not ids:
            raise ValueError("Select at least one Generation Library image.")
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", (int(creator_profile_id),))
            row = self._active_row(cursor, creator_profile_id)
            if row is None:
                cursor.execute(
                    """INSERT INTO public.bundle_studio_bundles(bundle_id,creator_profile_id,name)
                       VALUES(%s,%s,%s) RETURNING *""",
                    (uuid4(), int(creator_profile_id), self._name(bundle_name)),
                )
                row = cursor.fetchone()
            bundle_id = row["bundle_id"]
            self._require_assembling(row)
            cursor.execute(
                """SELECT image_id,creator_profile_id,status FROM public.generation_library_records
                   WHERE image_id=ANY(%s) FOR UPDATE""", (list(ids),),
            )
            records = {str(item["image_id"]): item for item in cursor.fetchall()}
            missing = [image_id for image_id in ids if image_id not in records]
            if missing:
                raise KeyError(f"Generation Library image not found: {missing[0]}")
            if any(int(item["creator_profile_id"]) != int(creator_profile_id) for item in records.values()):
                raise KeyError("Generation Library image not found.")
            inactive = [image_id for image_id, item in records.items() if str(item["status"]) != "active"]
            if inactive:
                raise BundleStudioConflict(f"Image is not active in Generation Library: {inactive[0]}")
            cursor.execute(
                "SELECT image_id,owner,owner_id FROM public.generation_image_dispositions WHERE image_id=ANY(%s) FOR UPDATE",
                (list(ids),),
            )
            owned = {str(item["image_id"]): item for item in cursor.fetchall()}
            conflicts = [image_id for image_id, item in owned.items()
                         if item["owner"] != self.OWNER or str(item["owner_id"]) != str(bundle_id)]
            if conflicts:
                raise BundleStudioConflict(f"Image is already owned by another workspace: {conflicts[0]}")
            cursor.execute("SELECT COALESCE(MAX(position),0) value FROM public.bundle_studio_members WHERE bundle_id=%s", (bundle_id,))
            position = int(cursor.fetchone()["value"])
            for image_id in ids:
                if image_id in owned:
                    continue
                position += 1
                cursor.execute(
                    "INSERT INTO public.generation_image_dispositions(image_id,owner,owner_id) VALUES(%s,%s,%s)",
                    (image_id, self.OWNER, bundle_id),
                )
                cursor.execute(
                    "INSERT INTO public.bundle_studio_members(bundle_id,image_id,position) VALUES(%s,%s,%s)",
                    (bundle_id, image_id, position),
                )
            cursor.execute("UPDATE public.bundle_studio_bundles SET updated_at=NOW() WHERE bundle_id=%s RETURNING *", (bundle_id,))
            return self._bundle(cursor, cursor.fetchone())

    def return_images(self, *, creator_profile_id: int, image_ids) -> BundleStudioBundle:
        ids = self._ids(image_ids)
        with self.connection_factory() as connection, connection.cursor() as cursor:
            row = self._required_active(cursor, creator_profile_id)
            self._require_assembling(row)
            bundle_id = row["bundle_id"]
            cursor.execute(
                "DELETE FROM public.generation_image_dispositions WHERE image_id=ANY(%s) AND owner=%s AND owner_id=%s",
                (list(ids), self.OWNER, bundle_id),
            )
            cursor.execute("DELETE FROM public.bundle_studio_members WHERE bundle_id=%s AND image_id=ANY(%s)", (bundle_id, list(ids)))
            self._compact(cursor, bundle_id)
            cursor.execute("UPDATE public.bundle_studio_bundles SET updated_at=NOW() WHERE bundle_id=%s RETURNING *", (bundle_id,))
            return self._bundle(cursor, cursor.fetchone())

    def rename(self, *, creator_profile_id: int, name: str) -> BundleStudioBundle:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            row = self._required_active(cursor, creator_profile_id)
            self._require_assembling(row)
            cursor.execute("UPDATE public.bundle_studio_bundles SET name=%s,updated_at=NOW() WHERE bundle_id=%s RETURNING *",
                           (self._name(name), row["bundle_id"]))
            return self._bundle(cursor, cursor.fetchone())

    def reorder(self, *, creator_profile_id: int, image_ids) -> BundleStudioBundle:
        ids = self._ids(image_ids)
        with self.connection_factory() as connection, connection.cursor() as cursor:
            row = self._required_active(cursor, creator_profile_id)
            self._require_assembling(row)
            bundle_id = row["bundle_id"]
            cursor.execute("SELECT image_id FROM public.bundle_studio_members WHERE bundle_id=%s ORDER BY position", (bundle_id,))
            current = tuple(str(item["image_id"]) for item in cursor.fetchall())
            if set(ids) != set(current) or len(ids) != len(current):
                raise ValueError("Reorder must contain every Bundle Studio member exactly once.")
            cursor.execute("UPDATE public.bundle_studio_members SET position=position+1000000 WHERE bundle_id=%s", (bundle_id,))
            for position, image_id in enumerate(ids, 1):
                cursor.execute("UPDATE public.bundle_studio_members SET position=%s WHERE bundle_id=%s AND image_id=%s",
                               (position, bundle_id, image_id))
            cursor.execute("UPDATE public.bundle_studio_bundles SET updated_at=NOW() WHERE bundle_id=%s RETURNING *", (bundle_id,))
            return self._bundle(cursor, cursor.fetchone())

    def abandon(self, *, creator_profile_id: int) -> BundleStudioBundle:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            row = self._required_active(cursor, creator_profile_id)
            self._require_assembling(row)
            bundle_id = row["bundle_id"]
            cursor.execute("DELETE FROM public.generation_image_dispositions WHERE owner=%s AND owner_id=%s", (self.OWNER, bundle_id))
            cursor.execute("DELETE FROM public.bundle_studio_members WHERE bundle_id=%s", (bundle_id,))
            cursor.execute("UPDATE public.bundle_studio_bundles SET status='ABANDONED',updated_at=NOW() WHERE bundle_id=%s RETURNING *", (bundle_id,))
            return self._bundle(cursor, cursor.fetchone())

    @staticmethod
    def _active_row(cursor, creator_profile_id):
        cursor.execute("SELECT * FROM public.bundle_studio_bundles WHERE creator_profile_id=%s AND status IN ('ACTIVE','PREPARING','READY') ORDER BY created_at DESC LIMIT 1 FOR UPDATE",
                       (int(creator_profile_id),))
        return cursor.fetchone()

    def _required_active(self, cursor, creator_profile_id):
        row = self._active_row(cursor, creator_profile_id)
        if row is None:
            raise KeyError("Active Bundle Studio workspace not found.")
        return row

    @staticmethod
    def _compact(cursor, bundle_id):
        cursor.execute(
            """WITH ranked AS (SELECT image_id,ROW_NUMBER() OVER(ORDER BY position)::int value
               FROM public.bundle_studio_members WHERE bundle_id=%s)
               UPDATE public.bundle_studio_members m SET position=ranked.value+1000000
               FROM ranked WHERE m.bundle_id=%s AND m.image_id=ranked.image_id""", (bundle_id, bundle_id),
        )
        cursor.execute("UPDATE public.bundle_studio_members SET position=position-1000000 WHERE bundle_id=%s", (bundle_id,))

    def _bundle(self, cursor, row):
        cursor.execute(
            """SELECT m.image_id,m.position,m.added_at,r.record_payload
               FROM public.bundle_studio_members m JOIN public.generation_library_records r ON r.image_id=m.image_id
               WHERE m.bundle_id=%s ORDER BY m.position""", (row["bundle_id"],),
        )
        members = []
        for item in cursor.fetchall():
            payload = dict(item["record_payload"] or {})
            members.append(BundleStudioMember(
                image_id=str(item["image_id"]), position=int(item["position"]), added_at=item["added_at"],
                generation_job_id=str(payload.get("generation_job_id") or ""),
                generation_request_id=str(payload.get("generation_request_id") or ""),
                generation_recipe_id=str(payload.get("generation_recipe_id")) if payload.get("generation_recipe_id") else None,
                provider_id=str(payload.get("provider_id") or ""), output_reference=str(payload.get("output_reference") or ""),
                prompt_text=str(payload.get("prompt_text") or ""),
                creative_mode=str(payload.get("creative_mode")) if payload.get("creative_mode") else None,
                generation_date=str(payload.get("generation_date") or ""),
            ))
        return BundleStudioBundle(bundle_id=row["bundle_id"], creator_profile_id=int(row["creator_profile_id"]),
                                  name=str(row["name"]), status=str(row["status"]), created_at=row["created_at"],
                                  updated_at=row["updated_at"], members=tuple(members),
                                  sales_destination=row.get("sales_destination"),
                                  commercial_offering_id=row.get("commercial_offering_id"))

    @staticmethod
    def _require_assembling(row):
        if str(row["status"]) != "ACTIVE" or row.get("commercial_offering_id") is not None:
            raise BundleStudioConflict("Bundle membership is locked after sale preparation begins.")

    @staticmethod
    def _ids(values):
        return tuple(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))

    @staticmethod
    def _name(value):
        name = " ".join(str(value or "").split())
        if not name:
            raise ValueError("Bundle name is required.")
        return name[:160]
