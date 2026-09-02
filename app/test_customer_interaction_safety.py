from dataclasses import dataclass
from datetime import timedelta
from uuid import uuid4

import pytest

from app.models.telegram_identity import TelegramMvpIdentityOutput
from app.models.telegram_inbound import TelegramInboundPayload
from app.services.ai_training_control_service import AiTrainingControlService
from app.services.customer_interaction_safety_service import CustomerInteractionSafetyService
from app.services.telegram_delivery_executor import TelegramDeliveryExecutor
from app.services.telegram_inbound_adapter import TelegramInboundAdapter
from app.services.purchase_intent_service import PurchaseIntentService
from app.services.sales_session_service import SalesSessionError, SalesSessionService
from app.services.customer_sales_brain_service import CustomerSalesBrainService
from app.services.customer_sales_brain_config import CustomerSalesBrainConfig


class SafetyRepository:
    def __init__(self): self.states = {}; self.audit = []
    def get(self, **identity): return self.states.get(tuple(identity.values()))
    def set_status(self, **values):
        key = (values["creator_profile_id"], values["fanvue_account_id"], values["fanvue_user_id"])
        previous = self.states.get(key)
        row = {"safety_state_id": uuid4(), "safety_status": values["safety_status"], "reason": values["reason"]}
        self.states[key] = row
        self.audit.append((previous and previous["safety_status"], values["safety_status"], values["reason"]))
        return row


class PolicyRepository:
    def __init__(self, enabled=True): self.enabled = enabled
    def is_backend_policy_enabled(self, **_): return self.enabled


def test_underage_language_is_supported_structured_backend_policy():
    service = AiTrainingControlService(repository=object())
    for text in (
        "If a customer is determined to be underage, immediately stop chatting with that customer.",
        "Don't chat with customers who are confirmed underage.",
        "If we determine someone is under age, stop all automated communication with that person.",
    ):
        preview = service.classify(text)
        assert preview["instructionType"] == "SAFETY_HARD_STOP"
        assert preview["policyKey"] == "UNDERAGE_CUSTOMER"
        assert preview["enforcementMode"] == "BACKEND"
        assert "other customers are unaffected" in preview["classificationReason"].lower()
        assert "does not determine or mark age" in preview["classificationReason"].lower()


def test_conversation_and_unsupported_hard_stop_classification_regression():
    service = AiTrainingControlService(repository=object())
    assert service.classify("Don't use the word baby.")["instructionType"] == "CONVERSATION_RULE"
    unsupported = service.classify("Hard stop anyone who mentions pineapple")
    assert unsupported["classification"] == "REQUIRES_IMPLEMENTATION"
    assert unsupported["runtimeEligible"] is False


def test_customer_state_is_isolated_audited_persistent_and_deliberately_restored():
    repository = SafetyRepository(); training = PolicyRepository()
    service = CustomerInteractionSafetyService(repository, training)
    service.set_status(creator_profile_id=1, fanvue_account_id=10, fanvue_user_id=2,
                       safety_status="UNDERAGE_BLOCKED", reason="Operator verified age concern")
    assert service.decide(creator_profile_id=1, fanvue_account_id=10, fanvue_user_id=1).allowed
    assert not service.decide(creator_profile_id=1, fanvue_account_id=10, fanvue_user_id=2).allowed
    assert service.decide(creator_profile_id=1, fanvue_account_id=10, fanvue_user_id=3).allowed
    restarted = CustomerInteractionSafetyService(repository, training)
    assert restarted.decide(creator_profile_id=1, fanvue_account_id=10, fanvue_user_id=2).code == "BLOCKED_UNDERAGE"
    assert restarted.decide(creator_profile_id=1, fanvue_account_id=11, fanvue_user_id=2).allowed
    training.enabled = False
    assert not restarted.decide(creator_profile_id=1, fanvue_account_id=10, fanvue_user_id=2).allowed
    restarted.set_status(creator_profile_id=1, fanvue_account_id=10, fanvue_user_id=2,
                         safety_status="NORMAL", reason="Operator completed deliberate review")
    assert restarted.decide(creator_profile_id=1, fanvue_account_id=10, fanvue_user_id=2).allowed
    assert repository.audit == [(None, "UNDERAGE_BLOCKED", "Operator verified age concern"),
                                ("UNDERAGE_BLOCKED", "NORMAL", "Operator completed deliberate review")]


@dataclass
class Identity:
    fanvue_account_id: int = 10
    local_fanvue_user_id: int = 2
    external_fanvue_user_uuid: object = uuid4()
    engine_user_id: str = "10:2"


