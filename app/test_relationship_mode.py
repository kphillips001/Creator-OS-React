from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.commerce_mode import CommerceMode
from app.services.commerce_mode_service import CommerceModeService
from app.services.relationship_mode_service import RelationshipModeService


def test_commerce_mode_defaults_live_and_persists_explicit_changes():
    config = {}
    saved = []
    service = CommerceModeService(
        config_loader=lambda: (config, None),
        config_saver=lambda value: saved.append(dict(value)),
    )
    assert service.get_mode() is CommerceMode.LIVE
    assert service.set_mode("relationship") is CommerceMode.RELATIONSHIP
    assert saved[-1]["commerce_mode"] == "RELATIONSHIP"
    with pytest.raises(ValueError, match="OFF, RELATIONSHIP, or LIVE"):
        service.set_mode("OBSERVE")


def test_prelaunch_responses_are_deterministic_and_truthful():
    service = RelationshipModeService(
        learning=SimpleNamespace(), customers=SimpleNamespace(),
    )
    first = service.response(customer_identifier="customer-1", correlation_id="turn-1")
    assert first == service.response(
        customer_identifier="customer-1", correlation_id="turn-1"
    )
    assert "http" not in first.lower()
    assert "$" not in first


def test_would_have_sold_updates_learning_and_prelaunch_customer_stage():
    calls = []
    profile = SimpleNamespace(
        customer_commerce_profile_id=uuid4(), purchase_count=0,
        display_name="Fan", handle="fan", telegram_identity_mapping_id=1,
        telegram_user_id=22,
    )
    learning = SimpleNamespace(
        record_observed_outcome=lambda **values: calls.append(values) or values
    )
    customers = SimpleNamespace(
        repository=SimpleNamespace(
            get_by_buyer_uuid=lambda **_: profile,
        ),
        update_profile=lambda *args, **values: calls.append(values),
    )
    decision = SimpleNamespace(
        creator_profile_id=7, fanvue_account_id=4,
        external_fanvue_buyer_uuid=uuid4(), telegram_user_id=22,
        recommended_offering_id=uuid4(),
        recommended_offering_title="Beach Collection",
        recommended_offering_price_minor=999,
        decision_metadata={"offeringSelector": {"recommendationTrace": []}},
    )

    RelationshipModeService(
        learning=learning, customers=customers,
    ).record_would_have_sold(decision, correlation_id="turn-1")

    assert calls[0]["outcome_type"] == "WOULD_HAVE_SOLD"
    assert "purchase_intent_id" not in calls[0]
    assert calls[0]["evidence"]["suppression_reason"] == "RELATIONSHIP_MODE"
    assert calls[1]["profile_state"].value == "PRE_LAUNCH_INTEREST"
