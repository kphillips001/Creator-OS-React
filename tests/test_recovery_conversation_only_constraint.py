from types import SimpleNamespace
from datetime import datetime, timezone
from types import MappingProxyType

import pytest

from app.models.conversation_attention_resolution import ResolutionAction, RootCauseScope
from app.models.customer_sales_decision import (
    CustomerBuyerStage, CustomerSalesDecision, CustomerSalesDecisionType,
    CustomerSalesReasonCode,
)
from app.services.conversation_gateway import ConversationGateway
from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService
from app.services.conversation_attention_resolution_service import (
    ConversationAttentionResolutionService,
)
from app.services.recovery_execution_constraint_service import (
    RecoveryExecutionConstraintService as Constraint,
)


def operation(*, constrained=True, kind="HISTORICAL_CORRECTIVE"):
    delivery = {"recoveryExecutionConstraint": Constraint.authority()} if constrained else {}
    return SimpleNamespace(operation_kind=kind, delivery_payload=delivery,
                           response_payload={}, response_text="hey you")


def result(**changes):
    values = dict(delivery_payload={"type": "MESSAGE_TEXT", "message_text": "hey you"},
                  diagnostic_metadata={}, offer_authorized=False,
                  delivery_requires_payment=False, delivery_type="MESSAGE_TEXT",
                  delivery_mode="conversation", response_text="hey you")
    values.update(changes)
    return SimpleNamespace(**values)


@pytest.mark.parametrize("action", [
    "PRESENT_OFFER", "PRESENT_ALTERNATIVE_OFFER", "CONTENT_ALTERNATIVE",
])
def test_commercial_sales_actions_are_rejected(action):
    allowed, reason = Constraint.validate_result(
        operation(), result(diagnostic_metadata={"recommended_action": action}))
    assert allowed is False and reason == Constraint.REASON


@pytest.mark.parametrize("delivery", [
    {"type": "private_ppv_media", "asset_path": "paid.jpg"},
    {"type": "MESSAGE_TEXT", "private_chat_unlock_button": {"url": "https://x"}},
    {"type": "MESSAGE_TEXT", "purchase_intent_id": "intent"},
    {"type": "PHOTO", "message_text": "photo"},
])
def test_ppv_unlock_purchase_intent_and_media_are_rejected(delivery):
    assert Constraint.validate_result(operation(), result(
        delivery_payload=delivery, delivery_type=delivery["type"]))[0] is False


def test_plain_conversation_and_flirting_are_allowed():
    assert Constraint.validate_result(operation(), result(
        response_text="come keep me company then 😏"))[0] is True


def test_constraint_is_exact_operation_scoped_and_primary_unaffected():
    commercial = result(delivery_requires_payment=True)
    assert Constraint.validate_result(operation(), commercial)[0] is False
    assert Constraint.validate_result(operation(constrained=False), commercial)[0] is True
    assert Constraint.validate_result(
        operation(constrained=False, kind="PRIMARY"), commercial)[0] is True


def test_constraint_round_trips_through_resume_and_attempt_two_context():
    stored = operation()
    restored = operation(constrained=False)
    restored.delivery_payload = dict(stored.delivery_payload)
    context = Constraint.apply_generation_context({"attempt": 2, "required": True})
    assert Constraint.constrained(restored)
    assert context["attempt"] == 2
    assert context["recoveryExecutionConstraint"] == Constraint.authority()


def test_lifecycle_persistence_preserves_constraint_and_lineage_authority():
    stored=operation()
    stored.delivery_payload.update({
        "approvedHistoricalCorrection":{"causalOperationId":"root"},
        "canonicalNotDeliveredCorrection":{"freshGenerationRequired":True},
    })
    payload=OrdinaryChatReplyService._durable_delivery_payload(stored,result())
    assert payload["type"]=="MESSAGE_TEXT"
    assert payload["recoveryExecutionConstraint"]==Constraint.authority()
    assert payload["approvedHistoricalCorrection"]["causalOperationId"]=="root"
    assert payload["canonicalNotDeliveredCorrection"]["freshGenerationRequired"] is True


