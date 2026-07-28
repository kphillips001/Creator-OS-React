import pytest

from app.services.gpt_service import GPTService


class FakeMessage:
    content = "A natural response."


class FakeChoice:
    message = FakeMessage()


class FakeCompletion:
    choices = [FakeChoice()]


class FakeCompletions:
    def __init__(self, capture):
        self.capture = capture

    def create(self, **kwargs):
        self.capture["messages"] = kwargs["messages"]
        return FakeCompletion()


class FakeChat:
    def __init__(self, capture):
        self.completions = FakeCompletions(capture)


class FakeClient:
    def __init__(self, capture):
        self.chat = FakeChat(capture)


def render_prompt(*, decision, policy, selected_offering=None):
    capture = {}
    service = GPTService(api_key="test-key")
    client = FakeClient(capture)
    service.openai_client = client
    service.grok_client = client
    commerce = {
        "decision": decision,
        "reason_code": "TEST_REASON",
        "buyer_stage": "FIRST_TIME_BUYER",
        "current_offer_status": "PRESENTED",
        "conversion_state": "OFFER_PRESENTED",
        "commerce_execution_policy": policy,
    }
    if selected_offering is not None:
        commerce["selected_offering"] = selected_offering
    service.generate_response(
        persona_name="Ava",
        mode="flirty",
        user_message="What do you have?",
        user_memory={
            "creator_profile": {
                "persona_name": "Ava",
                "system_prompt": "Stay natural.",
            },
            "selected_provider": "OPENAI",
            "behavior_context": {
                "response_strategy": "close",
                "tone_mode": "warm",
                "pressure_level": "high",
                "should_handle_objection": True,
            },
            "runtime_injection": {
                "commerce_decision": commerce,
                "commerce_execution_policy": policy,
            },
            "buyer_tier": "legacy_whale",
            "last_offer_type": "legacy_vip",
            "offers_shown_count": 99,
            "recent_owned_content_tags": ["legacy-owned-item"],
            "intent_score": 88,
            "message_count": 12,
            "subscriber_engagement_mode": "flirty",
            "gpt_classifier_result": {
                "buying_intent": True,
                "close_ready": True,
                "recommended_action": "close",
            },
        },
        send_offer=True,
        offer={
            "offer_type": "legacy_vip",
            "price": 4200,
            "description": "Legacy conflicting offer",
            "content": {
                "tag": "legacy-item",
                "caption": "Legacy caption",
                "fanvue_link": "https://legacy.invalid/item",
            },
        },
        offer_copy="Legacy offer copy",
        chat_history=[],
    )
    return capture["messages"][0]["content"]


def test_present_offer_has_one_authoritative_commerce_block_and_one_offering():
    prompt = render_prompt(
        decision="PRESENT_OFFER",
        policy="COMMERCE_PRESENTATION_ALLOWED",
        selected_offering={
            "title": "Private Beach Release",
            "short_description": "A warm sunset portrait.",
            "price_minor": 999,
            "currency": "USD",
        },
    )

    assert prompt.count("AUTHORITATIVE COMMERCE") == 1
    assert prompt.count("Private Beach Release") == 1
    assert prompt.count("USD 9.99") == 1
    assert "Legacy conflicting offer" not in prompt
    assert "https://legacy.invalid/item" not in prompt
    assert "Legacy offer copy" not in prompt
    assert "You are in SELL MODE." not in prompt
    assert "You are now in CLOSE MODE." not in prompt
    assert "CONTENT OWNERSHIP CONTEXT" not in prompt
    assert "Buyer tier:" not in prompt
    assert "Last offer type:" not in prompt
    assert "Offers shown so far:" not in prompt
    assert "Recommended action:" not in prompt
    assert "Tone Mode: warm" in prompt
    assert "Intent score: 88" in prompt


@pytest.mark.parametrize(
    ("decision", "policy"),
    (
        ("WAIT", "COMMERCE_DISABLED_FOR_TURN"),
        ("NO_SALE", "COMMERCE_DISABLED_FOR_TURN"),
        ("CONTINUE_CONVERSATION", "COMMERCE_DISABLED_FOR_TURN"),
        ("PAYMENT_PENDING", "COMMERCE_PAYMENT_PENDING"),
        ("MANUAL_REVIEW", "COMMERCE_MANUAL_REVIEW"),
    ),
)
def test_non_presentation_modes_have_no_sales_or_purchase_claims(
    decision, policy,
):
    prompt = render_prompt(decision=decision, policy=policy)

    assert prompt.count("AUTHORITATIVE COMMERCE") == 1
    assert "No paid offer is authorized." in prompt
    assert "You are in SELL MODE." not in prompt
    assert "You are now in CLOSE MODE." not in prompt
    assert "Legacy conflicting offer" not in prompt
    assert "https://legacy.invalid/item" not in prompt


def test_nudge_references_only_the_active_selected_offering():
    prompt = render_prompt(
        decision="NUDGE_ACTIVE_OFFER",
        policy="COMMERCE_NUDGE_ALLOWED",
        selected_offering={
            "title": "Already Presented Release",
            "short_description": "The active offer.",
            "price_minor": 1299,
            "currency": "USD",
        },
    )

    assert prompt.count("Already Presented Release") == 1
    assert "existing active Purchase Intent" in prompt
    assert "Do not claim purchase." in prompt
    assert "Legacy conflicting offer" not in prompt


def test_purchase_acknowledgement_forbids_another_offer():
    prompt = render_prompt(
        decision="CONGRATULATE_PURCHASE",
        policy="COMMERCE_ACKNOWLEDGEMENT_ALLOWED",
    )

    assert prompt.count("AUTHORITATIVE COMMERCE") == 1
    assert "Acknowledge the verified purchase warmly." in prompt
    assert "Do not present another paid offer, upsell, or cross-sell." in prompt
    assert "Legacy conflicting offer" not in prompt
