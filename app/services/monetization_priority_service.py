class MonetizationPriorityService:
    """
    Central priority map for monetization routing.

    Highest priority wins.
    Prevents users from being processed by multiple monetization engines.
    """

    PRIORITY_ORDER = [
        "active_chat",
        "active_offer_or_nudge",
        "rewarm_block",
        "whale_protection",                # ✅ NEW
        "recent_monetization_block",       # ✅ NEW
        "subscriber_monetization",
        "follower_monetization",
        "outreach",
        "broadcast",
    ]

    def determine_priority_route(self, user_memory: dict, fanvue_user: dict = None) -> str:
        user_memory = user_memory or {}
        fanvue_user = fanvue_user or {}

        if self._has_active_chat(user_memory):
            return "active_chat"

        if self._has_active_offer_or_nudge(user_memory):
            return "active_offer_or_nudge"

        if self._requires_rewarm(user_memory):
            return "rewarm_block"

        if self._is_whale(user_memory):
            return "whale_protection"   # ✅ NEW

        if self._was_recently_monetized(user_memory):
            return "recent_monetization_block"   # ✅ NEW

        if self._is_subscriber(fanvue_user, user_memory):
            return "subscriber_monetization"

        if self._is_follower(fanvue_user, user_memory):
            return "follower_monetization"

        if self._is_outreach_eligible(user_memory):
            return "outreach"

        return "broadcast"

    def _is_whale(self, user_memory: dict) -> bool:
        return bool(
            user_memory.get("is_whale")
            or (user_memory.get("user_value_tier") or "").lower() in {"high", "whale"}
        )

    def _was_recently_monetized(self, user_memory: dict) -> bool:
        return bool(
            user_memory.get("last_content_sent_at")
            or user_memory.get("last_ppv_sent_at")
            or user_memory.get("last_subscriber_send_at")
        )

    def can_enter_monetization_flow(
        self,
        user_memory: dict,
        source: str,
        fanvue_user: dict = None,
    ) -> dict:
        user_memory = user_memory or {}
        fanvue_user = fanvue_user or {}
        source = (source or "").lower()

        selected_route = self.determine_priority_route(
            user_memory=user_memory,
            fanvue_user=fanvue_user,
        )

        # --- GLOBAL BLOCKS ---
        if selected_route == "rewarm_block":
            return {
                "eligible": False,
                "reason": "blocked_by_rewarm",
                "allowed_engine": "none",
                "selected_route": selected_route,
            }

        if selected_route == "whale_protection":
            return {
                "eligible": False,
                "reason": "blocked_whale_protection",
                "allowed_engine": "none",
                "selected_route": selected_route,
            }

        if selected_route == "recent_monetization_block":
            return {
                "eligible": False,
                "reason": "blocked_recent_monetization",
                "allowed_engine": "none",
                "selected_route": selected_route,
            }

        # --- NORMAL ROUTING ---
        allowed_engine = self._route_to_engine(selected_route)

        if source == allowed_engine:
            return {
                "eligible": True,
                "reason": "allowed",
                "allowed_engine": allowed_engine,
                "selected_route": selected_route,
            }

        return {
            "eligible": False,
            "reason": f"blocked_by_{selected_route}",
            "allowed_engine": allowed_engine,
            "selected_route": selected_route,
        }

    def _route_to_engine(self, route: str) -> str:
        route = (route or "").lower()

        route_map = {
            "active_chat": "none",
            "active_offer_or_nudge": "none",
            "rewarm_block": "none",
            "whale_protection": "none",                 # ✅ NEW
            "recent_monetization_block": "none",        # ✅ NEW
            "subscriber_monetization": "subscriber",
            "follower_monetization": "follower",
            "outreach": "outreach",
            "broadcast": "broadcast",
        }

        return route_map.get(route, "none")

    def _has_active_chat(self, user_memory: dict) -> bool:
        current_route = (user_memory.get("current_route") or "").lower()
        last_route = (user_memory.get("last_route") or "").lower()

        return current_route == "chat" or last_route == "chat"

    def has_active_offer_or_nudge(self, user_memory: dict) -> bool:
        offer_state = (user_memory.get("offer_state") or "").lower()
        post_offer_nudge_count = int(user_memory.get("post_offer_nudge_count") or 0)

        return offer_state in {
            "active",
            "pending",
            "offered",
            "nudged",
            "nudging",
        } or post_offer_nudge_count > 0

    def _has_active_offer_or_nudge(self, user_memory: dict) -> bool:
        return self.has_active_offer_or_nudge(user_memory)

    def _requires_rewarm(self, user_memory: dict) -> bool:
        return bool(user_memory.get("subscriber_rewarm_required"))

    def _is_subscriber(self, fanvue_user: dict, user_memory: dict) -> bool:
        relationship_status = (
            fanvue_user.get("relationship_status")
            or user_memory.get("relationship_status")
            or ""
        ).lower()

        return bool(
            fanvue_user.get("is_subscriber")
            or user_memory.get("is_subscriber")
            or relationship_status == "subscriber"
            or (user_memory.get("user_type") or "").lower() == "subscriber"
        )

    def _is_follower(self, fanvue_user: dict, user_memory: dict) -> bool:
        relationship_status = (
            fanvue_user.get("relationship_status")
            or user_memory.get("relationship_status")
            or ""
        ).lower()

        return bool(
            fanvue_user.get("is_follower")
            or user_memory.get("is_follower")
            or relationship_status == "follower"
            or (user_memory.get("user_type") or "").lower() == "follower"
        )

    def _is_outreach_eligible(self, user_memory: dict) -> bool:
        outreach_status = (user_memory.get("outreach_status") or "").lower()

        return outreach_status in {
            "eligible",
            "cold",
            "ignored",
            "exhausted",
        }

    def log_monetization_decision(
        self,
        source: str,
        user_id=None,
        username: str = None,
        result: dict = None,
        user_memory: dict = None,
    ):
        result = result or {}
        user_memory = user_memory or {}

        print(
            f"[MONETIZATION GUARD] "
            f"source={source} "
            f"user={user_id} "
            f"username={username} "
            f"eligible={result.get('eligible')} "
            f"reason={result.get('reason')} "
            f"allowed_engine={result.get('allowed_engine')} "
            f"selected_route={result.get('selected_route')} "
            f"relationship_status={user_memory.get('relationship_status')} "
            f"offer_state={user_memory.get('offer_state')} "
            f"subscriber_rewarm_required={user_memory.get('subscriber_rewarm_required')} "
            f"user_value_tier={user_memory.get('user_value_tier')}"
        )