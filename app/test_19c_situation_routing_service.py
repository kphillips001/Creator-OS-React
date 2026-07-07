from app.engine.decision_engine import DecisionEngine

from app.services.memory_service import MemoryService
from app.services.intent_service import IntentService
from app.services.user_value_service import UserValueService
from app.engine.mode_engine import ModeEngine
from app.services.offer_service import OfferService
from app.services.content_service import ContentService
from app.services.post_offer_service import PostOfferService
from app.services.timing_engine import TimingEngine
from app.services.gpt_service import GPTService
from app.config import settings
from app.logger import get_logger


def build_engine():
    logger = get_logger("test")

    return DecisionEngine(
        memory_service=MemoryService(),
        intent_service=IntentService(),
        user_value_service=UserValueService(),
        mode_engine=ModeEngine(),
        offer_service=OfferService(),
        content_service=ContentService(),
        post_offer_service=PostOfferService(),
        timing_engine=TimingEngine(),
        gpt_service=GPTService(settings.OPENAI_API_KEY),
        settings=settings,
        logger=logger,
    )


def run_test():
    print("\n=== 19C: SITUATION ROUTING SERVICE TEST ===\n")

    engine = build_engine()

    test_cases = [
        ("Sales / close route", "bet okay I need to see that now 😈"),
        ("Support route", "my payment keeps failing and I can’t unlock it"),
        ("Custom request route", "could you make something just for me?"),
        ("Curious chat route", "hmm okay now I’m curious 👀"),
        ("Reconnect-ish route", "I disappeared for a bit but I’m back now"),
    ]

    for label, message in test_cases:
        print(f"\n--- {label} ---")
        print(f"Message: {message}")

        result = engine.process_message(
            fanvue_account_id=1,
            fanvue_user_uuid="test_user",
            message=message,
            dry_run=True,
        )

        print("RESULT:", result)


if __name__ == "__main__":
    run_test()