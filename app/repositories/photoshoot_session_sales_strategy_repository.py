"""PostgreSQL persistence for versioned Photoshoot Session Sales Strategies."""

import json
from uuid import UUID

from app.database import get_db_connection
from app.models.photoshoot_session_sales_strategy import (
    PhotoshootSessionSalesStrategy,
    SessionShotSalesRecommendation,
)


class PhotoshootSessionSalesStrategyRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def get(self, photoshoot_session_id: str, strategy_version: str):
        return self._one(
            """SELECT * FROM public.photoshoot_session_sales_strategies
               WHERE photoshoot_session_id=%s AND strategy_version=%s AND status='READY'""",
            (photoshoot_session_id, strategy_version),
        )

    def latest(self, photoshoot_session_id: str):
        return self._one(
            """SELECT * FROM public.photoshoot_session_sales_strategies
               WHERE photoshoot_session_id=%s AND status='READY'
               ORDER BY generated_at DESC,strategy_version DESC LIMIT 1""",
            (photoshoot_session_id,),
        )

    def completed_session_teaser_asset_id(self, deliverable_id):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT teaser_asset_id
                       FROM public.photoshoot_session_teaser_edit_intents
                       WHERE deliverable_id=%s AND status='COMPLETED'
                       ORDER BY completed_at DESC LIMIT 1""",
                    (deliverable_id,),
                )
                row = cursor.fetchone()
        return int(row["teaser_asset_id"]) if row and row.get("teaser_asset_id") else None

    def save(self, *, photoshoot_session_id: str, deliverable_id, creator_profile_id: int,
             strategy_version: str, intelligence_version: str, strategy_data: dict,
             model: str, generated_at):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO public.photoshoot_session_sales_strategies
                       (photoshoot_session_id,deliverable_id,creator_profile_id,strategy_version,
                        intelligence_version,status,strategy_data,model,generated_at)
                       VALUES (%s,%s,%s,%s,%s,'READY',%s::jsonb,%s,%s)
                       ON CONFLICT (photoshoot_session_id,strategy_version) DO UPDATE SET
                        deliverable_id=EXCLUDED.deliverable_id,
                        creator_profile_id=EXCLUDED.creator_profile_id,
                        intelligence_version=EXCLUDED.intelligence_version,
                        status='READY',strategy_data=EXCLUDED.strategy_data,
                        model=EXCLUDED.model,generated_at=EXCLUDED.generated_at,updated_at=now()
                       WHERE photoshoot_session_sales_strategies.status<>'READY'
                       RETURNING *""",
                    (photoshoot_session_id, deliverable_id, creator_profile_id,
                     strategy_version, intelligence_version,
                     json.dumps(strategy_data, default=str), model, generated_at),
                )
                row = cursor.fetchone()
                if row is None:
                    cursor.execute(
                        """SELECT * FROM public.photoshoot_session_sales_strategies
                           WHERE photoshoot_session_id=%s AND strategy_version=%s""",
                        (photoshoot_session_id, strategy_version),
                    )
                    row = cursor.fetchone()
        return self._model(row)

    def _one(self, sql, arguments):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, arguments)
                row = cursor.fetchone()
        return self._model(row) if row else None

    @staticmethod
    def _model(row):
        data = dict(row["strategy_data"] or {})
        shots = tuple(SessionShotSalesRecommendation(
            asset_id=int(item["asset_id"]), shot_order=int(item["shot_order"]),
            sales_position=int(item["sales_position"]), sales_role=str(item["sales_role"]),
            teaser_recommended=bool(item["teaser_recommended"]),
            access_recommendation=str(item["access_recommendation"]),
            recommended_progression=str(item["recommended_progression"]),
            suggested_next_asset_id=(int(item["suggested_next_asset_id"])
                                     if item.get("suggested_next_asset_id") is not None else None),
            customer_journey_purpose=str(item["customer_journey_purpose"]),
            escalation_role=str(item["escalation_role"]),
            psychological_objective=str(item["psychological_objective"]),
            conversation_goal=str(item["conversation_goal"]),
        ) for item in data["shots"])
        return PhotoshootSessionSalesStrategy(
            photoshoot_session_id=str(row["photoshoot_session_id"]),
            deliverable_id=UUID(str(row["deliverable_id"])),
            creator_profile_id=int(row["creator_profile_id"]),
            strategy_version=str(row["strategy_version"]),
            intelligence_version=str(row["intelligence_version"]), status=str(row["status"]),
            best_teaser_asset_id=int(data["best_teaser_asset_id"]),
            recommended_customer_entry_point=str(data["recommended_customer_entry_point"]),
            suggested_sales_progression=tuple(int(value) for value in data["suggested_sales_progression"]),
            recommended_stopping_points=tuple(data["recommended_stopping_points"]),
            session_completion_strategy=str(data["session_completion_strategy"]),
            customer_engagement_strategy=str(data["customer_engagement_strategy"]),
            escalation_pacing=str(data["escalation_pacing"]),
            overall_selling_approach=str(data["overall_selling_approach"]),
            shots=shots, model=str(row["model"]), generated_at=row["generated_at"],
            metadata=dict(data.get("metadata") or {}),
        )