class TelegramIdentities:
    def observe(self, **_): pass
    def resolve_telegram_identity(self, _): return Identity()


class BlockedSafety:
    def decide(self, **_):
        return type("Decision", (), {"allowed": False, "code": "BLOCKED_UNDERAGE"})()


def test_telegram_inbound_blocks_before_gateway_or_ai_generation():
    calls = []
    adapter = TelegramInboundAdapter(
        identity_adapter=type("Adapter", (), {"adapt": lambda self, value: TelegramMvpIdentityOutput("10:2")})(),
        conversation_gateway=type("Gateway", (), {"execute": lambda self, value: calls.append(value)})(),
        creator_profile_id=1, fanvue_account_id=10,
        telegram_identity_service=TelegramIdentities(), customer_safety_service=BlockedSafety())
    result = adapter.execute(TelegramInboundPayload(telegram_user_id=50, telegram_chat_id=60,
        message_text="hello", message_id=70))
    assert result.blocked and result.error_code == "BLOCKED_UNDERAGE"
    assert result.response_text == "" and result.diagnostic_metadata["ai_generation_count"] == 0
    assert calls == []


def test_stale_telegram_delivery_is_suppressed_before_sender():
    sends = []
    sender = type("Sender", (), {"send_text": lambda self, **values: sends.append(values)})()
    executor = TelegramDeliveryExecutor(
        global_safety_service=type("Global", (), {"check_global_safety": lambda self: {"allowed": True}})(),
        customer_safety_service=BlockedSafety())
    result = executor.execute({"message_text": "already generated", "delivery_method": "text"},
        context={"transport": sender, "chat_id": 60, "creator_profile_id": 1,
                 "fanvue_account_id": 10, "fanvue_user_id": 2})
    assert result.executed is False and result.blocking_reason == "BLOCKED_UNDERAGE"
    assert sends == []


def test_marking_underage_requires_enabled_policy_and_operator_reason():
    service = CustomerInteractionSafetyService(SafetyRepository(), PolicyRepository(False))
    with pytest.raises(ValueError, match="Enable the Underage"):
        service.set_status(creator_profile_id=1, fanvue_account_id=10, fanvue_user_id=2,
                           safety_status="UNDERAGE_BLOCKED", reason="Operator verified concern")


def test_purchase_intent_and_session_progression_consult_customer_safety():
    identity = type("Identity", (), {"local_fanvue_user_id": 2})()
    identities = type("Identities", (), {
        "get_by_telegram_user_id": lambda self, value: identity,
        "get_verified_by_telegram_user_id": lambda self, value: identity,
    })()
    intents = PurchaseIntentService(repository=object(), learning_service=object(),
        commercial_eligibility=object(), customer_safety_service=BlockedSafety(),
        telegram_identity_repository=identities)
    with pytest.raises(ValueError, match="BLOCKED_UNDERAGE"):
        intents._require_customer_interaction({"creator_profile_id": 1,
            "fanvue_account_id": 10, "telegram_user_id": 50})

    sessions = object.__new__(SalesSessionService)
    sessions.customer_safety = BlockedSafety()
    session = type("Session", (), {"creator_profile_id": 1,
        "fanvue_account_id": 10, "fanvue_user_id": 2})()
    with pytest.raises(SalesSessionError, match="BLOCKED_UNDERAGE"):
        sessions._require_safe_session(session)


def test_customer_sales_brain_returns_no_sale_before_commercial_evaluation():
    identity = type("Identity", (), {"fanvue_account_id": 10,
        "local_fanvue_user_id": 2, "external_fanvue_user_uuid": uuid4(),
        "telegram_user_id": 50})()
    identities = type("Identities", (), {"get_by_telegram_user_id": lambda self, value: identity})()
    service = CustomerSalesBrainService(
        identity_repository=identities, customer_repository=object(),
        intent_repository=object(), commerce_signal_service=object(),
        offering_selector_service=object(), sales_session_repository=object(),
        customer_safety_service=BlockedSafety(),
        config=CustomerSalesBrainConfig(purchase_cooldown=timedelta(hours=24),
            offer_nudge_delay=timedelta(hours=24), offer_expiration=timedelta(hours=72)))
    decision = service.evaluate_for_telegram_user(creator_profile_id=1, telegram_user_id=50)
    assert decision.decision.value == "NO_SALE"
    assert decision.reason_code.value == "CUSTOMER_INTERACTION_SAFETY_BLOCKED"
    assert not decision.sell_allowed and not decision.nudge_allowed
