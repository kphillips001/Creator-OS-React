import inspect
from contextlib import contextmanager
from datetime import datetime, timezone
from types import MappingProxyType, SimpleNamespace
from uuid import uuid4

from app.models.customer_sales_decision import (
    CustomerBuyerStage, CustomerSalesDecision, CustomerSalesDecisionType,
    CustomerSalesReasonCode,
)
from app.repositories.autonomous_sales_progression_repository import (
    AutonomousSalesProgressionRepository,
)
from app.repositories.free_engagement_teaser_repository import (
    FreeEngagementTeaserRepository,
)
from app.repositories.telegram_provisional_sales_session_repository import (
    TelegramProvisionalSalesSessionRepository,
)
from app.services.conversation_gateway import ConversationGateway
from app.services.free_engagement_teaser_service import FreeEngagementTeaserService


def _strategy(foundation, teaser, unlock):
    return {
        "photoshoot_session_id": foundation,
        "strategy_version": "v1",
        "deliverable_id": uuid4(),
        "strategy_data": {"shots": [
            {"asset_id": teaser, "sales_position": 1,
             "sales_role": "FREE_TEASER", "access_recommendation": "FREE"},
            {"asset_id": unlock, "sales_position": 2,
             "sales_role": "FIRST_UNLOCK", "access_recommendation": "PAID"},
        ]},
    }


class Cursor:
    def __init__(self, strategies):
        self.strategies = strategies
        self.rows = []
        self.row = None

    def execute(self, sql, params):
        if "FROM public.photoshoot_session_sales_strategies" in sql:
            self.rows = self.strategies
        elif "JOIN public.commercial_offering_assets" in sql:
            foundation, asset = str(params[1]), int(params[2])
            self.rows = [{
                "offering_id": uuid4(), "publication_id": uuid4(),
                "price_minor": 900 if asset in {20, 120} else 1900,
                "currency": "USD", "foundation": foundation,
            }]
        elif "FROM public.photoshoot_asset_memberships" in sql:
            self.row = {"exists": 1}
        return self

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.row


class Connection:
    def __init__(self, strategies):
        self.cursor_value = Cursor(strategies)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    @contextmanager
    def cursor(self):
        yield self.cursor_value


def _factory(strategies):
    return lambda: Connection(strategies)


def test_mixed_inventory_session_selection_uses_only_ordered_session_membership():
    # General Engagement assets 9001/9002 deliberately never enter the Session
    # strategy result set. Their age, count, and ordering therefore cannot rank.
    repository = AutonomousSalesProgressionRepository(
        _factory([_strategy("foundation-x", 10, 20)])
    )
    candidates = repository.pre_session_free_teaser_candidates(
        creator_profile_id=7
    )
    assert len(candidates) == 1
    assert candidates[0]["photoshoot_reference"] == "foundation-x"
    assert candidates[0]["teaser_asset_id"] == 10
    assert candidates[0]["next_asset_id"] == 20
    assert candidates[0]["next_sales_role"] == "FIRST_UNLOCK"
    assert candidates[0]["next_price_minor"] == 900
    assert "9001" not in str(candidates) and "9002" not in str(candidates)


def test_session_and_general_engagement_candidate_domains_are_disjoint_by_sql():
    session_source = inspect.getsource(
        AutonomousSalesProgressionRepository.pre_session_free_teaser_candidates
    )
    engagement_sql = FreeEngagementTeaserRepository._eligible_sql()
    assert "photoshoot_session_sales_strategies" in session_source
    assert "photoshoot_asset_memberships" in session_source
    assert '"FREE_TEASER"' in session_source
    assert "asset_content_destinations" not in session_source
    assert "destination.destination='TEASER'" in engagement_sql
    assert "destination.metadata->>'purpose'='ENGAGEMENT_TEASER'" in engagement_sql
    assert "NOT EXISTS (SELECT 1 FROM public.photoshoot_asset_memberships" in engagement_sql
    assert "NOT EXISTS (SELECT 1 FROM public.commercial_role_assignments" in engagement_sql
    assert "NOT EXISTS (SELECT 1 FROM public.commercial_offering_assets" in engagement_sql


