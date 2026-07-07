from datetime import datetime, timezone
from app.repositories.memory_repository import update_memory_fields

class SubscriberReentryService:
    """
    Detects subscriber re-entry after inactivity and determines
    whether monetization pressure should be softened.
    """

    REENTRY_DAYS_THRESHOLD = 7
    FATIGUE_RESET_DAYS_THRESHOLD = 14

    def _days_since(self, dt_value) -> int | None:
        if not dt_value:
            return None

        if isinstance(dt_value, str):
            try:
                dt_value = datetime.fromisoformat(dt_value)
            except ValueError:
                return None

        if dt_value.tzinfo is None:
            dt_value = dt_value.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        delta = now - dt_value
        return delta.days

    def evaluate_reentry(self, user_memory: dict) -> dict:
        user_memory = user_memory or {}

        last_active_at = user_memory.get("last_active_at")
        last_subscriber_send_at = user_memory.get("last_subscriber_send_at")

        days_since_active = self._days_since(last_active_at)
        days_since_send = self._days_since(last_subscriber_send_at)

        reentry_detected = (
            days_since_active is not None
            and days_since_active >= self.REENTRY_DAYS_THRESHOLD
        )

        fatigue_reset_recommended = (
            days_since_send is not None
            and days_since_send >= self.FATIGUE_RESET_DAYS_THRESHOLD
        )

        rewarm_required = reentry_detected

        memory_updates = {}

        if reentry_detected:
            existing_count = user_memory.get("subscriber_reentry_count", 0) or 0
            memory_updates["subscriber_reentry_count"] = existing_count + 1
            memory_updates["subscriber_rewarm_required"] = True

        if fatigue_reset_recommended:
            memory_updates["subscriber_fatigue_flag"] = False

        return {
            "reentry_detected": reentry_detected,
            "fatigue_reset_recommended": fatigue_reset_recommended,
            "rewarm_required": rewarm_required,
            "days_since_active": days_since_active,
            "days_since_send": days_since_send,
            "memory_updates": memory_updates,
        }
    
    def process_reentry(
        self,
        fanvue_account_id: int,
        fanvue_user_id: int,
        user_memory: dict,
    ):
        result = self.evaluate_reentry(user_memory)

        updates = result.get("memory_updates", {})

        if updates:
            update_memory_fields(
                fanvue_account_id=fanvue_account_id,
                fanvue_user_id=fanvue_user_id,
                data=updates,
            )

        return result