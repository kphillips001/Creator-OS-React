from typing import Dict, Optional
from datetime import datetime, timedelta


class SubscriberSendRulesService:
    def get_subscriber_send_rules(self, user_memory: dict) -> Dict:
        """
        Returns subscriber send rules based on subscriber_profile.

        This controls:
        - cooldowns
        - send frequency
        - repeat behavior
        - monetization pacing
        """

        profile = user_memory.get("subscriber_profile", "ACTIVE_SUBSCRIBER")

        # Default fallback (safe behavior)
        rules = {
            "min_hours_between_sends": 12,
            "max_sends_per_24h": 2,
            "allow_repeat_content": True,
            "reengagement_mode": False,
            "premium_only": False,
        }

        if profile == "NEW_SUBSCRIBER":
            rules.update({
                "min_hours_between_sends": 24,
                "max_sends_per_24h": 1,
                "allow_repeat_content": False,
                "reengagement_mode": False,
                "premium_only": False,
            })

        elif profile == "ACTIVE_SUBSCRIBER":
            rules.update({
                "min_hours_between_sends": 12,
                "max_sends_per_24h": 2,
                "allow_repeat_content": True,
                "reengagement_mode": False,
                "premium_only": False,
            })

        elif profile == "LAPSED_SUBSCRIBER":
            rules.update({
                "min_hours_between_sends": 48,
                "max_sends_per_24h": 1,
                "allow_repeat_content": False,
                "reengagement_mode": True,
                "premium_only": False,
            })

        elif profile == "HIGH_VALUE_SUBSCRIBER":
            rules.update({
                "min_hours_between_sends": 24,
                "max_sends_per_24h": 1,
                "allow_repeat_content": False,
                "reengagement_mode": False,
                "premium_only": True,
            })

        return rules

    def can_send_to_subscriber(
        self,
        user_memory: dict,
        content_tag: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> Dict:
        """
        Determines whether a subscriber is eligible to receive a send right now.

        Returns:
        {
            "eligible": bool,
            "reason": str
        }
        """
        rules = self.get_subscriber_send_rules(user_memory)
        now = now or datetime.utcnow()

        last_send_at = user_memory.get("last_subscriber_send_at")
        sends_24h = user_memory.get("subscriber_send_count_24h", 0)
        last_content_tag = user_memory.get("last_subscriber_content_tag")

        # Check cooldown
        if last_send_at:
            if isinstance(last_send_at, str):
                try:
                    last_send_at = datetime.fromisoformat(last_send_at)
                except ValueError:
                    return {
                        "eligible": False,
                        "reason": "invalid_last_subscriber_send_at",
                    }

            min_next_send_time = last_send_at + timedelta(
                hours=rules["min_hours_between_sends"]
            )

            if now < min_next_send_time:
                return {
                    "eligible": False,
                    "reason": "cooldown_active",
                }

        # Check send count limit
        if sends_24h >= rules["max_sends_per_24h"]:
            return {
                "eligible": False,
                "reason": "max_sends_reached_24h",
            }

        # Check repeat content restriction
        if (
            content_tag
            and not rules["allow_repeat_content"]
            and last_content_tag == content_tag
        ):
            return {
                "eligible": False,
                "reason": "repeat_content_blocked",
            }

        return {
            "eligible": True,
            "reason": "eligible",
        }