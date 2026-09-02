from app.services.active_buying_window_service import ActiveBuyingWindowService


def project(**changes):
    values = {
        "recent_verified_purchase": True,
        "fresh_direct_intent": False,
        "explicit_continuation": False,
        "active_purchase_intent": False,
        "active_offer_context": False,
        "acknowledgement_pending": False,
        "declined": False,
        "safety_allowed": True,
        "active_session": False,
        "cooldown_active": True,
        "receptiveness": {"state": "HOT"},
        "deferred_continuation": {},
    }
    values.update(changes)
    return ActiveBuyingWindowService.project(**values)


def test_explicit_customer_continuation_opens_window_during_cooldown():
    result = project(fresh_direct_intent=True, explicit_continuation=True)
    assert result["active"] is True
    assert result["anotherSaleAppropriateNow"] is True
    assert result["source"] == "PRODUCTION_CUSTOMER_STATE"
    assert result["currentCommercialMomentum"] == (
        "EXPLICIT_CUSTOMER_CONTINUATION"
    )
    assert result["purchaseCooldownOverridden"] is True
    assert result["scenarioInfluencedCommercialAuthority"] is False


def test_non_explicit_post_purchase_praise_remains_suppressed():
    result = project()
    assert result["active"] is False
    assert result["reason"] == "PURCHASE_COOLDOWN_WITHOUT_DIRECT_CONTINUATION"
    assert result["currentCommercialMomentum"] == "INACTIVE"
    assert result["momentumDecayReason"] == (
        "PURCHASE_COOLDOWN_WITHOUT_DIRECT_CONTINUATION"
    )


def test_acknowledgement_preserves_but_temporarily_blocks_continuation():
    result = project(
        fresh_direct_intent=True, explicit_continuation=True,
        acknowledgement_pending=True,
    )
    assert result["active"] is True
    assert result["anotherSaleAppropriateNow"] is False
    assert result["reason"] == "ACKNOWLEDGEMENT_FIRST_CONTINUATION_DEFERRED"


def test_rejection_and_session_authority_close_ordinary_window():
    assert project(fresh_direct_intent=True, declined=True)["active"] is False
    result = project(fresh_direct_intent=True, active_session=True)
    assert result["active"] is False
    assert result["reason"] == "ACTIVE_SESSION_PRECEDENCE"


def test_customer_value_or_purchase_history_alone_never_opens_window():
    for receptiveness in (
        {"state": "HOT", "valueTier": "WHALE"},
        {"state": "HOT", "sexualReceptiveness": True},
    ):
        result = project(receptiveness=receptiveness)
        assert result["active"] is False
        assert result["anotherSaleAppropriateNow"] is False


def test_semantic_continuation_equivalents_open_the_same_global_window():
    from app.services.commercial_receptiveness_service import (
        CommercialReceptivenessService,
    )

    for message in (
        "what else have you got", "show me more", "keep going",
        "don't stop", "what's next", "I want more",
        "that one was good, give me something hotter",
    ):
        continuation = (
            CommercialReceptivenessService.explicit_continuation_detected(
                message
            )
        )
        assert continuation is True, message
        assert project(explicit_continuation=continuation)["active"] is True


def test_fresh_prospect_curiosity_cannot_create_a_buying_window():
    result = project(
        recent_verified_purchase=False,
        cooldown_active=False,
        explicit_continuation=True,
        receptiveness={
            "state": "WARM",
            "commercialInterestType": "COMMERCIAL_CURIOSITY",
            "freshDirectIntentDetected": False,
        },
    )

    assert result["active"] is False
    assert result["reason"] == "CONTINUATION_WITHOUT_COMMERCIAL_CONTEXT"
    assert result["customerLedContinuation"] is False
    assert result["continuationCommercialContextPresent"] is False
    assert result["activeBuyingWindowAuthoritySatisfied"] is False
    assert result["anotherSaleAppropriateNow"] is False


def test_broad_conversational_continuations_cannot_open_fresh_buyer_window():
    from app.services.commercial_receptiveness_service import (
        CommercialReceptivenessService,
    )

    for message in (
        "tell me more about yourself",
        "I want to hear more about your dog",
        "say more about that",
        "I want to know more",
        "tell me a little more",
    ):
        continuation = (
            CommercialReceptivenessService.explicit_continuation_detected(
                message
            )
        )
        result = project(
            recent_verified_purchase=False,
            cooldown_active=False,
            explicit_continuation=continuation,
            receptiveness={
                "state": "WARM",
                "commercialInterestType": "NONE",
                "freshDirectIntentDetected": False,
            },
        )
        assert result["active"] is False, message
        assert result["activeBuyingWindowAuthoritySatisfied"] is False, message


def test_fresh_prospect_genuine_direct_intent_still_opens_window():
    result = project(
        recent_verified_purchase=False,
        cooldown_active=False,
        fresh_direct_intent=True,
        explicit_continuation=False,
    )

    assert result["active"] is True
    assert result["reason"] == "CURRENT_CUSTOMER_DIRECT_INTENT"
    assert result["activeBuyingWindowAuthoritySatisfied"] is True


def test_persisted_active_offer_allows_customer_led_continuation():
    result = project(
        recent_verified_purchase=False,
        cooldown_active=False,
        explicit_continuation=True,
        active_offer_context=True,
    )

    assert result["active"] is True
    assert result["customerLedContinuation"] is True
    assert result["continuationCommercialContextPresent"] is True


def test_deferred_acknowledgement_continuation_keeps_commercial_context():
    result = project(
        recent_verified_purchase=False,
        cooldown_active=False,
        deferred_continuation={"state": "READY"},
    )

    assert result["active"] is True
    assert result["continuationCommercialContextPresent"] is True
    assert result["activeBuyingWindowAuthoritySatisfied"] is True
