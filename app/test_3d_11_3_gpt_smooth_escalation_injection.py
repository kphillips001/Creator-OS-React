from app.services.smooth_intimacy_escalation_service import (
    SmoothIntimacyEscalationService,
)


def run_test():
    print("\n====================================")
    print(" 3D.11.3 GPT SMOOTH ESCALATION")
    print("====================================\n")

    service = SmoothIntimacyEscalationService()

    profile = service.build_escalation_profile(
        intimacy_context={
            "intimacy_tier": "premium",
            "runtime_mode": "premium_gate",
            "spender_confidence": "high",
        },
        spend_profile={
            "buyer_tier": "LOW_SPENDER",
            "total_spend": 20,
            "purchase_count": 1,
            "recent_purchase_active": True,
        },
        conversation_state={
            "conversation_mode": "flirty",
            "heat_score": 65,
            "intent_score": 60,
        },
    )

    instruction = profile.get(
        "gpt_instruction"
    )

    print("Generated GPT Instruction:\n")
    print(instruction)
    print()

    assert instruction is not None
    assert "Smooth intimacy escalation is active" in instruction
    assert "Do not jump abruptly" in instruction

    print("✅ Smooth escalation instruction generated")
    print("\n✅ 3D.11.3 PASSED\n")


if __name__ == "__main__":
    run_test()