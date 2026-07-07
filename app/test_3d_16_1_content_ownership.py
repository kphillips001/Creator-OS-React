from app.services.content_ownership_service import (
    ContentOwnershipService,
)


def run_test():
    print("\n==============================")
    print(" 3D.16.1 CONTENT OWNERSHIP")
    print("==============================\n")

    service = ContentOwnershipService()

    fanvue_user_id = 1

    owned = service.get_owned_content_tags(
        fanvue_user_id
    )

    print("OWNED TAGS:")
    print(owned)

    if owned:
        test_tag = owned[0]

        already_owned = (
            service.user_already_owns_content(
                fanvue_user_id,
                test_tag,
            )
        )

        print("\nOWNERSHIP CHECK:")
        print(test_tag)
        print(already_owned)

    print("\n✅ TEST COMPLETE")


if __name__ == "__main__":
    run_test()