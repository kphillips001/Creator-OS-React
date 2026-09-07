"""Canonical ordered progression and idempotent next-action persistence."""
import json
from uuid import uuid4
from app.database import get_db_connection
from app.models.autonomous_sales_progression import ProgressionAssetRole,SellableProgressionAsset


class AutonomousSalesProgressionRepository:
    def __init__(self,connection_factory=get_db_connection): self.connection_factory=connection_factory
    def ordered_assets(self,*,creator_profile_id,customer_commerce_profile_id,photoshoot_id):
        with self.connection_factory() as c:
            with c.cursor() as q:
                q.execute("""SELECT m.asset_id,
                    COALESCE((strategy_shot.value->>'sales_position')::integer,m.shot_order) shot_order,
                    ci.content_type,
                    COALESCE(
                      CASE
                        WHEN strategy_shot.value->>'access_recommendation'='FREE' THEN 'DISCOVERY'
                        WHEN strategy_shot.value->>'sales_role'='FINALE' THEN 'FINALE_IMAGE'
                        WHEN strategy_shot.value IS NOT NULL THEN 'CORE_SESSION'
                      END,
                      r.role,
                      CASE WHEN ci.content_type ILIKE %s THEN 'FINALE_VIDEO' WHEN ci.content_type ILIKE %s THEN 'DISCOVERY' ELSE 'CORE_SESSION' END
                    ) role,
                    CASE WHEN strategy_shot.value IS NULL THEN '{}'::jsonb ELSE
                      jsonb_build_object(
                        'strategy_version',session_strategy.strategy_version,
                        'recommended_customer_entry_point',session_strategy.strategy_data->>'recommended_customer_entry_point',
                        'session_completion_strategy',session_strategy.strategy_data->>'session_completion_strategy',
                        'customer_engagement_strategy',session_strategy.strategy_data->>'customer_engagement_strategy',
                        'escalation_pacing',session_strategy.strategy_data->>'escalation_pacing',
                        'overall_selling_approach',session_strategy.strategy_data->>'overall_selling_approach',
                        'shot',strategy_shot.value
                      ) END session_sales_strategy,
                    o.offering_id,p.publication_id,p.publication_metadata#>>'{media_link,url}' delivery_url,o.price_minor,o.currency,
                    EXISTS(SELECT 1 FROM public.customer_photoshoot_lifecycle_events e JOIN public.customer_photoshoot_lifecycles l ON l.lifecycle_id=e.lifecycle_id WHERE l.creator_profile_id=%s AND l.customer_commerce_profile_id=%s AND l.photoshoot_id=%s AND e.asset_id=m.asset_id AND e.event_type='PURCHASED') owned,
                    EXISTS(SELECT 1 FROM public.customer_photoshoot_lifecycle_events e JOIN public.customer_photoshoot_lifecycles l ON l.lifecycle_id=e.lifecycle_id WHERE l.creator_profile_id=%s AND l.customer_commerce_profile_id=%s AND l.photoshoot_id=%s AND e.asset_id=m.asset_id AND e.event_type='PRESENTED') presented
                    FROM public.photoshoot_asset_memberships m JOIN public.content_items ci ON ci.id=m.asset_id
                    LEFT JOIN LATERAL (
                      SELECT strategy_version,strategy_data FROM public.photoshoot_session_sales_strategies
                      WHERE photoshoot_session_id=m.photoshoot_session_id AND status='READY'
                      ORDER BY generated_at DESC,strategy_version DESC LIMIT 1
                    ) session_strategy ON TRUE
                    LEFT JOIN LATERAL (
                      SELECT value FROM jsonb_array_elements(COALESCE(session_strategy.strategy_data->'shots','[]'::jsonb))
                      WHERE (value->>'asset_id')::bigint=m.asset_id LIMIT 1
                    ) strategy_shot ON TRUE
                    LEFT JOIN LATERAL (SELECT role FROM public.commercial_role_assignments WHERE asset_id=m.asset_id AND creator_profile_id=%s AND state='APPROVED' ORDER BY CASE role WHEN 'TEASER' THEN 1 WHEN 'DISCOVERY' THEN 1 WHEN 'CORE_SESSION' THEN 2 WHEN 'CORE' THEN 2 WHEN 'PROGRESSION' THEN 2 WHEN 'FINALE_IMAGE' THEN 3 WHEN 'FINALE' THEN 3 WHEN 'FINALE_VIDEO' THEN 4 ELSE 5 END LIMIT 1) r ON TRUE
                    LEFT JOIN LATERAL (SELECT co.* FROM public.commercial_offering_assets coa JOIN public.commercial_offerings co ON co.offering_id=coa.offering_id WHERE coa.asset_id=m.asset_id AND co.creator_profile_id=%s AND co.status='READY' AND EXISTS (SELECT 1 FROM public.commercial_publications ready_publication WHERE ready_publication.commercial_offering_id=co.offering_id AND ready_publication.status='LIVE' AND ready_publication.provider_resource_status='PRESENT' AND COALESCE(ready_publication.publication_metadata#>>'{media_link,url}','')<>'') ORDER BY CASE WHEN EXISTS (SELECT 1 FROM public.commercial_publications canonical_publication WHERE canonical_publication.commercial_offering_id=co.offering_id AND canonical_publication.publication_metadata->>'source_workflow'='photoshoot_session_sale_preparation') THEN 0 ELSE 1 END,CASE co.offering_type WHEN 'SINGLE_IMAGE' THEN 1 WHEN 'VIDEO' THEN 1 ELSE 2 END,co.created_at DESC LIMIT 1) o ON TRUE
                    LEFT JOIN LATERAL (SELECT * FROM public.commercial_publications WHERE commercial_offering_id=o.offering_id AND status='LIVE' AND provider_resource_status='PRESENT' ORDER BY published_at DESC LIMIT 1) p ON TRUE
                    WHERE m.photoshoot_session_id::text=%s AND m.approved=TRUE
                    ORDER BY COALESCE((strategy_shot.value->>'sales_position')::integer,m.shot_order),m.asset_id""",('video%','teaser%',creator_profile_id,customer_commerce_profile_id,str(photoshoot_id),creator_profile_id,customer_commerce_profile_id,str(photoshoot_id),creator_profile_id,creator_profile_id,str(photoshoot_id))); rows=q.fetchall()
        return tuple(self._asset(r) for r in rows)

    def pre_session_free_teaser_candidates(self, *, creator_profile_id):
        """Return canonical READY Session graphs that begin with a free teaser.

        This is inventory authority only. It neither creates paid commerce nor
        claims that media was delivered.
        """
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT strategy.photoshoot_session_id,
                           strategy.strategy_version,strategy.strategy_data,
                           deliverable.deliverable_id
                    FROM public.photoshoot_session_sales_strategies strategy
                    JOIN public.photoshoot_commerce_deliverables deliverable
                      ON deliverable.deliverable_id=strategy.deliverable_id
                    WHERE strategy.creator_profile_id=%s
                      AND strategy.status='READY'
                      AND deliverable.selling_mode='SESSION'
                      AND deliverable.intelligence_status='READY'
                      AND deliverable.commerce_status='READY'
                      AND deliverable.is_active=TRUE
                      AND deliverable.is_archived=FALSE
                    ORDER BY strategy.photoshoot_session_id,
                             strategy.generated_at DESC,
                             strategy.strategy_version DESC""",
                    (creator_profile_id,))
                strategies = cursor.fetchall()
                candidates = []
                seen = set()
                for row in strategies:
                    foundation = str(row["photoshoot_session_id"])
                    if foundation in seen:
                        continue
                    seen.add(foundation)
                    shots = sorted(
                        (dict(value) for value in
                         dict(row.get("strategy_data") or {}).get("shots") or ()),
                        key=lambda value: int(value.get("sales_position") or 0),
                    )
                    if len(shots) < 2:
                        continue
                    teaser, next_step = shots[0], shots[1]
                    if not (
                        int(teaser.get("sales_position") or 0) == 1
                        and str(teaser.get("sales_role") or "") == "FREE_TEASER"
                        and str(teaser.get("access_recommendation") or "") == "FREE"
                        and teaser.get("asset_id") is not None
                        and int(next_step.get("sales_position") or 0) == 2
                        and str(next_step.get("sales_role") or "") == "FIRST_UNLOCK"
                        and str(next_step.get("access_recommendation") or "") == "PAID"
                        and next_step.get("asset_id") is not None
                    ):
                        continue
                    cursor.execute("""SELECT offering.offering_id,
                               publication.publication_id,offering.price_minor,
                               offering.currency
                        FROM public.photoshoot_asset_memberships membership
                        JOIN public.commercial_offering_assets member
                          ON member.asset_id=membership.asset_id
                        JOIN public.commercial_offerings offering
                          ON offering.offering_id=member.offering_id
                         AND offering.creator_profile_id=%s
                         AND offering.status='READY'
                         AND offering.price_minor>0
                        JOIN public.commercial_publications publication
                          ON publication.commercial_offering_id=offering.offering_id
                         AND publication.status='LIVE'
                         AND publication.provider_resource_status='PRESENT'
                        WHERE membership.photoshoot_session_id=%s
                          AND membership.asset_id=%s
                          AND membership.approved=TRUE
                        ORDER BY publication.published_at DESC
                        LIMIT 2""", (creator_profile_id, foundation,
                                     int(next_step["asset_id"])))
                    paid = cursor.fetchall()
                    cursor.execute("""SELECT 1
                        FROM public.photoshoot_asset_memberships
                        WHERE photoshoot_session_id=%s AND asset_id=%s
                          AND approved=TRUE""",
                        (foundation, int(teaser["asset_id"])))
                    teaser_member = cursor.fetchone()
                    if teaser_member is None or len(paid) != 1:
                        continue
                    candidates.append({
                        "photoshoot_reference": foundation,
                        "strategy_version": str(row["strategy_version"]),
                        "deliverable_id": str(row["deliverable_id"]),
                        "teaser_asset_id": int(teaser["asset_id"]),
                        "teaser_position": 1,
                        "next_asset_id": int(next_step["asset_id"]),
                        "next_position": 2,
                        "next_sales_role": "FIRST_UNLOCK",
                        "next_offering_id": str(paid[0]["offering_id"]),
                        "next_publication_id": str(paid[0]["publication_id"]),
                        "next_price_minor": int(paid[0]["price_minor"]),
                        "currency": str(paid[0]["currency"]),
                    })
        return tuple(candidates)
    def claim_action(self,action):
        fingerprint=':'.join(str(v or '') for v in (action.customer_profile_id,action.action.value,action.current_photoshoot_id,action.target_photoshoot_id,action.selected_asset_id,action.purchase_intent_id))
        with self.connection_factory() as c:
            with c.cursor() as q:
                q.execute("SELECT lifecycle_id FROM public.customer_photoshoot_lifecycles WHERE lifecycle_id=%s FOR UPDATE",(action.active_lifecycle_id,))
                q.execute("SELECT * FROM public.autonomous_sales_actions WHERE customer_commerce_profile_id=%s AND completed_at IS NULL AND expires_at>NOW() ORDER BY created_at DESC LIMIT 1 FOR UPDATE",(action.customer_profile_id,)); existing=q.fetchone()
                if existing is not None: return existing
                q.execute("""INSERT INTO public.autonomous_sales_actions(action_id,creator_profile_id,customer_commerce_profile_id,lifecycle_id,action,action_fingerprint,decision,expires_at)
                    SELECT %s,l.creator_profile_id,%s,%s,%s,%s,%s::jsonb,NOW()+INTERVAL '30 minutes' FROM public.customer_photoshoot_lifecycles l WHERE l.lifecycle_id=%s
                    ON CONFLICT (customer_commerce_profile_id,action_fingerprint) DO UPDATE SET updated_at=NOW() RETURNING *""",(uuid4(),action.customer_profile_id,action.active_lifecycle_id,action.action.value,fingerprint,json.dumps(action.to_context()),action.active_lifecycle_id)); return q.fetchone()
    def recent_actions(self,*,creator_profile_id,customer_commerce_profile_id,limit=20):
        with self.connection_factory() as c:
            with c.cursor() as q: q.execute("SELECT decision FROM public.autonomous_sales_actions WHERE creator_profile_id=%s AND customer_commerce_profile_id=%s ORDER BY created_at DESC LIMIT %s",(creator_profile_id,customer_commerce_profile_id,limit)); return tuple(row['decision'] for row in q.fetchall())
    @staticmethod
    def _asset(r):
        raw=r['role']; role=ProgressionAssetRole.DISCOVERY if raw in {'TEASER','DISCOVERY'} else ProgressionAssetRole.FINALE_VIDEO if raw=='FINALE_VIDEO' else ProgressionAssetRole.FINALE_IMAGE if raw in {'FINALE','FINALE_IMAGE'} else ProgressionAssetRole.CORE_SESSION
        return SellableProgressionAsset(asset_id=r['asset_id'],position=r['shot_order'],role=role,offering_id=r['offering_id'],publication_id=r['publication_id'],delivery_url=r['delivery_url'],price_minor=r['price_minor'],currency=r['currency'],owned=r['owned'],presented=r['presented'],strategy=dict(r.get('session_sales_strategy') or {}))
