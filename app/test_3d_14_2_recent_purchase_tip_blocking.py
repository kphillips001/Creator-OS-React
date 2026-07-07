from datetime import datetime, timezone

from app.services.mass_ppv_suppression_signal_service import (
    MassPPVSuppressionSignalService,
)


def run_test():
    print("\n==============================")
    print("3D.14.2 RECENT PURCHASE/TIP BLOCKING TEST")
    print("==============================\n")

    service = MassPPVSuppressionSignalService()

    recent_purchase = datetime.now(
        timezone.utc
    ).isoformat()

    recent_tip = datetime.now(
        timezone.utc
    ).isoformat()

    purchase_result = service._safe_parse_datetime(
        recent_purchase
    )

    tip_result = service._safe_parse_datetime(
        recent_tip
    )

    assert purchase_result is not None
    assert tip_result is not None

    purchase_active = service._is_recent_purchase_active(
        {
            "last_purchase_at": recent_purchase
        },
        {},
    )

    tip_active = service._is_recent_tip_active(
        {
            "last_tip_at": recent_tip
        },
        {},
    )

    print("Recent purchase active:", purchase_active)
    print("Recent tip active:", tip_active)

    assert purchase_active is True
    assert tip_active is True

    print("\n✅ 3D.14.2 PASSED")


if __name__ == "__main__":
    run_test()