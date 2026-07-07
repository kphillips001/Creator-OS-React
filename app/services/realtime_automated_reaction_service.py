from app.services.automated_reaction_type_router_service import (
    AutomatedReactionTypeRouterService,
)

from app.services.automated_reaction_target_safety_service import (
    AutomatedReactionTargetSafetyService,
)

from app.services.automated_reaction_duplicate_protection_service import (
    AutomatedReactionDuplicateProtectionService,
)

from app.services.automated_reaction_cooldown_service import (
    AutomatedReactionCooldownService,
)

from app.services.automated_reaction_buyer_session_safety_service import (
    AutomatedReactionBuyerSessionSafetyService,
)

from app.services.automated_reaction_global_safety_service import (
    AutomatedReactionGlobalSafetyService,
)

from app.services.automated_reaction_execution_mode_service import (
    AutomatedReactionExecutionModeService,
)

from app.services.automated_reaction_message_builder_service import (
    AutomatedReactionMessageBuilderService,
)

from app.services.automated_reaction_persistence_service import (
    AutomatedReactionPersistenceService,
)

from app.services.automated_reaction_outbound_service import (
    AutomatedReactionOutboundService,
)


class RealtimeAutomatedReactionService:
    """
    3D.18.12 — Realtime Monetization Event Integration

    Full orchestration pipeline for automated
    monetization reactions.

    IMPORTANT:
    Still dry-run protected.
    No live Fanvue outbound sends occur yet.
    """

    def __init__(self):
        self.router = (
            AutomatedReactionTypeRouterService()
        )

        self.target_safety = (
            AutomatedReactionTargetSafetyService()
        )

        self.duplicate_protection = (
            AutomatedReactionDuplicateProtectionService()
        )

        self.cooldown_service = (
            AutomatedReactionCooldownService()
        )

        self.buyer_session_safety = (
            AutomatedReactionBuyerSessionSafetyService()
        )

        self.global_safety = (
            AutomatedReactionGlobalSafetyService()
        )

        self.execution_mode_service = (
            AutomatedReactionExecutionModeService()
        )

        self.message_builder = (
            AutomatedReactionMessageBuilderService()
        )

        self.persistence_service = (
            AutomatedReactionPersistenceService()
        )

        self.outbound_service = (
            AutomatedReactionOutboundService()
        )

    def process_realtime_reaction(
        self,
        monetization_event: dict,
        post_purchase_decision: dict | None = None,
        runtime_state: dict | None = None,
        buyer_context: dict | None = None,
        reaction_history: list | None = None,
    ):
        runtime_state = runtime_state or {}
        buyer_context = buyer_context or {}
        reaction_history = reaction_history or []

        route_result = self.router.resolve_reaction_type(
            monetization_event=monetization_event,
            post_purchase_decision=(
                post_purchase_decision
            ),
        )

        if route_result.get("blocked"):
            return route_result

        reaction_type = (
            route_result.get("reaction_type")
        )

        target_result = (
            self.target_safety
            .validate_target_safety(
                monetization_event=(
                    monetization_event
                ),
                runtime_state=runtime_state,
            )
        )

        if target_result.get("blocked"):
            return target_result

        duplicate_result = (
            self.duplicate_protection
            .validate_duplicate_reaction(
                monetization_event=(
                    monetization_event
                ),
                reaction_type=reaction_type,
                reaction_history=(
                    reaction_history
                ),
            )
        )

        if duplicate_result.get("blocked"):
            return duplicate_result

        cooldown_result = (
            self.cooldown_service
            .validate_cooldown(
                reaction_type=reaction_type,
                user_memory=buyer_context,
                outbound_history=runtime_state.get(
                    "outbound_history",
                    [],
                ),
            )
        )

        if cooldown_result.get("blocked"):
            return cooldown_result

        buyer_session_result = (
            self.buyer_session_safety
            .validate_buyer_session_safety(
                reaction_type=reaction_type,
                runtime_state=runtime_state,
            )
        )

        if buyer_session_result.get(
            "blocked"
        ):
            return buyer_session_result

        global_result = (
            self.global_safety
            .validate_global_safety(
                runtime_state=runtime_state
            )
        )

        if global_result.get("blocked"):
            return global_result

        execution_mode_result = (
            self.execution_mode_service
            .determine_execution_mode(
                runtime_state=runtime_state
            )
        )

        if execution_mode_result.get(
            "blocked"
        ):
            return execution_mode_result

        message_result = (
            self.message_builder.build_message(
                reaction_type=reaction_type,
                monetization_event=(
                    monetization_event
                ),
                buyer_context=buyer_context,
            )
        )

        if message_result.get("blocked"):
            return message_result

        persistence_result = (
            self.persistence_service
            .persist_reaction(
                message_payload=message_result,
                execution_mode_result=(
                    execution_mode_result
                ),
                status="planned",
            )
        )

        outbound_result = (
            self.outbound_service
            .execute_reaction(
                message_payload=message_result,
                execution_mode_result=(
                    execution_mode_result
                ),
            )
        )

        return {
            "success": True,
            "blocked": False,
            "reaction_processed": True,
            "reaction_type": reaction_type,
            "execution_mode": (
                execution_mode_result.get(
                    "execution_mode"
                )
            ),
            "message_result": message_result,
            "persistence_result": (
                persistence_result
            ),
            "outbound_result": (
                outbound_result
            ),
            "reason": (
                "realtime_reaction_processed"
            ),
        }