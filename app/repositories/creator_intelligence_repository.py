"""Lightweight read model for the Creator Intelligence Center."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from app.database import get_db_connection


class CreatorIntelligenceRepository:
    """Fetch the dashboard's database facts in one account-scoped query."""

    def __init__(self, connection_factory: Callable = get_db_connection) -> None:
        self.connection_factory = connection_factory

    def snapshot(
        self, *, creator_profile_id: int, fanvue_account_id: int, today: datetime
    ) -> dict:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                      (SELECT count(*) FROM public.purchase_intents
                       WHERE creator_profile_id=%s
                         AND status IN ('CREATED','PRESENTED','CLICKED')) AS waiting_intents,
                      (SELECT count(*) FROM public.purchase_intents
                       WHERE creator_profile_id=%s AND presented_at >= %s) AS offers_today,
                      (SELECT count(*) FROM public.customer_commerce_transactions
                       WHERE fanvue_account_id=%s
                         AND payment_timestamp >= %s) AS purchases_today,
                      (SELECT COALESCE(sum(gross_minor),0)
                       FROM public.customer_commerce_transactions
                       WHERE fanvue_account_id=%s
                         AND payment_timestamp >= %s) AS revenue_today_minor,
                      (SELECT count(*) FROM public.commerce_recommendation_outcomes
                       WHERE creator_profile_id=%s
                         AND observed_at >= %s) AS learning_events_today,
                      (SELECT count(*) FROM public.commerce_recommendation_outcomes
                       WHERE creator_profile_id=%s AND observed_at >= %s
                         AND outcome_type='WOULD_HAVE_SOLD') AS would_have_sold_today,
                      (SELECT count(*) FROM public.customer_commerce_profiles
                       WHERE creator_profile_id=%s) AS customers_met,
                      (SELECT count(*) FROM public.customer_commerce_profiles
                       WHERE creator_profile_id=%s
                         AND profile_state='PRE_LAUNCH_INTEREST')
                         AS pre_launch_interest_customers,
                      (SELECT count(*) FROM public.customer_commerce_learning_profiles
                       WHERE creator_profile_id=%s) AS learning_profiles,
                      (SELECT preferred_offering_type
                       FROM public.customer_commerce_learning_profiles
                       WHERE creator_profile_id=%s
                         AND preferred_offering_type IS NOT NULL
                       GROUP BY preferred_offering_type
                       ORDER BY count(*) DESC,preferred_offering_type LIMIT 1)
                         AS top_offering_type,
                      (SELECT favorite_media_type
                       FROM public.customer_commerce_learning_profiles
                       WHERE creator_profile_id=%s
                         AND favorite_media_type IS NOT NULL
                       GROUP BY favorite_media_type
                       ORDER BY count(*) DESC,favorite_media_type LIMIT 1)
                         AS top_media_type,
                      (SELECT avg(confidence)
                       FROM public.customer_commerce_learning_profiles
                       WHERE creator_profile_id=%s) AS average_learning_confidence,
                      (SELECT count(*) FROM public.customer_commerce_profiles
                       WHERE creator_profile_id=%s AND purchase_count > 1)
                         AS repeat_buyers,
                      (SELECT count(*) FROM public.customer_commerce_profiles
                       WHERE creator_profile_id=%s
                         AND profile_state IN ('VIP','HIGH_VALUE'))
                         AS high_value_buyers,
                      (SELECT count(*) FROM public.purchase_intents
                       WHERE creator_profile_id=%s AND status='EXPIRED')
                         AS expired_intents,
                      (SELECT count(*) FROM public.commerce_recommendation_outcomes
                       WHERE creator_profile_id=%s
                         AND outcome_type IN ('IGNORED','EXPIRED'))
                         AS ignored_offers,
                      (SELECT count(*) FROM public.content_items
                       WHERE creator_profile_id=%s) AS canonical_assets,
                      (SELECT count(*) FROM public.asset_intelligence_profiles
                       WHERE creator_profile_id=%s
                         AND analysis_status='READY') AS ready_assets,
                      (SELECT count(*) FROM public.asset_content_destinations d
                       JOIN public.content_items a ON a.id=d.asset_id
                       WHERE a.creator_profile_id=%s
                         AND d.destination='AVAILABLE_INVENTORY')
                         AS available_inventory,
                      (SELECT count(*) FROM public.commercial_offerings
                       WHERE creator_profile_id=%s AND status <> 'ARCHIVED')
                         AS offerings,
                      (SELECT count(*) FROM public.commercial_offerings
                       WHERE creator_profile_id=%s AND status='READY')
                         AS ready_offerings,
                      (SELECT count(*) FROM public.commercial_publications p
                       JOIN public.commercial_offerings o
                         ON o.offering_id=p.commercial_offering_id
                       WHERE o.creator_profile_id=%s
                         AND p.status='READY_TO_PUBLISH')
                         AS ready_to_publish,
                      (SELECT count(*) FROM public.commercial_publications p
                       JOIN public.commercial_offerings o
                         ON o.offering_id=p.commercial_offering_id
                       WHERE o.creator_profile_id=%s AND p.status='LIVE')
                         AS live_publications,
                      (SELECT count(*) FROM public.commercial_publications p
                       JOIN public.commercial_offerings o
                         ON o.offering_id=p.commercial_offering_id
                       WHERE o.creator_profile_id=%s AND p.status='FAILED')
                         AS failed_publications,
                      (SELECT count(*) FROM public.commercial_offerings o
                       WHERE o.creator_profile_id=%s
                         AND o.offering_type='PHOTOSET'
                         AND o.status='READY'
                         AND NOT EXISTS (
                           SELECT 1 FROM public.purchase_intents i
                           WHERE i.commercial_offering_id=o.offering_id
                         )) AS never_offered_photosets
                    """,
                    (
                        creator_profile_id,
                        creator_profile_id, today,
                        fanvue_account_id, today,
                        fanvue_account_id, today,
                        creator_profile_id, today,
                        creator_profile_id, today,
                        creator_profile_id,
                        creator_profile_id,
                        creator_profile_id,
                        creator_profile_id,
                        creator_profile_id,
                        creator_profile_id,
                        creator_profile_id,
                        creator_profile_id,
                        creator_profile_id,
                        creator_profile_id,
                        creator_profile_id,
                        creator_profile_id,
                        creator_profile_id,
                        creator_profile_id,
                        creator_profile_id,
                        creator_profile_id,
                        creator_profile_id,
                        creator_profile_id,
                        creator_profile_id,
                    ),
                )
                row = cursor.fetchone()
        return dict(row or {})
