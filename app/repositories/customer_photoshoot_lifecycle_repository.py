"""PostgreSQL persistence for protected Photoshoot Sales Opportunities."""
import json
from datetime import datetime, timezone
from uuid import uuid4

from app.database import get_db_connection
from app.models.customer_photoshoot_lifecycle import (
    CustomerPhotoshootLifecycle, CustomerPhotoshootStatus, FinaleDecision,
)


class CustomerPhotoshootLifecycleRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def resolve(self, *, creator_profile_id, customer_commerce_profile_id, photoshoot_id,
                selected_offering_id=None, recommendation_reason=None, metadata=None):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""INSERT INTO public.customer_photoshoot_lifecycles
                    (lifecycle_id,creator_profile_id,customer_commerce_profile_id,photoshoot_id,status,
                     selected_offering_id,recommendation_reason,metadata,first_started_at,last_activity_at,expires_at)
                    VALUES (%s,%s,%s,%s,'ACTIVE',%s,%s,%s::jsonb,NOW(),NOW(),NOW()+INTERVAL '7 days')
                    ON CONFLICT (creator_profile_id,customer_commerce_profile_id,photoshoot_id)
                    DO UPDATE SET
                      selected_offering_id=CASE WHEN customer_photoshoot_lifecycles.status='ACTIVE'
                        THEN COALESCE(EXCLUDED.selected_offering_id,customer_photoshoot_lifecycles.selected_offering_id)
                        ELSE customer_photoshoot_lifecycles.selected_offering_id END,
                      recommendation_reason=CASE WHEN customer_photoshoot_lifecycles.status='ACTIVE'
                        THEN COALESCE(EXCLUDED.recommendation_reason,customer_photoshoot_lifecycles.recommendation_reason)
                        ELSE customer_photoshoot_lifecycles.recommendation_reason END,
                      metadata=CASE WHEN customer_photoshoot_lifecycles.status='ACTIVE'
                        THEN customer_photoshoot_lifecycles.metadata || EXCLUDED.metadata
                        ELSE customer_photoshoot_lifecycles.metadata END,
                      updated_at=NOW()
                    RETURNING *""", (
                        uuid4(), creator_profile_id, customer_commerce_profile_id,
                        str(photoshoot_id), selected_offering_id, recommendation_reason,
                        json.dumps(dict(metadata or {}), default=str),
                    ))
                row = cursor.fetchone()
        return self._model(row)

    def get(self, *, creator_profile_id, customer_commerce_profile_id, photoshoot_id):
        return self._one(
            "SELECT * FROM public.customer_photoshoot_lifecycles WHERE creator_profile_id=%s AND customer_commerce_profile_id=%s AND photoshoot_id=%s",
            (creator_profile_id, customer_commerce_profile_id, str(photoshoot_id)),
        )

    def get_by_id(self, lifecycle_id):
        return self._one(
            "SELECT * FROM public.customer_photoshoot_lifecycles WHERE lifecycle_id=%s",
            (lifecycle_id,),
        )

    def list_for_customer(self, *, creator_profile_id, customer_commerce_profile_id):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM public.customer_photoshoot_lifecycles WHERE creator_profile_id=%s AND customer_commerce_profile_id=%s ORDER BY last_activity_at DESC NULLS LAST,created_at DESC", (creator_profile_id, customer_commerce_profile_id))
                rows = cursor.fetchall()
        return tuple(self._model(row) for row in rows)

    def expire_due(self, *, creator_profile_id=None, customer_commerce_profile_id=None):
        conditions = ["status IN ('ACTIVE','OBJECTION')", "expires_at<=NOW()"]
        arguments = []
        if creator_profile_id is not None:
            conditions.append("creator_profile_id=%s"); arguments.append(creator_profile_id)
        if customer_commerce_profile_id is not None:
            conditions.append("customer_commerce_profile_id=%s"); arguments.append(customer_commerce_profile_id)
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"""WITH due AS (
                      SELECT lifecycle_id,status AS old_status
                      FROM public.customer_photoshoot_lifecycles
                      WHERE {' AND '.join(conditions)} FOR UPDATE
                    )
                    UPDATE public.customer_photoshoot_lifecycles opportunity
                    SET status='CLOSED',closed_at=NOW(),last_activity_at=NOW(),updated_at=NOW()
                    FROM due WHERE opportunity.lifecycle_id=due.lifecycle_id
                    RETURNING opportunity.*,due.old_status""", tuple(arguments))
                rows = cursor.fetchall()
                for row in rows:
                    cursor.execute("""INSERT INTO public.customer_photoshoot_lifecycle_events
                        (lifecycle_id,event_type,previous_status,new_status,metadata)
                        VALUES (%s,'OPPORTUNITY_EXPIRED',%s,'CLOSED','{}'::jsonb)""", (row["lifecycle_id"], row["old_status"]))
        return tuple(self._model(row) for row in rows)

    def transition(self, lifecycle_id, *, status, event_type, asset_id=None,
                   purchase_outcome_id=None, sales_session_id=None,
                   purchase_intent_id=None, metadata=None, provider=None,
                   provider_delivery_id=None):
        now = datetime.now(timezone.utc)
        detail = dict(metadata or {})
        finale_decision = detail.get("finale_decision")
        objection_delta = int(detail.get("objection_attempt_delta") or 0)
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM public.customer_photoshoot_lifecycles WHERE lifecycle_id=%s FOR UPDATE", (lifecycle_id,))
                old = cursor.fetchone()
                if not old:
                    return None
                cursor.execute("""UPDATE public.customer_photoshoot_lifecycles SET
                    status=%s,last_activity_at=%s,
                    completed_at=CASE WHEN %s='COMPLETED' THEN %s ELSE completed_at END,
                    closed_at=CASE WHEN %s='CLOSED' THEN %s ELSE closed_at END,
                    expires_at=CASE WHEN %s='ACTIVE' THEN %s+INTERVAL '7 days' ELSE expires_at END,
                    finale_decision=COALESCE(%s,finale_decision),
                    objection_at=CASE WHEN %s='OBJECTION' THEN COALESCE(objection_at,%s) ELSE objection_at END,
                    objection_attempts=objection_attempts+%s,
                    first_sales_session_id=COALESCE(first_sales_session_id,%s),
                    last_sales_session_id=COALESCE(%s,last_sales_session_id),
                    last_purchase_intent_id=COALESCE(%s,last_purchase_intent_id),updated_at=%s
                    WHERE lifecycle_id=%s RETURNING *""", (
                        status.value, now, status.value, now, status.value, now,
                        status.value, now, finale_decision, status.value, now,
                        objection_delta, sales_session_id,
                        sales_session_id, purchase_intent_id, now, lifecycle_id,
                    ))
                row = cursor.fetchone()
                cursor.execute("""INSERT INTO public.customer_photoshoot_lifecycle_events
                    (lifecycle_id,event_type,previous_status,new_status,asset_id,purchase_outcome_id,
                     sales_session_id,purchase_intent_id,provider,provider_delivery_id,metadata)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                    ON CONFLICT DO NOTHING""", (
                        lifecycle_id, event_type, old["status"], status.value, asset_id,
                        purchase_outcome_id, sales_session_id, purchase_intent_id,
                        provider, provider_delivery_id,
                        json.dumps(detail, default=str),
                    ))
                if sales_session_id:
                    cursor.execute("INSERT INTO public.customer_photoshoot_lifecycle_sessions (lifecycle_id,sales_session_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (lifecycle_id, sales_session_id))
        return self._model(row)

    def record_presented_delivery(
        self, lifecycle_id, *, asset_id: int, provider: str,
        provider_delivery_id: str, metadata=None,
    ):
        """Atomically persist one provider-confirmed presentation."""
        now = datetime.now(timezone.utc)
        detail = dict(metadata or {})
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM public.customer_photoshoot_lifecycles "
                    "WHERE lifecycle_id=%s FOR UPDATE", (lifecycle_id,),
                )
                row = cursor.fetchone()
                cursor.execute(
                    """SELECT 1 FROM public.customer_photoshoot_lifecycle_events
                       WHERE lifecycle_id=%s AND event_type='PRESENTED' AND asset_id=%s
                         AND provider=%s AND provider_delivery_id=%s""",
                    (lifecycle_id, asset_id, provider, provider_delivery_id),
                )
                duplicate = cursor.fetchone() is not None
                if row is None or duplicate:
                    return self._model(row) if row else None
                cursor.execute(
                    """UPDATE public.customer_photoshoot_lifecycles
                       SET last_activity_at=%s,updated_at=%s
                       WHERE lifecycle_id=%s RETURNING *""",
                    (now, now, lifecycle_id),
                )
                row = cursor.fetchone()
                cursor.execute(
                    """INSERT INTO public.customer_photoshoot_lifecycle_events
                       (lifecycle_id,event_type,previous_status,new_status,asset_id,
                        provider,provider_delivery_id,metadata,occurred_at)
                       VALUES (%s,'PRESENTED',%s,%s,%s,%s,%s,%s::jsonb,%s)
                       ON CONFLICT DO NOTHING""",
                    (
                        lifecycle_id, row["status"], row["status"], asset_id,
                        provider, provider_delivery_id,
                        json.dumps(detail, default=str), now,
                    ),
                )
        return self._model(row)

    def coverage(self, lifecycle_id):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT COALESCE(array_agg(DISTINCT asset_id) FILTER (WHERE event_type='PRESENTED'),'{}') presented,
                    COALESCE(array_agg(DISTINCT asset_id) FILTER (WHERE event_type='PURCHASED'),'{}') purchased
                    FROM public.customer_photoshoot_lifecycle_events WHERE lifecycle_id=%s""", (lifecycle_id,))
                event = cursor.fetchone()
                cursor.execute("""SELECT COALESCE(array_agg(DISTINCT m.asset_id),'{}') sellable
                    FROM public.customer_photoshoot_lifecycles l
                    JOIN public.photoshoot_asset_memberships p ON p.photoshoot_session_id::text=l.photoshoot_id AND p.approved=TRUE
                    JOIN public.commercial_offering_assets m ON m.asset_id=p.asset_id
                    JOIN public.commercial_offerings o ON o.offering_id=m.offering_id AND o.creator_profile_id=l.creator_profile_id
                    WHERE l.lifecycle_id=%s""", (lifecycle_id,))
                assets = cursor.fetchone()
        presented = tuple(event["presented"]); purchased = tuple(event["purchased"]); sellable = tuple(assets["sellable"])
        return {"presented_asset_ids": presented, "purchased_asset_ids": purchased,
                "remaining_asset_ids": tuple(sorted(set(sellable)-set(purchased))),
                "sellable_asset_ids": sellable}

    def history(self, lifecycle_id):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM public.customer_photoshoot_lifecycle_events WHERE lifecycle_id=%s ORDER BY occurred_at,event_id", (lifecycle_id,))
                return tuple(dict(row) for row in cursor.fetchall())

    def offering_asset_ids(self, offering_id):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT asset_id FROM public.commercial_offering_assets WHERE offering_id=%s ORDER BY position", (offering_id,))
                return tuple(row["asset_id"] for row in cursor.fetchall())

    def photoshoot_asset_ids(self, lifecycle_id):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT membership.asset_id
                    FROM public.customer_photoshoot_lifecycles lifecycle
                    JOIN public.photoshoot_asset_memberships membership
                      ON membership.photoshoot_session_id::text=lifecycle.photoshoot_id
                     AND membership.approved=TRUE
                    WHERE lifecycle.lifecycle_id=%s
                    ORDER BY membership.shot_order,membership.asset_id""", (lifecycle_id,))
                return tuple(row["asset_id"] for row in cursor.fetchall())

    def _role_asset_ids(self, lifecycle_id, predicate):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"""SELECT DISTINCT p.asset_id FROM public.customer_photoshoot_lifecycles l
                    JOIN public.photoshoot_asset_memberships p ON p.photoshoot_session_id::text=l.photoshoot_id AND p.approved=TRUE
                    JOIN public.content_items ci ON ci.id=p.asset_id
                    LEFT JOIN LATERAL (SELECT strategy_data
                      FROM public.photoshoot_session_sales_strategies strategy
                      WHERE strategy.photoshoot_session_id=p.photoshoot_session_id AND strategy.status='READY'
                      ORDER BY strategy.generated_at DESC,strategy.strategy_version DESC LIMIT 1) session_strategy ON TRUE
                    LEFT JOIN LATERAL (SELECT value
                      FROM jsonb_array_elements(COALESCE(session_strategy.strategy_data->'shots','[]'::jsonb))
                      WHERE (value->>'asset_id')::bigint=p.asset_id LIMIT 1) strategy_shot ON TRUE
                    LEFT JOIN LATERAL (SELECT role FROM public.commercial_role_assignments r
                      WHERE r.asset_id=p.asset_id AND r.creator_profile_id=l.creator_profile_id AND r.state='APPROVED'
                      ORDER BY r.updated_at DESC LIMIT 1) role ON TRUE
                    WHERE l.lifecycle_id=%s AND {predicate} ORDER BY p.asset_id""", (lifecycle_id,))
                return tuple(row["asset_id"] for row in cursor.fetchall())

    def teaser_asset_ids(self, lifecycle_id):
        return self._role_asset_ids(lifecycle_id, "(strategy_shot.value->>'access_recommendation'='FREE' OR (strategy_shot.value IS NULL AND (role.role IN ('DISCOVERY','TEASER') OR (role.role IS NULL AND ci.content_type ILIKE 'teaser%'))))")

    def finale_video_asset_ids(self, lifecycle_id):
        return self._role_asset_ids(lifecycle_id, "(role.role='FINALE_VIDEO' OR ci.content_type ILIKE 'video%')")

    def required_core_asset_ids(self, lifecycle_id):
        return self._role_asset_ids(lifecycle_id, "((strategy_shot.value IS NOT NULL AND strategy_shot.value->>'access_recommendation'='PAID') OR (strategy_shot.value IS NULL AND COALESCE(role.role,'CORE_SESSION') NOT IN ('DISCOVERY','TEASER','FINALE_VIDEO') AND ci.content_type NOT ILIKE 'video%' AND ci.content_type NOT ILIKE 'teaser%'))")

    def get_for_purchase_intent(self, intent):
        if intent.external_fanvue_user_uuid is None:
            return None
        return self._one("""SELECT l.* FROM public.customer_photoshoot_lifecycles l
            JOIN public.customer_commerce_profiles c ON c.customer_commerce_profile_id=l.customer_commerce_profile_id
            WHERE l.creator_profile_id=%s AND c.external_fanvue_user_uuid=%s
              AND l.selected_offering_id=%s""", (intent.creator_profile_id, intent.external_fanvue_user_uuid, intent.commercial_offering_id))

    def _one(self, sql, args):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, args); row = cursor.fetchone()
        return self._model(row) if row else None

    @staticmethod
    def _model(row):
        return CustomerPhotoshootLifecycle(
            lifecycle_id=row["lifecycle_id"], creator_profile_id=row["creator_profile_id"],
            customer_commerce_profile_id=row["customer_commerce_profile_id"],
            photoshoot_id=row["photoshoot_id"], status=CustomerPhotoshootStatus(row["status"]),
            current_position=row["current_position"], first_started_at=row["first_started_at"],
            last_activity_at=row["last_activity_at"], paused_at=row["paused_at"],
            completed_at=row["completed_at"], abandoned_at=row["abandoned_at"],
            revival_eligible_at=row["revival_eligible_at"],
            first_sales_session_id=row["first_sales_session_id"], last_sales_session_id=row["last_sales_session_id"],
            last_purchase_intent_id=row["last_purchase_intent_id"], selected_offering_id=row["selected_offering_id"],
            recommendation_reason=row["recommendation_reason"], metadata=row["metadata"] or {},
            created_at=row["created_at"], updated_at=row["updated_at"],
            expires_at=row.get("expires_at"), closed_at=row.get("closed_at"),
            finale_decision=FinaleDecision(row.get("finale_decision") or "NOT_APPLICABLE"),
            objection_attempts=int(row.get("objection_attempts") or 0),
            objection_at=row.get("objection_at"),
        )
