from datetime import datetime, timezone
from uuid import uuid4
from types import SimpleNamespace

from app.models.customer_sales_decision import (
    CustomerBuyerStage, CustomerSalesDecision, CustomerSalesDecisionType,
    CustomerSalesReasonCode, immutable_mapping,
)
from app.services.conversation_gateway import ConversationGateway


class Permissions:
    def __init__(self, *, content, session):
        self.content, self.session = content, session
    def content_allowed(self): return self.content
    def session_allowed(self): return self.session


def decision(action, *, selling_mode=None):
    offering_id = uuid4()
    return CustomerSalesDecision(
        creator_profile_id=1, fanvue_account_id=2,
        external_fanvue_buyer_uuid=None, telegram_user_id=3,
        identity_resolved=True, decision=action,
        reason_code=CustomerSalesReasonCode.NO_ACTIVE_OFFER,
        reason_summary="offer", buyer_stage=CustomerBuyerStage.PROSPECT,
        commerce_signal=immutable_mapping({}), active_purchase_intent_id=None,
        active_offering_id=None, active_offer_status=None,
        active_offer_conversion_state="NONE",
        recommended_offering_id=offering_id,
        recommended_publication_id=uuid4(),
        recommended_delivery_url="https://fanvue.com/example",
        sell_allowed=True, nudge_allowed=False, upsell_allowed=False,
        cross_sell_allowed=False, congratulate_allowed=False,
        cooldown_until=None, evaluated_at=datetime.now(timezone.utc),
        decision_metadata=immutable_mapping({}),
        recommended_offering_title="Offer",
        recommended_offering_short_description="Description",
        recommended_offering_price_minor=1000,
        recommended_offering_currency="USD",
        recommended_product_context=immutable_mapping(
            {"sellingMode": selling_mode} if selling_mode else {}),
    )


def gateway(content, session):
    value = ConversationGateway.__new__(ConversationGateway)
    value._global_selling_permissions = Permissions(
        content=content, session=session)
    return value


def test_content_off_blocks_new_content_presentation_but_not_ordinary_chat():
    original = decision(CustomerSalesDecisionType.PRESENT_OFFER)
    blocked = gateway(False, True)._apply_global_selling_ceiling(original)
    assert blocked.decision is CustomerSalesDecisionType.CONTINUE_CONVERSATION
    assert blocked.sell_allowed is False
    assert blocked.recommended_offering_id is None
    ordinary = decision(CustomerSalesDecisionType.CONTINUE_CONVERSATION)
    assert gateway(False, False)._apply_global_selling_ceiling(ordinary) is ordinary


def test_session_permission_is_independent_from_content_permission():
    session_offer = decision(CustomerSalesDecisionType.PRESENT_OFFER,
                             selling_mode="SESSION")
    assert gateway(True, False)._apply_global_selling_ceiling(
        session_offer).sell_allowed is False
    assert gateway(False, True)._apply_global_selling_ceiling(
        session_offer).sell_allowed is True
    content_offer = decision(CustomerSalesDecisionType.PRESENT_OFFER)
    assert gateway(True, False)._apply_global_selling_ceiling(
        content_offer).sell_allowed is True


def test_existing_active_offer_nudge_is_preserved_when_permissions_turn_off():
    active = decision(CustomerSalesDecisionType.NUDGE_ACTIVE_OFFER)
    assert gateway(False, False)._apply_global_selling_ceiling(active) is active


def test_new_session_proposal_is_blocked_when_session_selling_off():
    proposal = decision(CustomerSalesDecisionType.PROPOSE_SESSION)
    blocked = gateway(True, False)._apply_global_selling_ceiling(proposal)
    assert blocked.decision is CustomerSalesDecisionType.CONTINUE_CONVERSATION
    assert blocked.decision_metadata["globalSellingPermission"]["reason"] == (
        "GLOBAL_SESSION_SELLING_DISABLED")


def test_customer_content_off_blocks_when_global_content_is_on():
    class CustomerPermissions:
        def read(self, **_):
            return {"effective": {
                "contentSellingAllowed": False,
                "contentSellingReason": "CUSTOMER_CONTENT_SELLING_DISABLED",
                "sessionSellingAllowed": True,
                "sessionSellingReason": None,
            }}
    value = gateway(True, True)
    value._customer_effective_permissions = CustomerPermissions()
    request = SimpleNamespace(brain_context=SimpleNamespace(
        creator_profile_id=1, fanvue_account_id=2, telegram_user_id=3,
        telegram_chat_id=3))
    blocked = value._apply_global_selling_ceiling(
        decision(CustomerSalesDecisionType.PRESENT_OFFER), gateway_input=request)
    assert blocked.sell_allowed is False
    assert blocked.decision_metadata["globalSellingPermission"]["reason"] == (
        "CUSTOMER_CONTENT_SELLING_DISABLED")
