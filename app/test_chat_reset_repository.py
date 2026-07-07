from app.repositories.chat_reset_repository import reset_user_chat


def run_test():
    print("\n==============================")
    print(" CHAT RESET REPOSITORY TEST")
    print("==============================\n")

    # Use your test Fanvue user UUID (NOT id anymore)
    fanvue_user_uuid = "11111111-1111-1111-1111-111111111111"

    print(f"Testing reset for fanvue_user_uuid={fanvue_user_uuid}")

    reset_user_chat(fanvue_user_uuid)

    print("\n✅ Chat reset repository test complete")


if __name__ == "__main__":
    run_test()