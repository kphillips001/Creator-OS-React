import os

from app.services.gpt_service import GPTService


def build_user_memory(intimacy_tier: str) -> dict:
    return {
        "buyer_tier": "ACTIVE_BUYER",
        "intent_score": 75,
        "conversation_mode": "tension",
        "subscriber_engagement_mode": "tension",
        "behavior_context": {
            "response_strategy": "build_tension",
            "tone_mode": "seductive",
            "pressure_level": "medium",
            "should_handle_objection": False,
            "should_downgrade_effort": False,
            "behavior_notes": [
                "Dynamic escalation profile test.",
                "Shape tone based on intimacy tier.",
            ],
        },
        "intimacy_context": {
            "intimacy_tier": intimacy_tier,
            "spender_confidence": "high",
            "premium_sexting_allowed": False,
            "explicit_allowed": False,
            "escalation_priority": "high",
            "runtime_mode": "premium_gate",
            "allowed_behaviors": [
                "flirting",
                "teasing",
                "curiosity building",
                "seductive tension",
            ],
            "blocked_behaviors": [
                "hardcore escalation",
                "explicit sexual detail",
                "graphic wording",
            ],
        },
    }


def run_case(
    gpt: GPTService,
    title: str,
    intimacy_tier: str,
) -> str:
    print("\n================================")
    print(title)
    print("================================")

    user_memory = build_user_memory(intimacy_tier)

    response = gpt.generate_response(
        persona_name="amanda",
        mode="tension",
        user_message="You seem dangerous tonight.",
        user_memory=user_memory,
        send_offer=False,
        offer=None,
        offer_copy="",
        chat_history=[],
    )

    print(response)
    print()

    assert response is not None
    assert len(response.strip()) > 0

    return response.lower()


def run_test():
    print("\n======================================")
    print("3D.10.15D — DYNAMIC PROFILES TEST")
    print("======================================\n")

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing.")

    gpt = GPTService(api_key=api_key)

    cold_response = run_case(
        gpt,
        "CASE 1 — COLD PROFILE",
        "cold",
    )

    warm_response = run_case(
        gpt,
        "CASE 2 — WARM PROFILE",
        "warm",
    )

    hot_response = run_case(
        gpt,
        "CASE 3 — HOT PROFILE",
        "hot",
    )

    premium_response = run_case(
        gpt,
        "CASE 4 — PREMIUM PROFILE",
        "premium",
    )

    blocked_terms = [
        "hardcore",
        "graphic",
    ]

    for label, response in [
        ("cold", cold_response),
        ("warm", warm_response),
        ("hot", hot_response),
        ("premium", premium_response),
    ]:
        for term in blocked_terms:
            assert term not in response, (
                f"{label} response violated blocked term: {term}"
            )

    print("\n======================================")
    print("✅ DYNAMIC PROFILE TEST COMPLETE")
    print("✅ Cold / Warm / Hot / Premium profiles generated")
    print("✅ Runtime safety still respected")
    print("======================================\n")


if __name__ == "__main__":
    run_test()