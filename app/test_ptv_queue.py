from app.repositories.content_repository import get_content_ready_for_ptv_set_creation


def run_test():
    print("\n=== 14M STEP 3B: PTV SET QUEUE TEST ===\n")

    queue = get_content_ready_for_ptv_set_creation(limit=5)

    print(f"Queue count: {len(queue)}")

    for item in queue:
        print(item)


if __name__ == "__main__":
    run_test()