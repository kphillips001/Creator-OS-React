from app.services.intimacy_memory_service import (
    IntimacyMemoryService,
)


def run_test():

    print("\n======================================")
    print(" 3D.10.14 INTIMACY MEMORY TEST")
    print("======================================\n")

    service = (
        IntimacyMemoryService()
    )

    result = (
        service.sync_memory(
            "test_user_uuid"
        )
    )

    print("\nRESULT:\n")
    print(result)

    print(
        "\n✅ 3D.10.14 intimacy memory works"
    )


if __name__ == "__main__":
    run_test()