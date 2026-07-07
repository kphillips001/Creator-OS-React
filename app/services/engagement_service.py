import random
from datetime import datetime, timedelta


class EngagementService:
    """
    Sends light engagement messages during WAIT state.

    Goal:
    - keep attention
    - build tension
    - avoid spam
    """

    MIN_INTERVAL_SECONDS = 120   # 2 min min gap
    MAX_INTERVAL_SECONDS = 420   # 7 min max gap

    def should_send(self, memory: dict) -> bool:
        """
        Decide whether to send a light engagement message.
        """

        last_engagement_at = memory.get("last_engagement_at")

        # If never sent → allow
        if not last_engagement_at:
            return True

        now = datetime.utcnow()
        delta = now - last_engagement_at

        # Not enough time passed → don't send
        if delta < timedelta(seconds=self.MIN_INTERVAL_SECONDS):
            return False

        # Random chance (human-like behavior)
        return random.random() < 0.6  # 60% chance

    def generate_message(self) -> str:
        """
        Very short, flirty, tension-building messages.
        """

        options = [
            "you got quiet on me 😏",
            "still thinking about that? 👀",
            "I kinda liked your reaction…",
            "don’t make me tease you again…",
            "I’ve got something else you’d like…",
            "you’d look good right now… just saying 😌",
        ]

        return random.choice(options)