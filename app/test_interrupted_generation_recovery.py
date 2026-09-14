from datetime import datetime, timedelta, timezone

from app.services.relationships_service import RelationshipsService


def inbox(**overrides):
    now=datetime.now(timezone.utc)
    value={"control_mode":"AVA_AUTO","operation_state":"GENERATING",
        "operation_id":"fixture-operation","claim_owner":"dead-worker",
        "lease_expires_at":now-timedelta(minutes=1),"database_now":now,
        "has_response_payload":False,"generation_attempt_count":2,
        "max_generation_attempts":2,"send_attempt_count":0,
        "inbound_telegram_message_id":5818,"telegram_chat_id":123,
        "last_inbound_message_id":5818,"last_customer_inbound_at":now,
        "last_visible_outbound_at":now-timedelta(minutes=1)}
    value.update(overrides)
    return value


def test_expired_exhausted_generation_projects_needs_attention():
    result=RelationshipsService._operational_projection(inbox())
    assert result["operationalStatus"]=="NEEDS_ATTENTION"
    assert result["operationalStatusReason"]==(
        "Generation was interrupted and automatic recovery is exhausted.")
    assert result["attentionOccurrenceId"]


def test_active_or_reclaimable_generation_does_not_raise_attention():
    now=datetime.now(timezone.utc)
    assert RelationshipsService._operational_projection(
        inbox(lease_expires_at=now+timedelta(minutes=1),database_now=now)
    )["operationalStatus"]=="NONE"
    assert RelationshipsService._operational_projection(
        inbox(generation_attempt_count=1)
    )["operationalStatus"]=="NONE"


def test_payload_or_send_evidence_blocks_generation_attention_projection():
    assert RelationshipsService._operational_projection(
        inbox(has_response_payload=True)
    )["operationalStatus"]=="NONE"
    assert RelationshipsService._operational_projection(
        inbox(send_attempt_count=1)
    )["operationalStatus"]=="NONE"
