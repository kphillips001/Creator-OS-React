import os

from app.services.fanvue_api_service import FanvueAPIService


def run_test():
    print("\n==============================")
    print("3D.15.3 FANVUE API SEND CUTOFF TEST")
    print("==============================\n")

    os.environ["GLOBAL_AUTOMATION_ENABLED"] = "false"
    os.environ["GLOBAL_SENDS_ENABLED"] = "false"
    os.environ["CHAT_AUTOMATION_ENABLED"] = "true"
    os.environ["ENABLE_REALTIME_FANVUE_SEND"] = "true"

    service = FanvueAPIService()

    result = service.send_chat_message(
        user_uuid="fake-user-uuid",
        payload={
            "message": "This should never send.",
        },
    )

    print("Result:")
    print(result)

    assert result["success"] is False
    assert result["sent"] is False
    assert result["blocked"] is True
    assert result["reason"] == "global_automation_disabled"

    print("\n✅ 3D.15.3 PASSED")


if __name__ == "__main__":
    run_test()