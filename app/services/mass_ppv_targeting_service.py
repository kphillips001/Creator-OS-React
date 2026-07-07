from app.dashboard.config import load_dashboard_config
from app.services.monetization_priority_service import MonetizationPriorityService
from app.services.realtime_buyer_state_service import RealtimeBuyerStateService
from app.services.content_ownership_service import (
    ContentOwnershipService,
)
from app.services.outreach_mass_ppv_coordination_service import (
    OutreachMassPPVCoordinationService,
)


class MassPPVTargetingService:
    """
    Mass PPV targeting rules.

    Purpose:
    - Allow followers / non-subscribers into Mass PPV campaigns
    - Allow low/mid value subscribers into Mass PPV campaigns
    - Block whales and high-value users
    - Block users currently being monetized 1-on-1
    - Block users in active buyer session / active offer / rewarm states
    - Respect the Mass PPV dashboard module switch
    - Keep Mass PPV separate from 1-on-1 monetization

    Section 6 hardened:
    Ownership checks are scoped by:
    - fanvue_account_id
    - fanvue_user_id
    """

    def __init__(self):
        self.priority_service = MonetizationPriorityService()
        self.realtime_buyer_state_service = RealtimeBuyerStateService()
        self.content_ownership_service = (
            ContentOwnershipService()
        )
        self.outreach_mass_ppv_coordination_service = (
            OutreachMassPPVCoordinationService()
        )

    def is_user_eligible_for_mass_ppv(
        self,
        fanvue_user: dict,
        memory: dict,
        content_tag: str | None = None,
    ) -> tuple[bool, str]:
        fanvue_user = fanvue_user or {}
        memory = memory or {}

        fanvue_account_id = (
            fanvue_user.get("fanvue_account_id")
            or memory.get("fanvue_account_id")
        )

        user_id = fanvue_user.get("id") or memory.get("fanvue_user_id")
        username = fanvue_user.get("username") or memory.get("username")

        print("\n[MASS PPV TARGETING CHECK]")
        print(f"account_id={fanvue_account_id}")
        print(f"user_id={user_id}")
        print(f"username={username}")

        if not fanvue_account_id:
            print("[MASS PPV BLOCK] missing_fanvue_account_id")
            return False, "missing_fanvue_account_id"

        if not user_id:
            print("[MASS PPV BLOCK] missing_fanvue_user_id")
            return False, "missing_fanvue_user_id"

        # --------------------------------------------------
        # 0. GLOBAL MODULE SWITCH CHECK (HARD BLOCK)
        # --------------------------------------------------
        if not self._is_mass_ppv_enabled():
            print("[MASS PPV BLOCK] module_disabled")
            return False, "module_disabled"

        # --------------------------------------------------
        # 0.5 OUTREACH → MASS PPV COORDINATION CHECK
        # --------------------------------------------------
        coordination_memory = {
            **memory,
            "fanvue_account_id": fanvue_account_id,
            "fanvue_user_id": user_id,
            "username": username,
        }

        coordination_result = (
            self.outreach_mass_ppv_coordination_service.evaluate(
                user_memory=coordination_memory,
            )
        )

        if not coordination_result.get("allow_mass_ppv", False):
            print(
                "[MASS PPV BLOCK] outreach_mass_ppv_coordination: "
                f"{coordination_result.get('recommended_action')}"
            )
            return (
                False,
                "outreach_mass_ppv_coordination:"
                f"{coordination_result.get('recommended_action')}",
            )

        print(
            "[MASS PPV INFO] outreach_mass_ppv_coordination "
            f"priority={coordination_result.get('mass_ppv_priority')} "
            f"action={coordination_result.get('recommended_action')}"
        )

        # --------------------------------------------------
        # 1. REAL-TIME BUYER STATE CHECK (SAFETY GATE)
        # --------------------------------------------------
        realtime_state = self.realtime_buyer_state_service.get_buyer_state(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=user_id,
        )

        realtime_eligibility = (
            self.realtime_buyer_state_service
            .is_eligible_for_mass_ppv(
                realtime_state
            )
        )

        if not realtime_eligibility["allowed"]:
            block_reason = realtime_eligibility["block_reason"]

            print(
                "[MASS PPV BLOCK] realtime_buyer_state_blocked: "
                f"{block_reason}"
            )

            return False, f"realtime_buyer_state:{block_reason}"

        # --------------------------------------------------
        # 1.5 OWNERSHIP FILTER
        # --------------------------------------------------
        if content_tag:
            already_owned = (
                self.content_ownership_service
                .user_already_owns_content(
                    fanvue_account_id=fanvue_account_id,
                    fanvue_user_id=user_id,
                    content_tag=content_tag,
                )
            )

            if already_owned:
                print(
                    "[MASS PPV BLOCK] already owns content: "
                    f"account_id={fanvue_account_id} "
                    f"user_id={user_id} "
                    f"content_tag={content_tag}"
                )

                return False, "already_owns_content"

        # --------------------------------------------------
        # 2. BLOCK WHALES / HIGH VALUE USERS
        # --------------------------------------------------
        if self._is_whale_or_high_value(memory):
            print("[MASS PPV BLOCK] whale_or_high_value")
            return False, "whale_or_high_value"

        # --------------------------------------------------
        # 3. BLOCK USERS IN 1-ON-1 MONETIZATION
        # --------------------------------------------------
        if self._is_in_one_on_one_monetization(memory):
            print("[MASS PPV BLOCK] one_on_one_monetization_active")
            return False, "one_on_one_monetization_active"

        # --------------------------------------------------
        # 4. BLOCK REWARM USERS
        # --------------------------------------------------
        if memory.get("subscriber_rewarm_required"):
            print("[MASS PPV BLOCK] rewarm_required")
            return False, "rewarm_required"

        # --------------------------------------------------
        # 5. GLOBAL MONETIZATION PRIORITY CHECK (LOG ONLY)
        # --------------------------------------------------
        priority_result = (
            self.priority_service
            .can_enter_monetization_flow(
                user_memory=memory,
                source="mass_ppv",
                fanvue_user=fanvue_user,
            )
        )

        self.priority_service.log_monetization_decision(
            source="mass_ppv",
            user_id=user_id,
            username=username,
            result=priority_result,
            user_memory=memory,
        )

        print("[MASS PPV INFO] priority check logged but NOT enforced")

        # --------------------------------------------------
        # 6. ALLOW FOLLOWERS / NON-SUBSCRIBERS
        # --------------------------------------------------
        if not self._is_subscriber(fanvue_user, memory):
            print("[MASS PPV ALLOW] follower_or_non_subscriber")
            return True, "follower_or_non_subscriber"

        # --------------------------------------------------
        # 7. ALLOW LOW / MID VALUE SUBSCRIBERS ONLY
        # --------------------------------------------------
        if self._is_low_or_mid_value_subscriber(memory):
            print("[MASS PPV ALLOW] low_mid_value_subscriber")
            return True, "low_mid_value_subscriber"

        print("[MASS PPV BLOCK] subscriber_not_low_mid_value")
        return False, "subscriber_not_low_mid_value"

    def _is_mass_ppv_enabled(self) -> bool:
        behavior_config, _creator_profile = load_dashboard_config()
        modules = behavior_config.get("modules", {})
        return bool(modules.get("mass_ppv_enabled", False))

    def _is_whale_or_high_value(self, memory: dict) -> bool:
        user_value_tier = (memory.get("user_value_tier") or "").lower()
        buyer_tier = (memory.get("buyer_tier") or "").lower()

        return bool(
            memory.get("is_whale")
            or user_value_tier in {"high", "whale"}
            or buyer_tier in {"whale", "high_value"}
        )

    def _is_in_one_on_one_monetization(self, memory: dict) -> bool:
        current_route = (memory.get("current_route") or "").lower()
        last_route = (memory.get("last_route") or "").lower()
        offer_state = (memory.get("offer_state") or "").lower()
        recommended_action = (memory.get("recommended_action") or "").lower()

        blocked_routes = {
            "active_chat",
            "subscriber_monetization",
            "offer",
            "close",
            "sales",
            "buyer_session",
        }

        active_offer_states = {
            "active",
            "sent",
            "pending",
            "nudging",
        }

        active_actions = {
            "offer",
            "close",
            "build_tension",
        }

        return bool(
            memory.get("buyer_session_active")
            or memory.get("close_ready")
            or current_route in blocked_routes
            or last_route in blocked_routes
            or offer_state in active_offer_states
            or recommended_action in active_actions
        )

    def _is_subscriber(self, fanvue_user: dict, memory: dict) -> bool:
        relationship_status = (
            fanvue_user.get("relationship_status")
            or memory.get("relationship_status")
            or ""
        ).lower()

        return bool(
            fanvue_user.get("is_subscriber")
            or memory.get("is_subscriber")
            or relationship_status == "subscriber"
        )

    def _is_low_or_mid_value_subscriber(self, memory: dict) -> bool:
        user_value_tier = (memory.get("user_value_tier") or "").lower()
        buyer_tier = (memory.get("buyer_tier") or "").lower()

        allowed_value_tiers = {"", "cold", "low", "mid", "medium"}
        blocked_buyer_tiers = {"hot", "whale", "high_value"}

        if user_value_tier not in allowed_value_tiers:
            return False

        if buyer_tier in blocked_buyer_tiers:
            return False

        return True