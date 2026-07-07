from app.config import settings

from app.services.emotional_dependency_classifier_service import (
    EmotionalDependencyClassifierService,
)


def run_test():
    service = EmotionalDependencyClassifierService(
        api_key=settings.OPENAI_API_KEY
    )

    print("\n=== 3D.20.6.1 GPT-AWARE DEPENDENCY CLASSIFIER TEST ===\n")

    test_cases = [
        {
            "name": "LOW — normal affectionate message",
            "message": "I missed chatting with you today, you always make me smile.",
            "memory": {
                "buyer_tier": "WHALE",
                "conversation_mode": "flirty",
                "relationship_status": "warm",
                "intent_score": 45,
                "heat_score": 55,
            },
        },
        {
            "name": "MEDIUM/HIGH — exclusivity pressure",
            "message": "I need to know if I'm the only one who matters to you.",
            "memory": {
                "buyer_tier": "HIGH_VALUE",
                "conversation_mode": "tension",
                "relationship_status": "attached",
                "intent_score": 65,
                "heat_score": 70,
            },
        },
        {
            "name": "HIGH/CRITICAL — attachment escalation",
            "message": "Please don't leave me. I feel like you're all I have right now.",
            "memory": {
                "buyer_tier": "WHALE",
                "conversation_mode": "premium_continuity",
                "relationship_status": "deep_attachment",
                "intent_score": 75,
                "heat_score": 80,
            },
        },
        {
            "name": "CRITICAL — volatility plus burnout overlap",
            "message": "Why didn't you answer me? I waited all night and it really hurt.",
            "memory": {
                "buyer_tier": "WHALE",
                "conversation_mode": "premium_continuity",
                "relationship_status": "emotionally_intense",
                "intent_score": 80,
                "heat_score": 85,
            },
            "burnout_context": {
                "burnout_risk_level": "HIGH",
                "emotional_recovery_mode": True,
                "cta_suppressed": True,
            },
        },
    ]

    for case in test_cases:
        print(f"\n--- {case['name']} ---")

        result = service.classify_dependency_risk(
            message=case["message"],
            memory=case.get("memory", {}),
            burnout_context=case.get("burnout_context", {}),
        )

        print("dependency_risk_level:", result.get("dependency_risk_level"))
        print("dependency_risk_score:", result.get("dependency_risk_score"))
        print("over_attachment_escalation:", result.get("over_attachment_escalation"))
        print("cling_behavior:", result.get("cling_behavior"))
        print("dependency_reinforcement_risk:", result.get("dependency_reinforcement_risk"))
        print("emotional_overreliance:", result.get("emotional_overreliance"))
        print("excessive_exclusivity_signaling:", result.get("excessive_exclusivity_signaling"))
        print("emotional_volatility_escalation:", result.get("emotional_volatility_escalation"))
        print("emotional_spacing_bias:", result.get("emotional_spacing_bias"))
        print("attachment_stabilization_mode:", result.get("attachment_stabilization_mode"))
        print("reinforcement_softening_required:", result.get("reinforcement_softening_required"))
        print("emotional_exclusivity_limit:", result.get("emotional_exclusivity_limit"))
        print("intimacy_ceiling_state:", result.get("intimacy_ceiling_state"))
        print("dependency_safe_response_bias:", result.get("dependency_safe_response_bias"))
        print("confidence:", result.get("confidence"))
        print("reason:", result.get("reason"))


if __name__ == "__main__":
    run_test()