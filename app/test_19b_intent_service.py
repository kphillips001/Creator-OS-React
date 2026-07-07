from app.services.intent_service import IntentService


def run_test():
    print("\n=== 19B: INTENT SERVICE TEST ===\n")

    service = IntentService()

    tests = [
        "bettt okay I need to see that now 😈",
        "hmm okay now I’m curious what kind of thing is it 👀",
        "okay I unlocked it",
        "eh maybe another time honestly",
        "my payment is not working",
    ]

    for msg in tests:
        print("\nMessage:", msg)

        result = service.detect_intent(msg)

        print("Result:", result)
        print("-" * 50)

    print("\n=== TEST COMPLETE ===\n")


if __name__ == "__main__":
    run_test()