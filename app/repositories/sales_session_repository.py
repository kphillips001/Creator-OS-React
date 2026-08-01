"""PostgreSQL persistence for Sales Sessions and their audit history."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from uuid import UUID, uuid4

from app.database import get_db_connection
from app.models.sales_session import (
    ACTIVE_SALES_SESSION_STATES,
    SalesSession,
    SalesSessionActorType,
    SalesSessionFoundationType,
    SalesSessionHistoryEntry,
    SalesSessionOutcome,
    SalesSessionProgression,
    SalesSessionState,
)


class SalesSessionRepository:
    def __init__(self, connection_factory: Callable = get_db_connection) -> None:
        self._connection_factory = connection_factory

    def create(
        self, *, creator_profile_id: int, fanvue_account_id: int,
        fanvue_user_id: int, external_fanvue_user_uuid: UUID,
        telegram_identity_mapping_id: int | None,
        conversation_thread_id: int | None,
        commercial_foundation_type: str,
        commercial_foundation_reference: str | None,
        objective: str | None, commercial_context: Mapping,
        actor_type: SalesSessionActorType, actor_identifier: str | None,
    ) -> SalesSession:
        session_id = uuid4()
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO public.sales_sessions (
                           sales_session_id,creator_profile_id,
                           fanvue_account_id,fanvue_user_id,
                           external_fanvue_user_uuid,
                           telegram_identity_mapping_id,
                           conversation_thread_id,
                           commercial_foundation_type,
                           commercial_foundation_reference,state,
                           progression_stage,objective,commercial_context,
                           started_by_type,started_by_identifier
                       ) VALUES (
                           %s,%s,%s,%s,%s,%s,%s,%s,%s,'ACTIVE',
                           'DISCOVERY',%s,%s::jsonb,%s,%s
                       ) RETURNING *""",
                    (
                        session_id, int(creator_profile_id),
                        int(fanvue_account_id), int(fanvue_user_id),
                        external_fanvue_user_uuid,
                        telegram_identity_mapping_id,
                        conversation_thread_id,
                        commercial_foundation_type,
                        commercial_foundation_reference, objective,
                        json.dumps(dict(commercial_context or {}), default=str),
                        actor_type.value, actor_identifier,
                    ),
                )
                row = cursor.fetchone()
                self._history(
                    cursor, row=row, event_type="STARTED",
                    previous_state=None, previous_stage=None,
                    purchase_intent_id=None, actor_type=actor_type,
                    actor_identifier=actor_identifier, reason=objective,
                )
        return self._session(row)

    def get(
        self, session_id: UUID, *, creator_profile_id: int,
    ) -> SalesSession | None:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT * FROM public.sales_sessions
                       WHERE sales_session_id=%s AND creator_profile_id=%s""",
                    (session_id, int(creator_profile_id)),
                )
                row = cursor.fetchone()
        return self._session(row) if row else None

    def get_active_for_customer(
        self, *, creator_profile_id: int, fanvue_account_id: int,
        fanvue_user_id: int,
    ) -> SalesSession | None:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT * FROM public.sales_sessions
                       WHERE creator_profile_id=%s AND fanvue_account_id=%s
                         AND fanvue_user_id=%s
                         AND state=ANY(%s)
                       ORDER BY started_at DESC LIMIT 1""",
                    (
                        int(creator_profile_id), int(fanvue_account_id),
                        int(fanvue_user_id),
                        [state.value for state in ACTIVE_SALES_SESSION_STATES],
                    ),
                )
                row = cursor.fetchone()
        return self._session(row) if row else None

    def list_for_creator(
        self, *, creator_profile_id: int, limit: int = 100,
    ) -> tuple[SalesSession, ...]:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT * FROM public.sales_sessions
                       WHERE creator_profile_id=%s
                       ORDER BY last_activity_at DESC,sales_session_id
                       LIMIT %s""",
                    (int(creator_profile_id), max(1, min(500, int(limit)))),
                )
                rows = cursor.fetchall()
        return tuple(self._session(row) for row in rows)

    def conversation_belongs_to_customer(
        self, *, conversation_thread_id: int, fanvue_account_id: int,
        fanvue_user_id: int,
    ) -> bool:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT 1 FROM public.chat_threads
                       WHERE id=%s AND fanvue_account_id=%s
                         AND fanvue_user_id=%s""",
                    (
                        int(conversation_thread_id),
                        int(fanvue_account_id), int(fanvue_user_id),
                    ),
                )
                return cursor.fetchone() is not None

    def transition(
        self, *, session_id: UUID, creator_profile_id: int,
        expected_state: SalesSessionState, new_state: SalesSessionState,
        progression_stage: SalesSessionProgression,
        outcome: SalesSessionOutcome | None, terminal_reason: str | None,
        event_type: str, actor_type: SalesSessionActorType,
        actor_identifier: str | None, reason: str | None,
        purchase_intent_id: UUID | None = None,
    ) -> SalesSession | None:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT * FROM public.sales_sessions
                       WHERE sales_session_id=%s AND creator_profile_id=%s
                       FOR UPDATE""",
                    (session_id, int(creator_profile_id)),
                )
                current = cursor.fetchone()
                if current is None or current["state"] != expected_state.value:
                    return None
                terminal = new_state not in ACTIVE_SALES_SESSION_STATES
                cursor.execute(
                    """UPDATE public.sales_sessions SET
                           state=%s,progression_stage=%s,outcome=%s,
                           terminal_reason=%s,last_activity_at=NOW(),
                           ended_at=CASE WHEN %s THEN NOW() ELSE NULL END,
                           updated_at=NOW()
                       WHERE sales_session_id=%s RETURNING *""",
                    (
                        new_state.value, progression_stage.value,
                        outcome.value if outcome else None, terminal_reason,
                        terminal, session_id,
                    ),
                )
                row = cursor.fetchone()
                self._history(
                    cursor, row=row, event_type=event_type,
                    previous_state=SalesSessionState(current["state"]),
                    previous_stage=SalesSessionProgression(
                        current["progression_stage"]
                    ),
                    purchase_intent_id=purchase_intent_id,
                    actor_type=actor_type,
                    actor_identifier=actor_identifier, reason=reason,
                )
        return self._session(row)

    def update_progression(
        self, *, session_id: UUID, creator_profile_id: int,
        expected_state: SalesSessionState,
        progression_stage: SalesSessionProgression,
        actor_type: SalesSessionActorType, actor_identifier: str | None,
        reason: str | None,
    ) -> SalesSession | None:
        return self.transition(
            session_id=session_id, creator_profile_id=creator_profile_id,
            expected_state=expected_state, new_state=expected_state,
            progression_stage=progression_stage, outcome=None,
            terminal_reason=None, event_type="PROGRESSION_CHANGED",
            actor_type=actor_type, actor_identifier=actor_identifier,
            reason=reason,
        )

    def associate_purchase_intent(
        self, *, session: SalesSession, purchase_intent_id: UUID,
        actor_type: SalesSessionActorType, actor_identifier: str | None,
        reason: str | None,
    ) -> int:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT sales_session_id
                       FROM public.sales_sessions
                       WHERE sales_session_id=%s FOR UPDATE""",
                    (session.sales_session_id,),
                )
                if cursor.fetchone() is None:
                    raise LookupError("Sales Session was not found.")
                cursor.execute(
                    """SELECT COALESCE(MAX(sequence_index),0)+1 AS next_index
                       FROM public.sales_session_purchase_intents
                       WHERE sales_session_id=%s""",
                    (session.sales_session_id,),
                )
                sequence = int(cursor.fetchone()["next_index"])
                cursor.execute(
                    """INSERT INTO public.sales_session_purchase_intents (
                           sales_session_id,purchase_intent_id,sequence_index
                       ) VALUES (%s,%s,%s)
                       ON CONFLICT (sales_session_id,purchase_intent_id)
                       DO UPDATE SET purchase_intent_id=EXCLUDED.purchase_intent_id
                       RETURNING sequence_index""",
                    (session.sales_session_id, purchase_intent_id, sequence),
                )
                actual_sequence = int(cursor.fetchone()["sequence_index"])
                cursor.execute(
                    """SELECT * FROM public.sales_sessions
                       WHERE sales_session_id=%s FOR UPDATE""",
                    (session.sales_session_id,),
                )
                row = cursor.fetchone()
                self._history(
                    cursor, row=row, event_type="PURCHASE_INTENT_ASSOCIATED",
                    previous_state=SalesSessionState(row["state"]),
                    previous_stage=SalesSessionProgression(
                        row["progression_stage"]
                    ),
                    purchase_intent_id=purchase_intent_id,
                    actor_type=actor_type,
                    actor_identifier=actor_identifier, reason=reason,
                )
        return actual_sequence

    def list_purchase_intents(
        self, *, session_id: UUID, creator_profile_id: int,
    ) -> tuple[dict, ...]:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT link.sequence_index,link.associated_at,
                              intent.*,
                              (
                                  SELECT COALESCE(
                                      array_agg(member.asset_id ORDER BY member.position),
                                      ARRAY[]::bigint[]
                                  )
                                  FROM public.commercial_offering_assets member
                                  WHERE member.offering_id=
                                        intent.commercial_offering_id
                              ) AS asset_ids
                       FROM public.sales_session_purchase_intents link
                       JOIN public.sales_sessions session
                         ON session.sales_session_id=link.sales_session_id
                       JOIN public.purchase_intents intent
                         ON intent.purchase_intent_id=link.purchase_intent_id
                       WHERE link.sales_session_id=%s
                         AND session.creator_profile_id=%s
                       ORDER BY link.sequence_index""",
                    (session_id, int(creator_profile_id)),
                )
                return tuple(dict(row) for row in cursor.fetchall())

    def purchase_intent_association(
        self, purchase_intent_id: UUID,
    ) -> tuple[UUID, int] | None:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT sales_session_id,sequence_index
                       FROM public.sales_session_purchase_intents
                       WHERE purchase_intent_id=%s""",
                    (purchase_intent_id,),
                )
                row = cursor.fetchone()
        return (
            (UUID(str(row["sales_session_id"])), int(row["sequence_index"]))
            if row else None
        )

    def history(
        self, *, session_id: UUID, creator_profile_id: int,
    ) -> tuple[SalesSessionHistoryEntry, ...]:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT history.* FROM public.sales_session_history history
                       JOIN public.sales_sessions session
                         USING (sales_session_id)
                       WHERE history.sales_session_id=%s
                         AND session.creator_profile_id=%s
                       ORDER BY history.occurred_at,history.history_id""",
                    (session_id, int(creator_profile_id)),
                )
                rows = cursor.fetchall()
        return tuple(self._history_entry(row) for row in rows)

    def commercial_guidance(
        self, *, session: SalesSession,
    ) -> dict:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT intelligence.profile_data
                       FROM public.photoshoot_intelligence_profiles intelligence
                       JOIN public.photoshoot_commerce_deliverables deliverable
                         USING (photoshoot_session_id)
                       WHERE intelligence.photoshoot_session_id=%s
                         AND deliverable.creator_profile_id=%s""",
                    (
                        session.commercial_foundation_reference,
                        session.creator_profile_id,
                    ),
                )
                intelligence = cursor.fetchone()
                cursor.execute(
                    """SELECT membership.asset_id,membership.shot_order,
                              membership.is_hero,role.role,
                              asset_intelligence.profile_data
                       FROM public.photoshoot_asset_memberships membership
                       LEFT JOIN public.commercial_role_assignments role
                         ON role.asset_id=membership.asset_id
                        AND role.creator_profile_id=%s
                        AND role.state='APPROVED'
                       LEFT JOIN public.asset_intelligence_profiles
                              asset_intelligence
                         ON asset_intelligence.asset_id=membership.asset_id
                        AND asset_intelligence.creator_profile_id=%s
                       WHERE membership.photoshoot_session_id=%s
                         AND membership.approved=TRUE
                       ORDER BY membership.shot_order,role.role""",
                    (
                        session.creator_profile_id,
                        session.creator_profile_id,
                        session.commercial_foundation_reference,
                    ),
                )
                rows = cursor.fetchall()
        assets: dict[int, dict] = {}
        for row in rows:
            value = assets.setdefault(int(row["asset_id"]), {
                "asset_id": int(row["asset_id"]),
                "shot_order": int(row["shot_order"]),
                "is_hero": bool(row["is_hero"]),
                "effective_commercial_roles": [],
                "asset_intelligence": self._mapping(
                    row.get("profile_data")
                ),
            })
            if row.get("role"):
                value["effective_commercial_roles"].append(row["role"])
        return {
            "photoshoot_intelligence": (
                dict(intelligence.get("profile_data") or {})
                if intelligence else {}
            ),
            "assets": tuple(assets.values()),
        }

    @staticmethod
    def _history(
        cursor, *, row, event_type: str,
        previous_state: SalesSessionState | None,
        previous_stage: SalesSessionProgression | None,
        purchase_intent_id: UUID | None,
        actor_type: SalesSessionActorType, actor_identifier: str | None,
        reason: str | None,
    ) -> None:
        cursor.execute(
            """INSERT INTO public.sales_session_history (
                   sales_session_id,creator_profile_id,event_type,
                   previous_state,new_state,previous_progression_stage,
                   new_progression_stage,purchase_intent_id,actor_type,
                   actor_identifier,reason
               ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                row["sales_session_id"], row["creator_profile_id"], event_type,
                previous_state.value if previous_state else None, row["state"],
                previous_stage.value if previous_stage else None,
                row["progression_stage"], purchase_intent_id,
                actor_type.value, actor_identifier, reason,
            ),
        )

    @classmethod
    def _session(cls, row) -> SalesSession:
        return SalesSession(
            sales_session_id=UUID(str(row["sales_session_id"])),
            creator_profile_id=int(row["creator_profile_id"]),
            fanvue_account_id=int(row["fanvue_account_id"]),
            fanvue_user_id=int(row["fanvue_user_id"]),
            external_fanvue_user_uuid=UUID(
                str(row["external_fanvue_user_uuid"])
            ),
            telegram_identity_mapping_id=(
                int(row["telegram_identity_mapping_id"])
                if row.get("telegram_identity_mapping_id") is not None else None
            ),
            conversation_thread_id=(
                int(row["conversation_thread_id"])
                if row.get("conversation_thread_id") is not None else None
            ),
            commercial_foundation_type=SalesSessionFoundationType(
                row["commercial_foundation_type"]
            ),
            commercial_foundation_reference=row[
                "commercial_foundation_reference"
            ],
            state=SalesSessionState(row["state"]),
            progression_stage=SalesSessionProgression(
                row["progression_stage"]
            ),
            objective=row.get("objective"),
            commercial_context=cls._mapping(row.get("commercial_context")),
            outcome=(
                SalesSessionOutcome(row["outcome"])
                if row.get("outcome") else None
            ),
            terminal_reason=row.get("terminal_reason"),
            started_by_type=SalesSessionActorType(row["started_by_type"]),
            started_by_identifier=row.get("started_by_identifier"),
            started_at=row.get("started_at"),
            last_activity_at=row.get("last_activity_at"),
            ended_at=row.get("ended_at"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    @staticmethod
    def _history_entry(row) -> SalesSessionHistoryEntry:
        return SalesSessionHistoryEntry(
            history_id=int(row["history_id"]),
            sales_session_id=UUID(str(row["sales_session_id"])),
            creator_profile_id=int(row["creator_profile_id"]),
            event_type=row["event_type"],
            previous_state=(
                SalesSessionState(row["previous_state"])
                if row.get("previous_state") else None
            ),
            new_state=SalesSessionState(row["new_state"]),
            previous_progression_stage=(
                SalesSessionProgression(row["previous_progression_stage"])
                if row.get("previous_progression_stage") else None
            ),
            new_progression_stage=SalesSessionProgression(
                row["new_progression_stage"]
            ),
            purchase_intent_id=(
                UUID(str(row["purchase_intent_id"]))
                if row.get("purchase_intent_id") else None
            ),
            actor_type=SalesSessionActorType(row["actor_type"]),
            actor_identifier=row.get("actor_identifier"),
            reason=row.get("reason"),
            occurred_at=row["occurred_at"],
        )

    @staticmethod
    def _mapping(value) -> dict:
        if isinstance(value, Mapping):
            return dict(value)
        if isinstance(value, str):
            parsed = json.loads(value)
            return dict(parsed) if isinstance(parsed, Mapping) else {}
        return {}
