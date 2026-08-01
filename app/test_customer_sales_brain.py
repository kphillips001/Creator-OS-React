from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import customer_sales_brain as api
from app.models.customer_sales_decision import (
    CustomerBuyerStage,
    CustomerSalesDecisionType,
    CustomerSalesReasonCode,
)
from app.models.commercial_offering_selection import (
    OfferingSelectionReason,
    SelectedOfferingResult,
    immutable_selector_metadata,
)
from app.models.commercial_intelligence import (
    CommercialIntelligenceContext,
    OwnershipCoverage,
)
from app.models.purchase_intent import (
    AttributionResult,
    PurchaseIntentStatus,
)
from app.services.customer_sales_brain_config import CustomerSalesBrainConfig
from app.services.customer_sales_brain_service import CustomerSalesBrainService


def test_historical_session_resolution_matches_customer_and_photoshoot():
    unrelated_latest = SimpleNamespace(
        fanvue_account_id=2, fanvue_user_id="buyer-1",
        commercial_foundation_reference="photoshoot-new",
    )
    matching_older = SimpleNamespace(
        fanvue_account_id=2, fanvue_user_id="buyer-1",
        commercial_foundation_reference="photoshoot-requested",
    )
    other_customer = SimpleNamespace(
        fanvue_account_id=2, fanvue_user_id="buyer-2",
        commercial_foundation_reference="photoshoot-requested",
    )

    result = CustomerSalesBrainService._resolve_historical_session(
        (unrelated_latest, other_customer, matching_older),
        fanvue_account_id=2,
        fanvue_user_id="buyer-1",
        intended_photoshoot_reference="photoshoot-requested",
    )

    assert result is matching_older


NOW = datetime(2026, 7, 26, tzinfo=timezone.utc)
BUYER = UUID("9d7ce679-ccef-4bb9-9b01-7ee8b97516bc")


class Customers:
    def __init__(self, profile):
        self.profile = profile

    def get_by_buyer_uuid(self, **kwargs):
        return self.profile

    def list_profiles(self, **kwargs):
        return ((self.profile,) if self.profile else ()), int(bool(self.profile)), 1


class Identities:
    def __init__(self, resolved=True):
        self.resolved = resolved

    def get_by_telegram_user_id(self, user):
        return SimpleNamespace(
            fanvue_account_id=7, external_fanvue_user_uuid=BUYER,
            telegram_user_id=user,
        ) if self.resolved else None


class Intents:
    def __init__(self, latest=None, active=None):
        self.latest, self.active = latest, active

    def get_latest_for_buyer(self, **kwargs):
        return self.latest

    def get_active_for_buyer(self, **kwargs):
        return self.active


class Signals:
    def __init__(self, signal):
        self.signal = signal

    def get_signal(self, **kwargs):
        return self.signal


class Selector:
    def __init__(self, offering=None):
        self.offering = offering
        self.calls = []

    def select(self, **kwargs):
        self.calls.append(kwargs)
        item = self.offering
        return SelectedOfferingResult(
            offering_id=item.offering_id if item else None,
            publication_id=item.publication_id if item else None,
            publication_provider="FANVUE" if item else None,
            delivery_url=item.delivery_url if item else None,
            offering_type="SINGLE_IMAGE" if item else None,
            primary_sales_channel="AI_CHAT" if item else None,
            selection_reason=(
                OfferingSelectionReason.MOST_RECENT
                if item else OfferingSelectionReason.NO_ELIGIBLE_OFFERING
            ),
            exclusion_reasons=(), evaluations=(),
            selector_metadata=immutable_selector_metadata({}),
            title=getattr(item, "title", None) if item else None,
            short_description=(
                getattr(item, "description", None) if item else None
            ),
            price_minor=getattr(item, "price_minor", None) if item else None,
            currency=getattr(item, "currency", None) if item else None,
        )


def profile(*, purchases=0, last_purchase=None, linked=True):
    return SimpleNamespace(
        creator_profile_id=2, fanvue_account_id=7,
        external_fanvue_user_uuid=BUYER,
        telegram_user_id=22 if linked else None,
        telegram_identity_mapping_id=11 if linked else None,
        purchase_count=purchases, lifetime_gross_minor=purchases * 999,
        last_purchase_at=last_purchase,
    )


def signal(*, reconciliation=None, attribution="PENDING", conversion="NO_ACTIVE_OFFER"):
    return SimpleNamespace(
        buyer_uuid=str(BUYER), telegram_user_id=22, identity_resolved=True,
        lifetime_spend_minor=999, purchase_count=1,
        last_purchase_at=NOW - timedelta(days=2),
        current_active_offer_id=None, current_offer_status=None,
        conversion_state=conversion, latest_transaction="order-1",
        attribution_state=attribution, reconciliation_state=reconciliation,
    )


def intent(*, status="PRESENTED", presented_at=None, attribution="PENDING"):
    return SimpleNamespace(
        purchase_intent_id=uuid4(), commercial_offering_id=uuid4(),
        status=PurchaseIntentStatus(status),
        attribution_result=AttributionResult(attribution),
        created_at=NOW - timedelta(hours=2),
        presented_at=presented_at or NOW - timedelta(hours=2),
    )


