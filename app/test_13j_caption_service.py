from app.repositories.content_repository import get_tease_content_for_user
from app.services.content_caption_service import (
    generate_tease_caption_from_content,
    generate_vip_caption_from_content,
    generate_premium_caption_from_content,
)


TEST_FANVUE_ACCOUNT_ID = 1
TEST_FANVUE_USER_ID = 999999


def run_test():
    print("\n========================================")
    print("13J CAPTION SERVICE TEST")
    print("========================================\n")

    content = get_tease_content_for_user(
        fanvue_account_id=TEST_FANVUE_ACCOUNT_ID,
        fanvue_user_id=TEST_FANVUE_USER_ID,
    )

    if not content:
        print("[STOP] No TEASE content found.")
        return

    print("[CONTENT SELECTED]")
    print({
        "id": content["id"],
        "file_name": content["file_name"],
        "classification": content["classification"],
        "detected_themes": content["detected_themes"],
        "suggested_tags": content["suggested_tags"],
    })

    user_memory = {
        "user_type": "follower",
        "user_value_tier": "cold",
        "attention_tier": "medium",
    }

    tease_caption = generate_tease_caption_from_content(
        content=content,
        user_memory=user_memory,
    )

    vip_caption = generate_vip_caption_from_content(
        content=content,
        user_memory=user_memory,
    )

    premium_caption = generate_premium_caption_from_content(
        content=content,
        user_memory=user_memory,
    )

    print("\n[TEASE CAPTION]")
    print(tease_caption)

    print("\n[VIP CAPTION]")
    print(vip_caption)

    print("\n[PREMIUM CAPTION]")
    print(premium_caption)

    print("\n========================================")
    print("[DONE] Caption service test complete")
    print("========================================\n")


if __name__ == "__main__":
    run_test()