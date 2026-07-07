from app.services.gpt_service import GPTService


# 🔥 Fake minimal memory builder
def build_memory(mode):
    return {
        "subscriber_engagement_mode": mode,
        "conversation_mode": "chat",
        "buyer_tier": "none",
        "intent_score": 10,
        "message_count": 5,
        "last_offer_type": "none",
        "offers_shown_count": 0,
        "attention_tier": "medium",
        "effort_mode": "balanced",
        "user_type": "normal",
        "value_score": 50,
        "behavior_config": {
            "tone_style": "balanced",
            "response_length": "medium",
            "pacing_level": "normal",
        },
    }


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    # 🔥 Load environment variables
    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "❌ OPENAI_API_KEY not found. Make sure your .env file is loaded correctly."
        )

    gpt = GPTService(api_key)

    test_message = "what are you doing tonight"

    modes = ["casual", "flirty", "tension"]

    for mode in modes:
        print("\n==============================")
        print(f"TESTING MODE: {mode}")
        print("==============================")

        memory = build_memory(mode)

        response = gpt.generate_response(
            persona_name="default",
            mode="chat",
            user_message=test_message,
            user_memory=memory,
            send_offer=False,
            offer=None,
            offer_copy="",
            chat_history=[],
        )

        print(f"User: {test_message}")
        print(f"Bot: {response}")