def offering():
    return SimpleNamespace(
        offering_id=uuid4(), publication_id=uuid4(),
        delivery_url="https://fanvue.com/media-link",
        title="Private Release", description="A private image.",
        price_minor=999, currency="USD",
    )


def brain(*, customer=None, identity=True, commerce_signal=None,
          latest=None, active=None, eligible=None):
    return CustomerSalesBrainService(
        customer_repository=Customers(customer),
        identity_repository=Identities(identity),
        intent_repository=Intents(latest, active),
        commerce_signal_service=Signals(commerce_signal),
        offering_selector_service=Selector(eligible),
        config=CustomerSalesBrainConfig(
            purchase_cooldown=timedelta(hours=24),
            offer_nudge_delay=timedelta(hours=24),
            offer_expiration=timedelta(hours=72),
        ),
        clock=lambda: NOW,
    )


def evaluate(service, context=None):
    return service.evaluate_for_telegram_user(
        creator_profile_id=2, telegram_user_id=22,
        conversation_context=context,
    )


def test_identity_unresolved_has_first_priority():
    result = evaluate(brain(identity=False))
    assert result.decision is CustomerSalesDecisionType.MANUAL_REVIEW
    assert result.reason_code is CustomerSalesReasonCode.IDENTITY_UNRESOLVED


def test_commercial_intelligence_diagnostics_preserve_boundary_contexts():
    result = evaluate(
        brain(customer=profile(), eligible=offering()),
        {
            "latest_message": "show me a beach photo",
            "requested_themes": ("beach",),
        },
    )
    diagnostics = result.decision_metadata["commercialIntelligence"]

    assert diagnostics["strategy"] == "LIBRARY_SELLING"
    assert "ownershipConsiderations" in diagnostics
    assert "salesSessionContext" in diagnostics
    assert diagnostics["customerRequestContext"]["requestedThemes"] == (
        "beach",
    )
    assert "diagnosticContext" in diagnostics
    assert result.decision_metadata["offeringSelector"] is not None
    assert result.decision.value == "PRESENT_OFFER"


def test_customer_sales_brain_returns_no_sale_for_ownership_insufficiency():
    service = brain(customer=profile(), eligible=offering())
    service.commercial_context = SimpleNamespace(assemble=lambda **_values:
        CommercialIntelligenceContext(
            creator_profile_id=2, fanvue_account_id=7,
            telegram_user_id=22,
            latest_message="show me a beach photo",
            ownership=OwnershipCoverage(incomplete=True),
        )
    )

    result = evaluate(service, {"latest_message": "show me a beach photo"})

    assert result.decision is CustomerSalesDecisionType.NO_SALE
    assert result.reason_code is CustomerSalesReasonCode.NO_SELLING_STRATEGY
    assert (
        result.decision_metadata["commercialIntelligence"]["reason"]
        == "INSUFFICIENT_OWNERSHIP_EVIDENCE"
    )


@pytest.mark.parametrize(
    ("commerce_signal", "latest", "expected", "reason"),
    [
        (
            signal(reconciliation="PENDING"), None,
            CustomerSalesDecisionType.PAYMENT_PENDING,
            CustomerSalesReasonCode.PAYMENT_RECONCILIATION_PENDING,
        ),
        (
            signal(attribution="UNKNOWN"), None,
            CustomerSalesDecisionType.MANUAL_REVIEW,
            CustomerSalesReasonCode.PAYMENT_ATTRIBUTION_UNKNOWN,
        ),
    ],
)
def test_payment_rules_precede_offer_rules(
    commerce_signal, latest, expected, reason,
):
    active = intent(presented_at=NOW - timedelta(days=2))
    result = evaluate(brain(
        customer=profile(), commerce_signal=commerce_signal,
        latest=latest or active, active=active, eligible=offering(),
    ))
    assert result.decision is expected
    assert result.reason_code is reason


def test_verified_purchase_acknowledgement_precedes_cooldown():
    purchased = intent(status="PURCHASED", attribution="ATTRIBUTED")
    result = evaluate(brain(
        customer=profile(
            purchases=1, last_purchase=NOW - timedelta(hours=1)
        ),
        commerce_signal=signal(attribution="ATTRIBUTED", conversion="PURCHASED"),
        latest=purchased,
    ), {"purchase_acknowledgement_pending": True})
    assert result.decision is CustomerSalesDecisionType.CONGRATULATE_PURCHASE
    assert result.congratulate_allowed is True


def test_recent_purchase_cooldown_blocks_sale():
    result = evaluate(brain(
        customer=profile(
            purchases=1, last_purchase=NOW - timedelta(hours=1)
        ),
        commerce_signal=signal(attribution="ATTRIBUTED"),
        eligible=offering(),
    ))
    assert result.decision is CustomerSalesDecisionType.CONTINUE_CONVERSATION
    assert result.reason_code is CustomerSalesReasonCode.RECENT_PURCHASE_COOLDOWN
    assert result.cooldown_until == NOW + timedelta(hours=23)


