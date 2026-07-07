from datetime import datetime, timedelta


class RetryService:
    def __init__(self):
        pass

    def should_retry(self, memory: dict) -> bool:
        """
        Determines if we should send a follow-up message.
        """

        last_outbound = memory.get("last_outbound_at")
        retry_count = memory.get("retry_count", 0)

        if not last_outbound:
            return False

        # ⏱️ Cooldown rules
        now = datetime.utcnow()
        elapsed = now - last_outbound

        # First retry after 10 minutes
        if retry_count == 0 and elapsed > timedelta(minutes=10):
            return True

        # Second retry after 30 minutes
        if retry_count == 1 and elapsed > timedelta(minutes=30):
            return True

        # Third retry after 2 hours
        if retry_count == 2 and elapsed > timedelta(hours=2):
            return True

        return False

    def get_retry_type(self, memory: dict) -> str:
        """
        Determines WHAT type of retry to send.
        """

        retry_count = memory.get("retry_count", 0)
        last_type = memory.get("last_sent_message_type")

        if last_type == "tease":
            return "tease_nudge"

        if last_type == "vip":
            return "vip_nudge"

        if retry_count == 0:
            return "soft_nudge"

        if retry_count == 1:
            return "tension_nudge"

        return "final_nudge"

    def increment_retry(self, memory: dict) -> dict:
        """
        Updates retry tracking.
        """

        retry_count = memory.get("retry_count", 0) + 1

        memory["retry_count"] = retry_count
        memory["last_retry_at"] = datetime.utcnow()

        return memory