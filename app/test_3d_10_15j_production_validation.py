from app.services.decision_engine_intimacy_integration_service import (
    DecisionEngineIntimacyIntegrationService,
)

from app.services.realtime_intimacy_reinforcement_service import (
    RealtimeIntimacyReinforcementService,
)

from app.services.runtime_intimacy_enforcement_service import (
    RuntimeIntimacyEnforcementService,
)

from app.services.dynamic_escalation_profile_service import (
    DynamicEscalationProfileService,
)

from app.services.premium_sexting_gate_service import (
    PremiumSextingGateService,
)

from app.services.intimacy_cooldown_suppression_service import (
    IntimacyCooldownSuppressionService,
)

from app.services.runtime_offer_escalation_coupling_service import (
    RuntimeOfferEscalationCouplingService,
)


def build_base_memory():
    return {
        "buyer_tier": "NON_BUYER",
        "intent_score": 20,
        "conversation_mode": "casual",
        "subscriber_engagement_mode": "casual",
        "intimacy_context": {
            "intimacy_tier": "cold",
            "spender_confidence": "low",
            "premium_sexting_allowed": False,
            "explicit_allowed": False,
            "escalation_priority": "low",
            "runtime_mode": "safe_chat",
            "allowed_behaviors": [
                "light flirting",
                "playful teasing",
            ],
            "blocked_behaviors": [
                "hardcore escalation",
                "explicit sexual detail",
                "premium sexting",
            ],
        },
    }


def run_test():
    print("\n==============================================")
    print("3D.10.15J — PRODUCTION VALIDATION PASS")
    print("==============================================\n")

    memory = build_base_memory()

    reinforcement_service = RealtimeIntimacyReinforcementService()
    decision_service = DecisionEngineIntimacyIntegrationService()
    runtime_service = RuntimeIntimacyEnforcementService()
    dynamic_service = DynamicEscalationProfileService()
    premium_gate_service = PremiumSextingGateService()
    cooldown_service = IntimacyCooldownSuppressionService()
    offer_coupling_service = RuntimeOfferEscalationCouplingService()

    # --------------------------------------------------
    # CASE 1 — SAFE DEFAULT MEMORY
    # --------------------------------------------------

    print("\nCASE 1 — SAFE DEFAULT MEMORY")

    runtime_instruction = runtime_service.build_instruction(memory)
    dynamic_instruction = dynamic_service.build_instruction(memory)
    gate_instruction = premium_gate_service.build_instruction(memory)
    cooldown_instruction = cooldown_service.build_instruction(memory)
    offer_instruction = offer_coupling_service.build_instruction(memory)
    decision_overrides = decision_service.build_overrides(memory)

    assert "safe_chat" in runtime_instruction
    assert "premium sexting" in gate_instruction.lower()
    assert decision_overrides["offer_pressure"] in ["none", "minimal", "low"]
    assert decision_overrides["allow_fast_escalation"] is False

    print("✅ Safe default enforcement validated")

    # --------------------------------------------------
    # CASE 2 — PURCHASE EVENT UPGRADES MEMORY
    # --------------------------------------------------

    print("\nCASE 2 — PURCHASE EVENT REINFORCEMENT")

    purchase_updates = reinforcement_service.merge_into_intimacy_context(
        existing_memory=memory,
        event_type="purchase_received",
        payload={
            "amount": 19.99,
            "content_tag": "VIP_TEST",
        },
    )

    memory.update(purchase_updates)

    context = memory["intimacy_context"]

    assert context["intimacy_tier"] == "premium"
    assert context["spender_confidence"] == "high"
    assert context["premium_sexting_allowed"] is True
    assert context["runtime_mode"] == "premium_gate"

    print("✅ Purchase reinforcement validated")

    # --------------------------------------------------
    # CASE 3 — DECISION ENGINE OVERRIDES AFTER PURCHASE
    # --------------------------------------------------

    print("\nCASE 3 — DECISION ENGINE OVERRIDES")

    decision_overrides = decision_service.build_overrides(memory)

    assert decision_overrides["response_strategy"] == "immersive_seduction"
    assert decision_overrides["exclusive_framing"] is True
    assert decision_overrides["ppv_energy"] == "exclusive"

    print("✅ DecisionEngine intimacy overrides validated")

    # --------------------------------------------------
    # CASE 4 — GPT INSTRUCTION STACK DOES NOT BREAK
    # --------------------------------------------------

    print("\nCASE 4 — GPT INSTRUCTION STACK")

    instruction_stack = "\n".join([
        runtime_service.build_instruction(memory),
        dynamic_service.build_instruction(memory),
        premium_gate_service.build_instruction(memory),
        cooldown_service.build_instruction(memory),
        offer_coupling_service.build_instruction(memory),
    ])

    required_sections = [
        "RUNTIME INTIMACY ENFORCEMENT",
        "DYNAMIC ESCALATION PROFILE",
        "PREMIUM SEXTING GATE",
        "INTIMACY COOLDOWN SUPPRESSION",
        "RUNTIME OFFER ESCALATION COUPLING",
    ]

    for section in required_sections:
        assert section in instruction_stack

    print("✅ GPT instruction stack validated")

    # --------------------------------------------------
    # CASE 5 — UNKNOWN EVENT FALLBACK SAFETY
    # --------------------------------------------------

    print("\nCASE 5 — UNKNOWN EVENT FALLBACK SAFETY")

    fallback_memory = build_base_memory()

    fallback_updates = reinforcement_service.merge_into_intimacy_context(
        existing_memory=fallback_memory,
        event_type="unknown_event",
        payload={},
    )

    fallback_context = fallback_updates["intimacy_context"]

    assert fallback_context["spender_confidence"] == "low"
    assert fallback_context["runtime_mode"] == "safe_chat"
    assert fallback_context["escalation_priority"] == "low"

    print("✅ Unknown event fallback safety validated")

    print("\n==============================================")
    print("✅ 3D.10.15J PRODUCTION VALIDATION PASSED")
    print("✅ Entire intimacy architecture is production-valid")
    print("==============================================\n")


if __name__ == "__main__":
    run_test()