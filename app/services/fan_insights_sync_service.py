from datetime import datetime

from app.services.fanvue_api_service import FanvueAPIService
from app.services.buyer_classification_service import BuyerClassificationService
from app.repositories.memory_repository import update_memory_fields


class FanInsightsSyncService:
    """
    15G-EXT Fan Insights Sync Service

    Flow:
    API → Normalize → Classify → Save to user_memory
    """

    def __init__(
        self,
        fanvue_account_id: int,
    ):
        self.fanvue_account_id = fanvue_account_id

        self.api = FanvueAPIService(
            fanvue_account_id=self.fanvue_account_id,
        )

        self.classifier = BuyerClassificationService()

    def sync_user_insights(
        self,
        fanvue_account_id: int,
        fanvue_user_uuid: int,  # ✅ DB uses INT
        mock_data: dict = None,
    ) -> dict:
        if fanvue_account_id != self.fanvue_account_id:
            return {
                "success": False,
                "status": "blocked",
                "reason": "fanvue_account_id_mismatch",
                "service_account_id": self.fanvue_account_id,
                "requested_account_id": fanvue_account_id,
            }
        print("\n[FAN INSIGHTS SYNC START]")
        print(f"user_uuid={fanvue_user_uuid}")

        # --------------------------------------------------
        # 1. FETCH DATA (MOCK OR API)
        # --------------------------------------------------

        if mock_data:
            print("[USING MOCK INSIGHTS DATA]")
            data = mock_data
        else:
            response = self.api.get_fan_insights(fanvue_user_uuid)

            if not response.get("success"):
                print("[INSIGHTS FETCH FAILED]")
                return response

            data = response.get("data", {})

        # --------------------------------------------------
        # 2. NORMALIZE DATA
        # --------------------------------------------------

        total_spend = float(data.get("total_spend", 0))
        purchase_count = int(data.get("purchase_count", 0))
        is_top_spender = bool(data.get("is_top_spender", False))

        print("[NORMALIZED DATA]")
        print(total_spend, purchase_count, is_top_spender)

        # --------------------------------------------------
        # 3. CLASSIFY USER
        # --------------------------------------------------

        classification = self.classifier.classify_buyer(
            total_spend=total_spend,
            purchase_count=purchase_count,
            is_top_spender=is_top_spender,
        )

        print("[CLASSIFICATION RESULT]")
        print(classification)

        # --------------------------------------------------
        # 4. UPDATE DATABASE (ONLY ALLOWED FIELDS)
        # --------------------------------------------------

        update_payload = {
            # ✅ CORE CLASSIFICATION → already valid fields
            "buyer_tier": classification.get("buyer_classification"),
            "user_value_tier": classification.get("user_value_tier"),
            "is_whale": classification.get("is_whale"),

            # ✅ PURCHASE TRACKING (exists in schema)
            "ppv_purchase_count": classification.get("purchase_count", 0),
            "avg_ppv_spend": classification.get("avg_spend_per_purchase", 0),

            # OPTIONAL: derive/update silent buyer score later
            # "silent_buyer_score": ...
        }

        update_memory_fields(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_uuid,
            data=update_payload,
        )

        print("[DB UPDATED]")

        # --------------------------------------------------
        # 5. RETURN RESULT
        # --------------------------------------------------

        return {
            "success": True,
            "classification": classification,
            "raw_data": data,
            "updated_fields": update_payload,
        }