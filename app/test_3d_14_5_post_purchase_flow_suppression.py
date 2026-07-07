from app.services.mass_ppv_suppression_signal_service import (
    MassPPVSuppressionSignalService,
)


def run_test():
    print("\n==============================")
    print("3D.14.5 POST-PURCHASE FLOW SUPPRESSION TEST")
    print("==============================\n")

    service = MassPPVSuppressionSignalService()

    memory = {
        "thank_you_flow_active": True,
        "premium_followup_active": True,
        "reaction_pipeline_active": True,
    }

    active_flows = (
        service._get_active_post_purchase_flows(
            memory,
            {},
        )
    )

    reasons = []

    for flow in active_flows:
        reasons.append(
            f"active_post_purchase_flow:{flow}"
        )

    print("Active flows:")
    print(active_flows)

    print("\nReasons:")
    print(reasons)

    assert "thank_you_flow_active" in active_flows

    assert "premium_followup_active" in active_flows

    assert "reaction_pipeline_active" in active_flows

    assert (
        "active_post_purchase_flow:"
        "thank_you_flow_active"
        in reasons
    )

    print("\n✅ 3D.14.5 PASSED")


if __name__ == "__main__":
    run_test()