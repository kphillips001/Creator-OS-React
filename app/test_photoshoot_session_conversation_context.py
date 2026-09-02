from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.autonomous_sales_progression import (
    BuyingMomentumAssessment,
    BuyingMomentumState,
    NextSalesAction,
    NextSalesActionType,
)
from app.models.photoshoot_session_runtime import (
    PhotoshootSessionRuntimeState,
    PhotoshootSessionRuntimeStatus,
)
from app.services.photoshoot_session_conversation_context_builder import (
    PhotoshootSessionConversationContextBuilder,
)
from app.services.gpt_service import GPTService
from app.services.conversation_gateway import ConversationGateway
from app.models.customer_sales_decision import (
    CustomerBuyerStage, CustomerSalesDecisionType, CustomerSalesReasonCode,
)


class Strategies:
    def latest(self, session_id):
        assert session_id == "session-1"
        return SimpleNamespace(shots=(
            SimpleNamespace(
                asset_id=20, sales_role="FREE_TEASER", access_recommendation="FREE",
                customer_journey_purpose="Create curiosity", recommended_progression="Open the session",
            ),
            SimpleNamespace(
                asset_id=21, sales_role="FIRST_UNLOCK", access_recommendation="PAID",
                customer_journey_purpose="Deepen interest", recommended_progression="Move beyond the teaser",
            ),
        ))


class Photoshoots:
    def get_by_session(self, session_id):
        return {"display_name": "Indoor Sequence"}

    def get_intelligence(self, session_id):
        return {
            "commercial_title": "Indoor Sequence", "theme": "Intimate home setting",
            "story": "A gradual indoor progression.", "profile_data": {},
        }

    def latest_shot_intelligence(self, session_id):
        return ({"asset_id": 20, "profile_data": {
            "sequence_role": "opening tease", "scene_environment": "home interior",
            "emotional_tone": "playful", "visual_focus": "controlled reveal",
        }},)


def action_with_runtime(role="FREE_TEASER"):
    runtime = PhotoshootSessionRuntimeState(
        customer_commerce_profile_id=uuid4(), photoshoot_session_id="session-1",
        lifecycle_id=uuid4(), status=PhotoshootSessionRuntimeStatus.ACTIVE,
        strategy_version="v1", current_position=1, total_positions=2,
        current_asset_id=20, current_sales_role=role, next_asset_id=21,
        next_sales_role="FIRST_UNLOCK", owned_asset_ids=(),
        conversation_goal="Invite interest", psychological_objective="Create curiosity",
        customer_engagement_strategy="Warm and responsive", escalation_pacing="Gradual",
        session_completion_strategy="Complete the ordered experience",
    )
    return NextSalesAction(
        action=NextSalesActionType.CONTINUE_PHOTOSHOOT, customer_profile_id=uuid4(),
        buying_momentum=BuyingMomentumAssessment(BuyingMomentumState.MODERATE, 2, {}, "engaged"),
        reason="Execute runtime", evaluated_at=datetime.now(timezone.utc),
        current_photoshoot_id="session-1", selected_asset_id=20,
        metadata={"sessionRuntime": runtime.to_context()},
    )


def test_builder_projects_persisted_runtime_strategy_and_intelligence_without_deciding():
    builder = PhotoshootSessionConversationContextBuilder(
        strategies=Strategies(), photoshoots=Photoshoots(),
    )
    decision = SimpleNamespace(next_sales_action=action_with_runtime())

    context = builder.build(decision)

    assert context["currentSession"] == {
        "photoshootSessionId": "session-1", "title": "Indoor Sequence",
        "theme": "Intimate home setting", "storySummary": "A gradual indoor progression.",
        "currentPosition": 1, "totalPositions": 2,
    }
    assert context["currentStep"]["assetId"] == 20
    assert context["currentStep"]["salesRole"] == "FREE_TEASER"
    assert context["currentStep"]["shotSummary"]["scene_environment"] == "home interior"
    assert context["conversation"]["conversationGoal"] == "Invite interest"
    assert context["conversation"]["psychologicalObjective"] == "Create curiosity"
    assert context["nextStep"]["salesRole"] == "FIRST_UNLOCK"
    assert "Do not describe later shots" in context["boundaries"]["hidden_progression"]
    assert "SESSION CONVERSATION CONTEXT" in context["promptBlock"]


