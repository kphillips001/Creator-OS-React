import uuid
from datetime import datetime, timezone


class WebhookNormalizerService:
    """
    STEP 11.2
    Normalizes incoming Fanvue webhook payloads into a consistent internal format.

    This service does NOT:
    - save to the database
    - verify signatures
    - process events
    - route events

    It only converts incoming webhook data into a predictable structure.
    """

    DEFAULT_STATUS = "received"

    def normalize(self, payload: dict, headers: dict | None = None) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("Webhook payload must be a dictionary")

        headers = headers or {}

        event_type = self._extract_event_type(
            payload,
            headers,
        )

        external_event_id = self._extract_external_event_id(
            payload,
            headers,
        )

        fanvue_user_id = self._extract_fanvue_user_id(payload)

        fanvue_account_id = self._extract_fanvue_account_id(payload)

        return {
            "internal_event_id": str(uuid.uuid4()),
            "external_event_id": external_event_id,
            "event_type": event_type,
            "fanvue_account_id": fanvue_account_id,
            "fanvue_user_id": fanvue_user_id,
            "payload": payload,
            "headers": dict(headers),
            "received_at": datetime.now(timezone.utc).isoformat(),
            "status": self.DEFAULT_STATUS,
        }

    def _extract_event_type(
        self,
        payload: dict,
        headers: dict,
    ) -> str:
        """
        REAL Fanvue webhook event type extraction.

        Fanvue sends:
        x-fanvue-topic: message.received

        We normalize:
        message.received -> message_received
        """

        event_type = (
            headers.get("x-fanvue-topic")
            or payload.get("event_type")
            or payload.get("type")
            or payload.get("event")
            or "unknown"
        )

        return event_type.replace(".", "_")

    def _extract_external_event_id(
        self,
        payload: dict,
        headers: dict,
    ) -> str | None:
        """
        REAL Fanvue event ids come from headers.
        """

        return (
            headers.get("x-fanvue-event-id")
            or payload.get("event_id")
            or payload.get("id")
            or payload.get("webhook_event_id")
        )

    def _extract_fanvue_user_id(self, payload: dict):
        """
        REAL Fanvue message.received payloads:
        recipientUuid = creator
        sender.uuid = fan/user
        """

        return (
            payload.get("sender", {}).get("uuid")
            or (
                payload.get("data", {}).get("purchaser", {}).get("uuid")
                if isinstance(payload.get("data", {}).get("purchaser"), dict)
                else None
            )
            or payload.get("data", {}).get("purchaserUuid")
            or payload.get("data", {}).get("buyerUuid")
            or payload.get("fanvue_user_id")
            or payload.get("user_id")
            or payload.get("subscriber_id")
            or payload.get("data", {}).get("fanvue_user_id")
            or payload.get("data", {}).get("user_id")
            or payload.get("data", {}).get("subscriber_id")
        )

    def _extract_fanvue_account_id(self, payload: dict):
        """
        REAL Fanvue creator account uuid.
        """

        return (
            payload.get("recipientUuid")
            or payload.get("data", {}).get("creatorUuid")
            or (
                payload.get("data", {}).get("creator", {}).get("uuid")
                if isinstance(payload.get("data", {}).get("creator"), dict)
                else None
            )
            or payload.get("fanvue_account_id")
            or payload.get("account_id")
            or payload.get("creator_id")
            or payload.get("data", {}).get("fanvue_account_id")
            or payload.get("data", {}).get("account_id")
            or payload.get("data", {}).get("creator_id")
        )
