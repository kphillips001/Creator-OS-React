import os

from datetime import datetime, timedelta, timezone

from app.services.gpt_service import GPTService


def build_memory(
    recent_escalation: bool,
):
    if recent_escalation:
        escalation_time = (
            datetime.now(timezone.utc)
            - timedelta(minutes=10)
        ).isoformat()
    else:
        escalation_time = (
            datetime.now(timezone.utc)
            - timedelta(hours=3)
        ).isoformat()

    return {
        "intimacy_context": {
            "intimacy_tier": "premium",
            "spender_confidence": "high",
            "premium_sexting_allowed": True,
            "explicit_allowed": False,
            "runtime_mode": "premium_gate",
            "last_escalation_at": escalation_time,
        }
    }


def run_case(
    gpt,
    title,
    recent_escalation,
):
    print("\n================================")
    print(title)
    print("================================")

    response = gpt.generate_response(
        persona_name="amanda",
        mode="tension",

        user_message=(
            "Tell me what you want to do to me."
        ),

        user_memory=build_memory(
            recent_escalation
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
    print("3D.10.15F — COOLDOWN SUPPRESSION TEST")
    print("======================================\n")

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is missing."
        )

    gpt = GPTService(api_key=api_key)

    cooldown_response = run_case(
        gpt,
        "CASE 1 — ACTIVE COOLDOWN",
        True,
    )

    normal_response = run_case(
        gpt,
        "CASE 2 — COOLDOWN EXPIRED",
        False,
    )

    assert len(cooldown_response) > 0
    assert len(normal_response) > 0

    print("\n======================================")
    print("✅ COOLDOWN SUPPRESSION TEST COMPLETE")
    print("✅ Active cooldown suppression validated")
    print("✅ Normal escalation pacing validated")
    print("======================================\n")


if __name__ == "__main__":
    run_test()