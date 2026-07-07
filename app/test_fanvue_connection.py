from app.services.fanvue_api_service import FanvueAPIService


def run_test():
    print("\n======================================")
    print("FANVUE API CONNECTION TEST")
    print("======================================\n")

    service = FanvueAPIService()

    result = service.test_connection()

    print("\n------------- RESULT -------------")
    print(f"success: {result.get('success')}")
    print(f"status_code: {result.get('status_code')}")

    if result.get("user_uuid"):
        print("\n🔥 YOUR USER UUID:")
        print(result.get("user_uuid"))

    print("\n======================================")
    print("TEST COMPLETE")
    print("======================================\n")


if __name__ == "__main__":
    run_test()