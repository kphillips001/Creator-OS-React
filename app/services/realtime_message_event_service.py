from app.repositories.realtime_chat_sync_repository import (
    create_inbound_chat_message,
)

from app.services.realtime_decision_trigger_service import (
    RealtimeDecisionTriggerService,
)

from app.services.realtime_buyer_session_refresh_service import (
    RealtimeBuyerSessionRefreshService,
)


class RealtimeMessageEventService:
    """
    SECTION 2 REALTIME ENRICHMENT

    Handles realtime Fanvue message_received webhook events.
    """

    def __init__(self, *, identity_verification_service=None):
        self.decision_trigger_service = RealtimeDecisionTriggerService()
        self.buyer_session_refresh_service = RealtimeBuyerSessionRefreshService()
        if identity_verification_service is None:
            from app.services.telegram_identity_verification_service import TelegramIdentityVerificationService
            identity_verification_service = TelegramIdentityVerificationService()
        self.identity_verification_service = identity_verification_service

    def process_message_received(self, event: dict):
        payload = event["payload"]

        fanvue_user_id = event.get("fanvue_user_id")
        fanvue_account_id = event.get("fanvue_account_id")
        external_event_id = event.get("external_event_id")

        if not fanvue_account_id:
            return {
                "success": False,
                "blocked": True,
                "reason": "missing_fanvue_account_id",
                "event_id": event.get("id"),
                "external_event_id": external_event_id,
            }

        if not fanvue_user_id:
            return {
                "success": False,
                "blocked": True,
                "reason": "missing_fanvue_user_id",
                "fanvue_account_id": fanvue_account_id,
                "event_id": event.get("id"),
                "external_event_id": external_event_id,
            }

        message_data = (
            payload.get("data", {})
            .get("message", {})
        )

        message_text = (
            message_data.get("text")
            or message_data.get("message")
            or ""
        )

        thread_id = (
            payload.get("threadUuid")
            or payload.get("thread_id")
            or payload.get("threadId")
            or payload.get("data", {}).get("thread_id")
            or payload.get("data", {}).get("threadUuid")
            or payload.get("data", {}).get("threadId")
        )

        verification_result = self.identity_verification_service.complete_from_fanvue_message(
            fanvue_account_id=int(fanvue_account_id),
            fanvue_user_uuid=fanvue_user_id,
            message_text=message_text,
            provider_event_id=str(external_event_id),
        )
        is_verification_message = verification_result.get("status") not in {
            "NOT_A_CHALLENGE", "DISABLED",
        }

        print("\n[REALTIME MESSAGE EVENT]")
        print(f"fanvue_user_id={fanvue_user_id}")
        print(f"fanvue_account_id={fanvue_account_id}")
        print(f"thread_id={thread_id}")
        print(f"message={'[IDENTITY VERIFICATION CODE REDACTED]' if is_verification_message else message_text}")

        chat_message_id = create_inbound_chat_message(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_uuid=str(fanvue_user_id),
            fanvue_message_uuid=str(external_event_id),
            sender_uuid=str(fanvue_user_id),
            message_text=("[Identity verification code]" if is_verification_message else message_text),
            raw_payload=({"identity_verification": True} if is_verification_message else payload),
        )

        print("[CHAT MESSAGE SAVED]")
        print(f"chat_message_id={chat_message_id}")

        if is_verification_message:
            return {
                "success": verification_result.get("status") == "VERIFIED",
                "chat_message_id": chat_message_id,
                "fanvue_user_id": fanvue_user_id,
                "fanvue_account_id": fanvue_account_id,
                "thread_id": thread_id,
                "message": "[Identity verification code]",
                "identity_verification": verification_result,
                "session_refresh_result": None,
                "trigger_result": None,
            }

        session_refresh_result = (
            self.buyer_session_refresh_service.refresh_from_message(
                fanvue_user_id=fanvue_user_id,
                fanvue_account_id=fanvue_account_id,
                message_text=message_text,
            )
        )

        print(f"session_refresh_result={session_refresh_result}")

        trigger_result = self.decision_trigger_service.trigger_for_inbound_message(
            fanvue_user_id=fanvue_user_id,
            fanvue_account_id=fanvue_account_id,
            chat_message_id=chat_message_id,
            message_text=message_text,
            thread_id=thread_id,
        )

        print(f"trigger_result={trigger_result}")

        return {
            "success": True,
            "chat_message_id": chat_message_id,
            "fanvue_user_id": fanvue_user_id,
            "fanvue_account_id": fanvue_account_id,
            "thread_id": thread_id,
            "message": message_text,
            "identity_verification": verification_result,
            "session_refresh_result": session_refresh_result,
            "trigger_result": trigger_result,
        }
