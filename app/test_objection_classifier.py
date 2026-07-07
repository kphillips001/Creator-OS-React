from app.services.objection_classifier_service import ObjectionClassifierService


def run_test():
    print("\n=== 15.5 STEP 1: OBJECTION CLASSIFIER TEST ===\n")

    service = ObjectionClassifierService()

    test_messages = [
        "this is too expensive",
        "hmm idk about it",
        "what do I get for that?",
        "maybe later",
        "damn you look good",
    ]

    for msg in test_messages:
        print(f"\n--- MESSAGE: {msg} ---")

        result = service.classify_objection(msg)

        print("RESULT:", result)


if __name__ == "__main__":
    run_test()