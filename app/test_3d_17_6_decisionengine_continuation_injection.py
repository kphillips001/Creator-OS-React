from app.services.decision_engine_continuation_injection_service import (
    DecisionEngineContinuationInjectionService,
)


def run_test():
    print("\n==============================")
    print("3D.17.6 DECISIONENGINE CONTINUATION INJECTION TEST")
    print("==============================\n")

    service = DecisionEngineContinuationInjectionService()

    refresh_payload = {
        "monetization_event": {
            "event_type": "purchase_received",
        },
        "buyer_state": {
            "buyer_tier": "ACTIVE_BUYER",
        },
        "continuation_route": {
            "route": "soft_continue",
        },
        "retention_route": {
            "retention_mode": "active_buyer_retention",
        },
    }

    result = service.build_injection(refresh_payload)

    print(result)

    assert result["success"] is True
    assert result["injection_enabled"] is True
    assert result["response_strategy"] == "soft_continue"
    assert result["buyer_tier"] == "ACTIVE_BUYER"
    assert result["ppv_energy"] == "selective_premium"
    assert result["premium_routing"] == "premium_eligible"
    assert result["suppression_handling"] == (
        "suppress_mass_ppv_and_preserve_premium_flow"
    )

    whale_payload = {
        "monetization_event": {
            "event_type": "tip_received",
        },
        "buyer_state": {
            "buyer_tier": "WHALE",
        },
    }

    whale_result = service.build_injection(whale_payload)

    print("\nWHALE RESULT:")
    print(whale_result)

    assert whale_result["response_strategy"] == "premium_retention"
    assert whale_result["retention_mode"] == "whale_retention"
    assert whale_result["ppv_energy"] == "premium_only_low_pressure"

    safe_result = service.build_injection(None)

    print("\nSAFE DEFAULT RESULT:")
    print(safe_result)

    assert safe_result["success"] is False
    assert safe_result["injection_enabled"] is False

    print("\n✅ 3D.17.6 continuation injection test passed")


if __name__ == "__main__":
    run_test()