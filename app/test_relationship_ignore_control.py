from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.models.telegram_relationship_control import (
    TelegramCommunicationDisposition, TelegramRelationshipControl,
    TelegramRelationshipMode,
)
from app.services.customer_effective_permissions_service import CustomerEffectivePermissionsService
from app.services.relationships_service import RelationshipsService
from app.services.telegram_operator_message_service import (
    TelegramOperatorMessageError, TelegramOperatorMessageService,
)
from app.services.telegram_relationship_control_service import TelegramRelationshipControlService


def control(*, ignored=False, mode=TelegramRelationshipMode.AVA_AUTO, version=2):
    return TelegramRelationshipControl(
        None, 1, 2, 3, 3, mode, version,
        communication_disposition=(TelegramCommunicationDisposition.IGNORED
                                   if ignored else TelegramCommunicationDisposition.ACTIVE),
        ignore_version=1 if ignored else 0)


def test_ignore_is_stronger_than_manual_customer_and_global_permissions():
    class Relationships:
        def get(self, **_): return control(ignored=True)
    service = CustomerEffectivePermissionsService(
        relationship_controls=Relationships(),
        ava_bot_controls=SimpleNamespace(read=lambda **_: {"avaBot": {"desired": "ON", "effective": "ON"}}),
        global_selling_permissions=SimpleNamespace(read=lambda: {
            "contentSellingEnabled": True, "sessionSellingEnabled": True}))
    state = service.read(creator_profile_id=1, fanvue_account_id=2,
                         telegram_user_id=3, telegram_chat_id=3)
    assert state["effective"] == {
        "chatAllowed": False, "chatReason": "RELATIONSHIP_IGNORED",
        "contentSellingAllowed": False, "contentSellingReason": "RELATIONSHIP_IGNORED",
        "sessionSellingAllowed": False, "sessionSellingReason": "RELATIONSHIP_IGNORED"}


def test_autonomous_and_manual_sends_are_blocked_while_ignored():
    service = TelegramRelationshipControlService(repository=SimpleNamespace(
        get=lambda **_: control(ignored=True)))
    allowed, current = service.autonomous_allowed(
        creator_profile_id=1, fanvue_account_id=2,
        telegram_user_id=3, telegram_chat_id=3)
    assert not allowed and service.block_reason(current) == "RELATIONSHIP_IGNORED"
    sender = TelegramOperatorMessageService(
        controls=SimpleNamespace(get=lambda **_: replace(
            control(ignored=True), mode=TelegramRelationshipMode.HUMAN_OPERATOR)),
        repository=SimpleNamespace(), transport=SimpleNamespace())
    with pytest.raises(TelegramOperatorMessageError, match="Unignore"):
        sender.send(context={"creator_profile_id": 1, "fanvue_account_id": 2,
            "telegram_user_id": 3, "telegram_chat_id": 3}, text="hello",
            idempotency_key="ignore-test", expected_control_version=2,
            changed_by="test")


def test_ignored_operational_status_outranks_manual_attention_and_debt():
    projected = RelationshipsService._operational_projection({
        "control_mode": "HUMAN_OPERATOR", "communication_disposition": "IGNORED",
        "last_customer_inbound_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc),
        "operation_state": "SEND_UNCERTAIN", "operation_last_error": "uncertain",
    })
    assert projected["operationalStatus"] == "IGNORED"
    assert projected["nextAutomaticAttemptAt"] is None
    assert projected["attentionOccurrenceId"] is None
    assert projected["operationalStatusReason"] == (
        "Automatic communication disabled for this relationship.")
