from app.repositories.buyer_memory_sync_repository import (
    sync_buyer_intelligence_to_user_memory,
)


class BuyerMemorySyncService:
    """
    3D.8 + 3D.10.15I + 3D.16.7

    Synchronizes realtime buyer intelligence into user_memory
    so DecisionEngine + GPT become monetization-aware.

    Also merges realtime intimacy reinforcement updates from
    monetization webhook events.

    Includes ownership intelligence synchronization from
    content_usage_log.
    """

    def sync_user_memory(
        self,
        fanvue_account_id: int,
        fanvue_user_id: str,
        intimacy_reinforcement: dict | None = None,
    ):
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

        row = sync_buyer_intelligence_to_user_memory(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_id,
        )

        if row and intimacy_reinforcement:
            row.update(intimacy_reinforcement)

        return {
            "success": True,
            "fanvue_account_id": fanvue_account_id,
            "fanvue_user_id": fanvue_user_id,
            "memory_row": row,
        }