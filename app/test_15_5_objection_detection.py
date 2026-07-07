from app.services.gpt_intent_classifier_service import GPTIntentClassifierService
from app.config import settings


def run_test():
    print("\n=== 15.5 OBJECTION DETECTION TEST ===\n")

    classifier = GPTIntentClassifierService(settings.OPENAI_API_KEY)

    test_cases = [
        "that is too expensive",
        "idk I’m not sure yet",
        "maybe later",
        "what do I get for that?",
        "is it worth it?",
        "okay send it now 😈",
        "you look amazing",
    ]

    for message in test_cases:
        print("\n--------------------------------------------------")
        print(f"MESSAGE: {message}")

        result = classifier.classify_message(
            message=message,
            memory={},
        )

        print(f"OBJECTION TYPE: {result.get('objection_type')}")
        print(f"USER STATE: {result.get('user_state')}")
        print(f"RECOMMENDED ACTION: {result.get('recommended_action')}")
        print(f"CONFIDENCE: {result.get('confidence')}")
        print(f"FULL RESULT: {result}")


if __name__ == "__main__":
    run_test()