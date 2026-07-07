from app.engine.decision_engine import DecisionEngine
from app.engine.mode_engine import ModeEngine
from app.services.memory_service import MemoryService
from app.services.intent_service import IntentService
from app.services.user_value_service import UserValueService
from app.services.offer_service import OfferService
from app.services.content_service import ContentService
from app.services.post_offer_service import PostOfferService
from app.services.timing_engine import TimingEngine
from app.services.gpt_service import GPTService
from app.config import settings
import logging


def run_test():
    print("\n=== 3D.20.6.2 DECISIONENGINE DEPENDENCY INJECTION TEST ===\n")

    engine = DecisionEngine(
        memory_service=MemoryService(),
        intent_service=IntentService(),
        user_value_service=UserValueService(),
        mode_engine=ModeEngine(),
        offer_service=OfferService(),
        content_service=ContentService(),
        post_offer_service=PostOfferService(),
        timing_engine=TimingEngine(),
        gpt_service=GPTService(api_key=settings.OPENAI_API_KEY),
        settings=settings,
        logger=logging.getLogger("3d_20_6_2_test"),
    )

    result = engine.process_message(
        user_id="1:1",
        message=(
            "Please don't leave me. I feel like you're all I have "
            "right now, and I waited all night for you."
        ),
        chat_history=[],
    )

    print("\n=== RESULT CHECK ===")
    print("response:", result.get("response"))
    print("dependency_risk_level:", result.get("dependency_risk_level"))
    print("dependency_risk_score:", result.get("dependency_risk_score"))
    print("attachment_stabilization_mode:", result.get("attachment_stabilization_mode"))
    print("dependency_safe_response_bias:", result.get("dependency_safe_response_bias"))
    print("stability_level:", result.get("stability_level"))
    print(
        "long_term_emotional_stability_active:",
        result.get("long_term_emotional_stability_active"),
    )
    print(
        "relationship_rhythm_state:",
        result.get("relationship_rhythm_state"),
    )
    print(
        "long_term_response_bias:",
        result.get("long_term_response_bias"),
    )

    print("\n=== 3D.20.6.2 TEST COMPLETE ===\n")


if __name__ == "__main__":
    run_test()