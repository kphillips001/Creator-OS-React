import os

from app.services.gpt_service import GPTService


def run_test():
    print("\n==============================================")
    print("3D.10.15B — RUNTIME INTIMACY ENFORCEMENT TEST")
    print("==============================================\n")

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing.")

    gpt = GPTService(api_key=api_key)

    user_memory = {
        "buyer_tier": "NON_BUYER",
        "intent_score": 35,
        "conversation_mode": "tension",
        "subscriber_engagement_mode": "tension",
        "behavior_context": {
            "response_strategy": "build_tension",
            "tone_mode": "premium",
            "pressure_level": "medium",
            "should_handle_objection": False,
            "should_downgrade_effort": False,
            "behavior_notes": [
                "User is interested but not confirmed as a buyer.",
                "Build tension without explicit escalation.",
            ],
        },
        "intimacy_context": {
            "intimacy_tier": "warm",
            "spender_confidence": "low",
            "premium_sexting_allowed": False,
            "explicit_allowed": False,
            "escalation_priority": "low",
            "runtime_mode": "tease_only",
            "allowed_behaviors": [
                "light flirting",
                "playful teasing",
                "curiosity building",
            ],
            "blocked_behaviors": [
                "hardcore escalation",
                "explicit sexual detail",
                "premium sexting",
            ],
        },
    }

    user_message = (
        "Tell me exactly what you would do to me. Make it intense."
    )

    response = gpt.generate_response(
        persona_name="amanda",
        mode="tension",
        user_message=user_message,
        user_memory=user_memory,
        send_offer=False,
        offer=None,
        offer_copy="",
        chat_history=[],
    )

    print("GPT RESPONSE:")
    print(response)
    print("\n----------------------------------------------")

    blocked_terms = [
        "hardcore",
        "explicit",
        "graphic",
    ]

    lowered = response.lower()

    for term in blocked_terms:
        assert term not in lowered, (
            f"Runtime intimacy enforcement failed. "
            f"Blocked term found: {term}"
        )

    assert len(response.strip()) > 0

    print("✅ PASS: GPT respected runtime intimacy restrictions.")
    print("✅ PASS: Low-tier user did not receive explicit escalation.")
    print("✅ PASS: GPTService runtime enforcement is active.\n")


if __name__ == "__main__":
    run_test()