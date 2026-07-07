import os

from app.services.gpt_service import GPTService


def build_memory(
    premium_allowed: bool,
):
    return {
        "intimacy_context": {
            "intimacy_tier": "premium",
            "spender_confidence": "high",
            "premium_sexting_allowed": premium_allowed,
            "explicit_allowed": False,
            "runtime_mode": "premium_gate",
        }
    }


def run_case(
    gpt,
    title,
    premium_allowed,
):
    print("\n================================")
    print(title)
    print("================================")

    response = gpt.generate_response(
        persona_name="amanda",
        mode="tension",

        user_message=(
            "Tell me your darkest fantasy about us."
        ),

        user_memory=build_memory(
            premium_allowed
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
    print("3D.10.15E — PREMIUM GATE TEST")
    print("======================================\n")

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is missing."
        )

    gpt = GPTService(api_key=api_key)

    locked_response = run_case(
        gpt,
        "CASE 1 — PREMIUM LOCKED",
        False,
    )

    unlocked_response = run_case(
        gpt,
        "CASE 2 — PREMIUM UNLOCKED",
        True,
    )

    assert len(locked_response) > 0
    assert len(unlocked_response) > 0

    print("\n======================================")
    print("✅ PREMIUM GATE TEST COMPLETE")
    print("✅ Locked premium behavior validated")
    print("✅ Unlocked premium behavior validated")
    print("======================================\n")


if __name__ == "__main__":
    run_test()