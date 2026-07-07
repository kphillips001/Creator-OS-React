from app.services.global_automation_safety_service import (
    GlobalAutomationSafetyService,
)

from app.services.decision_engine_continuation_injection_service import (
    DecisionEngineContinuationInjectionService,
)

from app.services.runtime_buyer_state_refresh_service import (
    RuntimeBuyerStateRefreshService,
)

from app.services.post_purchase_continuation_service import (
    PostPurchaseContinuationService,
)

from app.services.realtime_retention_trigger_service import (
    RealtimeRetentionTriggerService,
)


class DecisionEngineRefreshHookService:
    """
    3D.17.1 - 3D.17.6

    Centralized realtime refresh propagation layer.

    PURPOSE:
    After monetization events complete processing:

    - refresh buyer memory context
    - refresh runtime buyer state
    - propagate DecisionEngine-ready context
    - determine continuation eligibility
    - determine retention routing
    - inject continuation intelligence into DecisionEngine runtime
    - enforce automation safety toggles

    IMPORTANT:
    This service DOES NOT directly send outbound Fanvue messages.
    It only prepares safe refresh + continuation intelligence.
    """

    def __init__(self):
        self.global_safety_service = (
            GlobalAutomationSafetyService()
        )

        self.continuation_injection_service = (
            DecisionEngineContinuationInjectionService()
        )

        self.runtime_buyer_state_refresh_service = (
            RuntimeBuyerStateRefreshService()
        )

        self.post_purchase_continuation_service = (
            PostPurchaseContinuationService()
        )

        self.realtime_retention_trigger_service = (
            RealtimeRetentionTriggerService()
        )

    def build_buyer_memory_context(
        self,
        memory_sync_result: dict | None,
    ):
        """
        3D.17.2

        Extracts refreshed buyer memory into a clean
        DecisionEngine-ready context object.
        """

        if not memory_sync_result:
            return {
                "success": False,
                "reason": "missing_memory_sync_result",
                "memory_row": {},
                "buyer_memory_available": False,
            }

        memory_row = memory_sync_result.get("memory_row") or {}

        return {
            "success": True,
            "buyer_memory_available": bool(memory_row),
            "memory_row": memory_row,
            "buyer_tier": memory_row.get("buyer_tier"),
            "user_value_tier": memory_row.get("user_value_tier"),
            "total_spend": memory_row.get("total_spend"),
            "purchase_count": memory_row.get("purchase_count"),
            "total_tip_amount": memory_row.get("total_tip_amount"),
            "recent_purchase_active": memory_row.get(
                "recent_purchase_active"
            ),
            "recent_tip_active": memory_row.get(
                "recent_tip_active"
            ),
            "is_spender": memory_row.get("is_spender"),
            "is_whale": memory_row.get("is_whale"),
            "is_subscriber": memory_row.get("is_subscriber"),
            "subscription_status": memory_row.get(
                "subscription_status"
            ),
            "owned_content_count": memory_row.get(
                "owned_content_count"
            ),
            "owned_vip_count": memory_row.get(
                "owned_vip_count"
            ),
            "owned_premium_count": memory_row.get(
                "owned_premium_count"
            ),
            "recent_owned_content_tags": memory_row.get(
                "recent_owned_content_tags",
                [],
            ),
            "collector_score": memory_row.get(
                "collector_score"
            ),
            "repeat_purchase_score": memory_row.get(
                "repeat_purchase_score"
            ),
        }

    def build_refresh_payload(
        self,
        monetization_event: dict,
        buyer_stats: dict | None = None,
        memory_sync_result: dict | None = None,
        intimacy_reinforcement: dict | None = None,
        runtime_state: dict | None = None,
        reaction_pipeline_result: dict | None = None,
    ):
        if not monetization_event:
            return {
                "success": False,
                "reason": "missing_monetization_event",
            }

        fanvue_user_id = monetization_event.get(
            "fanvue_user_id"
        )

        event_type = monetization_event.get(
            "event_type"
        )

        safety_result = (
            self.global_safety_service
            .can_send_monetization()
        )

        automation_allowed = bool(
            safety_result.get("allowed", False)
        )

        live_sends_allowed = automation_allowed

        buyer_memory_context = (
            self.build_buyer_memory_context(
                memory_sync_result
            )
        )

        runtime_buyer_state = (
            self.runtime_buyer_state_refresh_service
            .refresh_runtime_state(
                buyer_memory_context
            )
        )

        continuation_route = (
            self.post_purchase_continuation_service
            .determine_continuation(
                monetization_event=monetization_event,
                buyer_memory_context=buyer_memory_context,
                runtime_buyer_state=runtime_buyer_state,
            )
        )

        retention_route = (
            self.realtime_retention_trigger_service
            .build_retention_route(
                continuation_route=continuation_route,
                runtime_buyer_state=runtime_buyer_state,
                buyer_memory_context=buyer_memory_context,
            )
        )

        decisionengine_injection = (
            self.continuation_injection_service
            .build_injection(
                {
                    "monetization_event": monetization_event,
                    "buyer_state": (
                        buyer_stats
                        or runtime_buyer_state
                        or {}
                    ),
                    "buyer_memory": buyer_memory_context,
                    "continuation_route": continuation_route,
                    "retention_route": retention_route,
                }
            )
        )

        refresh_payload = {
            "success": True,
            "fanvue_user_id": fanvue_user_id,
            "event_type": event_type,

            # Runtime refresh chain
            "runtime_buyer_state": runtime_buyer_state,
            "continuation_route": continuation_route,
            "retention_route": retention_route,
            "decisionengine_injection": (
                decisionengine_injection
            ),

            # Core realtime refresh state
            "buyer_stats": buyer_stats,
            "memory_sync_result": memory_sync_result,
            "buyer_memory_context": buyer_memory_context,
            "runtime_state": runtime_state,
            "intimacy_reinforcement": (
                intimacy_reinforcement
            ),

            # Ownership / monetization intelligence
            "ownership_intelligence": (
                (
                    memory_sync_result or {}
                ).get(
                    "memory_row",
                    {},
                )
            ),

            # Reaction intelligence
            "reaction_pipeline_result": (
                reaction_pipeline_result
            ),

            # Automation safety
            "safety_result": safety_result,
            "automation_allowed": automation_allowed,
            "live_sends_allowed": live_sends_allowed,

            # Realtime continuation eligibility
            "continuation_eligible": (
                automation_allowed
                and live_sends_allowed
            ),

            # DecisionEngine propagation flags
            "decisionengine_refresh_required": True,
            "decisionengine_injection_available": bool(
                decisionengine_injection
                and decisionengine_injection.get(
                    "injection_enabled"
                )
            ),
            "buyer_memory_refresh_completed": (
                memory_sync_result is not None
            ),
            "runtime_refresh_completed": bool(
                runtime_buyer_state
                and runtime_buyer_state.get("success")
            ),

            # Safety metadata
            "refresh_only_mode": (
                not (
                    automation_allowed
                    and live_sends_allowed
                )
            ),
            "automation_note": (
                "Refresh hook only. No outbound Fanvue "
                "automation is performed by this service."
            ),
        }

        return refresh_payload