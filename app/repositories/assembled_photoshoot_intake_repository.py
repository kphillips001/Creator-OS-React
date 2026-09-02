"""Persistence boundary for durable Generation Library Photoshoot intake."""
from __future__ import annotations

import json
from uuid import UUID

from app.database import get_db_connection


class AssembledPhotoshootIntakeRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def create(self, *, intake_id, creator_profile_id: int, idempotency_key: str,
               display_name: str, image_ids, hero_image_id: str):
        ids = tuple(str(value) for value in image_ids)
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO public.assembled_photoshoot_intakes(
                     intake_id,creator_profile_id,idempotency_key,display_name,hero_image_id,ordered_image_ids)
                   VALUES(%s,%s,%s,%s,%s,%s::jsonb)
                   ON CONFLICT(creator_profile_id,idempotency_key) DO NOTHING RETURNING *""",
                (intake_id, int(creator_profile_id), idempotency_key, display_name,
                 hero_image_id, json.dumps(ids)),
            )
            row = cursor.fetchone()
            if row is None:
                cursor.execute(
                    """SELECT * FROM public.assembled_photoshoot_intakes
                       WHERE creator_profile_id=%s AND idempotency_key=%s""",
                    (int(creator_profile_id), idempotency_key),
                )
                return dict(cursor.fetchone()), False
            cursor.executemany(
                """INSERT INTO public.assembled_photoshoot_intake_members(intake_id,image_id,position)
                   VALUES(%s,%s,%s)""",
                [(intake_id, image_id, position) for position, image_id in enumerate(ids, 1)],
            )
            return dict(row), True

    def get(self, intake_id):
        return self._one("SELECT * FROM public.assembled_photoshoot_intakes WHERE intake_id=%s", (intake_id,))

    def members(self, intake_id):
        return self._all(
            """SELECT * FROM public.assembled_photoshoot_intake_members
               WHERE intake_id=%s ORDER BY position""", (intake_id,))

    def attach_operation(self, intake_id, operation_id):
        return self._one(
            """UPDATE public.assembled_photoshoot_intakes SET operation_id=%s,updated_at=NOW()
               WHERE intake_id=%s RETURNING *""", (operation_id, intake_id))

    def start(self, intake_id):
        return self._one(
            """UPDATE public.assembled_photoshoot_intakes
               SET status='PROCESSING',last_error=NULL,updated_at=NOW()
               WHERE intake_id=%s AND status IN ('QUEUED','PROCESSING','WAITING_INTELLIGENCE','FAILED')
               RETURNING *""", (intake_id,))

    def record_asset(self, intake_id, image_id: str, asset_id: int):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE public.assembled_photoshoot_intake_members SET asset_id=%s
                   WHERE intake_id=%s AND image_id=%s RETURNING *""",
                (int(asset_id), intake_id, image_id),
            )
            member = cursor.fetchone()
            cursor.execute(
                """UPDATE public.assembled_photoshoot_intakes intake SET registered_asset_ids=(
                     SELECT COALESCE(jsonb_agg(member.asset_id ORDER BY member.position),'[]'::jsonb)
                     FROM public.assembled_photoshoot_intake_members member
                     WHERE member.intake_id=intake.intake_id AND member.asset_id IS NOT NULL)
                   WHERE intake_id=%s""", (intake_id,))
            return dict(member) if member else None

    def waiting(self, intake_id):
        return self._one(
            """UPDATE public.assembled_photoshoot_intakes
               SET status='WAITING_INTELLIGENCE',updated_at=NOW() WHERE intake_id=%s RETURNING *""",
            (intake_id,))

    def fail(self, intake_id, error):
        return self._one(
            """UPDATE public.assembled_photoshoot_intakes
               SET status='FAILED',last_error=%s,updated_at=NOW() WHERE intake_id=%s RETURNING *""",
            (str(error), intake_id))

    def finalize(self, *, intake_id, deliverable_id, session_key: str,
                 creator_profile_id: int, display_name: str, asset_ids, hero_asset_id: int):
        ids = tuple(int(value) for value in asset_ids)
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM public.assembled_photoshoot_intakes WHERE intake_id=%s FOR UPDATE", (intake_id,))
            intake = cursor.fetchone()
            if intake is None:
                raise KeyError("Assembled Photoshoot intake not found.")
            if intake["status"] == "SUCCEEDED":
                return dict(intake)
            cursor.execute(
                """INSERT INTO public.photoshoot_commerce_deliverables(
                     deliverable_id,photoshoot_session_id,creator_profile_id,display_name,
                     ordered_member_asset_ids,shot_count,hero_asset_id,completed_at,
                     intelligence_status,commerce_status,registration_state,selling_mode,
                     bundle_sales_channel,source_kind,source_reference)
                   VALUES(%s,%s,%s,%s,%s::jsonb,%s,%s,NOW(),'READY','READY',
                          'IN_ASSET_LIBRARY','BUNDLE',NULL,'GENERATION_LIBRARY_IMPORT',%s)
                   ON CONFLICT(photoshoot_session_id) DO UPDATE SET
                     display_name=EXCLUDED.display_name,ordered_member_asset_ids=EXCLUDED.ordered_member_asset_ids,
                     shot_count=EXCLUDED.shot_count,hero_asset_id=EXCLUDED.hero_asset_id,
                     source_kind=EXCLUDED.source_kind,source_reference=EXCLUDED.source_reference,
                     registration_state='IN_ASSET_LIBRARY',selling_mode='BUNDLE',bundle_sales_channel=NULL,
                     intelligence_status='READY',commerce_status='READY',updated_at=NOW()""",
                (deliverable_id, session_key, int(creator_profile_id), display_name,
                 json.dumps(ids), len(ids), int(hero_asset_id), intake_id),
            )
            cursor.execute("DELETE FROM public.photoshoot_asset_memberships WHERE photoshoot_session_id=%s", (session_key,))
            cursor.executemany(
                """INSERT INTO public.photoshoot_asset_memberships(
                     photoshoot_session_id,asset_id,shot_order,approved,is_hero)
                   VALUES(%s,%s,%s,TRUE,%s)""",
                [(session_key, asset_id, position, asset_id == int(hero_asset_id))
                 for position, asset_id in enumerate(ids, 1)],
            )
            self._persist_current_dispositions(cursor, intake_id, session_key)
            cursor.execute(
                """UPDATE public.assembled_photoshoot_intakes
                   SET status='SUCCEEDED',deliverable_id=%s,last_error=NULL,
                       completed_at=NOW(),updated_at=NOW()
                   WHERE intake_id=%s RETURNING *""", (deliverable_id, intake_id))
            return dict(cursor.fetchone())

    def reconcile_dispositions(self, intake_id):
        """Repair current Photoshoot ownership without relying on historical membership."""
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT photoshoot_session_id FROM public.photoshoot_commerce_deliverables
                   WHERE source_kind='GENERATION_LIBRARY_IMPORT' AND source_reference=%s""",
                (intake_id,),
            )
            deliverable = cursor.fetchone()
            if deliverable is None:
                raise RuntimeError("Succeeded Photoshoot intake has no canonical deliverable.")
            return self._persist_current_dispositions(
                cursor, intake_id, str(deliverable["photoshoot_session_id"])
            )

    @staticmethod
    def _persist_current_dispositions(cursor, intake_id, session_key: str) -> int:
        cursor.execute(
            """INSERT INTO public.generation_image_dispositions(image_id,owner,owner_id)
               SELECT member.image_id,'PHOTOSHOOT',member.intake_id
               FROM public.assembled_photoshoot_intake_members member
               JOIN public.photoshoot_asset_memberships membership
                 ON membership.asset_id=member.asset_id
                AND membership.photoshoot_session_id=%s
                AND membership.approved=TRUE
               WHERE member.intake_id=%s
               ON CONFLICT(image_id) DO UPDATE SET updated_at=NOW()
               WHERE generation_image_dispositions.owner='PHOTOSHOOT'
                 AND generation_image_dispositions.owner_id=EXCLUDED.owner_id""",
            (session_key, intake_id),
        )
        cursor.execute(
            """SELECT COUNT(*) AS total
               FROM public.assembled_photoshoot_intake_members member
               JOIN public.photoshoot_asset_memberships membership
                 ON membership.asset_id=member.asset_id
                AND membership.photoshoot_session_id=%s
                AND membership.approved=TRUE
               JOIN public.generation_image_dispositions disposition
                 ON disposition.image_id=member.image_id
                AND disposition.owner='PHOTOSHOOT'
                AND disposition.owner_id=member.intake_id
               WHERE member.intake_id=%s""",
            (session_key, intake_id),
        )
        disposition_count = int(cursor.fetchone()["total"])
        cursor.execute(
            """SELECT COUNT(*) AS total
               FROM public.assembled_photoshoot_intake_members member
               JOIN public.photoshoot_asset_memberships membership
                 ON membership.asset_id=member.asset_id
                AND membership.photoshoot_session_id=%s
                AND membership.approved=TRUE
               WHERE member.intake_id=%s""",
            (session_key, intake_id),
        )
        member_count = int(cursor.fetchone()["total"])
        if disposition_count != member_count:
            raise RuntimeError("Photoshoot source-image disposition could not be persisted.")
        return disposition_count

    def _one(self, query, params):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(query, params); row = cursor.fetchone()
        return dict(row) if row else None

    def _all(self, query, params):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(query, params); rows = cursor.fetchall()
        return tuple(dict(row) for row in rows)
