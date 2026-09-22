"""Explicit, single-use revalidation of an immutable exhausted text candidate.

This only schedules the existing canonical send-only path. No generation, budget
reservation, Telegram client or automatic discovery/reopening of historical rows.
"""
import hashlib
import json
from contextlib import contextmanager
from copy import deepcopy

from app.repositories.ordinary_chat_reply_repository import OrdinaryChatReplyRepository
from app.repositories.ordinary_generation_budget_repository import OrdinaryGenerationBudgetRepository
from app.repositories.relationships_repository import RelationshipsRepository
from app.services.relationships_service import RelationshipsService
from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService, durable_plain_data
from app.services.ordinary_reply_generation_service import OrdinaryReplyGenerationService
from app.services.foreground_relevance_contract import ForegroundRelevanceContract


class OrdinaryCandidateRevalidationService:
    def __init__(self, connection_factory=None):
        self.connection_factory = connection_factory or OrdinaryChatReplyRepository().connection_factory

    def revalidate(self, operation_id, *, expected_sha256, creator_profile_id, fanvue_account_id, owner):
        with self.connection_factory() as c:
            target=c.execute('SELECT telegram_chat_id FROM ordinary_chat_reply_operations WHERE operation_id=%s',
                             (operation_id,)).fetchone()
            if not target:
                raise ValueError('REVALIDATION_OPERATION_MISSING')
            c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',
                      (f"telegram-turn:{target['telegram_chat_id']}",))
            row=c.execute('SELECT * FROM ordinary_chat_reply_operations WHERE operation_id=%s FOR UPDATE',
                          (operation_id,)).fetchone()
            b=c.execute('SELECT * FROM ordinary_generation_budgets WHERE operation_id=%s FOR UPDATE',
                        (operation_id,)).fetchone()
            if (row['state']!='SUPPRESSED' or row['last_error']!='quality_corrective_retry_exhausted:FOREGROUND_SEMANTIC_RELEVANCE'
                    or row['send_attempt_count'] or row['outbound_telegram_message_id'] or row['sending_at']
                    or row['sent_confirmed_at'] or row['uncertain_at'] or row['claim_owner']
                    or row['lease_expires_at'] or row['next_retry_at'] or not b
                    or b['candidate_count']!=2 or not b['correction_started'] or not b['initial_started']
                    or b['provider_attempt_count']>3 or not b['obligation'].get('required')
                    or any(e.get('kind')=='EXISTING_CANDIDATE_REVALIDATION' for e in b['events'])):
                raise ValueError('REVALIDATION_NOT_ELIGIBLE')
            text=row['response_text']
            digest=hashlib.sha256(text.encode()).hexdigest()
            if (digest!=expected_sha256 or digest!=row['response_content_sha256']
                    or any(r.get('response_text')!=text or r.get('delivery_payload',{}).get('message_text')!=text
                           for r in (row['response_payload'],b['result_snapshot']))
                    or row['delivery_payload'].get('message_text')!=text):
                raise ValueError('REVALIDATION_CANDIDATE_MISMATCH')
            if (b['context_snapshot'].get('version')!='ORDINARY_CONTEXT_V1'
                    or not b['context_snapshot'].get('messages')
                    or b['context_snapshot'].get('userMessage',row['inbound_message_text'])!=row['inbound_message_text']):
                raise ValueError('REVALIDATION_CONTEXT_MISSING')
            @contextmanager
            def same():
                yield c
            inbox=RelationshipsRepository(same).inbox_state(
                creator_profile_id=creator_profile_id,fanvue_account_id=fanvue_account_id
            ).get(row['inbound_sender_telegram_user_id'])
            projection=RelationshipsService._operational_projection(inbox) if inbox else {}
            if (not inbox or str(inbox.get('operation_id'))!=str(operation_id)
                    or projection.get('operationalStatus')!='NEEDS_ATTENTION'
                    or not projection.get('responseObligation',{}).get('required')
                    or projection.get('uncertainOperations') or inbox.get('control_mode')!='AVA_AUTO'
                    or inbox.get('communication_disposition')!='ACTIVE'
                    or inbox.get('last_inbound_message_id')!=row['inbound_telegram_message_id']):
                raise ValueError('REVALIDATION_CURRENT_STATE_CHANGED')
            repository=OrdinaryChatReplyRepository(same)
            operation=repository._item(row)
            correction=deepcopy(row['delivery_payload'].get('qualityCorrectiveRetry') or {})
            # Only the repaired failure is cleared; every other reason survives.
            correction['blockingReasons']=['FOREGROUND_SEMANTIC_RELEVANCE']
            result=OrdinaryReplyGenerationService.validate_saved_candidate(operation,b,correction,text)
            history={'kind':'EXISTING_CANDIDATE_REVALIDATION','ruleVersion':ForegroundRelevanceContract.VERSION,
                     'sha256':digest,'newCandidates':0,'newProviderCalls':0,
                     'previousMaxSendAttempts':row['max_send_attempts'],
                     'previousState':row['state'],'previousError':row['last_error'],
                     'previousResult':b['result_snapshot'],'previousCorrection':row['delivery_payload'].get('qualityCorrectiveRetry')}
            delivery=deepcopy(row['delivery_payload'])
            delivery['qualityCorrectiveRetry']={**delivery.get('qualityCorrectiveRetry',{}),
                'required':False,'completedBy':'EXISTING_CANDIDATE_REVALIDATION'}
            updated=c.execute("""UPDATE ordinary_chat_reply_operations SET state='GENERATING',
                claim_owner=%s,claimed_at=now(),lease_expires_at=now()+interval '5 minutes',
                scheduled_delivery_at=now()+interval '15 seconds',max_send_attempts=1,
                delivery_payload=%s::jsonb,updated_at=now()
                WHERE operation_id=%s RETURNING *""",(owner,json.dumps(delivery),operation_id)).fetchone()
            budget=OrdinaryGenerationBudgetRepository(same)
            budget.save(operation_id,owner,event=history)
            final=OrdinaryChatReplyService(repository=repository,worker_id=owner,
                creator_profile_id=creator_profile_id,fanvue_account_id=fanvue_account_id).generated(repository._item(updated),result)
            if (not final or final.state.value!='RETRYABLE' or final.response_text!=text
                    or final.response_content_sha256!=digest):
                raise ValueError('REVALIDATION_FINAL_GATE_FAILED:'+str(getattr(final,'last_error',None)))
            after=budget.read(operation_id)
            for key in ('candidate_count','provider_attempt_count','initial_started','correction_started','context_snapshot'):
                if after[key]!=b[key]:
                    raise ValueError('REVALIDATION_BUDGET_CHANGED')
            return final
