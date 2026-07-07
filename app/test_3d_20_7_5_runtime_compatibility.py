from app.services.runtime_relationship_compatibility_service import (
    RuntimeRelationshipCompatibilityService,
)


def test_3d_20_7_5_runtime_compatibility():
    service = RuntimeRelationshipCompatibilityService()

    result = service.validate_runtime_compatibility(
        {
            "whale_burnout_prevention_active": True,
            "attachment_stabilization_mode": (
                "soft_grounding"
            ),
            "long_term_emotional_stability_active": True,
            "runtime_mode": "premium_intimacy",
            "send_offer": True,
        }
    )

    print(
        "compatibility_safe:",
        result[
            "runtime_relationship_compatibility_safe"
        ],
    )

    print(
        "conflicts:",
        result[
            "runtime_relationship_conflicts"
        ],
    )

    assert (
        result[
            "runtime_relationship_validation_active"
        ]
        is True
    )

    assert (
        result[
            "runtime_relationship_compatibility_safe"
        ]
        is False
    )

    assert (
        "burnout_vs_offer_conflict"
        in result[
            "runtime_relationship_conflicts"
        ]
    )

    assert (
        "dependency_vs_intimacy_conflict"
        in result[
            "runtime_relationship_conflicts"
        ]
    )

    assert (
        "stability_vs_pressure_conflict"
        in result[
            "runtime_relationship_conflicts"
        ]
    )


if __name__ == "__main__":
    test_3d_20_7_5_runtime_compatibility()

    print(
        "\n=== 3D.20.7.5 TEST COMPLETE ==="
    )