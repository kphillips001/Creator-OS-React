from app.repositories.realtime_buyer_repository import (
    apply_purchase_to_buyer,
)


class RealtimeBuyerUpdateService:
    """
    STEP 11.10

    Handles realtime buyer intelligence updates
    triggered from Fanvue webhook events.
    """

    def process_purchase_created(self, event: dict):
        payload = event["payload"]

        fanvue_user_id = event["fanvue_user_id"]

        purchase_data = payload.get("data", {})

        purchase_amount = purchase_data.get(
            "purchase_amount",
            0
        )

        print("\n[REALTIME BUYER UPDATE]")
        print(f"fanvue_user_id={fanvue_user_id}")
        print(f"purchase_amount={purchase_amount}")

        buyer_update = apply_purchase_to_buyer(
            fanvue_user_id=fanvue_user_id,
            purchase_amount=purchase_amount,
        )

        print("[BUYER DATABASE UPDATED]")
        print(f"buyer_update={buyer_update}")

        return {
            "success": True,
            "fanvue_user_id": fanvue_user_id,
            "purchase_amount": purchase_amount,
        }