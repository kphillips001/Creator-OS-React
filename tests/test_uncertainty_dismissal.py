from copy import deepcopy
from unittest.mock import Mock
from uuid import uuid4
import pytest
from test_conversation_lifecycle_closure import inbox
from test_ordinary_generation_budget import setup, connection
from app.services.relationships_service import RelationshipsService as Service
from app.repositories.relationships_repository import RelationshipsRepository


def uncertain(**changes):
    return inbox(operation_state='SEND_UNCERTAIN', operation_last_error='UNKNOWN', **changes)


def acknowledge(row):
    before=Service._operational_projection(row)
    return {**row,'uncertainty_acknowledgements':[{'attention_reason':before['attentionReasonIdentity']}]}


def test_hidden_warning_preserves_all_non_alert_state():
    row=uncertain(control_mode='AVA_AUTO'); original=deepcopy(row)
    before=Service._operational_projection(row)
    after=Service._operational_projection(acknowledge(row))
    assert before['operationalStatus']=='DELIVERY_UNCERTAIN'
    assert after['operationalStatus']=='NONE' and after['deliveryUncertaintyAcknowledged']
    for key in ('deliveryCertainty','responseObligation','candidateCount','candidateBudgetRemaining','automaticRecoveryEligible','operationState','sendAttempts'):
        assert before[key]==after[key]
    assert after['deliveryCertainty']=='UNKNOWN' and after['operationState']=='SEND_UNCERTAIN'
    assert row==original


def test_ack_survives_new_inbound_but_not_new_uncertain_operation():
    row=acknowledge(uncertain())
    row.update(last_inbound_message_id=99)
    assert Service._operational_projection(row)['operationalStatus']=='NONE'
    row['uncertain_operations']=[{'operationId':str(row['operation_id'])},{'operationId':str(uuid4())}]
    projection=Service._operational_projection(row)
    assert projection['operationalStatus']=='DELIVERY_UNCERTAIN'
    assert [v['acknowledged'] for v in projection['uncertainOperations']]==[True,False]


@pytest.mark.parametrize('state,error',[('TERMINAL_FAILED','EMPTY_GENERATION: failure'),('SUPPRESSED','quality_corrective_retry_exhausted:CUSTOMER_QUESTION_UNANSWERED')])
def test_other_attention_projection_unchanged(state,error):
    row=inbox(operation_state=state,operation_last_error=error)
    old=Service._operational_projection(row)
    row['uncertainty_acknowledgements']=[{'attention_reason':'{"operations":["old"]}'}]
    assert Service._operational_projection(row)==old


def test_real_persistence_and_rebuild_preserve_operation_and_budget(setup):
    ordinary,budget,owner,make=setup
    op=make('Hello')
    budget_before=budget.read(op.operation_id)
    with connection() as c:
        c.execute("update ordinary_chat_reply_operations set state='SEND_UNCERTAIN',lease_expires_at=null,claim_owner=null where operation_id=%s",(op.operation_id,))
        before=c.execute('select to_jsonb(o) data from ordinary_chat_reply_operations o where operation_id=%s',(op.operation_id,)).fetchone()['data']
    row=uncertain(operation_id=op.operation_id)
    repository=RelationshipsRepository(connection_factory=connection)
    service=Service.__new__(Service);service._person=Mock();service._record_projection=Mock()
    # The service invokes only acknowledgement persistence; every outbound or
    # control operation is absent from this injected boundary.
    repository.inbox_state=Mock(return_value={420:row})
    service.messages_repository=repository
    result=service.acknowledge_attention(creator_profile_id=2,fanvue_account_id=2,telegram_user_id=420,
        occurrence_id=Service._operational_projection(row)['attentionOccurrenceId'])
    assert result['operationalStatus']=='NONE'
    with connection() as c:
        saved=c.execute("select * from conversation_attention_acknowledgements where telegram_user_id=420 and predicate_version='DELIVERY_UNCERTAIN_ACK_V1'").fetchall()
        after=c.execute('select to_jsonb(o) data from ordinary_chat_reply_operations o where operation_id=%s',(op.operation_id,)).fetchone()['data']
    assert before==after and after['state']=='SEND_UNCERTAIN'
    rebuilt={**row,'uncertainty_acknowledgements':saved}
    assert Service._operational_projection(rebuilt)['operationalStatus']=='NONE'
    assert budget.read(op.operation_id)==budget_before
    # Compile/execute the real projection SQL in the isolated schema as well.
    RelationshipsRepository(connection_factory=connection).inbox_state(creator_profile_id=2,fanvue_account_id=2)


def test_stale_occurrence_rejected_without_write():
    service=Service.__new__(Service);service._person=Mock();service.messages_repository=Mock()
    service.messages_repository.inbox_state.return_value={420:uncertain()}
    with pytest.raises(ValueError):
        service.acknowledge_attention(creator_profile_id=2,fanvue_account_id=2,telegram_user_id=420,occurrence_id='stale')
    service.messages_repository.acknowledge_attention.assert_not_called()
