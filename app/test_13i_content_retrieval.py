from app.repositories.content_repository import get_content_by_classification


def run_test():
    print("\n========================================")
    print("13I.1 CONTENT RETRIEVAL TEST")
    print("========================================\n")

    for classification in ["TEASE", "VIP", "PREMIUM"]:
        result = get_content_by_classification(classification)

        print("----------------------------------------")
        print(f"[CLASSIFICATION] {classification}")

        if result:
            print("[FOUND]")
            print(result)
        else:
            print("[NOT FOUND]")


if __name__ == "__main__":
    run_test()