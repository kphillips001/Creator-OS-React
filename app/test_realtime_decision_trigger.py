from app.services.realtime_decision_trigger_service import (
    RealtimeDecisionTriggerService,
)


def main():
    print("\n=== 3E.4 REALTIME DECISION TRIGGER GUARD TEST ===\n")

    service = RealtimeDecisionTriggerService()

    result = service.trigger_for_inbound_message(
        fanvue_user_id=(
            "f9f91c18-8350-478f-b96b-1bea4a064d48"
        ),
        fanvue_account_id=1,
        chat_message_id=999,
        message_text="hey babe 😏",
        thread_id=(
            "22222222-2222-2222-2222-222222222222"
        ),
    )

    print("\n=== REALTIME DECISION TRIGGER TEST RESULT ===")
    print(result)


if __name__ == "__main__":
    main()