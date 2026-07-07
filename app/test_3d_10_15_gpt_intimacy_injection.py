import os

from app.services.gpt_service import GPTService


def run_test():
    print("\n======================================")
    print(" 3D.10.15 GPT INTIMACY INJECTION TEST")
    print("======================================\n")

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        print("❌ OPENAI_API_KEY missing")
        return

    service = GPTService(api_key=api_key)

    response = service.generate_response(
        persona_name="amanda",
        mode="flirty",
        user_message="So what kind of mood are you in tonight?",
        user_memory={
            "fanvue_user_id": "test_user_uuid",
            "buyer_tier": "ACTIVE_BUYER",
            "intent_score": 60,
            "conversation_mode": "flirty",
            "message_count": 5,
        },
        send_offer=False,
        offer=None,
        offer_copy="",
        chat_history=[],
    )

    print("\nGPT RESPONSE:\n")
    print(response)

    print("\n✅ 3D.10.15 GPT intimacy injection test complete")


if __name__ == "__main__":
    run_test()