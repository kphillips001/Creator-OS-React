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


def render_prompt(*, decision, policy, selected_offering=None, extra_context=None):
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
    commerce.update(extra_context or {})
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
            "customer_safe_description": "A warm sunset portrait.",
            "price_minor": 999,
            "currency": "USD",
        },
    )

    assert prompt.count("AUTHORITATIVE COMMERCE") == 1
    assert "Private Beach Release" not in prompt
    assert prompt.count("A warm sunset portrait.") == 1
    assert "USD 9.99" not in prompt
    assert "Price: withheld from conversational generation" in prompt
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


def test_unmapped_present_offer_contract_is_complete_and_price_neutral():
    prompt = render_prompt(
        decision="PRESENT_OFFER",
        policy="COMMERCE_PRESENTATION_ALLOWED",
        selected_offering={
            "title": "Controlled Single",
            "short_description": "A private image.",
        },
        extra_context={
            "identity_resolved": False,
            "paid_presentation_contract": {
                "price_neutral": True,
                "presentation_complete": True,
                "customer_facing_price_status": "ESTABLISHED_BY_UNLOCK_FLOW",
            },
        },
    )

    assert "Paid-offer presentation is authorized and must be completed now" in prompt
    assert "suitable to accompany the Creator-OS Unlock button immediately" in prompt
    assert "do not produce another teaser" in prompt
    assert "Do not quote the configured base price" in prompt
    assert "Customer-facing price: shown only by the structured paid presentation" in prompt
    assert "USD 3.00" not in prompt


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
            "customer_safe_description": "The active offer.",
            "price_minor": 1299,
            "currency": "USD",
        },
    )

    assert "Already Presented Release" not in prompt
    assert prompt.count("The active offer.") == 1
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


def test_single_image_prompt_receives_only_compact_verified_intelligence():
    prompt = render_prompt(
        decision="PRESENT_OFFER",
        policy="COMMERCE_PRESENTATION_ALLOWED",
        selected_offering={
            "title": "Soft Morning Intimacy", "short_description": "Warm light.",
            "price_minor": 999, "currency": "USD",
        },
        extra_context={"single_image_conversation": {
            "schemaVersion": "single_image_chat_conversation_v1",
            "assetId": 195,
            "canonicalIntelligence": {
                "contentSummary": "A verified morning portrait.",
                "sceneEnvironment": "sunlit bedroom",
                "explicitness": "EXPLICIT",
                "moodTone": "intimate",
            },
            "groundingRules": ["Do not invent absent visual details."],
        }},
    )
    assert "SINGLE IMAGE CHAT PRODUCT CONTEXT" in prompt
    assert "A verified morning portrait." in prompt
    assert "sunlit bedroom" in prompt
    assert "EXPLICIT" in prompt
    assert "never invent absent visual details" in prompt


def test_missing_asset_intelligence_forbids_invented_visual_specifics():
    prompt = render_prompt(
        decision="TEASE",
        policy="COMMERCE_TEASE_ONLY",
        extra_context={
            "selected_opportunity": {
                "title": "Generic Private Release",
                "short_description": "A private image.",
                "offering_type": "SINGLE_IMAGE",
            },
        },
    )
    assert "No verified Asset Intelligence is available" in prompt
    assert "do not invent wardrobe, pose, setting, expression, mood" in prompt


def test_generation_prompt_uses_customer_safe_copy_not_internal_title():
    prompt = render_prompt(
        decision="PRESENT_OFFER",
        policy="COMMERCE_PRESENTATION_ALLOWED",
        selected_offering={
            "title": "Certification available 3",
            "short_description": "Test-only eligible content",
            "customer_safe_description": (
                "a playful private photo with a confident, teasing mood"
            ),
        },
    )
    assert "Certification available 3" not in prompt
    assert "Test-only eligible content" not in prompt
    assert "a playful private photo with a confident, teasing mood" in prompt


def test_bundle_prompt_block_reaches_gpt_once_with_complete_set_contract():
    block = (
        "BUNDLE PHOTOSHOOT CONVERSATION CONTEXT\n"
        "paidMemberCount: 3\nTheme: dusky kitchen\nStory: tease to reveal\n"
        "Sales Brain brief: premium complete progression\n"
        "The entire Photoshoot is one purchase. Never offer individual Bundle members."
    )
    prompt = render_prompt(
        decision="PRESENT_OFFER",
        policy="COMMERCE_PRESENTATION_ALLOWED",
        selected_offering={
            "title": "Dusky Kitchen Wet Tank Reveal",
            "short_description": "A complete set.",
            "price_minor": 1899, "currency": "USD",
        },
        extra_context={"bundle_conversation": {"promptBlock": block}},
    )
    assert prompt.count("BUNDLE PHOTOSHOOT CONVERSATION CONTEXT") == 1
    assert "paidMemberCount: 3" in prompt
    assert "dusky kitchen" in prompt
    assert "Never offer individual Bundle members" in prompt
    assert "Legacy conflicting offer" not in prompt
