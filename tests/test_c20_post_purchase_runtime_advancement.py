from types import SimpleNamespace
from uuid import uuid4

from app.services.customer_sales_brain_service import CustomerSalesBrainService
from app.services.commercial_offering_selector_service import (
    CommercialOfferingSelectorService,
)
from app.models.autonomous_sales_progression import (
    ProgressionAssetRole,
    SellableProgressionAsset,
)
from app.services.private_chat_purchase_settlement_service import (
    PrivateChatPurchaseSettlementService,
)
from app.testing.session5_scenario_harness import CustomerScenarioHarness


class TransferCursor:
    def __init__(self, results):
        self.results = list(results)
        self.current = None
        self.sql = []

    def execute(self, statement, arguments=()):
        self.sql.append((" ".join(statement.split()), arguments))
        self.current = self.results.pop(0) if self.results else None
        return self

    def fetchone(self):
        return self.current

    def fetchall(self):
        if isinstance(self.current, list):
            return self.current
        return [] if self.current is None else [self.current]


def test_graduation_transfers_confirmed_free_step_without_ownership():
    lifecycle_id = uuid4()
    cursor = TransferCursor([None, None])
    provisional = {
        "provisional_session_id": uuid4(),
        "photoshoot_reference": "shoot-c20",
        "commercial_context": {"freeTeaserDelivery": {
            "assetId": 101,
            "salesRole": "FREE_TEASER",
            "provider": "SCENARIO_TEST_TRANSPORT",
            "providerDeliveryId": "message-1",
        }},
    }

    PrivateChatPurchaseSettlementService._transfer_confirmed_free_step(
        cursor, provisional=provisional,
        intent={"creator_profile_id": 7},
        lifecycle={"lifecycle_id": lifecycle_id, "status": "ACTIVE"},
        sales_session_id=uuid4(),
    )

    insert_sql, insert_args = cursor.sql[-1]
    assert "customer_photoshoot_lifecycle_events" in insert_sql
    assert "provider_purchase_asset_ownership" not in insert_sql
    assert insert_args[3] == 101
    assert "CONFIRMED_PROVISIONAL_FREE_TEASER_DELIVERY" in insert_args[-1]


class OrderedRepository:
    def ordered_assets(self, **_):
        return (
            SimpleNamespace(position=1, asset_id=101, offering_id=None,
                            price_minor=None, currency=None),
            SimpleNamespace(position=2, asset_id=102, offering_id=uuid4(),
                            price_minor=900, currency="USD"),
            SimpleNamespace(position=3, asset_id=103, offering_id=uuid4(),
                            price_minor=1900, currency="USD"),
            SimpleNamespace(position=4, asset_id=104, offering_id=uuid4(),
                            price_minor=2900, currency="USD"),
        )


class Runtime:
    def evaluate(self, **_):
        return SimpleNamespace(
            owned_asset_ids=(102,), current_position=3,
            status=SimpleNamespace(value="ACTIVE"),
            to_context=lambda: {
                "currentPosition": 3, "currentAssetId": 103,
                "currentSalesRole": "ESCALATION",
            },
        )


def test_full_analysis_context_uses_runtime_consumption_not_first_unowned():
    service = object.__new__(CustomerSalesBrainService)
    service.progression_repository = OrderedRepository()
    service.session_runtime = Runtime()

    result = service._active_session_continuity_context(
        context={
            "sales_session_id": str(uuid4()),
            "sales_session_foundation": "shoot-c20",
            "sales_session_foundation_type": "PHOTOSHOOT",
            "sales_session_state": "CONTINUING",
            "sales_session_progression": "PROGRESSION",
        },
        creator_profile_id=7, customer_commerce_profile_id=uuid4(),
    )

    assert result["ownedPositions"] == [2]
    assert result["consumedPositions"] == [1, 2]
    assert result["currentConsumedPosition"] == 2
    assert result["nextEligiblePosition"] == 3
    assert result["sessionRuntime"]["currentSalesRole"] == "ESCALATION"


def test_structured_confirmation_requires_all_exact_delivery_evidence():
    complete = {
        "purchase_intent_id": str(uuid4()),
        "purchase_intent_presented_at": "2026-09-06T00:00:00Z",
        "synthetic_delivery_operation_id": str(uuid4()),
        "synthetic_delivery_state": "CONFIRMED",
        "test_transport_customer_visible_confirmed": True,
    }
    assert CustomerScenarioHarness.structured_presentation_confirmed(complete)
    for key in complete:
        candidate = dict(complete)
        candidate[key] = None
        assert not CustomerScenarioHarness.structured_presentation_confirmed(candidate)


class CandidateRepository:
    def __init__(self, assets):
        self.assets = assets

    def ordered_assets(self, **_):
        return self.assets


def paid_step(asset_id, position, offering_id, *, owned=False, rejected=False):
    return SellableProgressionAsset(
        asset_id=asset_id, position=position,
        role=ProgressionAssetRole.CORE_SESSION,
        offering_id=offering_id, owned=owned, rejected=rejected,
    )


def test_active_session_selects_exact_next_step_and_never_leapfrogs():
    position_2, position_3, position_4 = uuid4(), uuid4(), uuid4()
    profile = SimpleNamespace(customer_commerce_profile_id=uuid4())
    opportunity = SimpleNamespace(photoshoot_id="shoot-c20")
    candidates = (
        {"offering_id": position_3, "photoshoot_identifier": "shoot-c20"},
        {"offering_id": position_4, "photoshoot_identifier": "shoot-c20"},
    )
    service = object.__new__(CommercialOfferingSelectorService)
    service.progression_repository = CandidateRepository((
        paid_step(102, 2, position_2, owned=True),
        paid_step(103, 3, position_3),
        paid_step(104, 4, position_4),
    ))

    selected = service._active_opportunity_candidates(
        candidates, opportunity, 7, profile, owned_asset_ids=(102,),
    )
    assert tuple(item["offering_id"] for item in selected) == (position_3,)

    service.progression_repository = CandidateRepository((
        paid_step(102, 2, position_2, owned=True),
        paid_step(103, 3, position_3, rejected=True),
        paid_step(104, 4, position_4),
    ))
    assert service._active_opportunity_candidates(
        candidates, opportunity, 7, profile, owned_asset_ids=(102,),
    ) == ()
