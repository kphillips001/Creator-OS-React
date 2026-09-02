from app.repositories.monetization_event_repository import (
    create_monetization_event,
    get_monetization_event_by_external_id,
    mark_monetization_event_processed,
)

from app.repositories.buyer_intelligence_repository import (
    upsert_buyer_purchase_stats,
    refresh_buyer_tier,
    upsert_buyer_tip_stats,
    activate_subscription,
    cancel_subscription,
)

from app.repositories.content_unlock_repository import (
    log_content_unlock,
)

from app.services.monetization_event_normalizer_service import (
    MonetizationEventNormalizerService,
)

from app.services.buyer_memory_sync_service import (
    BuyerMemorySyncService,
)

from app.services.realtime_intimacy_reinforcement_service import (
    RealtimeIntimacyReinforcementService,
)

from app.services.post_purchase_decision_service import (
    PostPurchaseDecisionService,
)

from app.services.reaction_execution_service import (
    ReactionExecutionService,
)

from app.services.reaction_safety_gate_service import (
    ReactionSafetyGateService,
)

from app.services.reaction_duplicate_guard_service import (
    ReactionDuplicateGuardService,
)

from app.services.reaction_cooldown_enforcement_service import (
    ReactionCooldownEnforcementService,
)

from app.services.reaction_buyer_session_protection_service import (
    ReactionBuyerSessionProtectionService,
)

from app.services.thank_you_message_executor_service import (
    ThankYouMessageExecutorService,
)

from app.services.tip_reward_executor_service import (
    TipRewardExecutorService,
)

from app.services.subscriber_welcome_executor_service import (
    SubscriberWelcomeExecutorService,
)

from app.services.premium_followup_queue_service import (
    PremiumFollowupQueueService,
)

from app.services.delayed_followup_scheduler_service import (
    DelayedFollowupSchedulerService,
)

from app.services.fanvue_outbound_reaction_service import (
    FanvueOutboundReactionService,
)
from app.services.global_automation_safety_service import GlobalAutomationSafetyService


