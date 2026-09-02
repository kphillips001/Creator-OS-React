from app.services.contextual_customer_tone_service import ContextualCustomerToneService
from app.services.customer_value_attention_service import CustomerValueAttentionService


def classify(message, *, history=(), relationship=None, commerce=None):
    return ContextualCustomerToneService().classify(
        message=message, recent_transcript=history,
        relationship_context=relationship, commerce_context=commerce,
    )


def test_hostile_stranger_disengagement_is_severe_and_noncommercial():
    result = classify("you're a disgusting person. leave me alone.")
    assert result["hostilityLevel"] in {"HIGH", "SEVERE"}
    assert result["explicitDisengagement"] is True
    assert result["buyingIntent"] is False


def test_profanity_or_provocation_alone_is_not_hostility_or_buying_intent():
    assert classify("fuck")["hostilityLevel"] == "NONE"
    result = classify("god you're such a wild one 😏")
    assert result["sexualOrProvocative"] is True
    assert result["buyingIntent"] is False


def test_explicit_sexual_receptiveness_is_not_buying_intent():
    result = classify("I'm feeling horny and turned on tonight.")
    assert result["sexualOrProvocative"] is True
    assert result["buyingIntent"] is False
    assert result["commercialCuriosity"] is False


def test_same_provocation_uses_relationship_context():
    phrase = "god you're such a wild one 😏"
    playful = classify(phrase, history=(
        {"role": "user", "content": "you're trouble 😏"},
        {"role": "assistant", "content": "maybe I am 😉"},
    ), relationship={"conversationDepth": 30, "mutualFlirtation": True})
    hostile = classify(phrase, history=(
        {"role": "user", "content": "stop wasting my time"},
        {"role": "user", "content": "your nonsense is disgusting"},
    ))
    assert playful["playfulOrBanter"] is True
    assert playful["hostilityLevel"] == "NONE"
    assert hostile["playfulOrBanter"] is False
    assert hostile["hostilityLevel"] in {"HIGH", "SEVERE"}


def test_crude_provocation_does_not_erase_explicit_buying_intent():
    result = classify("you're such a wild one 😏 how much for the private stuff?")
    assert result["sexualOrProvocative"] is True
    assert result["commercialCuriosity"] is True
    assert result["buyingIntent"] is True


def test_negative_active_offer_message_remains_price_objection():
    result = classify("$19? that's fucking ridiculous")
    assert result["negativeSentiment"] is True
    assert result["priceObjection"] is True
    assert result["commercialCuriosity"] is True


def test_hostile_rejection_and_buyer_boundary_remain_authoritative():
    result = classify("fuck off, I'm never buying anything",
                      commerce={"verifiedPurchaseCount": 12})
    assert result["explicitDisengagement"] is True
    assert result["hardBoundaryAuthoritative"] is True
    assert result["hostilityLevel"] in {"HIGH", "SEVERE"}


def test_hostile_nonbuyer_attention_is_minimal_but_crude_buyer_intent_is_protected():
    projection = CustomerValueAttentionService().project(
        commerce_memory={"schemaVersion": 1, "verifiedPurchaseCount": 0},
        behavior={"hostility_level": "HIGH", "repeated_hostility": True,
                  "explicit_disengagement": True},
    ).to_mapping()
    assert projection["attentionTier"] == "LOW"
    assert projection["effortMode"] == "MINIMAL"
    buyer = CustomerValueAttentionService().project(
        commerce_memory={"schemaVersion": 1, "verifiedPurchaseCount": 1},
        behavior={"hostility_level": "LOW", "direct_buying_intent": True},
    ).to_mapping()
    assert buyer["buyerStatus"] == "VERIFIED_BUYER"
    assert buyer["commercialMomentum"] == "HOT"


