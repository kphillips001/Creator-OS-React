from app.repositories.content_repository import (
    get_tease_content_for_user,
    get_vip_content_for_user,
    get_premium_content_for_user,
)


FANVUE_ACCOUNT_ID = 2
FANVUE_USER_ID = 4


def print_result(label, content):
    print("\n" + "=" * 60)
    print(label)
    print("=" * 60)

    if not content:
        print("❌ No CMS content returned")
        return

    print("✅ CMS content returned")
    print("id:", content.get("id"))
    print("classification:", content.get("classification"))
    print("file_name:", content.get("file_name"))
    print("status:", content.get("status"))
    print("ready_for_rotation:", content.get("ready_for_rotation"))


def main():
    print("\n🔥 TEST: CMS → CONTENT REPOSITORY LINKAGE")

    tease = get_tease_content_for_user(
        fanvue_account_id=FANVUE_ACCOUNT_ID,
        fanvue_user_id=FANVUE_USER_ID,
    )
    print_result("TEASE CONTENT", tease)

    vip = get_vip_content_for_user(
        fanvue_account_id=FANVUE_ACCOUNT_ID,
        fanvue_user_id=FANVUE_USER_ID,
    )
    print_result("VIP CONTENT", vip)

    premium = get_premium_content_for_user(
        fanvue_account_id=FANVUE_ACCOUNT_ID,
        fanvue_user_id=FANVUE_USER_ID,
    )
    print_result("PREMIUM CONTENT", premium)


if __name__ == "__main__":
    main()