def test_raw_send_uncertain_stays_unplanned_but_attested_eligible_routes_corrective():
    raw = {"failureSignature": "SEND_UNCERTAIN", "recoveryEligibility": {"eligible": False}}
    attested = {"failureSignature": "SEND_UNCERTAIN", "recoveryEligibility": {
        "eligible": True, "category": "CANONICALLY_CONFIRMED_NOT_DELIVERED"}}
    delivered = {"failureSignature": "SEND_UNCERTAIN", "recoveryEligibility": {
        "eligible": False, "reason": "CANONICAL_NOT_DELIVERED_RESOLUTION_REQUIRED"}}
    assert ConversationAttentionResolutionService._server_action(raw) is ResolutionAction.NO_AUTOMATED_RESOLUTION
    assert ConversationAttentionResolutionService._server_action(delivered) is ResolutionAction.NO_AUTOMATED_RESOLUTION
    assert ConversationAttentionResolutionService._server_action(attested) is ResolutionAction.REQUEUE_CORRECTIVE_REPLY
    assert ConversationAttentionResolutionService._server_scope({**attested,
        "similarCurrentCases": []}) is RootCauseScope.CUSTOMER_ONLY


def commercial_decision(action=CustomerSalesDecisionType.PRESENT_OFFER):
    return CustomerSalesDecision(
        creator_profile_id=2, fanvue_account_id=2,
        external_fanvue_buyer_uuid=None, telegram_user_id=7,
        identity_resolved=True, decision=action,
        reason_code=CustomerSalesReasonCode.DIRECT_PURCHASE_INTENT,
        reason_summary="strong commercial history", buyer_stage=CustomerBuyerStage.PROSPECT,
        commerce_signal=MappingProxyType({"sexualEngagement": True}),
        active_purchase_intent_id=None, active_offering_id=None,
        active_offer_status=None, active_offer_conversion_state="NONE",
        recommended_offering_id=None, recommended_publication_id=None,
        recommended_delivery_url="https://unlock", sell_allowed=True,
        nudge_allowed=True, upsell_allowed=True, cross_sell_allowed=True,
        congratulate_allowed=False, cooldown_until=None,
        evaluated_at=datetime.now(timezone.utc),
        decision_metadata=MappingProxyType({
            "inventoryExistence": {"eligible": True},
            "commercialReceptiveness": {"state": "HOT"},
        }),
        recommended_offering_title="Paid set",
        recommended_offering_short_description="paid content",
        recommended_offering_price_minor=999,
        recommended_offering_currency="USD",
        recommended_product_context={"heroAssetId": 5, "assetIntelligence": {"title": "asset"}},
    )


@pytest.mark.parametrize("action", [
    CustomerSalesDecisionType.PRESENT_OFFER,
    CustomerSalesDecisionType.PRESENT_ALTERNATIVE_OFFER,
])
def test_gateway_deterministically_downgrades_commercial_action_before_generation(action):
    gateway_input=SimpleNamespace(quality_correction_context={
        "recoveryExecutionConstraint": Constraint.authority()})
    decision=ConversationGateway._apply_recovery_execution_constraint(
        commercial_decision(action),gateway_input=gateway_input)
    assert decision.decision is CustomerSalesDecisionType.CONTINUE_CONVERSATION
    assert decision.reason_code is CustomerSalesReasonCode.CONVERSATION_ONLY
    assert decision.sell_allowed is False and decision.recommended_delivery_url is None
    runtime=ConversationGateway.__new__(ConversationGateway)._commerce_runtime_injection(decision)
    commerce=runtime["commerce_decision"]
    assert commerce["decision"]=="CONTINUE_CONVERSATION"
    assert commerce["commerce_execution_policy"]=="COMMERCE_DISABLED_FOR_TURN"
    assert commerce["active_offering_id"] is None
    assert "selected_offering" not in commerce and "inventory_existence" not in commerce
    assert commerce["delivery_type_required"]=="MESSAGE_TEXT"


def test_unconstrained_commercial_action_is_unchanged():
    original=commercial_decision()
    gateway_input=SimpleNamespace(quality_correction_context={})
    assert ConversationGateway._apply_recovery_execution_constraint(
        original,gateway_input=gateway_input) is original