def test_canonical_decline_alignment_for_stop_wasting_my_time():
    result = classify("I'm not interested. Stop wasting my time.")
    assert result["explicitDisengagement"] is True
    assert result["hardBoundaryAuthoritative"] is True
    allocation = CustomerValueAttentionService().project(
        commerce_memory={"schemaVersion": 1, "verifiedPurchaseCount": 0},
        behavior={
            "hostility_level": result["hostilityLevel"],
            "explicit_disengagement": result["explicitDisengagement"],
        },
    ).to_mapping()
    assert allocation["attentionTier"] == "LOW"
    assert allocation["effortMode"] == "MINIMAL"


def test_repeated_abuse_is_contextual_not_vocabulary_triggered():
    isolated = classify("fuck")
    assert isolated["rageBaitPattern"] is False
    repeated = classify("answer me, your nonsense is disgusting", history=(
        {"role": "user", "content": "stop wasting my time"},
        {"role": "assistant", "content": "I'll step back."},
    ))
    assert repeated["repeatedHostility"] is True
    assert repeated["rageBaitPattern"] is True


def test_rage_bait_does_not_override_buyer_or_commercial_dimensions():
    buyer = classify("seriously, this is ridiculous", commerce={
        "verifiedPurchaseCount": 4,
    })
    assert buyer["rageBaitPattern"] is False
    commercial = classify(
        "you're such a wild one ðŸ˜ how much for the private stuff?",
        history=({"role": "user", "content": "your nonsense is disgusting"},),
    )
    assert commercial["buyingIntent"] is True
    assert commercial["rageBaitPattern"] is False


def test_progressive_disrespect_is_discovered_without_profanity():
    first = classify("not much. you always this chatty?")
    assert first["dismissiveOrContemptuous"] is True
    assert first["hostilityLevel"] == "LOW"
    assert first["repeatedHostility"] is False

    repeated = classify("honestly, you're trying a little too hard", history=(
        {"role": "user", "content": "not much. you always this chatty?"},
        {"role": "assistant", "content": "maybe I'm just in a good mood"},
    ))
    assert repeated["dismissiveOrContemptuous"] is True
    assert repeated["repeatedHostility"] is True
    assert repeated["hostilityLevel"] == "MODERATE"
    assert repeated["insultingOrDegrading"] is True
    assert repeated["explicitDisengagement"] is False


def test_attention_demand_after_dismissal_is_contextual_disrespect_not_commerce():
    result = classify("well? keep me entertained then", history=(
        {"role": "user", "content": "I didn't ask for your whole life story"},
        {"role": "user", "content": "you're still talking like I care"},
    ))
    assert result["dismissiveOrContemptuous"] is True
    assert result["repeatedHostility"] is True
    assert result["commercialCuriosity"] is False
    assert result["buyingIntent"] is False


def test_later_respectful_message_is_reassessed_instead_of_permanently_labeled():
    result = classify("sorry, that was rude. how are you doing?", history=(
        {"role": "user", "content": "you're still talking like I care"},
        {"role": "user", "content": "whatever, this is getting boring"},
    ))
    assert result["dismissiveOrContemptuous"] is False
    assert result["repeatedHostility"] is False
    assert result["hostilityLevel"] == "NONE"
    assert result["priorHostileTurnCount"] == 2


def test_hostility_reduces_attention_without_fabricating_commercial_time_waster():
    result = CustomerValueAttentionService().project(
        commerce_memory={"schemaVersion": 1, "verifiedPurchaseCount": 0},
        behavior={
            "inbound_message_count": 4,
            "hostility_level": "MODERATE",
            "repeated_hostility": True,
            "presented_opportunity_count": 0,
            "failed_nonconverted_opportunity_count": 0,
        },
    ).to_mapping()
    assert result["attentionTier"] == "LOW"
    assert result["effortMode"] == "COMPRESSED"
    assert result["conversationContinuationValue"] == "LOW"
    assert result["taperReason"] == "SUSTAINED_CONTEXTUAL_DISRESPECT"
    assert result["timeWasterRisk"] == "NONE"
    assert result["presentedOpportunityCount"] == 0
    assert result["failedNonconvertedOpportunityCount"] == 0
