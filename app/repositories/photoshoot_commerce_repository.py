"""Normalized persistence for Photoshoot commerce sets and member Assets."""

from __future__ import annotations

import json
from pathlib import Path
from app.database import get_db_connection


class PhotoshootCommerceRepository:
    DISPLAY_COLUMNS = """
        COALESCE(NULLIF(BTRIM(i.commercial_title), ''), d.display_name) AS display_title,
        NULLIF(BTRIM(i.commercial_summary), '') AS display_description
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

    def get_intelligence(self, session_id: str):
        return self._one("SELECT * FROM public.photoshoot_intelligence_profiles WHERE photoshoot_session_id=%s",
                         (session_id,))

    def mark_intelligence_running(self, session_id: str, version: str):
        with self.connection_factory() as conn:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO public.photoshoot_intelligence_profiles
                    (photoshoot_session_id,status,profile_data,intelligence_version,pipeline_stage,
                     stage_status,generation_status,error_code,error_message)
                    VALUES (%s,'RUNNING','{}'::jsonb,%s,'PRODUCTION_ANALYSIS',
                            '{"production":"RUNNING","shots":"PENDING","cross_validation":"PENDING"}'::jsonb,
                            'RUNNING',NULL,NULL)
                    ON CONFLICT (photoshoot_session_id) DO UPDATE SET
                     status='RUNNING',intelligence_version=EXCLUDED.intelligence_version,
                     pipeline_stage='PRODUCTION_ANALYSIS',stage_status=EXCLUDED.stage_status,
                     generation_status='RUNNING',error_code=NULL,error_message=NULL,updated_at=now()
                    RETURNING *""", (session_id, version))
                return dict(cur.fetchone())

    def mark_intelligence_failure(self, session_id: str, version: str, stage: str, error: Exception):
        with self.connection_factory() as conn:
            with conn.cursor() as cur:
                cur.execute("""UPDATE public.photoshoot_intelligence_profiles SET
                    status='FAILED',intelligence_version=%s,pipeline_stage=%s,
                    stage_status=jsonb_set(COALESCE(stage_status,'{}'::jsonb),ARRAY[%s],to_jsonb('FAILED'::text),TRUE),
                    generation_status='FAILED',error_code=%s,error_message=%s,updated_at=now()
                    WHERE photoshoot_session_id=%s RETURNING *""",
                    (version, stage, stage.lower(), type(error).__name__, str(error), session_id))
                return dict(cur.fetchone())

    def update_intelligence_stage(self, session_id: str, stage: str, progress: dict):
        with self.connection_factory() as conn:
            with conn.cursor() as cur:
                cur.execute("""UPDATE public.photoshoot_intelligence_profiles SET pipeline_stage=%s,
                    stage_status=COALESCE(stage_status,'{}'::jsonb) || %s::jsonb,updated_at=now()
                    WHERE photoshoot_session_id=%s RETURNING *""",
                    (stage, json.dumps({"current_stage": stage, **dict(progress)}, default=str), session_id))
                return dict(cur.fetchone())

    def persist_canonical_intelligence(self, session_id: str, version: str, profile: dict):
        """Atomically publish production, every shot, and cross-validation as the canonical result."""
        shots = tuple(profile.get("shot_intelligence") or ())
        with self.connection_factory() as conn:
            with conn.cursor() as cur:
                for shot in shots:
                    cur.execute("""INSERT INTO public.photoshoot_shot_intelligence_profiles
                        (photoshoot_session_id,asset_id,intelligence_version,shot_order,status,
                         sequence_role,profile_data,production_context,error_code,error_message)
                        VALUES (%s,%s,%s,%s,'READY',%s,%s::jsonb,%s::jsonb,NULL,NULL)
                        ON CONFLICT (photoshoot_session_id,asset_id,intelligence_version) DO UPDATE SET
                         shot_order=EXCLUDED.shot_order,status='READY',sequence_role=EXCLUDED.sequence_role,
                         profile_data=EXCLUDED.profile_data,production_context=EXCLUDED.production_context,
                         error_code=NULL,error_message=NULL,updated_at=now()""",
                        (session_id,int(shot["asset_id"]),version,int(shot["shot_order"]),
                         shot.get("sequence_role"),json.dumps(shot,default=str),
                         json.dumps(profile.get("production_analysis") or {},default=str)))
                cur.execute("""UPDATE public.photoshoot_intelligence_profiles SET
                    status='READY',profile_data=%s::jsonb,error_code=NULL,error_message=NULL,
                    commercial_title=COALESCE(%s,commercial_title),subtitle=COALESCE(%s,subtitle),
                    commercial_summary=COALESCE(%s,commercial_summary),story=COALESCE(%s,story),
                    theme=COALESCE(%s,theme),experience=COALESCE(%s,experience),
                    emotional_journey=COALESCE(%s,emotional_journey),
                    buyer_profile=CASE WHEN %s::jsonb='{}'::jsonb THEN buyer_profile ELSE %s::jsonb END,
                    sales_strategy=CASE WHEN %s::jsonb='{}'::jsonb THEN sales_strategy ELSE %s::jsonb END,
                    sales_brain_brief=COALESCE(%s,sales_brain_brief),input_snapshot=%s::jsonb,
                    model=%s,generated_at=%s,intelligence_version=%s,pipeline_stage='COMPLETE',
                    stage_status='{"production":"READY","shots":"READY","cross_validation":"READY"}'::jsonb,
                    production_analysis=%s::jsonb,cross_validation=%s::jsonb,
                    analysis_completed_at=%s,generation_status='READY',updated_at=now()
                    WHERE photoshoot_session_id=%s RETURNING *""",
                    (json.dumps(profile,default=str),profile.get("commercial_title"),profile.get("subtitle"),
                     profile.get("commercial_summary"),profile.get("story"),profile.get("theme"),
                     profile.get("experience"),profile.get("emotional_journey"),
                     json.dumps(profile.get("buyer_profile") or {}),json.dumps(profile.get("buyer_profile") or {}),
                     json.dumps(profile.get("sales_strategy") or {}),json.dumps(profile.get("sales_strategy") or {}),
                     profile.get("sales_brain_brief"),json.dumps(profile.get("input_snapshot") or {}),
                     profile.get("model"),profile.get("generated_at"),version,
                     json.dumps(profile.get("production_analysis") or {},default=str),
                     json.dumps(profile.get("cross_validation") or {},default=str),
                     profile.get("generated_at"),session_id))
                return dict(cur.fetchone())

    def upsert_commercial_intelligence(self, session_id: str, status: str, profile: dict,
                                       *, error_code=None, error_message=None):
        with self.connection_factory() as conn:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO public.photoshoot_intelligence_profiles
                    (photoshoot_session_id,status,profile_data,error_code,error_message,
                     commercial_title,subtitle,commercial_summary,story,theme,experience,
                     emotional_journey,buyer_profile,sales_strategy,sales_brain_brief,
                     input_snapshot,model,generated_at,generation_status)
                    VALUES (%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s::jsonb,%s,%s,%s)
                    ON CONFLICT (photoshoot_session_id) DO UPDATE SET
                     status=EXCLUDED.status,profile_data=EXCLUDED.profile_data,
                     error_code=EXCLUDED.error_code,error_message=EXCLUDED.error_message,
                     commercial_title=EXCLUDED.commercial_title,subtitle=EXCLUDED.subtitle,
                     commercial_summary=EXCLUDED.commercial_summary,story=EXCLUDED.story,
                     theme=EXCLUDED.theme,experience=EXCLUDED.experience,
                     emotional_journey=EXCLUDED.emotional_journey,buyer_profile=EXCLUDED.buyer_profile,
                     sales_strategy=EXCLUDED.sales_strategy,sales_brain_brief=EXCLUDED.sales_brain_brief,
                     input_snapshot=EXCLUDED.input_snapshot,model=EXCLUDED.model,
                     generated_at=EXCLUDED.generated_at,generation_status=EXCLUDED.generation_status,
                     updated_at=now() RETURNING *""",
                    (session_id,status,json.dumps(profile,default=str),error_code,error_message,
                     profile.get("commercial_title"),profile.get("subtitle"),profile.get("commercial_summary"),
                     profile.get("story"),profile.get("theme"),profile.get("experience"),
                     profile.get("emotional_journey"),json.dumps(profile.get("buyer_profile") or {}),
                     json.dumps(profile.get("sales_strategy") or {}),profile.get("sales_brain_brief"),
                     json.dumps(profile.get("input_snapshot") or {}),profile.get("model"),
                     profile.get("generated_at"),status))
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
        return self._one(f"""SELECT d.*,i.profile_data AS intelligence_profile,w.current_stage AS workflow_stage, {self.DISPLAY_COLUMNS}
            FROM public.photoshoot_commerce_deliverables d
            LEFT JOIN public.photoshoot_intelligence_profiles i USING (photoshoot_session_id)
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
            WHERE d.creator_profile_id=%s AND d.registration_state='PHOTOSHOOT_COMPLETE'
              AND d.is_archived=FALSE ORDER BY d.completed_at DESC""", (creator_profile_id,))

    def list_asset_library(self, creator_profile_id: int, *, search: str | None = None, limit: int | None = None):
        filters = ["d.creator_profile_id=%s", "d.registration_state='IN_ASSET_LIBRARY'", "d.is_archived=FALSE"]
        params = [creator_profile_id]
        if search:
            filters.append("(COALESCE(NULLIF(BTRIM(i.commercial_title), ''), d.display_name) ILIKE %s OR COALESCE(NULLIF(BTRIM(i.commercial_summary), ''), '') ILIKE %s)")
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
        filters = ["d.creator_profile_id=%s", "d.registration_state='IN_ASSET_LIBRARY'", "d.is_archived=FALSE"]
        params = [creator_profile_id]
        if search:
            filters.append("(COALESCE(NULLIF(BTRIM(i.commercial_title), ''), d.display_name) ILIKE %s OR COALESCE(NULLIF(BTRIM(i.commercial_summary), ''), '') ILIKE %s)")
            term = f"%{search.strip()}%"
            params.extend((term, term))
        row = self._one(f"""SELECT COUNT(*) AS total FROM public.photoshoot_commerce_deliverables d
            LEFT JOIN public.photoshoot_intelligence_profiles i USING (photoshoot_session_id)
            WHERE {' AND '.join(filters)}""", tuple(params))
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

    def set_completion_intelligence_status(self, deliverable_id: str, status: str):
        return self._one("""UPDATE public.photoshoot_commerce_deliverables
            SET intelligence_status=%s,updated_at=now()
            WHERE deliverable_id=%s RETURNING *""", (status, deliverable_id))

    def set_ready(self, deliverable_id: str):
        return self._one("""UPDATE public.photoshoot_commerce_deliverables SET
            intelligence_status='READY',commerce_status='READY',updated_at=now()
            WHERE deliverable_id=%s AND registration_state='REGISTERED'
              AND is_active=TRUE AND is_archived=FALSE RETURNING *""", (deliverable_id,))

    def members(self, session_id: str):
        return self._all("SELECT * FROM public.photoshoot_asset_memberships WHERE photoshoot_session_id=%s AND approved=TRUE ORDER BY shot_order", (session_id,))

    def intelligence_members(self, session_id: str):
        return self._all("""SELECT m.*,c.file_path,c.media_metadata,
                ci.content_profile,ci.normalized_context,ci.status AS content_intelligence_status
            FROM public.photoshoot_asset_memberships m
            JOIN public.content_items c ON c.id=m.asset_id
            LEFT JOIN public.content_intelligence_profiles ci ON ci.asset_id=m.asset_id
            WHERE m.photoshoot_session_id=%s AND m.approved=TRUE ORDER BY m.shot_order""", (session_id,))

    def shot_intelligence(self, session_id: str, version: str):
        return self._all("""SELECT * FROM public.photoshoot_shot_intelligence_profiles
            WHERE photoshoot_session_id=%s AND intelligence_version=%s ORDER BY shot_order""",
            (session_id, version))

    def latest_shot_intelligence(self, session_id: str):
        return self._all("""SELECT DISTINCT ON (asset_id) *
            FROM public.photoshoot_shot_intelligence_profiles
            WHERE photoshoot_session_id=%s
            ORDER BY asset_id,updated_at DESC""", (session_id,))

    def common_approved_photoshoot(
        self, asset_ids: tuple[int, ...],
    ) -> str | None:
        if not asset_ids:
            return None
        row = self._one(
            """SELECT photoshoot_session_id
               FROM public.photoshoot_asset_memberships
               WHERE approved=TRUE AND asset_id=ANY(%s)
               GROUP BY photoshoot_session_id
               HAVING COUNT(DISTINCT asset_id)=%s
               ORDER BY photoshoot_session_id
               LIMIT 1""",
            (list(asset_ids), len(set(asset_ids))),
        )
        return str(row["photoshoot_session_id"]) if row else None

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
