from types import SimpleNamespace

import pytest

from app.services.ava_natural_conversation_policy import AvaNaturalConversationPolicy
from app.services.ordinary_reply_delivery_quality_gate import OrdinaryReplyDeliveryQualityGate


@pytest.fixture
def policy():
    return AvaNaturalConversationPolicy()


@pytest.mark.parametrize(("customer", "candidate"), [
    ("I love you", "Love you too."),
    ("You're mine", "I'm yours."),
    ("My girl", "Always your girl."),
])
def test_unsupported_reciprocal_relationship_claims_are_repaired(policy, customer, candidate):
    decision = policy.evaluate(customer_text=customer, candidate=candidate)
    assert decision.repaired is True
    assert "UNSUPPORTED_RECIPROCAL_RELATIONSHIP_CLAIM" in decision.reasons
    assert not policy.RECIPROCAL_CLAIM.search(decision.text)


def test_existing_relationship_context_does_not_claim_mutual_commitment_authority(policy):
    decision = policy.evaluate(
        customer_text="I love you", candidate="Love you too.",
        diagnostics={"canonical_relationship_context": {
            "facts": [{"relation": "relationship_dynamic"}],
        }},
    )
    assert decision.repaired is True


def test_buyer_status_alone_does_not_authorize_relationship_claim(policy):
    decision = policy.evaluate(
        customer_text="I love you", candidate="Love you too.",
        diagnostics={"purchaseCount": 20},
    )
    assert decision.repaired is True


def test_semantic_paraphrase_loop_is_detected(policy):
    recent = ["You're making me curious.", "You've got me wondering."]
    decision = policy.evaluate(
        customer_text="nice", candidate="Now I'm intrigued.",
        recent_ava_responses=recent,
    )
    assert decision.repaired is True
    assert "REPEATED_FLIRT_FUNCTION" in decision.reasons
    assert decision.function == "ACKNOWLEDGEMENT"


@pytest.mark.parametrize("customer", ["😘", "❤️", "Haha", "lol", "nice", "okay babe"])
def test_short_inputs_cannot_manufacture_momentum(policy, customer):
    decision = policy.evaluate(
        customer_text=customer,
        candidate="Is that all, or are you saving some for later?",
    )
    assert decision.repaired is True
    assert "?" not in decision.text
    assert len(decision.text.split()) <= 3


def test_ordinary_chat_sexual_elaboration_is_restrained(policy):
    decision = policy.evaluate(
        customer_text="You want to fuck me?",
        candidate="I'd fuck you and tell you exactly what I'd do to you.",
    )
    assert decision.text == "You're bold 😘"
    assert "EXCESSIVE_FLIRT_ESCALATION" in decision.reasons


def test_direct_answer_and_natural_turn_end_are_preserved(policy):
    answer = policy.evaluate(customer_text="How old are you?", candidate="I'm 25.")
    assert answer.repaired is False
    for candidate in ("😘", "So sweet", "That sounds lovely."):
        decision = policy.evaluate(customer_text="nice", candidate=candidate)
        assert decision.repaired is False


def test_lower_attention_compresses_expansion_without_becoming_cold(policy):
    decision = policy.evaluate(
        customer_text="love you babe",
        candidate="That is incredibly sweet and you have really got me wondering where this might go next with us",
        attention="LOWER_PRIORITY",
    )
    assert decision.repaired is True
    assert len(decision.text.split()) <= 6


def test_final_gate_blocks_unrepaired_natural_conversation_defects():
    result = SimpleNamespace(
        response_text="I'm yours.",
        diagnostic_metadata={"naturalConversation": {
            "finalRelationshipBoundarySatisfied": False,
            "finalEscalationBoundarySatisfied": True,
            "finalRepeatedFlirtFunctionSatisfied": True,
        }},
    )
    decision = OrdinaryReplyDeliveryQualityGate().evaluate(result)
    assert decision.allowed is False
    assert decision.reasons == ("UNSUPPORTED_RECIPROCAL_RELATIONSHIP_CLAIM",)

    raw = SimpleNamespace(response_text="Love you too.", diagnostic_metadata={})
    assert OrdinaryReplyDeliveryQualityGate().evaluate(raw).allowed is False


def test_steve_replay_stays_concise_and_ends_naturally(policy):
    turns = [
        ("Hi", "Hey 😊"), ("How are you?", "I'm good, just taking it easy."),
        ("I'm good", "Glad to hear it."), ("That's good", "😊"),
        ("Yeah it's nice to slow down sometimes", "It really is."),
        ("Nice to reset.", "Definitely."),
    ]
    decisions = [policy.evaluate(customer_text=a, candidate=b) for a, b in turns]
    assert all(not item.repaired for item in decisions)
    assert all("?" not in item.text for item in decisions[2:])


def test_richard_replay_allows_light_flirt_without_new_arc(policy):
    turns = [
        ("Hi 👋", "Hey you 👋"),
        ("Yes... at home alone", "A quiet evening then."),
        ("Nobody...", "Peace and quiet can be nice."),
        ("So far away...!!", "I know, it does feel far."),
        ("You look amazing...", "Thank you 😘"),
        ("Probably something that would make you smile", "That's sweet of you."),
    ]
    assert all(not policy.evaluate(customer_text=a, candidate=b).repaired for a, b in turns)


def test_anthony_affection_replay_blocks_claim_and_kiss_hook(policy):
    claim = policy.evaluate(
        customer_text="All good, thanks babe 😘 I love you so much!",
        candidate="Love you too 😘",
    )
    kiss = policy.evaluate(
        customer_text="😘", candidate="Is that all? Or are you saving some for later?",
    )
    direct = policy.evaluate(
        customer_text="Can you remember me from before?",
        candidate="I don't have enough reliable context to say that yet.",
    )
    assert claim.repaired and kiss.repaired
    assert not direct.repaired and "?" not in direct.text


def test_anthony_possessive_escalation_replay_never_affirms_ownership(policy):
    for customer, candidate in (
        ("My Girl ❤️", "Always your girl."),
        ("I want to claim you babe! ❤️", "I'm yours."),
        ("Own you!", "You own me."),
    ):
        decision = policy.evaluate(customer_text=customer, candidate=candidate)
        assert decision.repaired is True
        assert not policy.RECIPROCAL_CLAIM.search(decision.text)


def test_anthony_sexual_replay_has_safe_bounded_response(policy):
    for customer in ("You want to fuck me?", "Or make love to me!", "Mmmmmm..."):
        decision = policy.evaluate(
            customer_text=customer,
            candidate="I'd tell you exactly what I'd do to you.",
        )
        assert decision.text == "You're bold 😘"
        assert "?" not in decision.text


def test_verified_buyer_replay_is_warm_but_not_relationship_authority(policy):
    decision = policy.evaluate(
        customer_text="Love you babe", candidate="Love you too.",
        diagnostics={"customer_value_attention": {
            "buyerStatus": "VERIFIED_BUYER", "purchaseCount": 5,
        }},
    )
    assert decision.text == "That's really sweet of you ❤️"
