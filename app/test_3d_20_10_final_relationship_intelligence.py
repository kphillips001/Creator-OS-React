from app.services.final_relationship_intelligence_service import (
    FinalRelationshipIntelligenceService,
)


def test_3d_20_10_final_relationship_intelligence():
    service = FinalRelationshipIntelligenceService()

    result = service.build_final_relationship_profile(
        runtime_state={
            "burnout_prevention_active": True,
            "dependency_safeguard_active": True,
            "long_term_emotional_stability_active": True,
            "relationship_recovery_active": True,
            "advanced_intimacy_governance_active": True,
            "intimacy_governance_mode": (
                "attachment_safe_grounding"
            ),
            "recovery_mode": "soft_emotional_recovery",
            "stability_level": "active_stabilization",
            "intimacy_escalation_allowed": False,
        }
    )

    print(
        "master_relationship_mode:",
        result["master_relationship_mode"],
    )

    print(
        "protection_active:",
        result["relationship_protection_active"],
    )

    print(
        "override_active:",
        result["relationship_override_active"],
    )

    assert (
        result[
            "final_relationship_intelligence_active"
        ]
        is True
    )

    assert (
        result[
            "relationship_protection_active"
        ]
        is True
    )

    assert (
        result[
            "master_relationship_mode"
        ]
        == "protective_grounding"
    )

    assert (
        result[
            "relationship_override_active"
        ]
        is True
    )


if __name__ == "__main__":
    test_3d_20_10_final_relationship_intelligence()

    print(
        "\n=== 3D.20.10 TEST COMPLETE ==="
    )