from app.repositories.cms_fanvue_upload_repository import (
    get_uploaded_media_by_destination,
)

from app.services.content_delivery_guard_service import ContentDeliveryGuardService


class ContentMediaDeliveryService:
    def __init__(self):
        self.guard_service = ContentDeliveryGuardService()

    def get_media_for_delivery(
        self,
        fanvue_account_id: int,
        destination: str,
        requested_delivery: str,
        limit: int = 10,
    ) -> dict:
        """
        13F-1 — Fetch stored media UUIDs safely by destination.

        Guard runs BEFORE DB fetch so invalid delivery requests are blocked
        even when no matching media exists yet.
        """

        print("[13F GET MEDIA FOR DELIVERY]")
        print(f"fanvue_account_id={fanvue_account_id}")
        print(f"destination={destination}")
        print(f"requested_delivery={requested_delivery}")

        # --------------------------------------------------
        # 1. PRE-FETCH GUARD
        # --------------------------------------------------

        precheck = self.guard_service.validate_destination_delivery(
            destination=destination,
            requested_delivery=requested_delivery,
        )

        if not precheck.get("allowed"):
            print("[13F BLOCKED BEFORE FETCH]")
            print(precheck)

            return {
                "success": True,
                "destination": destination,
                "requested_delivery": requested_delivery,
                "count": 0,
                "media": [],
                "blocked": [
                    {
                        "content_item_id": None,
                        "reason": precheck,
                    }
                ],
            }

        # --------------------------------------------------
        # 2. FETCH ONLY MATCHING DESTINATION MEDIA
        # --------------------------------------------------

        records = get_uploaded_media_by_destination(
            fanvue_account_id=fanvue_account_id,
            destination=destination,
            limit=limit,
        )

        safe_records = []
        blocked_records = []

        # --------------------------------------------------
        # 3. RECORD-LEVEL GUARD
        # --------------------------------------------------

        for record in records:
            guard_result = self.guard_service.validate_delivery(
                content_record=record,
                requested_delivery=requested_delivery,
            )

            if guard_result.get("allowed"):
                safe_records.append(record)
            else:
                blocked_records.append(
                    {
                        "content_item_id": record.get("content_item_id"),
                        "reason": guard_result,
                    }
                )

        return {
            "success": True,
            "destination": destination,
            "requested_delivery": requested_delivery,
            "count": len(safe_records),
            "media": safe_records,
            "blocked": blocked_records,
        }