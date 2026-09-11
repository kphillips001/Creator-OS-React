from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.telegram_relationship_control import TelegramRelationshipControl, TelegramRelationshipMode
from app.services.telegram_delivery_executor import TelegramDeliveryExecutor
from app.services.telegram_operator_message_service import TelegramOperatorMessageError, TelegramOperatorMessageService


def control(mode=TelegramRelationshipMode.HUMAN_OPERATOR, version=3):
    return TelegramRelationshipControl(uuid4(), 1, 2, 3, 4, mode, version)


class Controls:
    HOLD_REASON = "RELATIONSHIP_HUMAN_OPERATOR_ACTIVE"
    def __init__(self, current): self.current=current; self.repository=SimpleNamespace(touch_manual_activity=lambda value:value)
    def get(self, **_scope): return self.current
    def autonomous_allowed(self, *, captured_version=None, **_scope):
        return (not self.current.manual and (captured_version is None or captured_version == self.current.control_version), self.current)


class Operations:
    def __init__(self): self.row=None; self.claims=0
    def reserve(self, **values):
        if self.row is None:
            self.row={**values,"operation_id":uuid4(),"state":"PREPARED","outbound_telegram_message_id":None,"confirmed_at":None}
        elif self.row["message_text"] != values["message_text"]: raise ValueError("different text")
        return self.row
    def claim(self, operation_id, *, expected_version): self.claims+=1; self.row["state"]="SENDING"; return self.row
    def confirmed(self, operation_id, message_id):
        self.row.update(state="CONFIRMED",outbound_telegram_message_id=message_id,confirmed_at=datetime.now(timezone.utc)); return self.row
    def failed(self, operation_id, error): self.row["state"]="FAILED"; return self.row
    def ambiguous(self, operation_id, error): self.row["state"]="AMBIGUOUS"; return self.row


class Transport:
    def __init__(self): self.calls=0
    def send_text(self, **values): self.calls+=1; assert values["button_label"] is None; return 77


def scope():
    return {"creator_profile_id":1,"fanvue_account_id":2,"telegram_user_id":3,
            "telegram_chat_id":4,"telegram_identity_mapping_id":None,
            "local_fanvue_user_id":None,"conversation_thread_id":None}


def test_manual_send_requires_manual_mode_and_expected_epoch():
    service=TelegramOperatorMessageService(repository=Operations(),controls=Controls(control(TelegramRelationshipMode.AVA_AUTO)),transport=Transport())
    with pytest.raises(TelegramOperatorMessageError): service.send(context=scope(),text="hello",idempotency_key="stable-key",expected_control_version=3,changed_by="operator")
    service.controls.current=control(version=4)
    with pytest.raises(TelegramOperatorMessageError): service.send(context=scope(),text="hello",idempotency_key="stable-key",expected_control_version=3,changed_by="operator")


def test_manual_send_reuses_transport_and_confirmed_retry_is_idempotent():
    operations,transport=Operations(),Transport()
    service=TelegramOperatorMessageService(repository=operations,controls=Controls(control()),transport=transport)
    first=service.send(context=scope(),text="hello",idempotency_key="stable-key",expected_control_version=3,changed_by="operator")
    second=service.send(context=scope(),text="hello",idempotency_key="stable-key",expected_control_version=3,changed_by="operator")
    assert first["state"] == second["state"] == "CONFIRMED"
    assert first["outbound_telegram_message_id"] == 77
    assert transport.calls == operations.claims == 1


def test_final_send_blocks_manual_and_stale_autonomous_work():
    sender=SimpleNamespace(send_text=lambda **_values: pytest.fail("must not send"))
    manual=TelegramDeliveryExecutor(global_safety_service=SimpleNamespace(check_global_safety=lambda:{"allowed":True}),relationship_control_service=Controls(control()),business_commercial_transport=sender)
    context={**scope(),"transport":sender,"relationship_control_version":2}
    result=manual.execute({"message_text":"reply","delivery_method":"text"},context=context)
    assert not result.executed and result.blocking_reason == "RELATIONSHIP_HUMAN_OPERATOR_ACTIVE"
    auto=TelegramDeliveryExecutor(global_safety_service=SimpleNamespace(check_global_safety=lambda:{"allowed":True}),relationship_control_service=Controls(control(TelegramRelationshipMode.AVA_AUTO,4)),business_commercial_transport=sender)
    stale=auto.execute({"message_text":"reply","delivery_method":"text"},context=context)
    assert not stale.executed
