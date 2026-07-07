from app.services.fanvue_api_service import FanvueAPIService


def run_test():
    print("\n==============================")
    print("GET FANVUE USER UUID TEST")
    print("==============================\n")

    api = FanvueAPIService()

    result = api.list_chats()

    if not result.get("success"):
        print("❌ Failed to fetch chats")
        print(result)
        return

    chats = result.get("data", [])

    if not chats:
        print("⚠️ No chats found — message yourself or a test account first")
        return

    print("\n🔥 AVAILABLE USER UUIDs:\n")

    for chat in chats:
        user = chat.get("user", {})
        username = user.get("username")
        user_uuid = user.get("uuid")

        print(f"Username: {username}")
        print(f"UUID: {user_uuid}")
        print("------------------------")

    print("\n==============================")
    print("DONE")
    print("==============================\n")


if __name__ == "__main__":
    run_test()