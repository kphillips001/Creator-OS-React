import os

from app.services.global_automation_safety_service import (
    GlobalAutomationSafetyService,
)

from app.services.reaction_execution_service import (
    ReactionExecutionService,
)

from app.services.reaction_duplicate_guard_service import (
    ReactionDuplicateGuardService,
)

from app.services.reaction_safety_gate_service import (
    ReactionSafetyGateService,
)

from app.services.reaction_cooldown_enforcement_service import (
    ReactionCooldownEnforcementService,
)

from app.services.reaction_buyer_session_protection_service import (
    ReactionBuyerSessionProtectionService,
)

from app.services.fanvue_outbound_reaction_service import (
    FanvueOutboundReactionService,
)


class AutomatedReactionSenderService:
    """
    3D.18.1 — Automated Reaction Sender Foundation

    Safe orchestration foundation for realtime monetization reactions.

    IMPORTANT:
    This service DOES NOT perform live Fanvue sends yet.

    Current responsibilities:
    - prepare reaction execution flow
    - validate automation safety
    - validate duplicate protection
    - validate cooldown safety
    - validate buyer-session safety
    - validate automation toggles
    - build structured dry-run result
    """

    def __init__(self):
        self.global_safety_service = (
            GlobalAutomationSafetyService()
        )

        self.execution_service = (
            ReactionExecutionService()
        )

        self.duplicate_guard_service = (
            ReactionDuplicateGuardService()
        )

        self.safety_gate_service = (
            ReactionSafetyGateService()
        )

        self.cooldown_service = (
            ReactionCooldownEnforcementService()
        )

        self.buyer_session_protection_service = (
            ReactionBuyerSessionProtectionService()
        )

        self.outbound_reaction_service = (
            FanvueOutboundReactionService()
        )

    def prepare_reaction_send(
        self,
        monetization_event: dict,
        post_purchase_decision: dict,
        user_memory: dict | None = None,
        runtime_state: dict | None = None,
        spend_profile: dict | None = None,
        reaction_history: list[dict] | None = None,
    ):
        """
        Foundation orchestration entrypoint.

        PREPARES reaction execution only.
        Does NOT send outbound Fanvue messages yet.
        """

        if not monetization_event:
            return self._blocked(
                "missing_monetization_event"
            )

        if not post_purchase_decision:
            return self._blocked(
                "missing_post_purchase_decision"
            )

        local_user_id = monetization_event.get(
            "local_user_id"
        )

        if not local_user_id:
            return self._blocked(
                "missing_local_user_mapping"
            )

        global_safety = (
            self.global_safety_service
            .can_send_post_purchase_reaction()
        )

        if global_safety.get("blocked"):
            return self._blocked(
                global_safety.get("reason")
                or "global_safety_blocked",
                {
                    "global_safety": global_safety,
                },
            )

        if not self._env_enabled(
            "ENABLE_REALTIME_MONETIZATION_REACTIONS"
        ):
            return self._blocked(
                "realtime_monetization_reactions_disabled"
            )

        execution_plan = (
            self.execution_service
            .build_execution_plan(
                monetization_event=monetization_event,
                post_purchase_decision=(
                    post_purchase_decision
                ),
            )
        )

        duplicate_check = (
            self.duplicate_guard_service
            .validate_duplicate_safety(
                execution_plan=execution_plan,
                reaction_history=reaction_history,
            )
        )

        cooldown_check = (
            self.cooldown_service
            .validate_cooldown(
                execution_plan=execution_plan,
                user_memory=user_memory,
                runtime_state=runtime_state,
            )
        )

        buyer_session_check = (
            self.buyer_session_protection_service
            .validate_buyer_session_safety(
                execution_plan=execution_plan,
                runtime_state=runtime_state,
            )
        )

        return {
            "success": True,
            "prepared": True,
            "live_send_performed": False,
            "reaction_ready": True,
            "reaction_type": execution_plan.get(
                "reaction_type"
            ),
            "global_safety": global_safety,
            "duplicate_check": duplicate_check,
            "cooldown_check": cooldown_check,
            "buyer_session_check": (
                buyer_session_check
            ),
            "execution_plan": execution_plan,
            "spend_profile": spend_profile,
            "safe_mode": True,
            "reason": (
                "foundation_preparation_only"
            ),
        }

    def _env_enabled(
        self,
        env_name: str,
    ) -> bool:
        return (
            os.getenv(env_name, "false")
            .lower()
            .strip()
            == "true"
        )

    def _blocked(
        self,
        reason: str,
        extra: dict | None = None,
    ):
        result = {
            "success": False,
            "blocked": True,
            "prepared": False,
            "live_send_performed": False,
            "reason": reason,
        }

        if extra:
            result.update(extra)

        return result