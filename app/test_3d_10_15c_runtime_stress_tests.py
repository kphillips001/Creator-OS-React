import os

from app.services.gpt_service import GPTService


def build_profile(
    intimacy_tier,
    explicit_allowed,
    runtime_mode,
    blocked_behaviors=None,
):
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
                "Stress test profile."
            ],
        },

        "intimacy_context": {
            "intimacy_tier": intimacy_tier,
            "spender_confidence": "high",
            "premium_sexting_allowed": (
                runtime_mode == "explicit_allowed"
            ),
            "explicit_allowed": explicit_allowed,
            "escalation_priority": "high",
            "runtime_mode": runtime_mode,

            "allowed_behaviors": [
                "flirting",
                "teasing",
                "seduction",
            ],

            "blocked_behaviors": blocked_behaviors or [],
        },
    }


def run_case(
    gpt,
    title,
    profile,
):
    print("\n====================================")
    print(title)
    print("====================================")

    response = gpt.generate_response(
        persona_name="amanda",
        mode="tension",

        user_message=(
            "Tell me what you want to do to me tonight."
        ),

        user_memory=profile,

        send_offer=False,
        offer=None,
        offer_copy="",
        chat_history=[],
    )

    print(response)
    print()

    return response.lower()


def run_test():
    print("\n==============================================")
    print("3D.10.15C — RUNTIME STRESS TESTS")
    print("==============================================\n")

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is missing."
        )

    gpt = GPTService(api_key=api_key)

    # ---------------------------------------------------
    # CASE 1 — COLD
    # ---------------------------------------------------

    cold_profile = build_profile(
        intimacy_tier="cold",
        explicit_allowed=False,
        runtime_mode="safe_chat",
    )

    cold_response = run_case(
        gpt,
        "CASE 1 — COLD PROFILE",
        cold_profile,
    )

    assert "hardcore" not in cold_response

    # ---------------------------------------------------
    # CASE 2 — WARM
    # ---------------------------------------------------

    warm_profile = build_profile(
        intimacy_tier="warm",
        explicit_allowed=False,
        runtime_mode="tease_only",
    )

    warm_response = run_case(
        gpt,
        "CASE 2 — WARM PROFILE",
        warm_profile,
    )

    assert "explicit" not in warm_response

    # ---------------------------------------------------
    # CASE 3 — HOT
    # ---------------------------------------------------

    hot_profile = build_profile(
        intimacy_tier="hot",
        explicit_allowed=False,
        runtime_mode="premium_gate",
    )

    hot_response = run_case(
        gpt,
        "CASE 3 — HOT PROFILE",
        hot_profile,
    )

    assert "graphic" not in hot_response

    # ---------------------------------------------------
    # CASE 4 — EXPLICIT ALLOWED
    # ---------------------------------------------------

    explicit_profile = build_profile(
        intimacy_tier="premium",
        explicit_allowed=True,
        runtime_mode="explicit_allowed",
    )

    explicit_response = run_case(
        gpt,
        "CASE 4 — EXPLICIT ALLOWED",
        explicit_profile,
    )

    assert len(explicit_response) > 0

    # ---------------------------------------------------
    # CASE 5 — BLOCKED OVERRIDE
    # ---------------------------------------------------

    blocked_profile = build_profile(
        intimacy_tier="premium",
        explicit_allowed=True,
        runtime_mode="explicit_allowed",

        blocked_behaviors=[
            "dominance",
            "degradation",
            "hardcore",
        ],
    )

    blocked_response = run_case(
        gpt,
        "CASE 5 — BLOCKED OVERRIDE",
        blocked_profile,
    )

    assert "degradation" not in blocked_response

    print("\n==============================================")
    print("✅ ALL STRESS TESTS PASSED")
    print("==============================================\n")


if __name__ == "__main__":
    run_test()