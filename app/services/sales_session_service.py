"""Canonical Sales Session lifecycle and existing-system coordination."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from uuid import UUID

from psycopg.errors import UniqueViolation

from app.models.sales_session import (
    ACTIVE_SALES_SESSION_STATES,
    SalesSessionActorType,
    SalesSessionOutcome,
    SalesSessionProgression,
    SalesSessionState,
)
from app.repositories.customer_repository import CustomerRepository
from app.repositories.memory_repository import get_user_memory_row
from app.repositories.photoshoot_commerce_repository import (
    PhotoshootCommerceRepository,
)
from app.repositories.purchase_intent_repository import PurchaseIntentRepository
from app.repositories.sales_session_repository import SalesSessionRepository
from app.repositories.telegram_identity_repository import (
    TelegramIdentityRepository,
)
from app.repositories.user_repository import get_user_by_account_and_id
from app.services.buyer_session_service import BuyerSessionService


logger = logging.getLogger("sales-session")


class SalesSessionError(ValueError):
    pass


class SalesSessionCompatibilityAdapter:
    """Best-effort projection to the existing Buyer Session runtime."""

    def __init__(self, *, buyer_sessions=None, memory_fetcher=None) -> None:
        self.buyer_sessions = buyer_sessions or BuyerSessionService()
        self.memory_fetcher = memory_fetcher or get_user_memory_row

    def started(self, session) -> None:
        self._run(
            "start",
            lambda: self.buyer_sessions.start_or_refresh_session(
                session.fanvue_account_id, session.fanvue_user_id,
                self.memory_fetcher(
                    session.fanvue_account_id, session.fanvue_user_id
                ) or {},
            ),
        )

    def ended(self, session) -> None:
        exit_type = (
            "converted"
            if session.outcome is SalesSessionOutcome.COMPLETED_WITH_PURCHASE
            else "cooldown"
        )
        self._run(
            "end",
            lambda: self.buyer_sessions.exit_session(
                session.fanvue_account_id, session.fanvue_user_id,
                exit_type, session.terminal_reason or session.state.value,
            ),
        )

    @staticmethod
    def _run(action, operation) -> None:
        try:
            operation()
        except Exception as error:
            logger.warning(
                "event=sales_session_legacy_projection_failed action=%s "
                "error_type=%s",
                action, type(error).__name__,
            )


class SalesSessionService:
    TERMINAL_OUTCOMES = {
        SalesSessionState.EXPIRED: SalesSessionOutcome.EXPIRED,
        SalesSessionState.ABANDONED: SalesSessionOutcome.ABANDONED,
        SalesSessionState.CANCELLED: SalesSessionOutcome.CANCELLED,
    }
    TRANSITIONS = {
        SalesSessionState.ACTIVE: {
            SalesSessionState.OFFERING,
            SalesSessionState.CONTINUING,
        },
        SalesSessionState.OFFERING: {
            SalesSessionState.AWAITING_PAYMENT,
            SalesSessionState.CONTINUING,
        },
        SalesSessionState.AWAITING_PAYMENT: {
            SalesSessionState.CONTINUING,
        },
        SalesSessionState.CONTINUING: {
            SalesSessionState.OFFERING,
        },
    }

    def __init__(
        self, *, repository=None, identity_repository=None,
        purchase_intent_repository=None, photoshoot_repository=None,
        customer_fetcher=None, compatibility=None,
    ) -> None:
        self.repository = repository or SalesSessionRepository()
        self.identities = identity_repository or TelegramIdentityRepository()
        self.purchase_intents = (
            purchase_intent_repository or PurchaseIntentRepository()
        )
        self.photoshoots = (
            photoshoot_repository or PhotoshootCommerceRepository()
        )
        self.customer_fetcher = customer_fetcher or get_user_by_account_and_id
        self.compatibility = (
            compatibility or SalesSessionCompatibilityAdapter()
        )

    def start(
        self, *, creator_profile_id: int, fanvue_account_id: int,
        fanvue_user_id: int, telegram_user_id: int | None,
        conversation_thread_id: int | None,
        commercial_foundation_reference: str,
        objective: str | None, commercial_context: Mapping | None,
        actor_type, actor_identifier: str | None,
    ):
        actor = self._actor(actor_type, allow_system=False)
        customer = self.customer_fetcher(
            int(fanvue_account_id), int(fanvue_user_id)
        )
        if customer is None:
            raise KeyError("Canonical Customer was not found.")
        customer_creator = int(customer.get("fanvue_account_id") or 0)
        if customer_creator != int(fanvue_account_id):
            raise SalesSessionError("Canonical Customer identity is inconsistent.")
        existing = self.repository.get_active_for_customer(
            creator_profile_id=int(creator_profile_id),
            fanvue_account_id=int(fanvue_account_id),
            fanvue_user_id=int(fanvue_user_id),
        )
        if existing is not None:
            return existing
        identity = None
        if telegram_user_id is not None:
            identity = self.identities.get_by_telegram_user_id(
                int(telegram_user_id)
            )
            if (
                identity is None
                or identity.fanvue_account_id != int(fanvue_account_id)
                or identity.local_fanvue_user_id != int(fanvue_user_id)
            ):
                raise SalesSessionError(
                    "Telegram identity does not match the canonical Customer."
                )
        foundation = str(commercial_foundation_reference or "").strip()
        if not foundation:
            raise SalesSessionError("A Photoshoot foundation is required.")
        photoshoot = self.photoshoots.get_by_session(foundation)
        if (
            photoshoot is None
            or int(photoshoot.get("creator_profile_id") or 0)
            != int(creator_profile_id)
        ):
            raise KeyError("Commercial Photoshoot foundation was not found.")
        if (
            conversation_thread_id is not None
            and not self.repository.conversation_belongs_to_customer(
                conversation_thread_id=int(conversation_thread_id),
                fanvue_account_id=int(fanvue_account_id),
                fanvue_user_id=int(fanvue_user_id),
            )
        ):
            raise SalesSessionError(
                "Conversation does not belong to the canonical Customer."
            )
        context = self._context(commercial_context)
        try:
            session = self.repository.create(
                creator_profile_id=int(creator_profile_id),
                fanvue_account_id=int(fanvue_account_id),
                fanvue_user_id=int(fanvue_user_id),
                external_fanvue_user_uuid=UUID(
                    str(customer["fanvue_user_uuid"])
                ),
                telegram_identity_mapping_id=(
                    identity.id if identity is not None else None
                ),
                conversation_thread_id=(
                    int(conversation_thread_id)
                    if conversation_thread_id is not None else None
                ),
                commercial_foundation_type="PHOTOSHOOT",
                commercial_foundation_reference=foundation,
                objective=self._text(objective), commercial_context=context,
                actor_type=actor,
                actor_identifier=self._text(actor_identifier),
            )
        except UniqueViolation:
            session = self.repository.get_active_for_customer(
                creator_profile_id=int(creator_profile_id),
                fanvue_account_id=int(fanvue_account_id),
                fanvue_user_id=int(fanvue_user_id),
            )
            if session is None:
                raise
        self.compatibility.started(session)
        return session

    def get(self, *, session_id, creator_profile_id: int):
        session = self.repository.get(
            self._uuid(session_id), creator_profile_id=int(creator_profile_id)
        )
        if session is None:
            raise KeyError("Sales Session was not found.")
        return session

    def list(self, *, creator_profile_id: int, limit: int = 100):
        return self.repository.list_for_creator(
            creator_profile_id=int(creator_profile_id), limit=limit
        )

    def history(self, *, session_id, creator_profile_id: int):
        session = self.get(
            session_id=session_id, creator_profile_id=creator_profile_id
        )
        return self.repository.history(
            session_id=session.sales_session_id,
            creator_profile_id=session.creator_profile_id,
        )

    def advance(
        self, *, session_id, creator_profile_id: int, state,
        progression_stage=None, actor_type="OPERATOR",
        actor_identifier: str | None = None, reason: str | None = None,
    ):
        session = self.get(
            session_id=session_id, creator_profile_id=creator_profile_id
        )
        target = self._state(state)
        if target not in self.TRANSITIONS.get(session.state, set()):
            raise SalesSessionError(
                f"Sales Session cannot transition from "
                f"{session.state.value} to {target.value}."
            )
        stage = (
            self._progression(progression_stage)
            if progression_stage is not None
            else session.progression_stage
        )
        return self._transition(
            session, target=target, progression=stage, outcome=None,
            actor=self._actor(actor_type), actor_identifier=actor_identifier,
            reason=reason,
        )

    def set_progression(
        self, *, session_id, creator_profile_id: int, progression_stage,
        actor_type="OPERATOR", actor_identifier: str | None = None,
        reason: str | None = None,
    ):
        session = self.get(
            session_id=session_id, creator_profile_id=creator_profile_id
        )
        if session.state not in ACTIVE_SALES_SESSION_STATES:
            raise SalesSessionError(
                "A terminal Sales Session cannot change progression."
            )
        updated = self.repository.update_progression(
            session_id=session.sales_session_id,
            creator_profile_id=session.creator_profile_id,
            expected_state=session.state,
            progression_stage=self._progression(progression_stage),
            actor_type=self._actor(actor_type),
            actor_identifier=self._text(actor_identifier),
            reason=self._text(reason),
        )
        if updated is None:
            raise SalesSessionError("Sales Session changed concurrently.")
        return updated

    def associate_purchase_intent(
        self, *, session_id, creator_profile_id: int, purchase_intent_id,
        actor_type="SYSTEM", actor_identifier: str | None = None,
        reason: str | None = None,
    ):
        session = self.get(
            session_id=session_id, creator_profile_id=creator_profile_id
        )
        if session.state not in ACTIVE_SALES_SESSION_STATES:
            raise SalesSessionError(
                "A Purchase Intent cannot join a terminal Sales Session."
            )
        intent = self.purchase_intents.get(
            self._uuid(purchase_intent_id),
            creator_profile_id=session.creator_profile_id,
        )
        if intent is None:
            raise KeyError("Purchase Intent was not found.")
        intent_identity = self.identities.get_by_id(
            intent.telegram_identity_mapping_id
        )
        if (
            intent.fanvue_account_id != session.fanvue_account_id
            or intent_identity is None
            or intent_identity.local_fanvue_user_id != session.fanvue_user_id
            or (
                intent.external_fanvue_user_uuid is not None
                and intent.external_fanvue_user_uuid
                != session.external_fanvue_user_uuid
            )
            or (
                session.telegram_identity_mapping_id is not None
                and intent.telegram_identity_mapping_id
                != session.telegram_identity_mapping_id
            )
        ):
            raise SalesSessionError(
                "Purchase Intent does not belong to the Sales Session customer."
            )
        association = self.repository.purchase_intent_association(
            intent.purchase_intent_id
        )
        if (
            association is not None
            and association[0] != session.sales_session_id
        ):
            raise SalesSessionError(
                "Purchase Intent already belongs to another Sales Session."
            )
        if association is not None:
            return {
                "session": session, "purchase_intent": intent,
                "sequence": association[1],
            }
        sequence = self.repository.associate_purchase_intent(
            session=session, purchase_intent_id=intent.purchase_intent_id,
            actor_type=self._actor(actor_type),
            actor_identifier=self._text(actor_identifier),
            reason=self._text(reason),
        )
        return {"session": session, "purchase_intent": intent, "sequence": sequence}

    def complete(
        self, *, session_id, creator_profile_id: int, with_purchase: bool,
        actor_type="OPERATOR", actor_identifier: str | None = None,
        reason: str | None = None,
    ):
        session = self.get(
            session_id=session_id, creator_profile_id=creator_profile_id
        )
        if with_purchase:
            linked = self.repository.list_purchase_intents(
                session_id=session.sales_session_id,
                creator_profile_id=session.creator_profile_id,
            )
            if not any(
                row["status"] == "PURCHASED"
                and row["attribution_result"] == "ATTRIBUTED"
                for row in linked
            ):
                raise SalesSessionError(
                    "Completion with purchase requires an attributed "
                    "purchased Purchase Intent."
                )
        outcome = (
            SalesSessionOutcome.COMPLETED_WITH_PURCHASE
            if with_purchase
            else SalesSessionOutcome.COMPLETED_WITHOUT_PURCHASE
        )
        return self._terminal(
            session, SalesSessionState.COMPLETED, outcome,
            actor_type=actor_type, actor_identifier=actor_identifier,
            reason=reason,
        )

    def expire(self, **values):
        return self._terminal_action(SalesSessionState.EXPIRED, **values)

    def abandon(self, **values):
        return self._terminal_action(SalesSessionState.ABANDONED, **values)

    def cancel(self, **values):
        return self._terminal_action(SalesSessionState.CANCELLED, **values)

    def commercial_context(self, *, session_id, creator_profile_id: int):
        session = self.get(
            session_id=session_id, creator_profile_id=creator_profile_id
        )
        customer = CustomerRepository().get_by_legacy_fanvue_user(
            fanvue_account_id=session.fanvue_account_id,
            fanvue_user_id=session.fanvue_user_id,
        )
        return {
            "sales_session": session,
            "customer": customer,
            "commercial_guidance": self.repository.commercial_guidance(
                session=session
            ),
            "purchase_intents": self.repository.list_purchase_intents(
                session_id=session.sales_session_id,
                creator_profile_id=session.creator_profile_id,
            ),
        }

    def _terminal_action(
        self, target, *, session_id, creator_profile_id: int,
        actor_type="OPERATOR", actor_identifier: str | None = None,
        reason: str | None = None,
    ):
        session = self.get(
            session_id=session_id, creator_profile_id=creator_profile_id
        )
        return self._terminal(
            session, target, self.TERMINAL_OUTCOMES[target],
            actor_type=actor_type, actor_identifier=actor_identifier,
            reason=reason,
        )

    def _terminal(
        self, session, target, outcome, *, actor_type,
        actor_identifier, reason,
    ):
        if session.state not in ACTIVE_SALES_SESSION_STATES:
            if session.state is target:
                return session
            raise SalesSessionError("Sales Session is already terminal.")
        updated = self._transition(
            session, target=target,
            progression=session.progression_stage, outcome=outcome,
            actor=self._actor(actor_type), actor_identifier=actor_identifier,
            reason=reason,
        )
        self.compatibility.ended(updated)
        return updated

    def _transition(
        self, session, *, target, progression, outcome, actor,
        actor_identifier, reason,
    ):
        updated = self.repository.transition(
            session_id=session.sales_session_id,
            creator_profile_id=session.creator_profile_id,
            expected_state=session.state, new_state=target,
            progression_stage=progression, outcome=outcome,
            terminal_reason=(
                self._text(reason)
                if target not in ACTIVE_SALES_SESSION_STATES else None
            ),
            event_type=target.value, actor_type=actor,
            actor_identifier=self._text(actor_identifier),
            reason=self._text(reason),
        )
        if updated is None:
            raise SalesSessionError("Sales Session changed concurrently.")
        return updated

    @staticmethod
    def _actor(value, *, allow_system=True):
        try:
            actor = (
                value if isinstance(value, SalesSessionActorType)
                else SalesSessionActorType(str(value).strip().upper())
            )
        except ValueError as error:
            raise SalesSessionError("Unsupported Sales Session actor.") from error
        if actor is SalesSessionActorType.SYSTEM and not allow_system:
            raise SalesSessionError("SYSTEM cannot initiate a Sales Session.")
        return actor

    @staticmethod
    def _state(value):
        try:
            return (
                value if isinstance(value, SalesSessionState)
                else SalesSessionState(str(value).strip().upper())
            )
        except ValueError as error:
            raise SalesSessionError("Unsupported Sales Session state.") from error

    @staticmethod
    def _progression(value):
        try:
            return (
                value if isinstance(value, SalesSessionProgression)
                else SalesSessionProgression(str(value).strip().upper())
            )
        except ValueError as error:
            raise SalesSessionError(
                "Unsupported Sales Session progression."
            ) from error

    @staticmethod
    def _uuid(value):
        try:
            return value if isinstance(value, UUID) else UUID(str(value))
        except (TypeError, ValueError, AttributeError) as error:
            raise SalesSessionError("A valid identifier is required.") from error

    @staticmethod
    def _text(value):
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _context(value):
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise SalesSessionError("Commercial context must be a mapping.")
        forbidden = {
            "messages", "chat_messages", "customer", "customer_profile",
            "media_assets", "commercial_roles", "commercial_offerings",
            "purchase_intents", "ownership", "entitlements",
        }
        if forbidden.intersection(value):
            raise SalesSessionError(
                "Commercial context cannot duplicate authoritative domain data."
            )
        return dict(value)
