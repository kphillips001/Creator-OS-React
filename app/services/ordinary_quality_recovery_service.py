"""Explicit recovery of a typed, pre-send quality failure on its original budget."""
import json
from contextlib import contextmanager
from app.models.telegram_inbound import TelegramInboundResult
from app.repositories.ordinary_chat_reply_repository import OrdinaryChatReplyRepository
from app.repositories.ordinary_generation_budget_repository import OrdinaryGenerationBudgetRepository
from app.repositories.relationships_repository import RelationshipsRepository
from app.services.relationships_service import RelationshipsService
from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService, durable_plain_data
from app.services.ordinary_quality_rejection import recoverable_failure, normalize


class OrdinaryQualityRecoveryService:
    def __init__(self, connection_factory=None):
        self.connection_factory = connection_factory or OrdinaryChatReplyRepository().connection_factory

    def resume(self, operation_id, *, creator_profile_id, fanvue_account_id, owner):
        with self.connection_factory() as c:
            target = c.execute('SELECT telegram_chat_id FROM ordinary_chat_reply_operations WHERE operation_id=%s',
                               (operation_id,)).fetchone()
            if not target:
                raise ValueError('QUALITY_RECOVERY_OPERATION_MISSING')
            c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',
                      (f"telegram-turn:{target['telegram_chat_id']}",))
            row = c.execute('SELECT * FROM ordinary_chat_reply_operations WHERE operation_id=%s FOR UPDATE',
                            (operation_id,)).fetchone()
            b = c.execute('SELECT * FROM ordinary_generation_budgets WHERE operation_id=%s FOR UPDATE',
                          (operation_id,)).fetchone()
            if (row['state'] != 'TERMINAL_FAILED' or row['send_attempt_count'] != 0
                    or row['outbound_telegram_message_id'] or row['sending_at'] or row['sent_confirmed_at'] or row['uncertain_at']
                    or row['claim_owner'] or row['lease_expires_at'] or row['next_retry_at']
                    or not b or b['candidate_count'] != 1 or b['provider_attempt_count'] >= 3
                    or not b['initial_started'] or b['correction_started']
                    or not b['obligation'].get('required')
                    or b['context_snapshot'].get('version') != 'ORDINARY_CONTEXT_V1'
                    or not b['context_snapshot'].get('messages')):
                raise ValueError('QUALITY_RECOVERY_NOT_ELIGIBLE')
            @contextmanager
            def same():
                yield c
            inbox = RelationshipsRepository(same).inbox_state(
                creator_profile_id=creator_profile_id, fanvue_account_id=fanvue_account_id
            ).get(row['inbound_sender_telegram_user_id'])
            if not inbox:
                raise ValueError('QUALITY_RECOVERY_RELATIONSHIP_MISSING')
            projection = RelationshipsService._operational_projection(inbox)
            if (str(inbox.get('operation_id')) != str(operation_id)
                    or not projection['responseObligation']['required']
                    or any(str(item.get('operationId')) == str(operation_id)
                           or not item.get('inboundMessageId')
                           or int(item['inboundMessageId']) >= row['inbound_telegram_message_id']
                           for item in projection.get('uncertainOperations') or ())
                    or inbox.get('control_mode') != 'AVA_AUTO'
                    or inbox.get('communication_disposition') != 'ACTIVE'
                    or inbox.get('last_inbound_message_id') != row['inbound_telegram_message_id']):
                raise ValueError('QUALITY_RECOVERY_CURRENT_STATE_CHANGED')
            result = TelegramInboundResult(**b['result_snapshot'])
            if not recoverable_failure(result):
                raise ValueError('QUALITY_RECOVERY_TYPED_EVIDENCE_REQUIRED')
            result = normalize(result)
            history = {'state':row['state'], 'lastError':row['last_error'],
                       'previousMaxSendAttempts':row['max_send_attempts'],
                       'previousResult':b['result_snapshot'],
                       'failedAt':str(row['failed_at']), 'updatedAt':str(row['updated_at']),
                       'authority':'EXPLICIT_SAME_OPERATION_QUALITY_RECOVERY'}
            updated = c.execute("""UPDATE ordinary_chat_reply_operations SET state='GENERATING',
                claim_owner=%s,claimed_at=now(),lease_expires_at=now()+interval '5 minutes',max_send_attempts=1,
                delivery_payload=COALESCE(delivery_payload,'{}'::jsonb)||%s::jsonb,updated_at=now()
                WHERE operation_id=%s RETURNING *""",
                (owner,json.dumps({'qualityFailureRecoveryHistory':history}),operation_id)).fetchone()
            repository = OrdinaryChatReplyRepository(same)
            operation = repository._item(updated)
            OrdinaryGenerationBudgetRepository(same).save(operation_id,owner,
                result=durable_plain_data(result),event={'kind':'QUALITY_FAILURE_RECONCILED',**history})
            scheduled = OrdinaryChatReplyService(repository=repository,worker_id=owner,
                creator_profile_id=creator_profile_id,fanvue_account_id=fanvue_account_id).generated(operation,result)
            if not scheduled or scheduled.state.value != 'RETRYABLE':
                raise ValueError('QUALITY_RECOVERY_NOT_SCHEDULED')
            return scheduled
