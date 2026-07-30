"""Normalized persistence for Photoshoot commerce sets and member Assets."""

from __future__ import annotations

import json
from pathlib import Path
from app.database import get_db_connection


class PhotoshootCommerceRepository:
    DISPLAY_COLUMNS = """
        COALESCE(NULLIF(BTRIM(d.user_title), ''), d.ai_title, d.display_name) AS display_title,
        COALESCE(NULLIF(BTRIM(d.user_description), ''), d.ai_description) AS display_description
    """
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def replace_members(self, session_id: str, members: tuple[tuple[int, int], ...], hero_asset_id: int | None):
        with self.connection_factory() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM public.photoshoot_asset_memberships WHERE photoshoot_session_id=%s", (session_id,))
                for asset_id, order in members:
                    cur.execute("""INSERT INTO public.photoshoot_asset_memberships
                        (photoshoot_session_id,asset_id,shot_order,approved,is_hero)
                        VALUES (%s,%s,%s,TRUE,%s)""", (session_id, asset_id, order, asset_id == hero_asset_id))

    def upsert_intelligence(self, session_id: str, status: str, profile: dict, *, error_code=None, error_message=None):
        with self.connection_factory() as conn:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO public.photoshoot_intelligence_profiles
                    (photoshoot_session_id,status,profile_data,error_code,error_message)
                    VALUES (%s,%s,%s::jsonb,%s,%s)
                    ON CONFLICT (photoshoot_session_id) DO UPDATE SET status=EXCLUDED.status,
                    profile_data=EXCLUDED.profile_data,error_code=EXCLUDED.error_code,
                    error_message=EXCLUDED.error_message,updated_at=now() RETURNING *""",
                    (session_id, status, json.dumps(profile, default=str), error_code, error_message))
                return dict(cur.fetchone())

    def upsert_deliverable(self, *, deliverable_id: str, session_id: str, creator_profile_id: int,
                           display_name: str, member_ids: tuple[int, ...], hero_asset_id: int | None,
                           gallery_path: str, completed_at, intelligence_status: str, commerce_status: str):
        manifest = str(Path(gallery_path) / "session.json") if gallery_path else None
        with self.connection_factory() as conn:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO public.photoshoot_commerce_deliverables
                    (deliverable_id,photoshoot_session_id,creator_profile_id,display_name,
                     ordered_member_asset_ids,shot_count,hero_asset_id,gallery_path,gallery_manifest_path,
                     completed_at,intelligence_status,commerce_status)
                    VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (photoshoot_session_id) DO UPDATE SET
                     creator_profile_id=EXCLUDED.creator_profile_id,display_name=EXCLUDED.display_name,
                     ordered_member_asset_ids=EXCLUDED.ordered_member_asset_ids,shot_count=EXCLUDED.shot_count,
                     hero_asset_id=EXCLUDED.hero_asset_id,gallery_path=EXCLUDED.gallery_path,
                     gallery_manifest_path=EXCLUDED.gallery_manifest_path,completed_at=EXCLUDED.completed_at,
                     intelligence_status=EXCLUDED.intelligence_status,commerce_status=EXCLUDED.commerce_status,
                     updated_at=now() RETURNING *""",
                    (deliverable_id,session_id,creator_profile_id,display_name,json.dumps(member_ids),len(member_ids),
                     hero_asset_id,gallery_path,manifest,completed_at,intelligence_status,commerce_status))
                return dict(cur.fetchone())

    def get_by_session(self, session_id: str):
        return self._one(f"""SELECT d.*,w.current_stage AS workflow_stage, {self.DISPLAY_COLUMNS}
            FROM public.photoshoot_commerce_deliverables d
            LEFT JOIN public.photoshoot_analysis_workflows w USING (deliverable_id)
            WHERE d.photoshoot_session_id=%s""", (session_id,))

    def get(self, deliverable_id: str):
        return self._one(f"""SELECT d.*,i.profile_data AS intelligence_profile,w.current_stage AS workflow_stage, {self.DISPLAY_COLUMNS}
            FROM public.photoshoot_commerce_deliverables d
            LEFT JOIN public.photoshoot_intelligence_profiles i USING (photoshoot_session_id)
            LEFT JOIN public.photoshoot_analysis_workflows w USING (deliverable_id)
            WHERE d.deliverable_id=%s""", (deliverable_id,))

    def list_active(self, creator_profile_id: int):
        """Registered, active commerce inventory only."""
        return self._all(f"""SELECT d.*,i.profile_data AS intelligence_profile,w.current_stage AS workflow_stage, {self.DISPLAY_COLUMNS}
            FROM public.photoshoot_commerce_deliverables d
            LEFT JOIN public.photoshoot_intelligence_profiles i USING (photoshoot_session_id)
            LEFT JOIN public.photoshoot_analysis_workflows w USING (deliverable_id)
            WHERE d.creator_profile_id=%s AND d.registration_state='REGISTERED'
              AND d.is_active=TRUE AND d.is_archived=FALSE ORDER BY d.completed_at DESC""", (creator_profile_id,))

    def list_gallery(self, creator_profile_id: int):
        """All preserved completed Photoshoots, independent of commerce registration."""
        return self._all(f"""SELECT d.*,i.profile_data AS intelligence_profile,w.current_stage AS workflow_stage, {self.DISPLAY_COLUMNS}
            FROM public.photoshoot_commerce_deliverables d
            LEFT JOIN public.photoshoot_intelligence_profiles i USING (photoshoot_session_id)
            LEFT JOIN public.photoshoot_analysis_workflows w USING (deliverable_id)
            WHERE d.creator_profile_id=%s AND d.registration_state<>'ARCHIVED'
              AND d.is_archived=FALSE ORDER BY d.completed_at DESC""", (creator_profile_id,))

    def list_asset_library(self, creator_profile_id: int, *, search: str | None = None, limit: int | None = None):
        filters = ["d.creator_profile_id=%s", "d.registration_state='IN_ASSET_LIBRARY'", "d.is_archived=FALSE"]
        params = [creator_profile_id]
        if search:
            filters.append(f"(COALESCE(NULLIF(BTRIM(d.user_title), ''), d.ai_title, d.display_name) ILIKE %s OR COALESCE(NULLIF(BTRIM(d.user_description), ''), d.ai_description, '') ILIKE %s)")
            term = f"%{search.strip()}%"
            params.extend((term, term))
        suffix = " LIMIT %s OFFSET 0" if limit is not None else ""
        if limit is not None:
            params.append(max(0, int(limit)))
        return self._all(f"""SELECT d.*,i.profile_data AS intelligence_profile,w.current_stage AS workflow_stage, {self.DISPLAY_COLUMNS}
            FROM public.photoshoot_commerce_deliverables d
            LEFT JOIN public.photoshoot_intelligence_profiles i USING (photoshoot_session_id)
            LEFT JOIN public.photoshoot_analysis_workflows w USING (deliverable_id)
            WHERE {' AND '.join(filters)}
            ORDER BY COALESCE(d.updated_at, d.completed_at) DESC NULLS LAST, d.deliverable_id DESC{suffix}""", tuple(params))

    def count_asset_library(self, creator_profile_id: int, *, search: str | None = None) -> int:
        filters = ["creator_profile_id=%s", "registration_state='IN_ASSET_LIBRARY'", "is_archived=FALSE"]
        params = [creator_profile_id]
        if search:
            filters.append("(COALESCE(NULLIF(BTRIM(user_title), ''), ai_title, display_name) ILIKE %s OR COALESCE(NULLIF(BTRIM(user_description), ''), ai_description, '') ILIKE %s)")
            term = f"%{search.strip()}%"
            params.extend((term, term))
        row = self._one(f"SELECT COUNT(*) AS total FROM public.photoshoot_commerce_deliverables WHERE {' AND '.join(filters)}", tuple(params))
        return int(row["total"] if row else 0)

    def add_to_asset_library(self, deliverable_id: str, creator_profile_id: int):
        return self._one("""UPDATE public.photoshoot_commerce_deliverables
            SET registration_state='IN_ASSET_LIBRARY', updated_at=now()
            WHERE deliverable_id=%s AND creator_profile_id=%s
              AND registration_state='PHOTOSHOOT_COMPLETE' AND is_archived=FALSE
            RETURNING *""", (deliverable_id, creator_profile_id))

    def register(self, deliverable_id: str, creator_profile_id: int):
        return self._one("""UPDATE public.photoshoot_commerce_deliverables
            SET registration_state='REGISTERED',is_active=TRUE,
                intelligence_status='PENDING',commerce_status='ANALYZING',updated_at=now()
            WHERE deliverable_id=%s AND creator_profile_id=%s
              AND registration_state='IN_ASSET_LIBRARY' AND is_archived=FALSE
            RETURNING *""", (deliverable_id, creator_profile_id))

    def set_analysis_pending(self, deliverable_id: str):
        return self._one("""UPDATE public.photoshoot_commerce_deliverables SET
            intelligence_status='PENDING',commerce_status='ANALYZING',updated_at=now()
            WHERE deliverable_id=%s RETURNING *""", (deliverable_id,))

    def set_analysis_failure(self, deliverable_id: str, error: str):
        return self._one("""UPDATE public.photoshoot_commerce_deliverables SET
            intelligence_status='FAILED',commerce_status='FAILED',updated_at=now()
            WHERE deliverable_id=%s RETURNING *""", (deliverable_id,))

    def set_naming_failure(self, deliverable_id: str, error: str):
        return self._one("""UPDATE public.photoshoot_commerce_deliverables SET
            naming_status='FAILED',naming_error=%s,intelligence_status='FAILED',
            commerce_status='FAILED',updated_at=now() WHERE deliverable_id=%s RETURNING *""", (error, deliverable_id))

    def set_ready(self, deliverable_id: str):
        return self._one("""UPDATE public.photoshoot_commerce_deliverables SET
            intelligence_status='READY',commerce_status='READY',updated_at=now()
            WHERE deliverable_id=%s AND registration_state='REGISTERED'
              AND is_active=TRUE AND is_archived=FALSE RETURNING *""", (deliverable_id,))

    def set_ai_naming(self, deliverable_id: str, title: str, description: str):
        return self._one("""UPDATE public.photoshoot_commerce_deliverables
            SET ai_title=%s, ai_description=%s,
                naming_status='COMPLETE', naming_error=NULL, updated_at=now()
            WHERE deliverable_id=%s RETURNING *""", (title, description, deliverable_id))

    def record_naming_failure(self, deliverable_id: str, error: str):
        return self._one("""UPDATE public.photoshoot_commerce_deliverables
            SET naming_status=CASE WHEN ai_title IS NOT NULL AND ai_description IS NOT NULL THEN 'COMPLETE' ELSE 'FAILED' END,
                naming_error=CASE WHEN ai_title IS NOT NULL AND ai_description IS NOT NULL THEN NULL ELSE %s END,
                updated_at=now() WHERE deliverable_id=%s RETURNING *""", (error, deliverable_id))

    def members(self, session_id: str):
        return self._all("SELECT * FROM public.photoshoot_asset_memberships WHERE photoshoot_session_id=%s AND approved=TRUE ORDER BY shot_order", (session_id,))

    def commercial_role_context_for_asset(self, asset_id: int, creator_profile_id: int):
        return self._one(
            """SELECT membership.photoshoot_session_id,membership.shot_order,
                      membership.is_hero,
                      membership.shot_order=(
                          SELECT MAX(last_member.shot_order)
                          FROM public.photoshoot_asset_memberships last_member
                          WHERE last_member.photoshoot_session_id=
                                membership.photoshoot_session_id
                            AND last_member.approved=TRUE
                      ) AS is_last,
                      intelligence.profile_data AS photoshoot_intelligence
               FROM public.photoshoot_asset_memberships membership
               JOIN public.photoshoot_commerce_deliverables deliverable
                 USING (photoshoot_session_id)
               LEFT JOIN public.photoshoot_intelligence_profiles intelligence
                 USING (photoshoot_session_id)
               WHERE membership.asset_id=%s AND membership.approved=TRUE
                 AND deliverable.creator_profile_id=%s
               ORDER BY membership.updated_at DESC LIMIT 1""",
            (int(asset_id), int(creator_profile_id)),
        )

    def archive(self, deliverable_id: str):
        return self._one("""UPDATE public.photoshoot_commerce_deliverables SET is_active=FALSE,is_archived=TRUE,
            archived_at=COALESCE(archived_at,now()),updated_at=now() WHERE deliverable_id=%s RETURNING *""", (deliverable_id,))

    def archive_asset_library(self, deliverable_id: str, creator_profile_id: int):
        return self._one("""UPDATE public.photoshoot_commerce_deliverables SET
            is_active=FALSE,is_archived=TRUE,archived_at=COALESCE(archived_at,now()),updated_at=now()
            WHERE deliverable_id=%s AND creator_profile_id=%s
              AND registration_state='IN_ASSET_LIBRARY' AND is_archived=FALSE RETURNING *""",
            (deliverable_id, creator_profile_id))

    def list_archived_asset_library(self, creator_profile_id: int):
        return self._all(f"""SELECT d.*,i.profile_data AS intelligence_profile,w.current_stage AS workflow_stage, {self.DISPLAY_COLUMNS}
            FROM public.photoshoot_commerce_deliverables d
            LEFT JOIN public.photoshoot_intelligence_profiles i USING (photoshoot_session_id)
            LEFT JOIN public.photoshoot_analysis_workflows w USING (deliverable_id)
            WHERE d.creator_profile_id=%s AND d.registration_state='IN_ASSET_LIBRARY' AND d.is_archived=TRUE
            ORDER BY d.archived_at DESC NULLS LAST""", (creator_profile_id,))

    def restore_asset_library(self, deliverable_id: str, creator_profile_id: int):
        return self._one("""UPDATE public.photoshoot_commerce_deliverables SET
            is_active=TRUE,is_archived=FALSE,archived_at=NULL,updated_at=now()
            WHERE deliverable_id=%s AND creator_profile_id=%s
              AND registration_state='IN_ASSET_LIBRARY' AND is_archived=TRUE RETURNING *""",
            (deliverable_id, creator_profile_id))

    def _one(self, sql, params):
        rows = self._all(sql, params); return rows[0] if rows else None

    def _all(self, sql, params):
        with self.connection_factory() as conn:
            with conn.cursor() as cur: cur.execute(sql, params); return tuple(dict(row) for row in cur.fetchall())
