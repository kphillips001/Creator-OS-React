from app.services.advanced_intimacy_governance_service import (
    AdvancedIntimacyGovernanceService,
)


def test_3d_20_9_advanced_intimacy_governance():
    service = AdvancedIntimacyGovernanceService()

    result = service.build_governance_profile(
        runtime_state={
            "buyer_tier": "WHALE",
            "runtime_mode": "premium_intimacy",
            "stability_level": "active_stabilization",
            "dependency_risk_level": "low",
            "burnout_risk": "low",
            "recovery_risk": "low",
        }
    )

    print(
        "governance_mode:",
        result["intimacy_governance_mode"],
    )

    print(
        "escalation_allowed:",
        result["intimacy_escalation_allowed"],
    )

    print(
        "ceiling:",
        result["intimacy_escalation_ceiling"],
    )

    assert (
        result[
            "advanced_intimacy_governance_active"
        ]
        is True
    )

    assert (
        result[
            "premium_intimacy_allowed"
        ]
        is True
    )

    assert (
        result[
            "intimacy_governance_mode"
        ]
        == "stability_paced"
    )

    assert (
        result[
            "intimacy_escalation_ceiling"
        ]
        == "slow_increment"
    )


if __name__ == "__main__":
    test_3d_20_9_advanced_intimacy_governance()

    print(
        "\n=== 3D.20.9 TEST COMPLETE ==="
    )