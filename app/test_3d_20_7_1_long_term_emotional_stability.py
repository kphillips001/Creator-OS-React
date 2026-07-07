from app.services.long_term_emotional_stability_service import (
    LongTermEmotionalStabilityService,
)


def run_test():
    service = LongTermEmotionalStabilityService()

    print("\n=== 3D.20.7.1 LONG-TERM EMOTIONAL STABILITY TEST ===\n")

    test_cases = [
        {
            "name": "TEST 1 — ACTIVE WHALE STABLE RHYTHM",
            "buyer_memory": {
                "buyer_tier": "WHALE",
                "conversation_streak": 18,
                "engagement_depth_score": 22,
            },
            "conversation_state": {
                "conversation_mode": "tension",
                "intent_score": 55,
                "heat_score": 65,
                "buyer_tier": "WHALE",
                "user_value_tier": "WHALE",
            },
        },
        {
            "name": "TEST 2 — DEPENDENCY HIGH STABILIZATION",
            "buyer_memory": {
                "buyer_tier": "HIGH_VALUE",
                "conversation_streak": 12,
                "engagement_depth_score": 20,
            },
            "conversation_state": {
                "conversation_mode": "flirty",
                "intent_score": 35,
                "heat_score": 50,
                "buyer_tier": "HIGH_VALUE",
                "user_value_tier": "HIGH_VALUE",
            },
            "emotional_dependency_profile": {
                "dependency_risk_level": "high",
            },
        },
        {
            "name": "TEST 3 — BURNOUT PRESSURE REBALANCE",
            "buyer_memory": {
                "buyer_tier": "WHALE",
                "conversation_streak": 15,
                "engagement_depth_score": 28,
            },
            "conversation_state": {
                "conversation_mode": "tension",
                "intent_score": 45,
                "heat_score": 70,
                "buyer_tier": "WHALE",
                "user_value_tier": "WHALE",
            },
            "whale_burnout_profile": {
                "burnout_risk": "high",
            },
        },
        {
            "name": "TEST 4 — NON BUYER SAFE DEFAULT",
            "buyer_memory": {
                "buyer_tier": "NON_BUYER",
                "conversation_streak": 1,
                "engagement_depth_score": 1,
            },
            "conversation_state": {
                "conversation_mode": "casual",
                "intent_score": 5,
                "heat_score": 5,
                "buyer_tier": "NON_BUYER",
                "user_value_tier": "none",
            },
        },
    ]

    for case in test_cases:
        print("\n" + "=" * 60)
        print(case["name"])
        print("=" * 60)

        result = service.build_stability_profile(
            buyer_memory=case.get("buyer_memory", {}),
            conversation_state=case.get("conversation_state", {}),
            emotional_presence_profile=case.get(
                "emotional_presence_profile",
                {},
            ),
            premium_conversation_continuity_profile=case.get(
                "premium_conversation_continuity_profile",
                {},
            ),
            whale_burnout_profile=case.get(
                "whale_burnout_profile",
                {},
            ),
            emotional_dependency_profile=case.get(
                "emotional_dependency_profile",
                {},
            ),
        )

        print("success:", result.get("success"))
        print(
            "long_term_emotional_stability_active:",
            result.get("long_term_emotional_stability_active"),
        )
        print("stability_level:", result.get("stability_level"))
        print(
            "relationship_rhythm_state:",
            result.get("relationship_rhythm_state"),
        )
        print(
            "emotional_volatility_smoothing:",
            result.get("emotional_volatility_smoothing"),
        )
        print(
            "emotional_consistency_mode:",
            result.get("emotional_consistency_mode"),
        )
        print(
            "anti_whiplash_required:",
            result.get("anti_whiplash_required"),
        )
        print(
            "familiarity_preservation_level:",
            result.get("familiarity_preservation_level"),
        )
        print(
            "emotional_drift_correction:",
            result.get("emotional_drift_correction"),
        )
        print(
            "long_term_response_bias:",
            result.get("long_term_response_bias"),
        )
        print("gpt_instruction:", result.get("gpt_instruction"))
        print("reasons:", result.get("reasons"))

    print("\n=== 3D.20.7.1 TEST COMPLETE ===\n")


if __name__ == "__main__":
    run_test()