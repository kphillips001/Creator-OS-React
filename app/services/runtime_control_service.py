"""Creator OS Runtime Control service.

RuntimeControlService owns runtime mode/state only. It does not own
DecisionEngine intelligence, Telegram transport, Publishing, Product state, or
business-domain decisions.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from app.models.runtime_control import (
    RuntimeControlDecision,
    RuntimeControlSnapshot,
    RuntimeControlState,
    RuntimeMode,
    RuntimeObservation,
    RuntimeStatus,
    utc_now,
)
from app.repositories.runtime_control_repository import RuntimeControlRepository


class RuntimeControlService:
    """Persist and evaluate Creator OS runtime mode per creator profile."""

    DEFAULT_CREATOR_PROFILE_ID = "default"

    BANNERS = {
        RuntimeMode.OFFLINE: (
            "Creator OS is currently paused. Customers will not receive automatic replies."
        ),
        RuntimeMode.OBSERVE: (
            "Creator OS is observing conversations. No customer messages will be sent."
        ),
        RuntimeMode.LIVE: "Creator OS is actively managing your business.",
    }

    def __init__(
        self,
        *,
        repository: RuntimeControlRepository | None = None,
        default_provider: str = "telegram",
    ) -> None:
        self.repository = repository or RuntimeControlRepository()
        self.default_provider = default_provider

    def build_snapshot(
        self,
        *,
        creator_profile_id: str | int | None = None,
    ) -> RuntimeControlSnapshot:
        state = self.get_state(creator_profile_id=creator_profile_id)
        return RuntimeControlSnapshot(
            creator_profile_id=state.creator_profile_id,
            runtime_status=state.status,
            current_mode=state.mode,
            last_started=state.last_started,
            last_stopped=state.last_stopped,
            active_conversations=state.active_conversations,
            pending_deliveries=state.pending_deliveries,
            pending_offers=state.pending_offers,
            current_runtime_provider=state.current_runtime_provider,
            observed_recommendations=state.observed_recommendations,
            warning_banner=self.BANNERS[state.mode],
            compatibility=self._compatibility(),
            summary={
                "runtime_status": state.status.value,
                "current_mode": state.mode.value,
                "active_conversations": state.active_conversations,
                "pending_deliveries": state.pending_deliveries,
                "pending_offers": state.pending_offers,
                "current_runtime_provider": state.current_runtime_provider,
                "observed_recommendation_count": len(state.observed_recommendations),
            },
        )

    def start(
        self,
        *,
        creator_profile_id: str | int | None = None,
        provider: str | None = None,
    ) -> RuntimeControlState:
        state = self.get_state(creator_profile_id=creator_profile_id)
        updated = replace(
            state,
            mode=RuntimeMode.LIVE,
            status=RuntimeStatus.LIVE,
            current_runtime_provider=provider or state.current_runtime_provider,
            last_started=utc_now(),
            updated_at=utc_now(),
        )
        self.repository.save_state(updated)
        return updated

    def observe(
        self,
        *,
        creator_profile_id: str | int | None = None,
        provider: str | None = None,
    ) -> RuntimeControlState:
        state = self.get_state(creator_profile_id=creator_profile_id)
        updated = replace(
            state,
            mode=RuntimeMode.OBSERVE,
            status=RuntimeStatus.OBSERVE,
            current_runtime_provider=provider or state.current_runtime_provider,
            last_started=state.last_started or utc_now(),
            updated_at=utc_now(),
        )
        self.repository.save_state(updated)
        return updated

    def stop(
        self,
        *,
        creator_profile_id: str | int | None = None,
    ) -> RuntimeControlState:
        state = self.get_state(creator_profile_id=creator_profile_id)
        updated = replace(
            state,
            mode=RuntimeMode.OFFLINE,
            status=RuntimeStatus.OFFLINE,
            active_conversations=0,
            last_stopped=utc_now(),
            updated_at=utc_now(),
        )
        self.repository.save_state(updated)
        return updated

    def get_state(
        self,
        *,
        creator_profile_id: str | int | None = None,
    ) -> RuntimeControlState:
        profile_id = self._profile_id(creator_profile_id)
        state = self.repository.get_state(profile_id)
        if state is not None:
            return state
        state = RuntimeControlState(
            creator_profile_id=profile_id,
            current_runtime_provider=self.default_provider,
            metadata={
                "source": "RuntimeControlService",
                "provider_neutral": True,
            },
        )
        return state

    def evaluate_runtime(
        self,
        *,
        creator_profile_id: str | int | None = None,
    ) -> RuntimeControlDecision:
        state = self.get_state(creator_profile_id=creator_profile_id)
        if state.mode == RuntimeMode.LIVE:
            return RuntimeControlDecision(
                mode=state.mode,
                status=state.status,
                allow_decision_engine=True,
                allow_replies=True,
                allow_offers=True,
                allow_deliveries=True,
                reason="runtime_live",
                metadata=self._compatibility(),
            )
        if state.mode == RuntimeMode.OBSERVE:
            return RuntimeControlDecision(
                mode=state.mode,
                status=state.status,
                allow_decision_engine=True,
                allow_replies=False,
                allow_offers=False,
                allow_deliveries=False,
                observe_only=True,
                reason="runtime_observe",
                metadata=self._compatibility(),
            )
        return RuntimeControlDecision(
            mode=state.mode,
            status=state.status,
            allow_decision_engine=False,
            allow_replies=False,
            allow_offers=False,
            allow_deliveries=False,
            reason="runtime_offline",
            metadata=self._compatibility(),
        )

    def record_live_turn(
        self,
        *,
        creator_profile_id: str | int | None = None,
        has_offer: bool = False,
        has_delivery: bool = False,
    ) -> RuntimeControlState:
        state = self.get_state(creator_profile_id=creator_profile_id)
        updated = replace(
            state,
            active_conversations=state.active_conversations + 1,
            pending_offers=max(0, state.pending_offers + (1 if has_offer else 0)),
            pending_deliveries=max(
                0,
                state.pending_deliveries + (1 if has_delivery else 0),
            ),
            updated_at=utc_now(),
        )
        self.repository.save_state(updated)
        return updated

    def record_observation(
        self,
        *,
        creator_profile_id: str | int | None = None,
        customer_id: str | None = None,
        conversation_id: str | None = None,
        message_text: str = "",
        suggested_reply: str | None = None,
        suggested_offer: Mapping[str, Any] | None = None,
        suggested_delivery: Mapping[str, Any] | None = None,
        suggested_follow_up: Mapping[str, Any] | None = None,
        provider: str | None = None,
    ) -> RuntimeObservation:
        state = self.get_state(creator_profile_id=creator_profile_id)
        observation = RuntimeObservation(
            observation_id=f"runtime-observation-{len(state.observed_recommendations) + 1}",
            creator_profile_id=state.creator_profile_id,
            customer_id=customer_id,
            conversation_id=conversation_id,
            message_text=message_text,
            suggested_reply=suggested_reply,
            suggested_offer=dict(suggested_offer or {}),
            suggested_delivery=dict(suggested_delivery or {}),
            suggested_follow_up=dict(suggested_follow_up or {}),
            provider=provider or state.current_runtime_provider,
            metadata={
                "source": "RuntimeControlService",
                "observe_only": True,
                "sent_to_customer": False,
                "executed_delivery": False,
            },
        )
        observations = (observation,) + tuple(state.observed_recommendations)
        updated = replace(
            state,
            active_conversations=state.active_conversations + 1,
            pending_offers=state.pending_offers
            + (1 if suggested_offer else 0),
            pending_deliveries=state.pending_deliveries
            + (1 if suggested_delivery else 0),
            observed_recommendations=observations[:100],
            updated_at=utc_now(),
        )
        self.repository.save_state(updated)
        return observation

    @classmethod
    def _profile_id(cls, creator_profile_id: str | int | None) -> str:
        if creator_profile_id is None:
            return cls.DEFAULT_CREATOR_PROFILE_ID
        text = str(creator_profile_id).strip()
        return text or cls.DEFAULT_CREATOR_PROFILE_ID

    @staticmethod
    def _compatibility() -> Mapping[str, Any]:
        return {
            "read_only_snapshot": True,
            "owns_runtime_state": True,
            "owns_decision_engine": False,
            "owns_telegram_transport": False,
            "owns_products": False,
            "owns_publishing": False,
            "provider_neutral": True,
        }