def test_active_offer_waits_then_becomes_nudge_eligible():
    waiting = intent(presented_at=NOW - timedelta(hours=2))
    wait = evaluate(brain(
        customer=profile(), commerce_signal=signal(),
        latest=waiting, active=waiting,
    ))
    assert wait.decision is CustomerSalesDecisionType.WAIT
    old = intent(presented_at=NOW - timedelta(hours=25))
    service = brain(
        customer=profile(), commerce_signal=signal(),
        latest=old, active=old,
        eligible=offering(),
    )
    nudge = evaluate(service)
    assert nudge.decision is CustomerSalesDecisionType.NUDGE_ACTIVE_OFFER
    assert nudge.nudge_allowed is True
    assert len(service.offering_selector.calls) == 1
    assert (
        service.offering_selector.calls[0]["active_purchase_intent"] is old
    )


def test_expired_offer_precedes_new_offer_selection():
    expired = intent(status="EXPIRED")
    result = evaluate(brain(
        customer=profile(), commerce_signal=signal(),
        latest=expired, eligible=offering(),
    ))
    assert result.decision is CustomerSalesDecisionType.CONTINUE_CONVERSATION
    assert result.reason_code is CustomerSalesReasonCode.ACTIVE_OFFER_EXPIRED
    assert result.active_purchase_intent_id is None
    assert result.active_offering_id is None
    assert result.decision_metadata["latestIntentStatus"] == "EXPIRED"


def test_decision_and_nested_metadata_are_immutable():
    result = evaluate(brain(
        customer=profile(), commerce_signal=signal(), eligible=offering(),
    ))
    with pytest.raises(FrozenInstanceError):
        result.sell_allowed = False
    with pytest.raises(TypeError):
        result.decision_metadata["rulePriority"] = 99


def test_first_repository_ordered_offering_is_structurally_selected():
    selected = offering()
    service = brain(
        customer=profile(), commerce_signal=signal(), eligible=selected,
    )
    result = evaluate(service)
    assert result.decision is CustomerSalesDecisionType.PRESENT_OFFER
    assert len(service.offering_selector.calls) == 1
    assert result.recommended_offering_id == selected.offering_id
    assert result.recommended_publication_id == selected.publication_id
    assert result.recommended_offering_title == selected.title
    assert result.recommended_offering_price_minor == 999
    assert result.sell_allowed is True
    assert result.upsell_allowed is False
    assert result.cross_sell_allowed is False


def test_no_eligible_offering_means_no_sale():
    result = evaluate(brain(
        customer=profile(), commerce_signal=signal(),
    ))
    assert result.decision is CustomerSalesDecisionType.NO_SALE
    assert result.reason_code is CustomerSalesReasonCode.NO_ELIGIBLE_OFFERING


def test_buyer_stages_do_not_invent_high_value_or_inactive_thresholds():
    assert CustomerSalesBrainService.buyer_stage(0) is CustomerBuyerStage.PROSPECT
    assert CustomerSalesBrainService.buyer_stage(1) is CustomerBuyerStage.FIRST_TIME_BUYER
    assert CustomerSalesBrainService.buyer_stage(2) is CustomerBuyerStage.REPEAT_BUYER
    assert CustomerSalesBrainService.buyer_stage(100) is CustomerBuyerStage.REPEAT_BUYER


def test_statistics_and_read_only_api(monkeypatch):
    decision = evaluate(brain(
        customer=profile(), commerce_signal=signal(), eligible=offering(),
    ))

    class Service:
        def list_decisions(self, **kwargs):
            return (decision,), 1, 1

        def statistics(self, **kwargs):
            return {
                "total": 1,
                "decisionDistribution": {"PRESENT_OFFER": 1},
                "buyerStageDistribution": {"PROSPECT": 1},
                "currentActiveOffers": 0,
                "pendingPayments": 0,
                "unknownAttributions": 0,
            }

        def evaluate_for_telegram_user(self, **kwargs):
            return decision

    monkeypatch.setattr(api, "CustomerSalesBrainService", Service)
    monkeypatch.setattr(api, "_creator_profile", lambda: {"id": 2})
    application = FastAPI()
    application.include_router(api.router)
    client = TestClient(application)
    headers = {"X-Creator-OS-Developer": "true"}
    assert client.get(
        "/api/v1/developer/customer-sales-brain", headers=headers
    ).json()["items"][0]["decision"] == "PRESENT_OFFER"
    assert client.get(
        "/api/v1/developer/customer-sales-brain/statistics", headers=headers
    ).json()["decisionDistribution"] == {"PRESENT_OFFER": 1}
    assert client.get(
        "/api/v1/developer/customer-sales-brain/22", headers=headers
    ).json()["sellAllowed"] is True
    assert client.post(
        "/api/v1/developer/customer-sales-brain", headers=headers
    ).status_code == 405
