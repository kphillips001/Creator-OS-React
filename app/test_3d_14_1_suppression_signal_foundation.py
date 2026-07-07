from app.services.mass_ppv_suppression_signal_service import (
    MassPPVSuppressionSignalService,
)


def run_test():
    print("\n==============================")
    print("3D.14.1 SUPPRESSION SIGNAL FOUNDATION TEST")
    print("==============================\n")

    service = MassPPVSuppressionSignalService()

    fanvue_user_id = "1"

    result = service.get_suppression_signals(fanvue_user_id)

    print("Result:")
    print(result)

    assert "suppressed" in result
    assert "reasons" in result
    assert "signals" in result

    print("\n✅ 3D.14.1 PASSED")


if __name__ == "__main__":
    run_test()