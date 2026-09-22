from datetime import datetime, timedelta, timezone

import pytest

from app.services.commercial_receptiveness_service import (
    CommercialReceptivenessService,
)
from app.services.conversational_sales_progression_service import (
    ConversationalSalesProgressionService,
)
from app.services.sexual_sales_opportunity_service import (
    SexualSalesOpportunityService,
)


STU_MESSAGE = "You are very sexy tell me more about you"
CLASSIFIER = {
    "route": "chat",
    "buying_intent": False,
    "monetization_intent": False,
    "purchase_language_present": False,
    "close_ready": False,
    "sexual_engagement": True,
    "recommended_action": "build_tension",
    "explicit_without_buying_intent": True,
}


class NoPresentations:
    @staticmethod
    def list_confirmed_presentations_for_buyer(**_kwargs):
        return ()


def test_stu_exact_turn_is_compliment_without_direct_commercial_authority():
    progression = ConversationalSalesProgressionService()
    receptiveness = CommercialReceptivenessService(
        progression.has_direct_purchase_intent
    ).evaluate(
        context={"latest_message": STU_MESSAGE, "classifier_result": CLASSIFIER},
        recent_purchase=False,
        cooldown_active=False,
        readiness={
            "recommended_conversational_action":
                progression.recommended_conversational_action(
                    STU_MESSAGE, CLASSIFIER
                )
        },
        active_offer=False,
    )
    sexual = SexualSalesOpportunityService(
        intents=NoPresentations(), cooldown=timedelta(hours=72),
    ).project(
        creator_profile_id=2, fanvue_account_id=2,
        telegram_user_id=7489120428, latest_message=STU_MESSAGE,
        now=datetime(2026, 9, 17, 23, tzinfo=timezone.utc),
        tone={"sexualOrProvocative": True},
        commercial_signal=receptiveness.current_commercial_interest,
    )

    assert progression.has_direct_purchase_intent(STU_MESSAGE) is False
    assert receptiveness.current_commercial_interest is False
    assert receptiveness.another_sale_appropriate_now is False
    assert sexual["sexualSignalClass"] == "SEXUAL_ATTRACTIVE_COMPLIMENT"
    assert sexual["sexualSalesOpportunityEligible"] is False
    assert sexual["activePresentationBridge"] is False


@pytest.mark.parametrize(
    "message",
    [
        "how much is that set?",
        "how do I unlock it?",
        "I want to buy it",
        "send me the content",
        "what do I get?",
    ],
)
def test_genuine_commercial_requests_remain_direct(message):
    progression = ConversationalSalesProgressionService()
    assert progression.has_direct_purchase_intent(message) is True


def test_genuine_sexual_escalation_still_reaches_opportunity_policy():
    value = SexualSalesOpportunityService(
        intents=NoPresentations(), cooldown=timedelta(hours=72),
    ).project(
        creator_profile_id=2, fanvue_account_id=2, telegram_user_id=3,
        latest_message="I want you naked in bed",
        now=datetime(2026, 9, 17, 23, tzinfo=timezone.utc),
    )
    assert value["sexualSignalClass"] == "SEXUAL_ESCALATION"
    assert value["sexualSalesOpportunityEligible"] is True
