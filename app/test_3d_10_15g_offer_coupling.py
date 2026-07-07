import os

from app.services.gpt_service import GPTService


def build_memory(
    intimacy_tier,
    spender_confidence,
):
    return {
        "intimacy_context": {
            "intimacy_tier": intimacy_tier,
            "spender_confidence": spender_confidence,
            "premium_sexting_allowed": (
                intimacy_tier == "premium"
            ),
            "explicit_allowed": False,
            "runtime_mode": "premium_gate",
        }
    }


def run_case(
    gpt,
    title,
    intimacy_tier,
    spender_confidence,
):
    print("\n================================")
    print(title)
    print("================================")

    response = gpt.generate_response(
        persona_name="amanda",
        mode="tension",

        user_message=(
            "You seem like you'd be trouble behind closed doors."
        ),

        user_memory=build_memory(
            intimacy_tier,
            spender_confidence,
        ),

        send_offer=False,
        offer=None,
        offer_copy="",
        chat_history=[],
    )

    print(response)
    print()

    return response.lower()


def run_test():
    print("\n======================================")
    print("3D.10.15G — OFFER COUPLING TEST")
    print("======================================\n")

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is missing."
        )

    gpt = GPTService(api_key=api_key)

    run_case(
        gpt,
        "CASE 1 — LOW CONFIDENCE",
        "warm",
        "low",
    )

    run_case(
        gpt,
        "CASE 2 — HIGH CONFIDENCE",
        "hot",
        "high",
    )

    run_case(
        gpt,
        "CASE 3 — PREMIUM BUYER",
        "premium",
        "high",
    )

    print("\n======================================")
    print("✅ OFFER COUPLING TEST COMPLETE")
    print("======================================\n")


if __name__ == "__main__":
    run_test()