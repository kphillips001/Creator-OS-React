from app.config import settings
from app.services.gpt_intent_classifier_service import GPTIntentClassifierService


def run_test():
    print("\n=== 19A: GPT INTENT CLASSIFIER SERVICE TEST ===\n")

    classifier = GPTIntentClassifierService(settings.OPENAI_API_KEY)

    tests = [
        {
            "name": "Ready-to-buy buyer",
            "message": "bettt okay I need to see that now 😈",
            "memory": {
                "buyer_session_active": True,
                "buyer_session_step": 3,
                "buyer_session_last_action": "ppv_offer_presented",
            },
        },
        {
            "name": "Curious but not ready",
            "message": "hmm okay now I’m curious what kind of thing is it 👀",
            "memory": {
                "buyer_session_active": True,
                "buyer_session_step": 2,
            },
        },
        {
            "name": "Converted buyer",
            "message": "okay I unlocked it",
            "memory": {
                "buyer_session_active": True,
                "buyer_session_step": 3,
                "buyer_session_last_action": "close_mode",
            },
        },
        {
            "name": "Rejecting or delaying",
            "message": "eh maybe another time honestly",
            "memory": {
                "buyer_session_active": True,
                "buyer_session_step": 3,
                "buyer_session_last_action": "close_mode",
            },
        },
        {
            "name": "Support issue",
            "message": "my payment is not working and it keeps giving me an error",
            "memory": {},
        },
    ]

    for test in tests:
        print(f"\n--- {test['name']} ---")
        print("Message:", test["message"])

        result = classifier.classify_message(
            message=test["message"],
            memory=test["memory"],
        )

        print("Result:", result)
        print("-" * 60)

    print("\n=== TEST COMPLETE ===\n")


if __name__ == "__main__":
    run_test()