def test_multiple_session_foundations_remain_ambiguous_for_fail_closed_caller():
    repository = AutonomousSalesProgressionRepository(_factory([
        _strategy("foundation-x", 10, 20),
        _strategy("foundation-y", 110, 120),
    ]))
    candidates = repository.pre_session_free_teaser_candidates(
        creator_profile_id=7
    )
    assert len(candidates) == 2
    # CustomerSalesBrain authorizes only len(candidates) == 1.
    source = inspect.getsource(
        __import__(
            "app.services.customer_sales_brain_service", fromlist=[
                "CustomerSalesBrainService"
            ]
        ).CustomerSalesBrainService._evaluate_unmapped_prospect
    )
    assert "if len(candidates) == 1:" in source
    assert "CANONICAL_FREE_TEASER_UNAVAILABLE_OR_AMBIGUOUS" in source


def test_confirmation_updates_only_provisional_session_domain():
    source = inspect.getsource(
        TelegramProvisionalSalesSessionRepository.record_free_teaser_delivery
    )
    assert "telegram_provisional_sales_sessions" in source
    assert "current_position=2" in source
    assert "freeTeaserDelivery" in source
    assert "telegram_engagement_teaser_delivery_operations" not in source


def test_general_engagement_delivery_has_no_session_or_paid_authority():
    service_source = inspect.getsource(FreeEngagementTeaserService)
    assert '"teaser_domain": "GENERAL_ENGAGEMENT_TEASER"' in service_source
    assert "TelegramProvisionalSalesSession" not in service_source
    assert "PurchaseIntent" not in service_source
    assert "FIRST_UNLOCK" not in service_source


def test_session_delivery_diagnostics_name_the_domain_explicitly():
    gateway = ConversationGateway.__new__(ConversationGateway)
    gateway._asset_repository = SimpleNamespace(
        get_by_id=lambda asset_id: SimpleNamespace(id=asset_id)
    )
    gateway._runtime_media_resolver = SimpleNamespace(
        resolve_original=lambda *_args, **_kwargs: SimpleNamespace(
            path="C:/session/free.jpg", source="canonical"
        )
    )
    decision = CustomerSalesDecision(
        creator_profile_id=1, fanvue_account_id=2,
        external_fanvue_buyer_uuid=None, telegram_user_id=3,
        identity_resolved=False, decision=CustomerSalesDecisionType.TEASE,
        reason_code=CustomerSalesReasonCode.EXPLICIT_FREE_TEASER_REQUEST,
        reason_summary="test", buyer_stage=CustomerBuyerStage.PROSPECT,
        commerce_signal=MappingProxyType({}), active_purchase_intent_id=None,
        active_offering_id=None, active_offer_status=None,
        active_offer_conversion_state="NONE", recommended_offering_id=None,
        recommended_publication_id=None, recommended_delivery_url=None,
        sell_allowed=False, nudge_allowed=False, upsell_allowed=False,
        cross_sell_allowed=False, congratulate_allowed=False,
        cooldown_until=None, evaluated_at=datetime.now(timezone.utc),
        decision_metadata=MappingProxyType({"preSessionFreeTeaser": {
            "authorized": True, "provisionalSessionId": str(uuid4()),
            "photoshoot_reference": "foundation-x", "teaser_asset_id": 10,
            "next_position": 2, "next_asset_id": 20,
            "next_sales_role": "FIRST_UNLOCK",
            "next_offering_id": str(uuid4()), "next_price_minor": 900,
            "currency": "USD",
        }}),
    )
    delivery = gateway._authoritative_delivery(
        response_text="a little preview", offering=None,
        customer_sales_decision=decision,
    )[4]
    assert delivery["metadata"]["teaser_domain"] == "SESSION_FREE_TEASER"
    assert delivery["metadata"]["free_teaser_delivery"]["asset_id"] == 10
    assert "bundle_teaser_delivery" not in delivery["metadata"]
