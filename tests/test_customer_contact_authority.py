from datetime import datetime, timezone

import pytest

from app.models.customer_contact import ContactPolicyResult as Result, ContactPurpose as Purpose
from app.services.customer_contact_authority_service import CustomerContactAuthorityService


NOW = datetime(2026, 8, 30, tzinfo=timezone.utc)


def decide(purpose, **evidence):
    return CustomerContactAuthorityService().decide(
        purpose=purpose, evidence=evidence, now=NOW)


def test_legitimate_inbound_ignores_optional_proactive_cooldown():
    value = decide(Purpose.REACTIVE_CONVERSATION, cooldown_active=True,
                   recent_ppv=True, active_conversation=True)
    assert value.result is Result.ALLOW


@pytest.mark.parametrize("purpose", [Purpose.OUTREACH, Purpose.RE_ENGAGEMENT,
                                      Purpose.FREE_ENGAGEMENT, Purpose.MASS_PPV])
def test_backoff_suppresses_optional_proactive_contact(purpose):
    assert decide(purpose, back_off=True).result is Result.SUPPRESS


def test_minimal_attention_suppresses_optional_high_investment_contact():
    value = decide(Purpose.FREE_ENGAGEMENT, attention_mode="MINIMAL")
    assert value.result is Result.SUPPRESS


def test_active_offer_suppresses_competing_promotion():
    assert decide(Purpose.MASS_PPV, active_offer=True).reason == "ACTIVE_OFFER_SUPPRESSES_COMPETING_PROMOTION"


def test_active_offer_followup_allowed_only_when_due():
    assert decide(Purpose.ACTIVE_OFFER_FOLLOWUP, active_offer=True, followup_due=True).result is Result.ALLOW
    assert decide(Purpose.ACTIVE_OFFER_FOLLOWUP, active_offer=True, followup_due=False).result is Result.DEFER


def test_active_session_suppresses_outreach_but_allows_continuation():
    assert decide(Purpose.OUTREACH, active_session=True).result is Result.SUPPRESS
    assert decide(Purpose.SESSION_CONTINUATION, active_session=True).result is Result.ALLOW


def test_recent_purchase_protects_from_promotion_but_not_acknowledgement():
    assert decide(Purpose.MASS_PPV, recent_purchase=True).result is Result.DEFER
    ack = decide(Purpose.PURCHASE_ACKNOWLEDGEMENT, recent_purchase=True)
    assert ack.result is Result.ALLOW and ack.priority > decide(Purpose.MASS_PPV).priority


def test_free_teaser_and_outreach_do_not_collide_with_recent_contact():
    assert decide(Purpose.FREE_ENGAGEMENT, recent_ppv=True).result is Result.DEFER
    assert decide(Purpose.OUTREACH, recent_free_teaser=True).result is Result.DEFER


def test_generic_reengagement_and_mass_ppv_defer_to_active_conversation():
    assert decide(Purpose.RE_ENGAGEMENT, active_conversation=True).result is Result.DEFER
    assert decide(Purpose.MASS_PPV, active_conversation=True).result is Result.DEFER


def test_value_tier_never_bypasses_limits_and_dormant_buyer_can_reengage():
    whale = decide(Purpose.OUTREACH, buyer_value_tier="WHALE", cooldown_active=True)
    dormant = decide(Purpose.RE_ENGAGEMENT, buyer_value_tier="DORMANT_BUYER")
    assert whale.result is Result.DEFER
    assert dormant.result is Result.ALLOW


def test_unsent_does_not_count_as_contact_but_uncertain_defers_competitors():
    assert decide(Purpose.OUTREACH, generated_unsent=True).result is Result.ALLOW
    uncertain = decide(Purpose.OUTREACH, uncertain_delivery=True)
    assert uncertain.result is Result.DEFER
    assert uncertain.competing_interaction == "SEND_UNCERTAIN"


def test_confirmed_contact_only_applies_when_caller_reports_relevant_cooldown():
    clear = decide(Purpose.OUTREACH, last_confirmed_contact_at=NOW)
    cooled = decide(Purpose.OUTREACH, last_confirmed_contact_at=NOW,
                    cooldown_active=True)
    assert clear.result is Result.ALLOW
    assert cooled.result is Result.DEFER


def test_projection_is_structured_and_names_authority():
    projection = decide(Purpose.REACTIVE_COMMERCIAL).to_mapping()
    assert projection["authority"] == "CustomerContactAuthorityService"
    assert projection["purpose"] == "REACTIVE_COMMERCIAL"
    assert projection["reactive"] is True