class RealtimeMonetizationEventService:
    """
    3D.1–3D.13.12 — Realtime monetization event intake
    and reaction orchestration.
    """

    PURCHASE_EVENTS = (
        "purchase_received",
        "purchase_created",
        "unlock_confirmation",
    )

    UNLOCK_EVENTS = (
        "unlock_confirmation",
    )

    TIP_EVENTS = (
        "tip_received",
    )

    SUBSCRIPTION_CREATED_EVENTS = (
        "subscription_created",
    )

    SUBSCRIPTION_CANCELLED_EVENTS = (
        "subscription_cancelled",
    )

    def __init__(self):
        self.normalizer = MonetizationEventNormalizerService()
        self.memory_sync_service = BuyerMemorySyncService()
        self.intimacy_reinforcement_service = (
            RealtimeIntimacyReinforcementService()
        )

        self.post_purchase_decision_service = (
            PostPurchaseDecisionService()
        )
        self.reaction_execution_service = (
            ReactionExecutionService()
        )
        self.reaction_safety_gate_service = (
            ReactionSafetyGateService()
        )
        self.reaction_duplicate_guard_service = (
            ReactionDuplicateGuardService()
        )
        self.reaction_cooldown_enforcement_service = (
            ReactionCooldownEnforcementService()
        )
        self.reaction_buyer_session_protection_service = (
            ReactionBuyerSessionProtectionService()
        )
        self.thank_you_executor = (
            ThankYouMessageExecutorService()
        )
        self.tip_reward_executor = TipRewardExecutorService()
        self.subscriber_welcome_executor = (
            SubscriberWelcomeExecutorService()
        )
        self.premium_followup_queue_service = (
            PremiumFollowupQueueService()
        )
        self.delayed_followup_scheduler_service = (
            DelayedFollowupSchedulerService()
        )
        self.fanvue_outbound_reaction_service = (
            FanvueOutboundReactionService()
        )
        self.global_automation_safety_service = GlobalAutomationSafetyService()

    def process_event(self, event: dict):
        event_type = event.get("event_type")

        if not self.normalizer.is_supported(event_type):
            return {
                "success": False,
                "reason": "unsupported_monetization_event",
                "event_type": event_type,
            }

        normalized = self.normalizer.normalize(event)

        external_event_id = normalized.get("external_event_id")
        fanvue_account_id = normalized.get("fanvue_account_id")
        fanvue_user_id = normalized.get("fanvue_user_id")

        if not fanvue_account_id:
            return {
                "success": False,
                "blocked": True,
                "reason": "missing_fanvue_account_id",
                "event_type": event_type,
                "external_event_id": external_event_id,
            }

        if not fanvue_user_id:
            return {
                "success": False,
                "blocked": True,
                "reason": "missing_fanvue_user_id",
                "fanvue_account_id": fanvue_account_id,
                "event_type": event_type,
                "external_event_id": external_event_id,
            }

        existing = get_monetization_event_by_external_id(
            external_event_id
        )

        if existing:
            return {
                "success": True,
                "duplicate": True,
                "event_type": event_type,
                "external_event_id": external_event_id,
                "fanvue_account_id": fanvue_account_id,
                "fanvue_user_id": fanvue_user_id,
                "monetization_event_id": existing["id"],
            }

        monetization_event_id = create_monetization_event(
            normalized
        )

        if not monetization_event_id:
            return {
                "success": True,
                "duplicate": True,
                "event_type": event_type,
                "external_event_id": external_event_id,
                "fanvue_account_id": fanvue_account_id,
                "fanvue_user_id": fanvue_user_id,
            }

        buyer_stats = None
        unlock_result = None
        tip_result = None
        subscription_result = None
        memory_sync_result = None

        if event_type in self.PURCHASE_EVENTS:
            buyer_stats = self._handle_purchase_event(
                normalized
            )

        if event_type in self.UNLOCK_EVENTS:
            unlock_result = self._handle_unlock_event(
                normalized
            )

        if event_type in self.TIP_EVENTS:
            tip_result = self._handle_tip_event(
                normalized
            )

        if event_type in self.SUBSCRIPTION_CREATED_EVENTS:
            subscription_result = (
                self._handle_subscription_created(
                    normalized
                )
            )

        if event_type in self.SUBSCRIPTION_CANCELLED_EVENTS:
            subscription_result = (
                self._handle_subscription_cancelled(
                    normalized
                )
            )

        intimacy_reinforcement = (
            self.intimacy_reinforcement_service
            .build_updates_from_event(
                event_type=event_type,
                payload=normalized,
            )
        )

        print("\n[REALTIME INTIMACY REINFORCEMENT]")
        print(intimacy_reinforcement)

        memory_sync_result = (
            self.memory_sync_service
            .sync_user_memory(
                fanvue_account_id=fanvue_account_id,
                fanvue_user_id=fanvue_user_id,
                intimacy_reinforcement=intimacy_reinforcement,
            )
        )

        print("\n[BUYER MEMORY SYNCED]")
        print(memory_sync_result)

        reaction_pipeline_result = (
            self.execute_realtime_reaction_pipeline(
                monetization_event=normalized,
            )
        )

        print("\n[3D.13 REALTIME REACTION PIPELINE]")
        print(reaction_pipeline_result)

        mark_monetization_event_processed(
            monetization_event_id
        )

        return {
            "success": True,
            "duplicate": False,
            "event_type": event_type,
            "external_event_id": external_event_id,
            "fanvue_account_id": fanvue_account_id,
            "fanvue_user_id": fanvue_user_id,
            "monetization_event_id": monetization_event_id,
            "buyer_stats": buyer_stats,
            "unlock_result": unlock_result,
            "tip_result": tip_result,
            "subscription_result": subscription_result,
            "memory_sync_result": memory_sync_result,
            "reaction_pipeline_result": (
                reaction_pipeline_result
            ),
            "normalized": normalized,
        }

    def execute_realtime_reaction_pipeline(
        self,
        monetization_event: dict,
        user_memory: dict | None = None,
        runtime_state: dict | None = None,
        reaction_history: list[dict] | None = None,
        system_config: dict | None = None,
        spend_profile: dict | None = None,
    ):
        if not monetization_event:
            return {
                "success": False,
                "reason": "missing_monetization_event",
            }

        if not monetization_event.get("fanvue_account_id"):
            return {
                "success": False,
                "reason": "missing_fanvue_account_id",
            }

        if not monetization_event.get("fanvue_user_id"):
            return {
                "success": False,
                "reason": "missing_fanvue_user_id",
            }

        global_result = self.global_automation_safety_service.can_send_post_purchase_reaction()
        if not global_result.get("allowed", False):
            return {"success": False, "blocked": True, "stage": "global_safety",
                    "reason": global_result.get("reason"), "safety": global_result}

        decision = self._build_post_purchase_decision(
            monetization_event
        )

        execution_plan = (
            self.reaction_execution_service
            .build_execution_plan(
                monetization_event=monetization_event,
                post_purchase_decision=decision,
            )
        )

        if execution_plan.get("blocked"):
            return {
                "success": False,
                "stage": "execution_plan",
                "decision": decision,
                "execution_plan": execution_plan,
            }

        safety = (
            self.reaction_safety_gate_service
            .validate_execution(
                execution_plan=execution_plan,
                user_memory=user_memory,
                system_config=system_config,
            )
        )

        if safety.get("blocked"):
            return {
                "success": False,
                "stage": "safety_gate",
                "decision": decision,
                "execution_plan": execution_plan,
                "safety": safety,
            }

        duplicate = (
            self.reaction_duplicate_guard_service
            .validate_duplicate_safety(
                execution_plan=execution_plan,
                reaction_history=reaction_history,
            )
        )

        if duplicate.get("blocked"):
            return {
                "success": False,
                "stage": "duplicate_guard",
                "decision": decision,
                "execution_plan": execution_plan,
                "duplicate": duplicate,
            }

        cooldown = (
            self.reaction_cooldown_enforcement_service
            .evaluate_cooldown(
                execution_plan=execution_plan,
                spend_profile=spend_profile,
            )
        )

        session = (
            self.reaction_buyer_session_protection_service
            .validate_session_safety(
                execution_plan=execution_plan,
                user_memory=user_memory,
                runtime_state=runtime_state,
            )
        )

        if session.get("blocked"):
            return {
                "success": False,
                "stage": "buyer_session",
                "decision": decision,
                "execution_plan": execution_plan,
                "cooldown": cooldown,
                "session": session,
            }

        reaction_payload = self._build_reaction_payload(
            execution_plan=execution_plan,
            monetization_event=monetization_event,
            spend_profile=spend_profile,
        )

        outbound = (
            self.fanvue_outbound_reaction_service
            .build_outbound_reaction(
                reaction_payload=reaction_payload,
            )
        )

        queue_payload = (
            self.premium_followup_queue_service
            .build_followup_queue_payload(
                execution_plan=execution_plan,
                spend_profile=spend_profile,
            )
        )

        scheduled_followup = (
            self.delayed_followup_scheduler_service
            .build_scheduled_followup(
                queue_payload=queue_payload,
            )
        )

        return {
            "success": True,
            "stage": "complete",
            "decision": decision,
            "execution_plan": execution_plan,
            "safety": safety,
            "duplicate": duplicate,
            "cooldown": cooldown,
            "session": session,
            "reaction_payload": reaction_payload,
            "outbound": outbound,
            "queue_payload": queue_payload,
            "scheduled_followup": scheduled_followup,
        }

    def _build_post_purchase_decision(
        self,
        monetization_event: dict,
    ):
        if hasattr(
            self.post_purchase_decision_service,
            "determine_post_purchase_action",
        ):
            return (
                self.post_purchase_decision_service
                .determine_post_purchase_action(
                    monetization_event
                )
            )

        if hasattr(
            self.post_purchase_decision_service,
            "determine_decision",
        ):
            return (
                self.post_purchase_decision_service
                .determine_decision(
                    monetization_event
                )
            )

        if hasattr(
            self.post_purchase_decision_service,
            "decide",
        ):
            return (
                self.post_purchase_decision_service
                .decide(
                    monetization_event
                )
            )

        return self._fallback_post_purchase_decision(
            monetization_event
        )

    def _fallback_post_purchase_decision(
        self,
        monetization_event: dict,
    ):
        event_type = monetization_event.get("event_type")

        if event_type == "tip_received":
            decision = "tip_reward"

        elif event_type == "subscription_created":
            decision = "subscription_welcome"

        elif event_type in (
            "purchase_received",
            "purchase_created",
            "unlock_confirmation",
        ):
            decision = "thank_you_only"

        else:
            decision = "soft_continue"

        return {
            "decision": decision,
            "aggression_level": "low",
            "should_escalate": False,
            "should_slow_down": False,
            "allow_followup": True,
            "pacing_profile": "normal",
            "followup_mode": "delayed",
            "ppv_suppressed": True,
            "escalation_paused": False,
            "next_best_offer": "default_relationship_sequence",
            "reasons": [
                "fallback_post_purchase_decision",
            ],
        }

    def _build_reaction_payload(
        self,
        execution_plan: dict,
        monetization_event: dict,
        spend_profile: dict | None = None,
    ):
        decision_type = execution_plan.get(
            "decision_type"
        )

        if decision_type == "tip_reward":
            return (
                self.tip_reward_executor
                .build_tip_reward_payload(
                    execution_plan=execution_plan,
                    spend_profile=spend_profile,
                    monetization_event=monetization_event,
                )
            )

        if decision_type == "subscription_welcome":
            return (
                self.subscriber_welcome_executor
                .build_welcome_payload(
                    execution_plan=execution_plan,
                    spend_profile=spend_profile,
                    subscription_event=monetization_event,
                )
            )

        return (
            self.thank_you_executor
            .build_thank_you_payload(
                execution_plan=execution_plan,
                spend_profile=spend_profile,
            )
        )

    def _handle_purchase_event(
        self,
        normalized: dict,
    ):
        fanvue_account_id = normalized.get("fanvue_account_id")
        fanvue_user_id = normalized.get("fanvue_user_id")

        if not fanvue_account_id:
            return {
                "success": False,
                "reason": "missing_fanvue_account_id",
            }

        if not fanvue_user_id:
            return {
                "success": False,
                "reason": "missing_fanvue_user_id",
            }

        amount = float(normalized.get("amount") or 0)

        buyer_stats = upsert_buyer_purchase_stats(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_id,
            purchase_amount=amount,
        )

        print("\n[BUYER INTELLIGENCE UPDATED]")
        print(buyer_stats)

        refreshed = refresh_buyer_tier(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_id,
        )

        print("\n[BUYER TIER REFRESHED]")
        print(refreshed)

        return {
            "success": True,
            "fanvue_account_id": fanvue_account_id,
            "fanvue_user_id": fanvue_user_id,
            "amount": amount,
            "buyer_stats": buyer_stats,
            "refreshed_buyer_tier": refreshed,
        }

    def _handle_unlock_event(
        self,
        normalized: dict,
    ):
        fanvue_account_id = normalized.get("fanvue_account_id")
        fanvue_user_id = normalized.get("fanvue_user_id")

        if not fanvue_account_id:
            return {
                "success": False,
                "reason": "missing_fanvue_account_id",
            }

        if not fanvue_user_id:
            return {
                "success": False,
                "reason": "missing_fanvue_user_id",
            }

        content_tag = normalized.get("content_tag")
        fanvue_media_uuid = normalized.get("fanvue_media_uuid")
        amount = float(normalized.get("amount") or 0)

        unlock_row = log_content_unlock(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_id,
            content_item_id=normalized.get("content_item_id"),
            content_tag=content_tag,
            fanvue_media_uuid=fanvue_media_uuid,
            purchase_amount=amount,
            commercial_offering_id=normalized.get("commercial_offering_id"),
            provider_resource_id=normalized.get("provider_resource_id"),
        )

        print("\n[CONTENT UNLOCK LOGGED]")
        print(unlock_row)

        return {
            "success": True,
            "fanvue_account_id": fanvue_account_id,
            "fanvue_user_id": fanvue_user_id,
            "content_tag": content_tag,
            "fanvue_media_uuid": fanvue_media_uuid,
            "purchase_amount": amount,
            "unlock_row": unlock_row,
        }

    def _handle_tip_event(
        self,
        normalized: dict,
    ):
        fanvue_account_id = normalized.get("fanvue_account_id")
        fanvue_user_id = normalized.get("fanvue_user_id")

        if not fanvue_account_id:
            return {
                "success": False,
                "reason": "missing_fanvue_account_id",
            }

        if not fanvue_user_id:
            return {
                "success": False,
                "reason": "missing_fanvue_user_id",
            }

        amount = float(normalized.get("amount") or 0)

        tip_stats = upsert_buyer_tip_stats(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_id,
            tip_amount=amount,
        )

        refreshed = refresh_buyer_tier(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_id,
        )

        print("\n[TIP INTELLIGENCE UPDATED]")
        print(tip_stats)

        print("\n[BUYER TIER REFRESHED AFTER TIP]")
        print(refreshed)

        return {
            "success": True,
            "fanvue_account_id": fanvue_account_id,
            "fanvue_user_id": fanvue_user_id,
            "tip_amount": amount,
            "tip_stats": tip_stats,
            "refreshed_buyer_tier": refreshed,
            "should_acknowledge_tip": True,
        }

    def _handle_subscription_created(
        self,
        normalized: dict,
    ):
        fanvue_account_id = normalized.get("fanvue_account_id")
        fanvue_user_id = normalized.get("fanvue_user_id")

        if not fanvue_account_id:
            return {
                "success": False,
                "reason": "missing_fanvue_account_id",
            }

        if not fanvue_user_id:
            return {
                "success": False,
                "reason": "missing_fanvue_user_id",
            }

        result = activate_subscription(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_id,
        )

        print("\n[SUBSCRIPTION ACTIVATED]")
        print(result)

        return {
            "success": True,
            "fanvue_account_id": fanvue_account_id,
            "fanvue_user_id": fanvue_user_id,
            "subscription_result": result,
        }

    def _handle_subscription_cancelled(
        self,
        normalized: dict,
    ):
        fanvue_account_id = normalized.get("fanvue_account_id")
        fanvue_user_id = normalized.get("fanvue_user_id")

        if not fanvue_account_id:
            return {
                "success": False,
                "reason": "missing_fanvue_account_id",
            }

        if not fanvue_user_id:
            return {
                "success": False,
                "reason": "missing_fanvue_user_id",
            }

        result = cancel_subscription(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_id,
        )

        print("\n[SUBSCRIPTION CANCELLED]")
        print(result)

        return {
            "success": True,
            "fanvue_account_id": fanvue_account_id,
            "fanvue_user_id": fanvue_user_id,
            "subscription_result": result,
        }
