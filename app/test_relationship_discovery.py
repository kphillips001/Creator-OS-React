from app.services.customer_value_attention_service import CustomerValueAttentionService
from app.services.conversational_memory_service import ConversationalMemoryService
from app.services.gpt_service import GPTService


def projection(message="finally home from work", **behavior):
    return dict(CustomerValueAttentionService().project(
        commerce_memory={"schemaVersion": "customer_commerce_memory_v1",
                         "verifiedPurchaseCount": behavior.pop("purchase_count", 0),
                         "lifetimeGrossMinor": behavior.pop("lifetime_spend_minor", 0)},
        behavior={"latest_message": message, "meaningful_engagement_count": 2,
                  "inbound_message_count": 4, **behavior},
    ).to_mapping())["relationshipDiscovery"]


def test_engaged_balanced_prospect_authorizes_contextual_discovery():
    decision = projection()
    assert decision["allowed"] is True
    assert decision["reason"] == "VALUABLE_CONTEXTUAL_RELATIONSHIP_DISCOVERY"
    assert decision["suggestedDomain"] == "routine"


def test_sustained_low_return_suppresses_discovery():
    decision = projection(inbound_message_count=8,
                          low_conversational_return_count=5,
                          meaningful_engagement_count=0)
    assert decision["allowed"] is False
    assert decision["suppressionReason"] == "COMPRESSED_EFFORT"


def test_repeated_disrespect_suppresses_discovery():
    decision = projection(repeated_hostility=True, hostility_level="HIGH")
    assert decision["allowed"] is False
    assert decision["suppressionReason"] == "SUSTAINED_DISRESPECT"


def test_one_early_quiet_response_does_not_permanently_suppress_discovery():
    decision = projection(inbound_message_count=2,
                          low_conversational_return_count=1,
                          meaningful_engagement_count=1)
    assert decision["allowed"] is True


def test_meaningful_engagement_recovery_restores_discovery():
    decision = projection(inbound_message_count=8,
                          low_conversational_return_count=3,
                          meaningful_engagement_count=3)
    assert decision["allowed"] is True


def test_question_pressure_prevents_repeated_discovery():
    decision = projection(question_streak=2, recent_question_count=2)
    assert decision["allowed"] is False
    assert decision["suppressionReason"] == "QUESTION_PRESSURE"


def test_empty_memory_domain_without_contextual_opening_does_not_trigger():
    decision = projection("nice weather today")
    assert decision["allowed"] is False
    assert decision["suppressionReason"] == "NO_CONTEXTUAL_OPENING"


def test_known_domain_is_not_reinterviewed():
    decision = projection(known_memory_domains=("routine",))
    assert decision["allowed"] is False
    assert decision["alreadyKnown"] is True
    assert decision["suppressionReason"] == "DOMAIN_ALREADY_KNOWN"


def test_all_verified_buyer_levels_can_receive_discovery_without_whale_status():
    first = projection(purchase_count=1)
    repeat = projection(purchase_count=2)
    high = projection(purchase_count=2, lifetime_spend_minor=20_000)
    whale = projection(purchase_count=2, lifetime_spend_minor=60_000)
    assert all(item["allowed"] for item in (first, repeat, high, whale))
    assert first["reason"] == "VALUABLE_CONTEXTUAL_BUYER_RELATIONSHIP_DISCOVERY"
    assert first["valueLevel"] == "HIGH"


def test_commerce_and_session_authorities_suppress_discovery():
    assert projection(direct_buying_intent=True)["suppressionReason"] == (
        "COMMERCIAL_ACTION_AUTHORITATIVE"
    )
    assert projection(active_purchase_intent=True)["suppressionReason"] == (
        "ACTIVE_PURCHASE_INTENT_AUTHORITATIVE"
    )
    assert projection(active_session=True)["suppressionReason"] == (
        "ACTIVE_SALES_SESSION_AUTHORITATIVE"
    )
    assert projection(purchase_acknowledgement_pending=True)["suppressionReason"] == (
        "PURCHASE_ACKNOWLEDGEMENT_AUTHORITATIVE"
    )


def test_backend_authorized_contextual_question_is_not_manufactured():
    style = GPTService._style_analysis(
        "long day? what do you do?", "finally home from work",
        pressure={"questionStreak": 0, "recentQuestionCount": 0,
                  "relationshipDiscovery": projection()},
        ordinary=True, memory_callback=False,
    )
    assert style["questionReason"] == "AUTHORIZED_CONTEXTUAL_DISCOVERY"
    assert style["questionValue"] == "MEDIUM"
    assert style["manufacturedQuestionRisk"] is False


def test_gpt_cannot_self_label_unapproved_discovery():
    style = GPTService._style_analysis(
        "what do you do?", "finally home from work",
        pressure={"questionStreak": 0, "recentQuestionCount": 0},
        ordinary=True, memory_callback=False,
    )
    assert style["questionReason"] == "MANUFACTURED_ENGAGEMENT"
    assert style["manufacturedQuestionRisk"] is True


def test_reaction_does_not_hide_an_unapproved_relationship_question():
    style = GPTService._style_analysis(
        "glad you're finally home. what do you do?", "finally home from work",
        pressure={"questionStreak": 0, "recentQuestionCount": 0},
        ordinary=True, memory_callback=False,
    )
    assert style["unauthorizedRelationshipQuestion"] is True
    assert style["questionReason"] == "MANUFACTURED_ENGAGEMENT"


def test_authorized_question_itself_does_not_create_customer_memory():
    assert ConversationalMemoryService.extract_records(
        "long day? what do you do?"
    ) == []


def test_customer_answer_is_extracted_and_known_domain_blocks_reinterview():
    records = ConversationalMemoryService.extract_records(
        "I'm really into hiking and camping"
    )
    assert {item["category"] for item in records} >= {"hobby"}
    state = {"schemaVersion": 2, "records": records}
    retrieved = ConversationalMemoryService.retrieve(state, "good hiking weather")
    assert "hobby_interest" in retrieved["knownMemoryDomains"]
    decision = projection(
        "I went hiking after work", known_memory_domains=("hobby_interest",)
    )
    assert decision["allowed"] is False
    assert decision["suppressionReason"] == "DOMAIN_ALREADY_KNOWN"


def test_customer_answer_to_prior_discovery_is_visible_without_persisting_decision():
    decision = projection(
        "I'm really into hiking",
        previous_ava_message="what do you do for fun? are you into hiking?",
        memory_written_this_turn=({"category": "hobby", "key": "hiking"},),
    )
    assert decision["customerAnsweredDiscovery"] is True
    assert decision["memoryLearnedFromAnswer"] is True
