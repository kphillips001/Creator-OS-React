from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.services.telegram_negative_history_attestation_service import (
    TelegramNegativeHistoryAttestationService as Service,
)

NOW=datetime(2026,9,18,13,30,tzinfo=timezone.utc)
SEND=datetime(2026,9,18,12,44,9,tzinfo=timezone.utc)


class Repository:
    def __init__(self): self.calls=[];self.row=None
    def resolve(self,**values):
        self.calls.append(values)
        if self.row: return self.row,True
        self.row={"resolution_id":"resolution","outcome":values["outcome"],"evidence":values["evidence"]}
        return self.row,False


def operation(**changes):
    value={"operation_id":"1d99dda0-515b-4073-8e9e-3b7e5b05fa75",
      "state":"SEND_UNCERTAIN","telegram_chat_id":7489120428,
      "inbound_sender_telegram_user_id":7489120428,"sending_at":SEND,
      "uncertain_at":SEND+timedelta(seconds=4),"outbound_telegram_message_id":None,
      "sent_confirmed_at":None,"delivery_payload":{}}
    value.update(changes);return value


def fingerprint(**changes):
    value={"text":"private caption","media_expected":True,"asset_sha256":"hash",
      "button_url":"https://example.test/unlock","anchor_message_ids":[6665],
      "purchase_intent_id":"fb2dd59d-e6b7-494a-a430-ef946b6a0b37",
      "presentation_mode":"VISIBLE_URL"}
    value.update(changes);return value


def message(identifier=6665,*,out=False,text="I want to join you",media_type=None,buttons=None):
    return {"id":identifier,"date":SEND-timedelta(minutes=1),"out":out,"text":text,
            "media_type":media_type,"buttons":buttons or []}


def readback(**changes):
    value={"authenticated":True,"canonical_session":True,"peer_id":7489120428,
      "query_succeeded":True,"complete":True,"truncated":False,
      "authorization_error":False,"query_start":SEND-timedelta(minutes=15),
      "query_end":SEND+timedelta(minutes=31),"executed_at":NOW,
      "lower_boundary_reached":True,"upper_boundary_reached":True,
      "authentication_provenance":"AVA_TELETHON_PRIVATE","messages":[message()]}
    value.update(changes);return value


def evaluate(**changes):
    return Service(now=lambda:NOW).evaluate(operation=changes.pop("op",operation()),
        fingerprint=changes.pop("fp",fingerprint()),readback=readback(**changes))


def test_complete_authenticated_negative_history_qualifies_not_delivered():
    result=evaluate()
    assert result["classification"]=="CONFIRMED_NOT_DELIVERED" and result["eligible"]
    assert result["evidence"]["messagesInspected"]==1


@pytest.mark.parametrize("candidate,fp",[
    (message(7000,out=True,text="private caption"),fingerprint(media_expected=False)),
    (message(7000,out=True,text="private caption",media_type="MessageMediaPhoto"),fingerprint()),
])
def test_matching_outgoing_text_or_photo_is_delivered(candidate,fp):
    result=evaluate(messages=[message(),candidate],fp=fp)
    assert result["classification"]=="CONFIRMED_DELIVERED"
    assert len(result["matchingCandidates"])==1


@pytest.mark.parametrize("changes,reason",[
    ({"peer_id":1},"PEER_MISMATCH"),
    ({"authenticated":False},"READBACK_NOT_AUTHENTICATED"),
    ({"complete":False},"WINDOW_INCOMPLETE"),
    ({"truncated":True},"WINDOW_TRUNCATED"),
    ({"query_succeeded":False},"QUERY_FAILED"),
    ({"query_end":SEND+timedelta(minutes=20)},"INSUFFICIENT_POST_SEND_WINDOW"),
    ({"lower_boundary_reached":False},"LOWER_BOUNDARY_NOT_PROVEN"),
])
def test_incomplete_or_wrong_readback_fails_closed(changes,reason):
    result=evaluate(**changes)
    assert result["classification"]=="STILL_UNCERTAIN" and reason in result["reasons"]


def test_positive_provider_or_existing_outbound_conflicts_fail_closed():
    accepted=operation(delivery_payload={"provider_delivery_evidence":{"accepted":True}})
    assert "POSITIVE_PROVIDER_EVIDENCE_CONFLICT" in evaluate(op=accepted)["reasons"]
    assert "OUTBOUND_ID_ALREADY_EXISTS" in evaluate(op=operation(outbound_telegram_message_id=9))["reasons"]


def test_unrelated_outgoing_media_and_messages_do_not_false_match():
    unrelated=message(7001,out=True,text="different",media_type="MessageMediaPhoto")
    result=evaluate(messages=[message(),unrelated,message(7002,text="another inbound")])
    assert result["classification"]=="CONFIRMED_NOT_DELIVERED"


def test_missing_anchor_fails_closed():
    assert "CHRONOLOGY_ANCHOR_MISSING" in evaluate(messages=[])["reasons"]


def test_attestation_is_durable_idempotent_and_does_not_mutate_operation():
    repo=Repository();service=Service(repository=repo,now=lambda:NOW);op=operation();before=dict(op)
    args=dict(operation=op,fingerprint=fingerprint(),readback=readback(),creator_profile_id=2,
      fanvue_account_id=2,relationship_key="telegram:2:2:7489120428",
      purchase_intent_id=UUID("fb2dd59d-e6b7-494a-a430-ef946b6a0b37"),resolved_by="operator")
    first=service.attest_not_delivered(**args);second=service.attest_not_delivered(**args)
    assert first["resolution"]["outcome"]=="NOT_DELIVERED" and not first["idempotent"]
    assert second["idempotent"] and op==before
    assert repo.calls[0]["provider_readback_evidence"] is True
    assert repo.calls[0]["evidence"]["attestationMethod"]==service.METHOD
