"""Normalized persistence for Photoshoot commerce sets and member Assets."""

from __future__ import annotations

import json
from pathlib import Path
from app.database import get_db_connection


class PhotoshootCommerceRepository:
    DISPLAY_COLUMNS = """
        COALESCE(NULLIF(BTRIM(i.commercial_title), ''), d.display_name) AS display_title,
        NULLIF(BTRIM(i.commercial_summary), '') AS display_description,
        i.status AS commercial_intelligence_status,
        i.pipeline_stage AS commercial_intelligence_stage,
        i.error_code AS commercial_intelligence_error_code
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
                    (version, stage, stage.lower(),
                     getattr(error, "error_code", type(error).__name__), str(error), session_id))
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
        with self.connection_factory() as conn:
            with conn.cursor() as cur:
                return self._persist_canonical_intelligence(cur, session_id, version, profile)

    @staticmethod
    def _persist_canonical_intelligence(cur, session_id: str, version: str, profile: dict):
        for shot in tuple(profile.get("shot_intelligence") or ()):
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

    def list_gallery_page(self, creator_profile_id: int, *, page: int = 1, page_size: int = 24):
        """Bounded Gallery cards without loading Photoshoot intelligence JSON."""
        limit = max(1, min(int(page_size), 60))
        offset = (max(1, int(page)) - 1) * limit
        rows = self._all(
            """SELECT d.deliverable_id,d.photoshoot_session_id,d.display_name,
                      NULL::text AS display_title,NULL::text AS display_description,
                      d.completed_at,d.shot_count,d.hero_asset_id,d.intelligence_status,
                      d.registration_state,d.selling_mode,d.bundle_sales_channel
               FROM public.photoshoot_commerce_deliverables d
               WHERE d.creator_profile_id=%s AND d.registration_state='PHOTOSHOOT_COMPLETE'
                 AND d.is_archived=FALSE
               ORDER BY d.completed_at DESC,d.deliverable_id DESC LIMIT %s OFFSET %s""",
            (int(creator_profile_id), limit, offset),
        )
        total = self._one(
            """SELECT COUNT(*) AS total FROM public.photoshoot_commerce_deliverables
               WHERE creator_profile_id=%s AND registration_state='PHOTOSHOOT_COMPLETE'
                 AND is_archived=FALSE""", (int(creator_profile_id),)
        )
        return rows, int(total["total"])

    @staticmethod
    def _asset_library_sales_classification_filter(classification: str | None):
        value = str(classification or "").strip().upper()
        if value == "SESSION":
            return "COALESCE(d.selling_mode, 'SESSION')='SESSION'"
        if value == "CHAT":
            return "d.selling_mode='BUNDLE' AND COALESCE(d.bundle_sales_channel, 'CHAT')='CHAT'"
        if value == "CHAT_DESTINATION":
            return "(COALESCE(d.selling_mode, 'SESSION')='SESSION' OR (d.selling_mode='BUNDLE' AND COALESCE(d.bundle_sales_channel, 'CHAT')='CHAT'))"
        if value == "WALL":
            return "d.selling_mode='BUNDLE' AND d.bundle_sales_channel='CONTENT_WALL'"
        return None

    def list_asset_library(self, creator_profile_id: int, *, search: str | None = None, classification: str | None = None, limit: int | None = None):
        filters = ["d.creator_profile_id=%s", "d.registration_state='IN_ASSET_LIBRARY'", "d.is_archived=FALSE"]
        params = [creator_profile_id]
        if search:
            filters.append("(COALESCE(NULLIF(BTRIM(i.commercial_title), ''), d.display_name) ILIKE %s OR COALESCE(NULLIF(BTRIM(i.commercial_summary), ''), '') ILIKE %s)")
            term = f"%{search.strip()}%"
            params.extend((term, term))
        classification_filter = self._asset_library_sales_classification_filter(classification)
        if classification_filter:
            filters.append(f"({classification_filter})")
        suffix = " LIMIT %s OFFSET 0" if limit is not None else ""
        if limit is not None:
            params.append(max(0, int(limit)))
        return self._all(f"""SELECT d.*,i.profile_data AS intelligence_profile,w.current_stage AS workflow_stage, {self.DISPLAY_COLUMNS}
            FROM public.photoshoot_commerce_deliverables d
            LEFT JOIN public.photoshoot_intelligence_profiles i USING (photoshoot_session_id)
            LEFT JOIN public.photoshoot_analysis_workflows w USING (deliverable_id)
            WHERE {' AND '.join(filters)}
            ORDER BY COALESCE(d.updated_at, d.completed_at) DESC NULLS LAST, d.deliverable_id DESC{suffix}""", tuple(params))

    def count_asset_library(self, creator_profile_id: int, *, search: str | None = None, classification: str | None = None) -> int:
        filters = ["d.creator_profile_id=%s", "d.registration_state='IN_ASSET_LIBRARY'", "d.is_archived=FALSE"]
        params = [creator_profile_id]
        if search:
            filters.append("(COALESCE(NULLIF(BTRIM(i.commercial_title), ''), d.display_name) ILIKE %s OR COALESCE(NULLIF(BTRIM(i.commercial_summary), ''), '') ILIKE %s)")
            term = f"%{search.strip()}%"
            params.extend((term, term))
        classification_filter = self._asset_library_sales_classification_filter(classification)
        if classification_filter:
            filters.append(f"({classification_filter})")
        row = self._one(f"""SELECT COUNT(*) AS total FROM public.photoshoot_commerce_deliverables d
            LEFT JOIN public.photoshoot_intelligence_profiles i USING (photoshoot_session_id)
            WHERE {' AND '.join(filters)}""", tuple(params))
        return int(row["total"] if row else 0)

    def list_asset_library_cards(self, creator_profile_id: int, *, search: str | None = None,
                                 classification: str | None = None,
                                 limit: int | None = None):
        """Return persisted card status without invoking sale-preparation services."""
        filters = ["d.creator_profile_id=%s", "d.registration_state='IN_ASSET_LIBRARY'", "d.is_archived=FALSE"]
        params = [creator_profile_id]
        if search:
            filters.append("(COALESCE(NULLIF(BTRIM(i.commercial_title),''),d.display_name) ILIKE %s OR COALESCE(NULLIF(BTRIM(i.commercial_summary),''),'') ILIKE %s)")
            term = f"%{search.strip()}%"; params.extend((term, term))
        classification_filter = self._asset_library_sales_classification_filter(classification)
        if classification_filter: filters.append(f"({classification_filter})")
        suffix = " LIMIT %s OFFSET 0" if limit is not None else ""
        if limit is not None: params.append(max(0, int(limit)))
        return self._all(f"""
            SELECT d.deliverable_id,d.photoshoot_session_id,d.creator_profile_id,
                   d.display_name,d.completed_at,d.updated_at,d.hero_asset_id,d.shot_count,
                   d.selling_mode,d.bundle_sales_channel,d.source_kind,
                   COALESCE(NULLIF(BTRIM(i.commercial_title),''),d.display_name) AS display_title,
                   NULLIF(BTRIM(i.commercial_summary),'') AS display_description,
                   commerce.offering_count,commerce.ready_offering_count,
                   commerce.failed_publication_count,commerce.active_publication_count,
                   commerce.live_publication_count,commerce.wall_offering_id,
                   bundle_price.price_minor AS bundle_price_minor,
                   bundle_price.currency AS bundle_price_currency,
                   session_price.paid_step_count,session_price.priced_step_count,
                   session_price.total_minor AS session_total_minor,
                   session_price.currency AS session_price_currency
            FROM public.photoshoot_commerce_deliverables d
            LEFT JOIN public.photoshoot_intelligence_profiles i USING (photoshoot_session_id)
            LEFT JOIN LATERAL (
              SELECT COUNT(DISTINCT o.offering_id) AS offering_count,
                     COUNT(DISTINCT o.offering_id) FILTER (WHERE o.status='READY') AS ready_offering_count,
                     COUNT(DISTINCT p.publication_id) FILTER (WHERE p.status='FAILED') AS failed_publication_count,
                     COUNT(DISTINCT p.publication_id) FILTER (WHERE p.status IN ('READY_TO_PUBLISH','PUBLISHING')) AS active_publication_count,
                     COUNT(DISTINCT p.publication_id) FILTER (WHERE p.status='LIVE' AND p.provider_resource_status='PRESENT') AS live_publication_count,
                     MAX(o.offering_id::text) FILTER (WHERE o.offering_type='BUNDLE' AND o.primary_sales_channel='TELEGRAM_WALL') AS wall_offering_id
              FROM public.commercial_offerings o
              LEFT JOIN public.commercial_publications p ON p.commercial_offering_id=o.offering_id AND p.provider='FANVUE'
              WHERE o.source_photoshoot_deliverable_id=d.deliverable_id AND o.status<>'ARCHIVED'
            ) commerce ON TRUE
            LEFT JOIN LATERAL (
              SELECT o.price_minor,o.currency
              FROM public.commercial_offerings o
              WHERE o.source_photoshoot_deliverable_id=d.deliverable_id
                AND o.offering_type='BUNDLE' AND o.status<>'ARCHIVED'
              ORDER BY o.updated_at DESC,o.offering_id DESC LIMIT 1
            ) bundle_price ON d.selling_mode='BUNDLE'
            LEFT JOIN LATERAL (
              SELECT COUNT(*)::int AS paid_step_count,
                     COUNT(step_price.price_minor)::int AS priced_step_count,
                     CASE WHEN COUNT(*)>0
                                AND COUNT(step_price.price_minor)=COUNT(*)
                                AND COUNT(DISTINCT step_price.currency)=1
                          THEN SUM(step_price.price_minor)::bigint END AS total_minor,
                     CASE WHEN COUNT(DISTINCT step_price.currency)=1
                          THEN MIN(step_price.currency) END AS currency
              FROM LATERAL (
                SELECT strategy_data
                FROM public.photoshoot_session_sales_strategies
                WHERE photoshoot_session_id=d.photoshoot_session_id AND status='READY'
                ORDER BY generated_at DESC,strategy_version DESC LIMIT 1
              ) strategy
              CROSS JOIN LATERAL jsonb_array_elements(
                COALESCE(strategy.strategy_data->'shots','[]'::jsonb)
              ) shot
              LEFT JOIN LATERAL (
                SELECT o.price_minor,o.currency
                FROM public.commercial_offering_assets oa
                JOIN public.commercial_offerings o ON o.offering_id=oa.offering_id
                WHERE oa.asset_id=(shot->>'asset_id')::bigint
                  AND o.source_photoshoot_deliverable_id=d.deliverable_id
                  AND o.offering_type='SINGLE_IMAGE' AND o.status<>'ARCHIVED'
                ORDER BY o.updated_at DESC,o.offering_id DESC LIMIT 1
              ) step_price ON TRUE
              WHERE UPPER(COALESCE(shot->>'access_recommendation',''))='PAID'
            ) session_price ON d.selling_mode='SESSION'
            WHERE {' AND '.join(filters)}
            ORDER BY COALESCE(d.updated_at,d.completed_at) DESC NULLS LAST,d.deliverable_id DESC{suffix}
        """, tuple(params))

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

    def update_selling_mode(self, deliverable_id: str, creator_profile_id: int, selling_mode: str):
        """Persist an operator-selected mode when no immutable commerce evidence exists."""
        return self._one("""UPDATE public.photoshoot_commerce_deliverables deliverable
            SET selling_mode=%s,
                bundle_sales_channel=CASE WHEN %s='BUNDLE'
                    THEN COALESCE(bundle_sales_channel,'CHAT')
                    ELSE bundle_sales_channel END,
                updated_at=now()
            WHERE deliverable.deliverable_id=%s
              AND deliverable.creator_profile_id=%s
              AND deliverable.is_archived=FALSE
              AND NOT EXISTS (
                SELECT 1 FROM public.commercial_offerings offering
                JOIN public.commercial_publications publication
                  ON publication.commercial_offering_id=offering.offering_id
                WHERE offering.source_photoshoot_deliverable_id=deliverable.deliverable_id
                  AND publication.status='LIVE'
                  AND publication.provider_resource_status='PRESENT'
              )
              AND NOT EXISTS (
                SELECT 1 FROM public.commercial_offerings offering
                JOIN public.purchase_intents intent
                  ON intent.commercial_offering_id=offering.offering_id
                WHERE offering.source_photoshoot_deliverable_id=deliverable.deliverable_id
                  AND intent.status='PURCHASED'
              )
            RETURNING deliverable.*""",
            (selling_mode, selling_mode, deliverable_id, creator_profile_id))

    def selling_mode_reassignment_blockers(self, deliverable_id: str, creator_profile_id: int):
        """Return customer/commercial evidence that makes product-type mutation unsafe."""
        return self._one("""SELECT
            COUNT(DISTINCT offering.offering_id) AS offering_count,
            COUNT(DISTINCT publication.publication_id) AS publication_count,
            COUNT(DISTINCT intent.purchase_intent_id) AS purchase_intent_count,
            COUNT(DISTINCT lifecycle.lifecycle_id) AS lifecycle_count,
            COUNT(DISTINCT lifecycle_event.event_id) AS lifecycle_event_count,
            COUNT(DISTINCT sales_session.sales_session_id) AS sales_session_count,
            COUNT(DISTINCT teaser.deliverable_id) AS teaser_count
          FROM public.photoshoot_commerce_deliverables deliverable
          LEFT JOIN public.commercial_offerings offering
            ON offering.source_photoshoot_deliverable_id=deliverable.deliverable_id
           AND offering.status<>'ARCHIVED'
          LEFT JOIN public.commercial_publications publication
            ON publication.commercial_offering_id=offering.offering_id
           AND publication.status<>'ARCHIVED'
          LEFT JOIN public.purchase_intents intent
            ON intent.commercial_offering_id=offering.offering_id
          LEFT JOIN public.customer_photoshoot_lifecycles lifecycle
            ON lifecycle.photoshoot_id=deliverable.photoshoot_session_id
           AND lifecycle.creator_profile_id=deliverable.creator_profile_id
          LEFT JOIN public.customer_photoshoot_lifecycle_events lifecycle_event
            ON lifecycle_event.lifecycle_id=lifecycle.lifecycle_id
          LEFT JOIN public.sales_sessions sales_session
            ON sales_session.creator_profile_id=deliverable.creator_profile_id
           AND sales_session.commercial_foundation_type='PHOTOSHOOT'
           AND sales_session.commercial_foundation_reference IN (
                deliverable.photoshoot_session_id,deliverable.deliverable_id::text)
          LEFT JOIN public.photoshoot_bundle_teasers teaser
            ON teaser.deliverable_id=deliverable.deliverable_id
          WHERE deliverable.deliverable_id=%s AND deliverable.creator_profile_id=%s
          GROUP BY deliverable.deliverable_id""", (deliverable_id, int(creator_profile_id)))

    def reassign_selling_mode(self, deliverable_id: str, creator_profile_id: int, selling_mode: str):
        """Atomically guard, reclassify, and invalidate old mode-specific planning."""
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT * FROM public.photoshoot_commerce_deliverables
                WHERE deliverable_id=%s AND creator_profile_id=%s AND is_archived=FALSE
                FOR UPDATE""", (deliverable_id, int(creator_profile_id)))
            deliverable = cursor.fetchone()
            if deliverable is None:
                return None, {}
            cursor.execute("""SELECT
                (SELECT COUNT(*) FROM public.commercial_offerings o
                  WHERE o.source_photoshoot_deliverable_id=%s AND o.status<>'ARCHIVED') AS offering_count,
                (SELECT COUNT(*) FROM public.commercial_publications p JOIN public.commercial_offerings o
                  ON o.offering_id=p.commercial_offering_id
                  WHERE o.source_photoshoot_deliverable_id=%s AND p.status<>'ARCHIVED'
                    AND (p.status IN ('READY_TO_PUBLISH','PUBLISHING','LIVE')
                      OR p.external_product_id IS NOT NULL
                      OR COALESCE(p.provider_resource_status,'')='PRESENT')) AS publication_count,
                (SELECT COUNT(*) FROM public.purchase_intents i JOIN public.commercial_offerings o
                  ON o.offering_id=i.commercial_offering_id
                  WHERE o.source_photoshoot_deliverable_id=%s) AS purchase_intent_count,
                (SELECT COUNT(*) FROM public.customer_photoshoot_lifecycles l
                  WHERE l.photoshoot_id=%s AND l.creator_profile_id=%s) AS lifecycle_count,
                (SELECT COUNT(*) FROM public.customer_photoshoot_lifecycle_events e
                  JOIN public.customer_photoshoot_lifecycles l USING(lifecycle_id)
                  WHERE l.photoshoot_id=%s AND l.creator_profile_id=%s) AS lifecycle_event_count,
                (SELECT COUNT(*) FROM public.sales_sessions s WHERE s.creator_profile_id=%s
                  AND s.commercial_foundation_type='PHOTOSHOOT'
                  AND s.commercial_foundation_reference IN (%s,%s)) AS sales_session_count,
                (SELECT COUNT(*) FROM public.photoshoot_bundle_teasers t
                  WHERE t.deliverable_id=%s) AS teaser_count""",
                (deliverable_id, deliverable_id, deliverable_id,
                 deliverable["photoshoot_session_id"], int(creator_profile_id),
                 deliverable["photoshoot_session_id"], int(creator_profile_id),
                 int(creator_profile_id), deliverable["photoshoot_session_id"],
                 str(deliverable_id), deliverable_id))
            blockers = dict(cursor.fetchone())
            protected_keys = (
                "publication_count", "purchase_intent_count", "lifecycle_count",
                "lifecycle_event_count", "sales_session_count",
            )
            if any(int(blockers.get(key) or 0) > 0 for key in protected_keys):
                return None, blockers
            cursor.execute("""UPDATE public.commercial_publications publication
                SET status='ARCHIVED',updated_at=now()
                FROM public.commercial_offerings offering
                WHERE publication.commercial_offering_id=offering.offering_id
                  AND offering.source_photoshoot_deliverable_id=%s
                  AND publication.status<>'ARCHIVED'""", (deliverable_id,))
            cursor.execute("""UPDATE public.commercial_offerings
                SET status='ARCHIVED',updated_at=now()
                WHERE source_photoshoot_deliverable_id=%s AND status<>'ARCHIVED'""",
                (deliverable_id,))
            cursor.execute("DELETE FROM public.photoshoot_bundle_teasers WHERE deliverable_id=%s", (deliverable_id,))
            cursor.execute("""UPDATE public.photoshoot_commerce_deliverables SET
                selling_mode=%s,
                bundle_sales_channel=CASE WHEN %s='BUNDLE'
                    THEN COALESCE(bundle_sales_channel,'CHAT') ELSE NULL END,
                updated_at=now()
                WHERE deliverable_id=%s AND creator_profile_id=%s RETURNING *""",
                (selling_mode, selling_mode, deliverable_id, int(creator_profile_id)))
            updated = dict(cursor.fetchone())
            cursor.execute("""UPDATE public.photoshoot_session_sales_strategies
                SET status='FAILED',updated_at=now()
                WHERE deliverable_id=%s AND creator_profile_id=%s AND status='READY'""",
                (deliverable_id, int(creator_profile_id)))
            return updated, blockers

    def invalidate_session_sales_strategies(self, deliverable_id: str, creator_profile_id: int):
        """Invalidate only the old mode-specific strategy; preserve intelligence and media."""
        return self._all("""UPDATE public.photoshoot_session_sales_strategies strategy
            SET status='FAILED',updated_at=now()
            FROM public.photoshoot_commerce_deliverables deliverable
            WHERE strategy.deliverable_id=deliverable.deliverable_id
              AND deliverable.deliverable_id=%s
              AND deliverable.creator_profile_id=%s
              AND strategy.status='READY'
            RETURNING strategy.*""", (deliverable_id, int(creator_profile_id)))

    def update_bundle_sales_channel(self, deliverable_id: str,
                                    creator_profile_id: int, channel: str):
        """Persist the Bundle channel and keep its reusable offering projection aligned."""
        offering_channel = "TELEGRAM_WALL" if channel == "CONTENT_WALL" else "AI_CHAT"
        return self._one("""WITH updated_deliverable AS (
            UPDATE public.photoshoot_commerce_deliverables deliverable
            SET bundle_sales_channel=%s,updated_at=now()
            WHERE deliverable.deliverable_id=%s
              AND deliverable.creator_profile_id=%s
              AND deliverable.selling_mode='BUNDLE'
              AND deliverable.is_archived=FALSE
              AND NOT EXISTS (
                SELECT 1
                FROM public.customer_photoshoot_lifecycles lifecycle
                JOIN public.customer_photoshoot_lifecycle_events event
                  ON event.lifecycle_id=lifecycle.lifecycle_id
                WHERE lifecycle.photoshoot_id=deliverable.photoshoot_session_id
                  AND lifecycle.creator_profile_id=deliverable.creator_profile_id
                  AND event.event_type IN (
                    'BUNDLE_TEASER_PRESENTED','BUNDLE_OFFER_PRESENTED'
                  )
              )
              AND NOT EXISTS (
                SELECT 1 FROM public.commercial_offerings offering
                JOIN public.purchase_intents intent
                  ON intent.commercial_offering_id=offering.offering_id
                WHERE offering.source_photoshoot_deliverable_id=deliverable.deliverable_id
                  AND offering.offering_type='BUNDLE'
              )
            RETURNING deliverable.*
          ), updated_offerings AS (
            UPDATE public.commercial_offerings offering
            SET primary_sales_channel=%s,updated_at=now()
            FROM updated_deliverable deliverable
            WHERE offering.source_photoshoot_deliverable_id=deliverable.deliverable_id
              AND offering.status<>'ARCHIVED'
            RETURNING offering.offering_id
          )
          SELECT * FROM updated_deliverable""",
            (channel, deliverable_id, creator_profile_id, offering_channel))

    def has_bundle_channel_use_evidence(self, deliverable_id: str,
                                        creator_profile_id: int) -> bool:
        row = self._one("""SELECT EXISTS (
            SELECT 1 FROM public.photoshoot_commerce_deliverables deliverable
            WHERE deliverable.deliverable_id=%s
              AND deliverable.creator_profile_id=%s
              AND (
                EXISTS (
                  SELECT 1 FROM public.customer_photoshoot_lifecycles lifecycle
                  JOIN public.customer_photoshoot_lifecycle_events event
                    ON event.lifecycle_id=lifecycle.lifecycle_id
                  WHERE lifecycle.photoshoot_id=deliverable.photoshoot_session_id
                    AND lifecycle.creator_profile_id=deliverable.creator_profile_id
                    AND event.event_type IN (
                      'BUNDLE_TEASER_PRESENTED','BUNDLE_OFFER_PRESENTED'
                    )
                ) OR EXISTS (
                  SELECT 1 FROM public.commercial_offerings offering
                  JOIN public.purchase_intents intent
                    ON intent.commercial_offering_id=offering.offering_id
                  WHERE offering.source_photoshoot_deliverable_id=deliverable.deliverable_id
                    AND offering.offering_type='BUNDLE'
                )
              )
        ) AS protected""", (deliverable_id, creator_profile_id))
        return bool(row and row["protected"])

    def has_protected_commercial_evidence(self, deliverable_id: str, creator_profile_id: int) -> bool:
        row = self._one("""SELECT EXISTS (
              SELECT 1 FROM public.commercial_offerings offering
              LEFT JOIN public.commercial_publications publication
                ON publication.commercial_offering_id=offering.offering_id
              LEFT JOIN public.purchase_intents intent
                ON intent.commercial_offering_id=offering.offering_id
              WHERE offering.source_photoshoot_deliverable_id=%s
                AND offering.creator_profile_id=%s
                AND ((publication.status='LIVE' AND publication.provider_resource_status='PRESENT')
                     OR intent.status='PURCHASED')
            ) AS protected""", (deliverable_id, creator_profile_id))
        return bool(row and row["protected"])

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

    def content_intelligence_for_assets(self, asset_ids):
        """Return canonical per-Asset intelligence without requiring Photoshoot lineage."""
        values = tuple(int(value) for value in asset_ids)
        if not values:
            return ()
        return self._all("""SELECT c.id AS asset_id,ci.content_profile,
                ci.normalized_context,ci.status AS content_intelligence_status
            FROM public.content_items c
            LEFT JOIN public.content_intelligence_profiles ci ON ci.asset_id=c.id
            WHERE c.id=ANY(%s) ORDER BY array_position(%s::bigint[],c.id)""",
            (list(values), list(values)))

    def member_curation_blockers(self, deliverable_id: str, creator_profile_id: int):
        """Return immutable commerce evidence that prevents membership mutation."""
        return self._one("""SELECT
            COUNT(DISTINCT offering.offering_id) AS offering_count,
            COUNT(DISTINCT publication.publication_id) AS publication_count,
            COUNT(DISTINCT intent.purchase_intent_id) AS purchase_count,
            COUNT(DISTINCT teaser.deliverable_id) AS teaser_count,
            COUNT(DISTINCT lifecycle.lifecycle_id) AS lifecycle_count
          FROM public.photoshoot_commerce_deliverables deliverable
          LEFT JOIN public.commercial_offerings offering
            ON offering.source_photoshoot_deliverable_id=deliverable.deliverable_id
           AND offering.status<>'ARCHIVED'
          LEFT JOIN public.commercial_publications publication
            ON publication.commercial_offering_id=offering.offering_id
          LEFT JOIN public.purchase_intents intent
            ON intent.commercial_offering_id=offering.offering_id
          LEFT JOIN public.photoshoot_bundle_teasers teaser
            ON teaser.deliverable_id=deliverable.deliverable_id
          LEFT JOIN public.customer_photoshoot_lifecycles lifecycle
            ON lifecycle.photoshoot_id=deliverable.photoshoot_session_id
           AND lifecycle.creator_profile_id=deliverable.creator_profile_id
          WHERE deliverable.deliverable_id=%s AND deliverable.creator_profile_id=%s
          GROUP BY deliverable.deliverable_id""", (deliverable_id, int(creator_profile_id)))

    def extracted_assets_are_standalone(self, asset_ids, creator_profile_id: int) -> bool:
        ids = tuple(int(value) for value in asset_ids)
        if not ids:
            return False
        row = self._one("""SELECT COUNT(*) AS total FROM public.content_items
            WHERE id=ANY(%s) AND creator_profile_id=%s AND classification='SINGLE_IMAGE'
              AND status='approved' AND COALESCE(is_active,TRUE)=TRUE""",
            (list(ids), int(creator_profile_id)))
        return bool(row and int(row["total"] or 0) == len(ids))

    def apply_member_extraction(self, *, deliverable_id: str, creator_profile_id: int,
                                asset_ids, intelligence_version: str, intelligence_profile: dict):
        """Atomically promote members to standalone Images and reconcile the set."""
        selected = tuple(int(value) for value in asset_ids)
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT * FROM public.photoshoot_commerce_deliverables
                WHERE deliverable_id=%s AND creator_profile_id=%s AND is_archived=FALSE
                FOR UPDATE""", (deliverable_id, int(creator_profile_id)))
            deliverable = cursor.fetchone()
            if deliverable is None:
                raise KeyError("Photoshoot not found.")
            cursor.execute("""SELECT
                EXISTS(SELECT 1 FROM public.commercial_offerings o
                  WHERE o.source_photoshoot_deliverable_id=%s AND o.status<>'ARCHIVED')
                OR EXISTS(SELECT 1 FROM public.photoshoot_bundle_teasers t WHERE t.deliverable_id=%s)
                OR EXISTS(SELECT 1 FROM public.customer_photoshoot_lifecycles l
                  WHERE l.photoshoot_id=%s AND l.creator_profile_id=%s) AS protected""",
                (deliverable_id, deliverable_id, deliverable["photoshoot_session_id"],
                 int(creator_profile_id)))
            if bool(cursor.fetchone()["protected"]):
                raise ValueError("This Photoshoot has commercial activity and its members cannot be changed.")
            cursor.execute("""SELECT asset_id,shot_order,is_hero FROM public.photoshoot_asset_memberships
                WHERE photoshoot_session_id=%s AND approved=TRUE ORDER BY shot_order FOR UPDATE""",
                (deliverable["photoshoot_session_id"],))
            members = tuple(dict(row) for row in cursor.fetchall())
            member_ids = tuple(int(row["asset_id"]) for row in members)
            if any(value not in member_ids for value in selected):
                raise ValueError("One or more selected Assets are not members of this Photoshoot.")
            remaining = tuple(value for value in member_ids if value not in set(selected))
            if len(remaining) < 2:
                raise ValueError("A Photoshoot must retain at least 2 images.")
            hero_asset_id = int(deliverable["hero_asset_id"]) if deliverable.get("hero_asset_id") else None
            if hero_asset_id not in remaining:
                hero_asset_id = remaining[0]
            cursor.execute("""UPDATE public.content_items SET classification='SINGLE_IMAGE',updated_at=NOW()
                WHERE id=ANY(%s) AND creator_profile_id=%s""", (list(selected), int(creator_profile_id)))
            if cursor.rowcount != len(selected):
                raise ValueError("Selected Assets could not be promoted to standalone Images.")
            cursor.execute("""DELETE FROM public.photoshoot_asset_memberships
                WHERE photoshoot_session_id=%s AND asset_id=ANY(%s)""",
                (deliverable["photoshoot_session_id"], list(selected)))
            cursor.execute(
                """DELETE FROM public.generation_image_dispositions disposition
                   USING public.assembled_photoshoot_intake_members intake_member
                   WHERE disposition.image_id=intake_member.image_id
                     AND disposition.owner='PHOTOSHOOT'
                     AND disposition.owner_id=intake_member.intake_id
                     AND intake_member.asset_id=ANY(%s)""",
                (list(selected),),
            )
            cursor.execute("""UPDATE public.photoshoot_asset_memberships SET
                shot_order=shot_order+10000,is_hero=FALSE,updated_at=NOW()
                WHERE photoshoot_session_id=%s AND approved=TRUE""",
                (deliverable["photoshoot_session_id"],))
            cursor.execute("""WITH ordered AS (
                  SELECT asset_id,ROW_NUMBER() OVER (ORDER BY shot_order) AS next_order
                  FROM public.photoshoot_asset_memberships
                  WHERE photoshoot_session_id=%s AND approved=TRUE)
                UPDATE public.photoshoot_asset_memberships membership SET
                  shot_order=ordered.next_order,is_hero=(membership.asset_id=%s),updated_at=NOW()
                FROM ordered WHERE membership.photoshoot_session_id=%s
                  AND membership.asset_id=ordered.asset_id""",
                (deliverable["photoshoot_session_id"], hero_asset_id,
                 deliverable["photoshoot_session_id"]))
            cursor.execute("""DELETE FROM public.photoshoot_shot_intelligence_profiles
                WHERE photoshoot_session_id=%s
                  AND (intelligence_version<>%s OR asset_id=ANY(%s))""",
                (deliverable["photoshoot_session_id"], intelligence_version, list(selected)))
            self._persist_canonical_intelligence(
                cursor, str(deliverable["photoshoot_session_id"]),
                intelligence_version, intelligence_profile)
            cursor.execute("""UPDATE public.photoshoot_commerce_deliverables SET
                ordered_member_asset_ids=%s::jsonb,shot_count=%s,hero_asset_id=%s,
                intelligence_status='READY',commerce_status='READY',updated_at=NOW()
                WHERE deliverable_id=%s RETURNING *""",
                (json.dumps(remaining), len(remaining), hero_asset_id, deliverable_id))
            updated = dict(cursor.fetchone())
        return {"deliverable": updated, "remaining_asset_ids": remaining,
                "hero_asset_id": hero_asset_id}

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
