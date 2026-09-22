from datetime import datetime, timezone

import pytest

from app.services.pre_generation_commercial_decision_service import (
    PreGenerationCommercialDecisionService,
)


class Intents:
    def __init__(self, active=False): self.active=active; self.calls=0
    def get_active_for_buyer(self, **_): self.calls+=1; return object() if self.active else None


def project(text, *, active=False, classifier=None, historical=False):
    intents=Intents(active)
    result=PreGenerationCommercialDecisionService(intents=intents).project(
        customer_text=text,creator_profile_id=1,fanvue_account_id=2,
        telegram_user_id=3,classifier_result=classifier,
        historical_commercial_interest=historical)
    assert intents.calls == 1
    return result


@pytest.mark.parametrize("text,kind", [
    ("how much is that set?","PRICE_REQUEST"),
    ("what content do you have available?","OFFERING_AVAILABILITY_INQUIRY"),
    ("send me the link","SEND_OR_LINK_REQUEST"),
])
def test_deterministic_current_commercial_requests_are_eligible(text,kind):
    result=project(text)
    assert result.commercial_bypass_eligible and result.commercial_interest_type==kind


def test_purchase_acceptance_requires_active_referent():
    assert not project("deal").commercial_bypass_eligible
    result=project("deal",active=True)
    assert result.grounded_purchase_acceptance
    assert result.referent_present and result.commercial_bypass_eligible
    assert not project("yes",active=True).commercial_bypass_eligible


@pytest.mark.parametrize("text", [
    "you are so sexy", "I want you", "you're gorgeous", "maybe I will buy later",
    "not buying tonight",
])
def test_noncurrent_personal_and_negative_turns_are_not_eligible(text):
    assert not project(text,historical=True).commercial_bypass_eligible


def test_classifier_rejection_is_preserved_except_canonical_deterministic_evidence():
    rejected=project("hello",classifier={"buying_intent":False})
    assert rejected.classifier_rejected_buying_intent
    assert not rejected.commercial_bypass_eligible
    deterministic=project("how much is that set?",classifier={"buying_intent":False})
    assert deterministic.classifier_rejected_buying_intent
    assert deterministic.deterministic_commercial_evidence
    assert deterministic.commercial_bypass_eligible


def test_contract_contains_future_gate_inputs_without_budget_fields():
    values=project("hello").diagnostics()
    assert set(values)=={"fresh_direct_intent","current_commercial_interest",
        "commercial_interest_type","referent_present","grounded_purchase_acceptance",
        "temporal_deferred","no_buy_boundary","classifier_rejected_buying_intent",
        "deterministic_commercial_evidence","commercial_bypass_eligible","authority",
        "active_offer_nudge_candidate","active_offer_reservation_authorized",
        "active_offer_reservation_reason","mandatory_response_obligation"}
    assert not any("budget" in key or "tier" in key for key in values)


def test_declarative_auxiliary_verb_does_not_create_mandatory_obligation():
    result = project("My weekend plans are starting to come together")
    assert result.mandatory_response_obligation is False


@pytest.mark.parametrize("text", [
    "Are you having a good day",
    "What have you been doing this afternoon?",
    "I had a long day; how was yours?",
])
def test_genuine_direct_question_remains_a_mandatory_obligation(text):
    assert project(text).mandatory_response_obligation is True
