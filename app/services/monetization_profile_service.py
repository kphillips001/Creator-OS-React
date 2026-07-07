from datetime import datetime, timezone


class MonetizationProfileService:
    def get_profile(self, user_memory: dict) -> str:
        """
        Determines monetization profile for a user.
        """

        purchase_count = user_memory.get("purchase_count", 0) or 0
        total_spent = user_memory.get("total_spent_cents", 0) or 0
        content_send_count = user_memory.get("content_send_count", 0) or 0
        outreach_response_count = user_memory.get("outreach_response_count", 0) or 0
        last_active_at = user_memory.get("last_active_at")
        is_whale = user_memory.get("is_whale", False)

        # ------------------------
        # BASE PROFILE ASSIGNMENT
        # ------------------------

        profile = "LOW_PROBABILITY"

        if purchase_count >= 1:
            if total_spent >= 10000:
                profile = "HIGH_VALUE"
            else:
                profile = "ACTIVE_BUYER"

        elif purchase_count == 0:
            if outreach_response_count > 0 or self._is_recently_active(last_active_at):
                profile = "POTENTIAL_BUYER"
            elif content_send_count >= 5:
                profile = "LOW_PROBABILITY"
            else:
                profile = "POTENTIAL_BUYER"

        # ------------------------
        # OVERRIDES
        # ------------------------

        # Whale override
        if is_whale:
            return "WHALE_EXCLUDED"

        # Fatigue override (downgrade one level)
        if content_send_count >= 10:
            profile = self._downgrade(profile)

        # Inactivity boost
        if self._is_inactive(last_active_at):
            if profile == "LOW_PROBABILITY":
                profile = "POTENTIAL_BUYER"

        return profile

    # ------------------------
    # HELPERS
    # ------------------------

    def _downgrade(self, profile: str) -> str:
        order = [
            "HIGH_VALUE",
            "ACTIVE_BUYER",
            "POTENTIAL_BUYER",
            "LOW_PROBABILITY",
        ]

        if profile not in order:
            return profile

        idx = order.index(profile)
        if idx == len(order) - 1:
            return profile

        return order[idx + 1]

    def _is_recently_active(self, last_active_at):
        if not last_active_at:
            return False

        now = datetime.now(timezone.utc)
        delta = now - last_active_at
        return delta.days <= 2

    def _is_inactive(self, last_active_at):
        if not last_active_at:
            return True

        now = datetime.now(timezone.utc)
        delta = now - last_active_at
        return delta.days >= 3