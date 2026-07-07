class MonetizationEventNormalizerService:
    """
    3D.2 — Normalize Fanvue monetization webhook events into
    a consistent internal money-event structure.
    """

    SUPPORTED_EVENTS = {
        "purchase_received",
        "purchase_created",
        "unlock_confirmation",
        "tip_received",
        "subscription_created",
        "subscription_cancelled",
    }

    def normalize(self, event: dict) -> dict:
        event_type = event.get("event_type")
        payload = event.get("payload") or {}

        data = payload.get("data") or payload

        amount = (
            data.get("amount")
            or data.get("purchase_amount")
            or data.get("tip_amount")
            or data.get("price")
            or 0
        )

        return {
            "external_event_id": event.get("external_event_id"),
            "event_type": event_type,
            "fanvue_account_id": event.get("fanvue_account_id"),
            "fanvue_user_id": event.get("fanvue_user_id"),
            "local_user_id": None,
            "amount": amount,
            "currency": data.get("currency", "USD"),
            "content_item_id": data.get("content_item_id"),
            "content_tag": data.get("content_tag"),
            "fanvue_media_uuid": (
                data.get("fanvue_media_uuid")
                or data.get("media_uuid")
                or data.get("mediaUuid")
            ),
            "purchase_type": (
                data.get("purchase_type")
                or data.get("type")
                or event_type
            ),
            "status": "received",
            "raw_payload": payload,
        }

    def is_supported(self, event_type: str) -> bool:
        return event_type in self.SUPPORTED_EVENTS