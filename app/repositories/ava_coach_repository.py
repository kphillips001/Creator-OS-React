"""Persistence and narrow conversation projections for Ava Coach."""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

from app.database import get_db_connection


class AvaCoachRepository:
    def __init__(self, connection_factory: Callable = get_db_connection) -> None:
        self.connection_factory = connection_factory

    def conversation_messages(self, account_id: int, limit: int = 5000) -> list[dict]:
        return self._all(
            """SELECT cm.id,cm.thread_id,cm.fanvue_user_id,cm.direction,
                      cm.sender_type,cm.text,cm.sent_at
               FROM public.chat_messages cm
               JOIN public.chat_threads ct ON ct.id=cm.thread_id
               WHERE ct.fanvue_account_id=%s
               ORDER BY cm.sent_at ASC NULLS LAST,cm.id ASC LIMIT %s""",
            (account_id, max(1, min(limit, 10000))),
        )

    def create_snapshot(
        self, *, account_id: int, overview: dict, evidence_metadata: dict,
        period_start: Any, period_end: Any,
    ) -> dict:
        return self._required(
            """INSERT INTO public.ava_coach_snapshots(
                   snapshot_id,fanvue_account_id,period_start,period_end,
                   overview,evidence_metadata
               ) VALUES(%s,%s,%s,%s,%s::JSONB,%s::JSONB) RETURNING *""",
            (uuid4(), account_id, period_start, period_end,
             json.dumps(overview), json.dumps(evidence_metadata)),
        )

    def add_insight(self, *, snapshot_id: UUID, account_id: int, insight: dict) -> dict:
        return self._required(
            """INSERT INTO public.ava_conversation_insights(
                   insight_id,snapshot_id,fanvue_account_id,insight_type,title,
                   description,evidence,confidence
               ) VALUES(%s,%s,%s,%s,%s,%s,%s::JSONB,%s) RETURNING *""",
            (uuid4(), snapshot_id, account_id, insight["insight_type"],
             insight["title"], insight["description"],
             json.dumps(insight["evidence"]), insight["confidence"]),
        )

    def target_version(self) -> dict:
        return self._required(
            """SELECT * FROM public.ava_personality_versions
               WHERE status='DRAFT' ORDER BY created_at DESC LIMIT 1""", (),
        )

    def upsert_recommendation(
        self, *, account_id: int, target_version_id: UUID, recommendation: dict,
    ) -> dict:
        return self._required(
            """INSERT INTO public.ava_coaching_recommendations(
                   recommendation_id,fanvue_account_id,recommendation_key,
                   target_version_id,title,description,evidence,confidence,
                   expected_impact,status
               ) VALUES(%s,%s,%s,%s,%s,%s,%s::JSONB,%s,%s,'PENDING')
               ON CONFLICT(fanvue_account_id,recommendation_key,target_version_id)
               DO UPDATE SET
                   title=CASE WHEN ava_coaching_recommendations.status='PENDING'
                              THEN EXCLUDED.title ELSE ava_coaching_recommendations.title END,
                   description=CASE WHEN ava_coaching_recommendations.status='PENDING'
                              THEN EXCLUDED.description ELSE ava_coaching_recommendations.description END,
                   evidence=CASE WHEN ava_coaching_recommendations.status='PENDING'
                              THEN EXCLUDED.evidence ELSE ava_coaching_recommendations.evidence END,
                   confidence=CASE WHEN ava_coaching_recommendations.status='PENDING'
                              THEN EXCLUDED.confidence ELSE ava_coaching_recommendations.confidence END,
                   updated_at=NOW()
               RETURNING *""",
            (uuid4(), account_id, recommendation["recommendation_key"],
             target_version_id, recommendation["title"],
             recommendation["description"], json.dumps(recommendation["evidence"]),
             recommendation["confidence"], recommendation["expected_impact"]),
        )

    def transition(self, recommendation_id: UUID, status: str) -> dict:
        timestamp = {
            "REJECTED": "rejected_at", "DISMISSED": "dismissed_at",
            "APPROVED": "approved_at",
        }[status]
        return self._required(
            f"""UPDATE public.ava_coaching_recommendations SET
                    status=%s,{timestamp}=NOW(),updated_at=NOW()
                WHERE recommendation_id=%s AND status='PENDING' RETURNING *""",
            (status, recommendation_id),
        )

    def approve_and_apply(self, recommendation_id: UUID) -> dict:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE public.ava_coaching_recommendations SET
                       status='APPROVED_FOR_VERSION',approved_at=NOW(),updated_at=NOW()
                   WHERE recommendation_id=%s AND status='PENDING'
                   RETURNING *""",
                (recommendation_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise ValueError("Recommendation was not found or is no longer pending.")
            cursor.execute(
                """INSERT INTO public.ava_applied_improvements(
                       improvement_id,recommendation_id,version_id,evidence
                   ) VALUES(%s,%s,%s,%s::JSONB) RETURNING *""",
                (uuid4(), recommendation_id, row["target_version_id"],
                 json.dumps(row["evidence"])),
            )
            improvement = cursor.fetchone()
        return {"recommendation": dict(row), "improvement": dict(improvement)}

    def edit_recommendation(
        self, recommendation_id: UUID, *, title: str, description: str,
    ) -> dict:
        return self._required(
            """UPDATE public.ava_coaching_recommendations SET
                   title=%s,description=%s,updated_at=NOW()
               WHERE recommendation_id=%s AND status='PENDING' RETURNING *""",
            (title, description, recommendation_id),
        )

    def coach_summary(self, account_id: int) -> dict:
        return self._required(
            """SELECT
                   (SELECT created_at FROM public.ava_coach_snapshots
                    WHERE fanvue_account_id=%s ORDER BY created_at DESC LIMIT 1)
                       AS latest_analysis_at,
                   (SELECT COALESCE((overview->>'totalConversationsReviewed')::INT,0)
                    FROM public.ava_coach_snapshots WHERE fanvue_account_id=%s
                    ORDER BY created_at DESC LIMIT 1) AS conversations_reviewed,
                   COUNT(*) FILTER (WHERE status='PENDING') AS pending_recommendations,
                   COUNT(*) FILTER (WHERE status='APPROVED_FOR_VERSION')
                       AS approved_for_version
               FROM public.ava_coaching_recommendations
               WHERE fanvue_account_id=%s""",
            (account_id, account_id, account_id),
        )

    def latest_snapshot(self, account_id: int) -> dict | None:
        return self._one(
            """SELECT * FROM public.ava_coach_snapshots
               WHERE fanvue_account_id=%s ORDER BY created_at DESC LIMIT 1""",
            (account_id,),
        )

    def insights(self, snapshot_id: UUID) -> list[dict]:
        return self._all(
            """SELECT * FROM public.ava_conversation_insights
               WHERE snapshot_id=%s ORDER BY confidence DESC,created_at""",
            (snapshot_id,),
        )

    def recommendations(self, account_id: int) -> list[dict]:
        return self._all(
            """SELECT recommendation.*,version.version_label
               FROM public.ava_coaching_recommendations recommendation
               JOIN public.ava_personality_versions version
                 ON version.version_id=recommendation.target_version_id
               WHERE recommendation.fanvue_account_id=%s
               ORDER BY recommendation.created_at DESC""",
            (account_id,),
        )

    def improvements(self, account_id: int) -> list[dict]:
        return self._all(
            """SELECT improvement.*,recommendation.title,
                      recommendation.description,recommendation.confidence,
                      version.version_label
               FROM public.ava_applied_improvements improvement
               JOIN public.ava_coaching_recommendations recommendation
                 ON recommendation.recommendation_id=improvement.recommendation_id
               JOIN public.ava_personality_versions version
                 ON version.version_id=improvement.version_id
               WHERE recommendation.fanvue_account_id=%s
               ORDER BY improvement.applied_at DESC""",
            (account_id,),
        )

    def versions(self) -> list[dict]:
        return self._all(
            "SELECT * FROM public.ava_personality_versions ORDER BY created_at",
            (),
        )

    def _one(self, query: str, params: tuple) -> dict | None:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()
        return dict(row) if row else None

    def _all(self, query: str, params: tuple) -> list[dict]:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def _required(self, query: str, params: tuple) -> dict:
        row = self._one(query, params)
        if row is None:
            raise ValueError("Ava Coach record was not found or transition is invalid.")
        return row
