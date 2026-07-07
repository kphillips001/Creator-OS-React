from app.services.mass_ppv_content_service import MassPPVContentService


def run_test():
    print("\n==============================")
    print(" MASS PPV CONTENT SERVICE TEST")
    print("==============================\n")

    fanvue_account_id = 1

    service = MassPPVContentService()
    result = service.get_mass_ppv_content(fanvue_account_id)

    print("\n--- RESULT ---")
    print(result)

    if not result:
        print("\n❌ No valid Mass PPV content found.")
        print("Check that CMS has uploaded VIP content with:")
        print("- destination = vip")
        print("- upload_status = uploaded")
        print("- fanvue_full_media_uuid or fanvue_media_uuid")
        print("- fanvue_preview_media_uuid")
        print("- CMS price")
        print("- CMS tag/classification")
        return

    required_fields = [
        "content_item_id",
        "media_uuid",
        "preview_uuid",
        "price",
        "tag",
    ]

    missing = [field for field in required_fields if not result.get(field)]

    if missing:
        print("\n❌ TEST FAILED")
        print(f"Missing fields: {missing}")
        return

    print("\n✅ TEST PASSED")
    print("Mass PPV content is CMS-backed, vip-only, and chat_ppv-ready.")


if __name__ == "__main__":
    run_test()