"""PostgreSQL persistence for observed Commerce recommendation learning."""

import json
from collections.abc import Callable
from uuid import UUID, uuid4

from app.database import get_db_connection
from app.models.commerce_learning import (
    CommerceRecommendationOutcome,
    CommerceRecommendationOutcomeType,
    CustomerCommerceLearningProfile,
)


class CommerceLearningRepository:
    def __init__(self, connection_factory: Callable = get_db_connection):
        self.connection_factory = connection_factory

    def is_available(self):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT to_regclass(
                         'public.customer_commerce_learning_profiles'
                       ) IS NOT NULL AS available"""
                )
                return bool(cursor.fetchone()["available"])

    def record_outcome(self, **values):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO public.commerce_recommendation_outcomes
                       (outcome_id,creator_profile_id,fanvue_account_id,
                        external_fanvue_user_uuid,telegram_user_id,
                        commercial_offering_id,purchase_intent_id,outcome_type,
                        observed_at,source_event_key,evidence,recommendation_trace)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)
                       ON CONFLICT (source_event_key) DO NOTHING RETURNING *""",
                    (
                        uuid4(), values["creator_profile_id"],
                        values["fanvue_account_id"],
                        values["external_fanvue_user_uuid"],
                        values.get("telegram_user_id"),
                        values["commercial_offering_id"],
                        values.get("purchase_intent_id"),
                        values["outcome_type"].value,
                        values["observed_at"], values["source_event_key"],
                        json.dumps(dict(values.get("evidence") or {})),
                        json.dumps(dict(values.get("recommendation_trace") or {})),
                    ),
                )
                row = cursor.fetchone()
                if row is None:
                    cursor.execute(
                        """SELECT * FROM public.commerce_recommendation_outcomes
                           WHERE source_event_key=%s""",
                        (values["source_event_key"],),
                    )
                    row = cursor.fetchone()
        return self._outcome(row)

    def list_outcomes(
        self, *, creator_profile_id, fanvue_account_id,
        external_fanvue_user_uuid, limit=None,
    ):
        limit_clause = " LIMIT %s" if limit is not None else ""
        parameters = [
            creator_profile_id, fanvue_account_id,
            external_fanvue_user_uuid,
        ]
        if limit is not None:
            parameters.append(min(500, int(limit)))
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""SELECT * FROM public.commerce_recommendation_outcomes
                       WHERE creator_profile_id=%s AND fanvue_account_id=%s
                         AND external_fanvue_user_uuid=%s
                       ORDER BY observed_at,outcome_id{limit_clause}""",
                    tuple(parameters),
                )
                rows = cursor.fetchall()
        return tuple(self._outcome(row) for row in rows)

    def get_profile(
        self, *, creator_profile_id, fanvue_account_id,
        external_fanvue_user_uuid,
    ):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT * FROM public.customer_commerce_learning_profiles
                       WHERE creator_profile_id=%s AND fanvue_account_id=%s
                         AND external_fanvue_user_uuid=%s""",
                    (
                        creator_profile_id, fanvue_account_id,
                        external_fanvue_user_uuid,
                    ),
                )
                row = cursor.fetchone()
        return self._profile(row) if row else None

    def upsert_profile(self, **values):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO public.customer_commerce_learning_profiles
                       (learning_profile_id,creator_profile_id,fanvue_account_id,
                        external_fanvue_user_uuid,telegram_user_id,preferences,
                        outcome_counts,preferred_offering_type,favorite_media_type,
                        average_price_minor,preferred_price_min_minor,
                        preferred_price_max_minor,repeat_purchase_frequency,
                        average_purchase_interval_days,confidence,evidence_count,
                        last_observed_at)
                       VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s,
                               %s,%s,%s,%s,%s,%s)
                       ON CONFLICT (creator_profile_id,fanvue_account_id,
                                    external_fanvue_user_uuid)
                       DO UPDATE SET telegram_user_id=EXCLUDED.telegram_user_id,
                         preferences=EXCLUDED.preferences,
                         outcome_counts=EXCLUDED.outcome_counts,
                         preferred_offering_type=EXCLUDED.preferred_offering_type,
                         favorite_media_type=EXCLUDED.favorite_media_type,
                         average_price_minor=EXCLUDED.average_price_minor,
                         preferred_price_min_minor=EXCLUDED.preferred_price_min_minor,
                         preferred_price_max_minor=EXCLUDED.preferred_price_max_minor,
                         repeat_purchase_frequency=EXCLUDED.repeat_purchase_frequency,
                         average_purchase_interval_days=
                             EXCLUDED.average_purchase_interval_days,
                         confidence=EXCLUDED.confidence,
                         evidence_count=EXCLUDED.evidence_count,
                         last_observed_at=EXCLUDED.last_observed_at,updated_at=now()
                       RETURNING *""",
                    (
                        values.get("learning_profile_id") or uuid4(),
                        values["creator_profile_id"], values["fanvue_account_id"],
                        values["external_fanvue_user_uuid"],
                        values.get("telegram_user_id"),
                        json.dumps(values["preferences"]),
                        json.dumps(values["outcome_counts"]),
                        values.get("preferred_offering_type"),
                        values.get("favorite_media_type"),
                        values.get("average_price_minor"),
                        values.get("preferred_price_min_minor"),
                        values.get("preferred_price_max_minor"),
                        values["repeat_purchase_frequency"],
                        values.get("average_purchase_interval_days"),
                        values["confidence"], values["evidence_count"],
                        values.get("last_observed_at"),
                    ),
                )
                row = cursor.fetchone()
        return self._profile(row)

    def list_profiles(self, *, creator_profile_id, limit=100):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT * FROM public.customer_commerce_learning_profiles
                       WHERE creator_profile_id=%s
                       ORDER BY updated_at DESC LIMIT %s""",
                    (creator_profile_id, min(500, int(limit))),
                )
                rows = cursor.fetchall()
        return tuple(self._profile(row) for row in rows)

    def list_recommendation_outcomes(
        self, *, creator_profile_id, limit=50, offset=0,
        outcome_type=None, engine_version=None, date_from=None, date_to=None,
    ):
        clauses = ["creator_profile_id=%s"]
        parameters = [creator_profile_id]
        if outcome_type:
            clauses.append("outcome_type=%s")
            parameters.append(str(outcome_type).upper())
        if engine_version:
            clauses.append(
                "recommendation_trace->>'recommendationEngineVersion'=%s"
            )
            parameters.append(str(engine_version))
        if date_from:
            clauses.append("observed_at >= %s")
            parameters.append(date_from)
        if date_to:
            clauses.append("observed_at <= %s")
            parameters.append(date_to)
        bounded = min(100, max(1, int(limit)))
        parameters.extend((bounded, max(0, int(offset))))
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""SELECT *,count(*) OVER() AS result_count
                        FROM public.commerce_recommendation_outcomes
                        WHERE {' AND '.join(clauses)}
                        ORDER BY observed_at DESC,outcome_id DESC
                        LIMIT %s OFFSET %s""",
                    tuple(parameters),
                )
                rows = cursor.fetchall()
        total = int(rows[0]["result_count"]) if rows else 0
        return tuple(self._outcome(row) for row in rows), total

    def get_outcome(self, outcome_id, *, creator_profile_id):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT * FROM public.commerce_recommendation_outcomes
                       WHERE outcome_id=%s AND creator_profile_id=%s""",
                    (outcome_id, creator_profile_id),
                )
                row = cursor.fetchone()
        return self._outcome(row) if row else None

    def diagnostics_statistics(self, *, creator_profile_id):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT count(*) AS outcomes,
                              count(*) FILTER (
                                WHERE outcome_type='PURCHASED'
                              ) AS purchases,
                              count(*) FILTER (
                                WHERE outcome_type IN ('IGNORED','EXPIRED')
                              ) AS ignored_expired,
                              max(observed_at) AS latest
                       FROM public.commerce_recommendation_outcomes
                       WHERE creator_profile_id=%s""",
                    (creator_profile_id,),
                )
                outcome = cursor.fetchone()
                cursor.execute(
                    """SELECT count(*) AS profiles
                       FROM public.customer_commerce_learning_profiles
                       WHERE creator_profile_id=%s""",
                    (creator_profile_id,),
                )
                profiles = cursor.fetchone()
        return {
            "outcomes": int(outcome["outcomes"] or 0),
            "purchases": int(outcome["purchases"] or 0),
            "ignoredExpired": int(outcome["ignored_expired"] or 0),
            "profiles": int(profiles["profiles"] or 0),
            "latest": outcome["latest"],
        }

    def get_diagnostic_context(self, outcome_id, *, creator_profile_id):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT intent.status AS purchase_intent_status,
                              intent.attribution_result,
                              profile.preferences,
                              profile.outcome_counts,
                              profile.preferred_offering_type,
                              profile.preferred_price_min_minor,
                              profile.preferred_price_max_minor,
                              profile.repeat_purchase_frequency,
                              profile.confidence,
                              profile.evidence_count,
                              profile.updated_at AS profile_updated_at
                       FROM public.commerce_recommendation_outcomes outcome
                       LEFT JOIN public.purchase_intents intent
                         ON intent.purchase_intent_id=outcome.purchase_intent_id
                       LEFT JOIN public.customer_commerce_learning_profiles profile
                         ON profile.creator_profile_id=outcome.creator_profile_id
                        AND profile.fanvue_account_id=outcome.fanvue_account_id
                        AND profile.external_fanvue_user_uuid=
                            outcome.external_fanvue_user_uuid
                       WHERE outcome.outcome_id=%s
                         AND outcome.creator_profile_id=%s""",
                    (outcome_id, creator_profile_id),
                )
                row = cursor.fetchone()
        return dict(row) if row else {}

    def offering_evidence(self, offering_id):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT offering.offering_type,offering.price_minor,
                              offering.hero_asset_id,
                              (
                                SELECT membership.photoshoot_session_id
                                FROM public.photoshoot_asset_memberships membership
                                WHERE membership.asset_id=offering.hero_asset_id
                                  AND membership.approved=TRUE
                                ORDER BY membership.updated_at DESC LIMIT 1
                              ) AS photoshoot_identifier,
                              COALESCE(jsonb_agg(intelligence.profile_data)
                                FILTER (WHERE intelligence.asset_id IS NOT NULL),
                                '[]'::jsonb) AS intelligence
                       FROM public.commercial_offerings offering
                       JOIN public.commercial_offering_assets member
                         ON member.offering_id=offering.offering_id
                       LEFT JOIN public.asset_intelligence_profiles intelligence
                         ON intelligence.asset_id=member.asset_id
                       WHERE offering.offering_id=%s
                       GROUP BY offering.offering_id""",
                    (offering_id,),
                )
                row = cursor.fetchone()
        return dict(row) if row else {}

    @staticmethod
    def _outcome(row):
        return CommerceRecommendationOutcome(
            outcome_id=UUID(str(row["outcome_id"])),
            creator_profile_id=int(row["creator_profile_id"]),
            fanvue_account_id=int(row["fanvue_account_id"]),
            external_fanvue_user_uuid=UUID(str(row["external_fanvue_user_uuid"])),
            telegram_user_id=row.get("telegram_user_id"),
            commercial_offering_id=UUID(str(row["commercial_offering_id"])),
            purchase_intent_id=(
                UUID(str(row["purchase_intent_id"]))
                if row.get("purchase_intent_id") else None
            ),
            outcome_type=CommerceRecommendationOutcomeType(row["outcome_type"]),
            observed_at=row["observed_at"],
            source_event_key=str(row["source_event_key"]),
            evidence=dict(row.get("evidence") or {}),
            recommendation_trace=dict(row.get("recommendation_trace") or {}),
        )

    @staticmethod
    def _profile(row):
        return CustomerCommerceLearningProfile(
            learning_profile_id=UUID(str(row["learning_profile_id"])),
            creator_profile_id=int(row["creator_profile_id"]),
            fanvue_account_id=int(row["fanvue_account_id"]),
            external_fanvue_user_uuid=UUID(str(row["external_fanvue_user_uuid"])),
            telegram_user_id=row.get("telegram_user_id"),
            preferences=dict(row.get("preferences") or {}),
            outcome_counts=dict(row.get("outcome_counts") or {}),
            preferred_offering_type=row.get("preferred_offering_type"),
            favorite_media_type=row.get("favorite_media_type"),
            average_price_minor=row.get("average_price_minor"),
            preferred_price_min_minor=row.get("preferred_price_min_minor"),
            preferred_price_max_minor=row.get("preferred_price_max_minor"),
            repeat_purchase_frequency=float(row.get("repeat_purchase_frequency") or 0),
            average_purchase_interval_days=(
                float(row["average_purchase_interval_days"])
                if row.get("average_purchase_interval_days") is not None else None
            ),
            confidence=float(row.get("confidence") or 0),
            evidence_count=int(row.get("evidence_count") or 0),
            last_observed_at=row.get("last_observed_at"),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
