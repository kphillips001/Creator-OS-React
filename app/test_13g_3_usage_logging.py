from app.services.fanvue_api_service import FanvueAPIService


def run_test():
    print("\n====================================")
    print("13G-3 CONTENT USAGE LOGGING TEST")
    print("====================================\n")

    api = FanvueAPIService()

    test_payload = {
        "content_item_id": 52,
        "content_tag": "test_logging_13g_3",
        "payload_type": "chat_test",
        "text": "Test logging message",
    }

    result = api.send_chat_message(
        user_uuid="705b406b-edf0-43ce-93ca-b6e7e9aa3750",
        payload=test_payload,
        fanvue_account_id=1,
        fanvue_user_id=999001,
    )

    print("\n--- RESULT ---")
    print(result)

    print("\n====================================")
    print("13G-3 TEST COMPLETE")
    print("====================================\n")


if __name__ == "__main__":
    run_test()