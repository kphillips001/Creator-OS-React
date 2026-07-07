from datetime import datetime, timedelta

from app.repositories.memory_repository import update_memory_fields


class HotBuyerDetectionService:
    """
    Detects if a user is in a HOT BUYER state based on:

    - recent PPV activity
    - engagement spike
    - timing after offer

    This is REAL-TIME logic (not Insights-based).
    """

    HOT_WINDOW_MINUTES = 5  # 🔥 adjustable

    def _start_buyer_session_if_needed(
        self,
        fanvue_account_id: int,
        fanvue_user_id: int,
        memory: dict,
        now: datetime,
    ) -> None:
        """
        Starts buyer session tracking only if the user is not already
        inside an active buyer session.
        """

        if memory.get("buyer_session_active"):
            return

        update_memory_fields(fanvue_account_id, fanvue_user_id, {
            "buyer_session_active": True,
            "buyer_session_started_at": now,
            "buyer_session_last_action_at": now,
            "buyer_session_step": 1,
            "buyer_session_last_action": "session_start",
        })

    def is_hot_buyer(
        self,
        fanvue_account_id: int,
        fanvue_user_id: int,
        memory: dict,
    ) -> dict:
        """
        Returns:
        {
            "is_hot": bool,
            "reason": str
        }
        """

        now = datetime.utcnow()

        last_offer_ts = memory.get("last_offer_timestamp")
        intent_score = memory.get("intent_score", 0)
        messages_since_offer = memory.get("messages_since_last_offer", 0)

        # --------------------------------------------------
        # 1. RECENT OFFER WINDOW
        # --------------------------------------------------

        if last_offer_ts:
            delta = now - last_offer_ts

            if delta <= timedelta(minutes=self.HOT_WINDOW_MINUTES):

                # --------------------------------------------------
                # 2. HIGH INTENT RESPONSE
                # --------------------------------------------------

                if intent_score >= 70:
                    self._start_buyer_session_if_needed(
                        fanvue_account_id,
                        fanvue_user_id,
                        memory,
                        now,
                    )

                    return {
                        "is_hot": True,
                        "reason": "high_intent_after_offer",
                    }

                # --------------------------------------------------
                # 3. ACTIVE RESPONSE
                # --------------------------------------------------

                if messages_since_offer >= 1:
                    self._start_buyer_session_if_needed(
                        fanvue_account_id,
                        fanvue_user_id,
                        memory,
                        now,
                    )

                    return {
                        "is_hot": True,
                        "reason": "engaged_after_offer",
                    }

        # --------------------------------------------------
        # DEFAULT
        # --------------------------------------------------

        return {
            "is_hot": False,
            "reason": "no_signal",
        }