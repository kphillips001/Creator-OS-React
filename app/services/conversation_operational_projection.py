"""Current causal obligation, recovery and delivery certainty for Business Chat.

Pure projection: acknowledgement changes an alert only, never delivery or budgets.
"""
from datetime import datetime, timezone
import hashlib,json
from types import SimpleNamespace
from app.services.ordinary_response_obligation_service import OrdinaryResponseObligationService


def project(inbox, *, legacy, occurrence_id):
    now=inbox.get('database_now') or datetime.now(timezone.utc)
    latest=inbox.get('last_inbound_message_id')
    causal=inbox.get('burst_freshness_telegram_message_id') or inbox.get('operation_inbound_message_id')
    # A later member of the same unresolved media turn is not a new turn.
    media_watermark=inbox.get('media_turn_member_watermark')
    if media_watermark and latest == media_watermark:
        causal=max(causal or 0,media_watermark)
    superseded=bool(latest and causal and latest>causal)
    source=dict(inbox)
    if superseded:
        for key in ('operation_state','operation_id','operation_last_error','delivery_payload',
                    'response_payload','generation_obligation','candidate_count','claim_owner',
                    'lease_expires_at','next_retry_at','scheduled_delivery_at','outbound_telegram_message_id',
                    'sent_confirmed_at','sending_at','has_response_payload','initial_started','correction_started'):
            source[key]=None
        source['inbound_message_text']=inbox.get('latest_inbound_text') or ''
        source['burst_obligations']=[];source['burst_member_obligations']=[]
    result=legacy(source)
    diagnostics=dict((source.get('response_payload') or {}).get('diagnostic_metadata') or {})
    obligation=dict(source.get('generation_obligation') or {})
    if not obligation:
        obligation=OrdinaryResponseObligationService.decide(SimpleNamespace(**{
            'delivery_payload':source.get('delivery_payload'),
            'inbound_message_text':source.get('inbound_message_text') or source.get('latest_inbound_text') or '',
            'burst_obligations':source.get('burst_obligations'),
            'burst_member_obligations':source.get('burst_member_obligations')}),diagnostics)
        if source.get('operation_has_meaningful_obligation') is True and not superseded:
            obligation['required']=True
            obligation['source']+=' + durable_member_obligation'
    state=str(source.get('operation_state') or '')
    error=str(source.get('operation_last_error') or '')
    required=bool(obligation.get('required'))
    inbound=inbox.get('last_customer_inbound_at');outbound=inbox.get('last_visible_outbound_at')
    unanswered=bool(inbound and (not outbound or inbound>outbound))
    if not unanswered or state=='SENT_CONFIRMED':
        obligation={**obligation,'required':False,'requiredBeforeResolution':required,
                    'resolvedByConfirmedOutbound':bool(outbound or state=='SENT_CONFIRMED')}
        required=False
    count=source.get('candidate_count')
    remaining=max(0,2-int(count)) if count is not None else None
    active=bool(source.get('claim_owner') and source.get('lease_expires_at') and source['lease_expires_at']>now)
    uncertainty=list(inbox.get('uncertain_operations') or [])
    if state=='SEND_UNCERTAIN' and not (inbox.get('delivery_resolution_outcome')=='DELIVERED'
            and inbox.get('delivery_resolution_provenance')=='OPERATOR_ATTESTED') and not uncertainty:
        uncertainty=[{'operationId':str(inbox.get('operation_id') or ''),'reason':error}]
    if not uncertainty and state in {'SENDING','GENERATED'} and source.get('operation_id') and not active and (state=='SENDING' or source.get('outbound_telegram_message_id') or source.get('sent_confirmed_at') or source.get('sending_at')):
        uncertainty=[{'operationId':str(source['operation_id']),'kind':'ORDINARY','reason':error}]
    dismissed=set()
    for ack in inbox.get('uncertainty_acknowledgements') or []:
        try:
            dismissed.update(json.loads(ack['attention_reason']).get('operations', []))
        except (KeyError,ValueError,TypeError):
            continue
    uncertainty=[{**item, 'acknowledged': str(item.get('operationId')) in dismissed} for item in uncertainty]
    category='NO_REPLY_REQUIRED';reason=result.get('operationalStatusReason')
    eligible=False
    if uncertainty or (state=='SENDING' and not active) or (state=='GENERATED' and not active and (source.get('outbound_telegram_message_id') or source.get('sent_confirmed_at') or source.get('sending_at'))):
        category='DELIVERY_UNCERTAIN';status='DELIVERY_UNCERTAIN'
        reason='Telegram delivery may have been accepted; automatic resend is prohibited.'
    elif result['operationalStatus'] in {'MANUAL_MODE','IGNORED'}:
        category='OPERATOR_CONTROLLED';status=result['operationalStatus']
    elif not unanswered or state=='SENT_CONFIRMED':
        status='NONE';reason=None
    elif result['operationalStatus'] in {'MEDIUM_MARKET_LIMIT','LOW_MARKET_LIMIT'}:
        category='POLICY_DEFERRED';status=result['operationalStatus']
    elif active:
        category='RECOVERY_PENDING';status='RECOVERY_PENDING';eligible=True
        reason='Current operation has an active generation or delivery claim.'
    elif (state in {'PENDING_GENERATION','GENERATING','RETRYABLE'}
          and source.get('prospective_generation_eligible') is False and not source.get('has_response_payload')):
        category='SYSTEM_INCIDENT';status='SYSTEM_INCIDENT'
        reason='Historical generation is not automatically enrolled in the new recovery budget.'
    elif state in {'PENDING_GENERATION','GENERATING'} and source.get('initial_started'):
        category='SYSTEM_INCIDENT';status='SYSTEM_INCIDENT'
        reason='A generation phase already started; automatic replay is prohibited.'
    elif state=='RETRYABLE' and error=='quality_corrective_retry_scheduled' and (
            source.get('correction_started') or remaining==0):
        if remaining==0 and required:
            category='HUMAN_ATTENTION_REQUIRED';status='NEEDS_ATTENTION'
            reason='The lifetime candidate budget is exhausted and a response obligation survives.'
        else:
            category='SYSTEM_INCIDENT';status='SYSTEM_INCIDENT'
            reason='Correction already started; automatic replay is prohibited.'
    elif result['operationalStatus'] in {'REPLY_SCHEDULED','REPLY_READY','OVERDUE'}:
        category='RECOVERY_PENDING';status=result['operationalStatus'];eligible=True
    elif state in {'PENDING_GENERATION','GENERATING','GENERATED'} and result['operationalStatus']=='NONE':
        category='RECOVERY_PENDING';status='RECOVERY_PENDING';eligible=True
        reason='Current operation is eligible for bounded automatic processing.'
    elif (state=='TERMINAL_FAILED' and not required and not active
          and not source.get('next_retry_at') and not source.get('outbound_telegram_message_id')
          and not source.get('sent_confirmed_at')
          and not dict(source.get('delivery_payload') or {}).get('transport_route')
          and error == 'TelegramPreflightError: No current Business peer reply evidence.'):
        # This typed pre-invocation recipient failure is not a continuing system
        # fault when no response obligation survives. Keep the operation/history.
        status='NONE';reason='Historical pre-invocation failure; no response obligation survives.'
        result['incidentResolution']={'authority':'CURRENT_OBLIGATION_AND_DELIVERY_CERTAINTY',
            'outcome':'NO_RESPONSE_REQUIRED','historicalOperationId':str(source.get('operation_id')),
            'historicalError':error}
    elif state=='TERMINAL_FAILED' or error.startswith(('EMPTY_GENERATION:','DECISION_ENGINE_EXCEPTION:','GENERATION_FAILURE:')):
        category='SYSTEM_INCIDENT';status='SYSTEM_INCIDENT'
        reason=error or 'Automatic reply processing failed.'
    elif state in {'RETRYABLE','GENERATING','GENERATED'}:
        category='SYSTEM_INCIDENT';status='SYSTEM_INCIDENT'
        reason=result.get('operationalStatusReason') or 'Automatic processing has no actionable recovery path.'
    elif required and not state:
        category='SYSTEM_INCIDENT';status='SYSTEM_INCIDENT'
        reason='Latest inbound has an obligation but no current response operation.'
    elif required:
        category='HUMAN_ATTENTION_REQUIRED';status='NEEDS_ATTENTION'
        reason=('Latest inbound has no current response operation.' if not state else
                'A response obligation survives and no automatic correction remains actionable.')
    else:
        status='NONE';reason='No response obligation survives.'
    result.update(operationalStatus=status,operationalStatusReason=reason,
        operationalCategory=category,responseObligation=obligation,
        projectionHistory=list(inbox.get('projection_history') or []),
        latestInboundMessageId=latest,causalOperationId=str(source['operation_id']) if source.get('operation_id') else None,
        supersededOperationId=str(inbox['operation_id']) if superseded and inbox.get('operation_id') else None,
        automaticRecoveryEligible=eligible,candidateBudgetRemaining=remaining,
        candidateCount=count,responseProviderAttempts=source.get('provider_attempt_count'),
        systemIncidentReason=error or reason if category=='SYSTEM_INCIDENT' else None,
        deliveryCertainty='UNKNOWN' if category=='DELIVERY_UNCERTAIN' else 'SENT_CONFIRMED' if state=='SENT_CONFIRMED' else 'NOT_APPLICABLE' if not source.get('operation_id') else 'NOT_CONFIRMED',
        uncertainOperations=uncertainty,operatorAlertActive=False,
        attentionOccurrenceId=None,attentionAcknowledgedAt=None,attentionAcknowledgedBy=None,
        attentionAcknowledgementId=None)
    if category in {'HUMAN_ATTENTION_REQUIRED','SYSTEM_INCIDENT','DELIVERY_UNCERTAIN'}:
        if category=='DELIVERY_UNCERTAIN':
            pending=sorted({str(item['operationId']) for item in uncertainty if not item['acknowledged']})
            material=json.dumps({'operations':pending},sort_keys=True,separators=(',',':'))
            scope=f"DELIVERY_UNCERTAIN_ACK_V1|{inbox.get('telegram_chat_id')}|{material}"
            result.update(attentionOccurrenceId=hashlib.sha256(scope.encode()).hexdigest() if pending else None,
                attentionReasonIdentity=material,operatorAlertActive=bool(pending),
                deliveryUncertaintyAcknowledged=bool(uncertainty and not pending))
            if not pending:result['operationalStatus']='NONE'
            return result
        # Include material failure and candidate disposition so a new cause alerts again.
        material=f"{category}|{reason}|{error}|{count}|{','.join(str(v.get('operationId')) for v in uncertainty)}"
        occurrence=occurrence_id(source,material)
        acknowledged=(source.get('acknowledged_occurrence_id')==occurrence and category!='DELIVERY_UNCERTAIN')
        result.update(attentionOccurrenceId=occurrence,operatorAlertActive=not acknowledged,
            attentionReasonIdentity=material,
            attentionAcknowledgedAt=source.get('acknowledged_at') if acknowledged else None,
            attentionAcknowledgedBy=source.get('acknowledged_by') if acknowledged else None,
            attentionAcknowledgementId=str(source['acknowledgement_id']) if acknowledged and source.get('acknowledgement_id') else None)
        if acknowledged:result['operationalStatus']='NONE'
    return result