def test_role_objectives_change_framing_without_changing_runtime_selection():
    builder = PhotoshootSessionConversationContextBuilder(
        strategies=Strategies(), photoshoots=Photoshoots(),
    )
    original = action_with_runtime()
    runtime = dict(original.metadata["sessionRuntime"])
    runtime["currentSalesRole"] = "FIRST_UNLOCK"
    action = replace(original, metadata={"sessionRuntime": runtime})

    context = builder.build(SimpleNamespace(next_sales_action=action))

    assert context["currentStep"]["assetId"] == 20
    assert context["currentStep"]["salesRole"] == "FIRST_UNLOCK"
    assert "worth purchasing" in context["boundaries"]["message_objective"]


def test_missing_current_shot_intelligence_fails_closed(caplog):
    class MissingShot(Photoshoots):
        def latest_shot_intelligence(self, session_id):
            return ()

    builder = PhotoshootSessionConversationContextBuilder(
        strategies=Strategies(), photoshoots=MissingShot(),
    )
    with pytest.raises(ValueError, match="current-shot intelligence"):
        builder.build(SimpleNamespace(next_sales_action=action_with_runtime()))
    assert "session_current_shot_intelligence_missing" in caplog.text


def test_gateway_fails_closed_when_paid_session_context_cannot_be_built():
    class BrokenBuilder:
        def build(self, decision):
            raise RuntimeError("read unavailable")

    gateway = ConversationGateway.__new__(ConversationGateway)
    gateway._photoshoot_conversation_context_builder = BrokenBuilder()
    action = replace(
        action_with_runtime("FIRST_UNLOCK"),
        selected_offering_id=uuid4(), selected_asset_id=20,
    )
    decision = SimpleNamespace(
        decision=CustomerSalesDecisionType.PRESENT_OFFER,
        reason_code=CustomerSalesReasonCode.NO_ACTIVE_OFFER,
        buyer_stage=CustomerBuyerStage.PROSPECT,
        active_offer_status=None, active_offer_conversion_state="NONE",
        recommended_offering_id=action.selected_offering_id,
        recommended_offering_title="Current unlock",
        recommended_offering_price_minor=999,
        recommended_offering_currency="USD",
        recommended_offering_short_description="Verified chapter",
        recommended_photoshoot_experience=None,
        recommended_product_context={"sellingMode": "SESSION"},
        next_sales_action=action, bundle_sales_context=None,
    )
    runtime = gateway._commerce_runtime_injection(decision)
    assert runtime["authoritative_selection_missing"] is True
    assert runtime["commerce_execution_policy"] == "COMMERCE_DISABLED_FOR_TURN"
    assert runtime["commerce_decision"]["grounding_failure"] == (
        "SESSION_CURRENT_SHOT_INTELLIGENCE_UNAVAILABLE"
    )


def test_gpt_prompt_suppresses_session_selling_context_when_commerce_disabled():
    builder = PhotoshootSessionConversationContextBuilder(
        strategies=Strategies(), photoshoots=Photoshoots(),
    )
    context = builder.build(SimpleNamespace(next_sales_action=action_with_runtime()))
    captured = {}

    class Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(choices=(SimpleNamespace(
                message=SimpleNamespace(content="Natural response"),
            ),))

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    service = GPTService(api_key="test")
    service.openai_client = client
    service.grok_client = client
    service.generate_response(
        persona_name="Ava", mode="flirty", user_message="Show me",
        user_memory={
            "creator_profile": {"persona_name": "Ava", "system_prompt": "Stay natural."},
            "selected_provider": "OPENAI",
            "runtime_injection": {
                "commerce_execution_policy": "COMMERCE_DISABLED_FOR_TURN",
                "commerce_decision": {
                    "decision": "CONTINUE_CONVERSATION", "reason_code": "NO_ACTIVE_OFFER",
                    "buyer_stage": "PROSPECT", "current_offer_status": None,
                    "conversion_state": "NONE", "session_conversation": context,
                },
            },
        },
        send_offer=False, chat_history=[],
    )

    prompt = captured["messages"][0]["content"]
    assert "ORDINARY RELATIONSHIP CONVERSATION" in prompt
    assert "COMMERCE_DISABLED_FOR_TURN" in prompt
    assert "SESSION CONVERSATION CONTEXT" not in prompt
    assert '"assetId": 20' not in prompt
    assert '"conversationGoal": "Invite interest"' not in prompt
    assert "never choose a different Asset" not in prompt
