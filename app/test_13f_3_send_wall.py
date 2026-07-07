from app.services.content_send_service import ContentSendService


def run_test():
    print("\n======================================")
    print("13F-3.2 TEST — SEND WALL POST WITH HISTORY PROTECTION")
    print("======================================\n")

    service = ContentSendService()

    fanvue_account_id = 1

    print("[TEST] Dry run first")

    result = service.send_wall_post(
        fanvue_account_id=fanvue_account_id,
        caption="🚀 LIVE wall post test from 13F-3.3 — will delete after validation",
        dry_run=True,
    )

    print("\nRESULT:")
    print(result)

    print("\n======================================")
    print("13F-3.2 TEST COMPLETE")
    print("======================================\n")


if __name__ == "__main__":
    run_test()