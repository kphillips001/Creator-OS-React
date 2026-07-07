from app.services.relationship_recovery_service import (
    RelationshipRecoveryService,
)


def test_3d_20_8_relationship_recovery():
    service = RelationshipRecoveryService()

    result = (
        service.build_recovery_profile(
            buyer_memory={},
            conversation_state={
                "conversation_streak": 1,
                "engagement_depth_score": 1,
            },
            long_term_stability_profile={
                "stability_level": "fragile",
            },
            burnout_profile={
                "emotional_fatigue_level": "high",
            },
        )
    )

    print(
        "recovery_risk:",
        result["recovery_risk"],
    )

    print(
        "recovery_mode:",
        result["recovery_mode"],
    )

    assert (
        result[
            "relationship_recovery_active"
        ]
        is True
    )

    assert (
        result["recovery_risk"]
        == "high"
    )

    assert (
        result["recovery_mode"]
        == "soft_emotional_recovery"
    )

    assert (
        result[
            "recovery_cta_suppression"
        ]
        is True
    )


if __name__ == "__main__":
    test_3d_20_8_relationship_recovery()

    print(
        "\n=== 3D.20.8 TEST COMPLETE ==="
    )