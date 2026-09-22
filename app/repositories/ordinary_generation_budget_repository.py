"""Lifetime accounting independent of resettable ordinary generation claims."""
import json
from contextlib import contextmanager

from app.repositories.ordinary_chat_reply_repository import OrdinaryChatReplyRepository


class GenerationBudgetClosed(RuntimeError):
    pass


class OrdinaryGenerationBudgetRepository:
    def __init__(self, connection_factory=None):
        self.connection_factory = connection_factory or OrdinaryChatReplyRepository().connection_factory

    @contextmanager
    def locked(self, operation_id, owner):
        with self.connection_factory() as c:
            op = c.execute("""SELECT * FROM ordinary_chat_reply_operations
                WHERE operation_id=%s FOR UPDATE""", (operation_id,)).fetchone()
            if (not op or op['state'] != 'GENERATING' or op['claim_owner'] != owner
                    or not op['lease_expires_at']):
                raise GenerationBudgetClosed('GENERATION_OWNERSHIP_LOST')
            if op.get('causal_operation_id') or op.get('recovery_parent_operation_id'):
                authority = (op.get('delivery_payload') or {}).get('controlledFreshResponse') or {}
                reconciled = (authority.get('version') in {'ZERO_CANDIDATE_SNAPSHOT_REPAIR_V1', 'TEXT_CONTRACT_FOLLOWUP_V2'}
                    and str(op.get('causal_operation_id')) == str(op.get('recovery_parent_operation_id'))
                    and authority.get('failedOperationId') == str(op.get('causal_operation_id')))
                parent = c.execute('''SELECT p.*,b.candidate_count,b.provider_attempt_count,b.correction_started,
                    b.context_snapshot,b.obligation FROM ordinary_chat_reply_operations p
                    JOIN ordinary_generation_budgets b USING(operation_id) WHERE p.operation_id=%s''',
                    (op.get('causal_operation_id'),)).fetchone() if reconciled else None
                followup = bool(parent and authority.get('version') == 'TEXT_CONTRACT_FOLLOWUP_V2'
                    and OrdinaryChatReplyRepository.controlled_contract_followup_parent(parent, parent))
                if not followup and (not parent or parent['state'] != 'TERMINAL_FAILED' or parent['send_attempt_count']
                        or parent['response_text'] or parent['candidate_count'] or parent['provider_attempt_count']):
                    raise GenerationBudgetClosed('LEGACY_OPERATION_REQUIRES_EXPLICIT_BUDGET_RECONCILIATION')
            valid = c.execute("""SELECT lease_expires_at>now() AS valid
                FROM ordinary_chat_reply_operations WHERE operation_id=%s""", (operation_id,)).fetchone()
            if not valid['valid']:
                raise GenerationBudgetClosed('GENERATION_LEASE_EXPIRED')
            stale = c.execute("""SELECT EXISTS(SELECT 1 FROM telegram_private_inbound_messages
                WHERE telegram_chat_id=%s AND telegram_message_id>%s)
                OR EXISTS(SELECT 1 FROM ordinary_chat_reply_operations WHERE telegram_chat_id=%s
                  AND inbound_telegram_message_id>%s AND operation_id<>%s) AS stale""",
                (op['telegram_chat_id'], op.get('burst_freshness_telegram_message_id') or op['inbound_telegram_message_id'],
                 op['telegram_chat_id'], op.get('burst_freshness_telegram_message_id') or op['inbound_telegram_message_id'], operation_id)).fetchone()
            if stale['stale']:
                raise GenerationBudgetClosed('NEWER_INBOUND_SUPERSEDES_OBLIGATION')
            c.execute("""INSERT INTO ordinary_generation_budgets(operation_id)
                SELECT o.operation_id FROM ordinary_chat_reply_operations o, ordinary_generation_policy p
                WHERE o.operation_id=%s AND o.created_at>=p.installed_at
                  AND o.generation_attempt_count=1 AND o.send_attempt_count=0
                  AND o.causal_operation_id IS NULL AND o.recovery_parent_operation_id IS NULL
                  AND NOT (COALESCE(o.delivery_payload,'{}') ?| ARRAY[
                    'approvedHistoricalCorrection','canonicalNotDeliveredCorrection','historicalSurvivorReconciliation'])
                ON CONFLICT DO NOTHING""", (operation_id,))
            row = c.execute('SELECT * FROM ordinary_generation_budgets WHERE operation_id=%s FOR UPDATE',
                            (operation_id,)).fetchone()
            if row is None:
                raise GenerationBudgetClosed('LEGACY_OPERATION_REQUIRES_EXPLICIT_BUDGET_RECONCILIATION')
            yield c, row

    def read(self, operation_id):
        with self.connection_factory() as c:
            return c.execute('SELECT * FROM ordinary_generation_budgets WHERE operation_id=%s',
                             (operation_id,)).fetchone()

    def reserve_analysis(self, operation_id, owner, provider, purpose="ANALYSIS"):
        with self.locked(operation_id, owner) as (c, row):
            attempts = [e for e in row['events'] if e.get('kind') == 'ANALYSIS_STARTED']
            if row['correction_started'] or len(attempts) >= 5:
                raise GenerationBudgetClosed('ANALYSIS_BUDGET_EXHAUSTED')
            attempt = len(attempts)+1
            event = {'kind': 'ANALYSIS_STARTED', 'attempt': attempt, 'provider': provider, 'sdkRetries': 0, 'purpose': purpose,
                     'purposeAttempt': 1+sum(e.get('purpose') == purpose for e in attempts)}
            c.execute('UPDATE ordinary_generation_budgets SET events=events||%s::jsonb WHERE operation_id=%s',
                      (json.dumps([event]), operation_id))
            return attempt

    def begin(self, operation_id, owner, obligation, *, correction=False):
        with self.locked(operation_id, owner) as (c, row):
            key = 'correction_started' if correction else 'initial_started'
            if row[key] or (not correction and row['candidate_count']):
                raise GenerationBudgetClosed('PIPELINE_ALREADY_STARTED_NO_REPLAY')
            if correction and (not obligation['required'] or row['candidate_count'] != 1
                               or not row['result_snapshot']):
                raise GenerationBudgetClosed('CORRECTION_NOT_AUTHORIZED')
            c.execute(f'UPDATE ordinary_generation_budgets SET {key}=true, obligation=%s::jsonb, updated_at=now() WHERE operation_id=%s',
                      (json.dumps(obligation), operation_id))
            return {**row, key: True, 'obligation': obligation}

    def save(self, operation_id, owner, *, context=None, result=None, obligation=None, event=None):
        with self.locked(operation_id, owner) as (c, row):
            c.execute('''UPDATE ordinary_generation_budgets SET context_snapshot=%s::jsonb,
                result_snapshot=%s::jsonb,obligation=%s::jsonb,events=events||%s::jsonb,updated_at=now()
                WHERE operation_id=%s''', (json.dumps(context if context is not None else row['context_snapshot']),
                json.dumps(result if result is not None else row['result_snapshot']),
                json.dumps(obligation if obligation is not None else row['obligation']),
                json.dumps([event] if event else []), operation_id))

    def record_deterministic_candidate(self, operation_id, owner):
        with self.locked(operation_id, owner) as (c, row):
            if row['candidate_count'] != 0:
                raise GenerationBudgetClosed('INITIAL_CANDIDATE_ALREADY_ACCOUNTED')
            c.execute('''UPDATE ordinary_generation_budgets SET candidate_count=1,
                events=events||%s::jsonb,updated_at=now() WHERE operation_id=%s''',
                (json.dumps([{'kind': 'DETERMINISTIC_CANDIDATE', 'candidateNumber': 1,
                              'providerRequests': 0}]), operation_id))

    def reserve_provider(self, operation_id, owner, *, provider, correction):
        with self.locked(operation_id, owner) as (c, row):
            events = row['events']
            started = [e for e in events if e.get('kind') == 'PROVIDER_STARTED']
            finished = {e.get('attempt') for e in events if e.get('kind') == 'PROVIDER_FINISHED'}
            if any(e['attempt'] not in finished for e in started):
                raise GenerationBudgetClosed('PROVIDER_OUTCOME_NOT_DURABLE_NO_REPLAY')
            phase = 'CORRECTION' if correction else 'INITIAL'
            phase_attempts = sum(e.get('phase') == phase for e in started)
            if (row['candidate_count'] >= (2 if correction else 1)
                    or row['provider_attempt_count'] >= 3
                    or phase_attempts >= (1 if correction else 2)):
                raise GenerationBudgetClosed('PROVIDER_OR_CANDIDATE_BUDGET_EXHAUSTED')
            attempt = row['provider_attempt_count'] + 1
            event = {'kind': 'PROVIDER_STARTED', 'attempt': attempt, 'provider': provider,
                     'phase': phase, 'sdkRetries': 0, 'fallback': phase_attempts > 0}
            c.execute('''UPDATE ordinary_generation_budgets SET provider_attempt_count=%s,
                events=events||%s::jsonb,updated_at=now() WHERE operation_id=%s''',
                (attempt, json.dumps([event]), operation_id))
            return attempt

    def finish_provider(self, operation_id, owner, attempt, *, text='', error=None, usage=None):
        with self.locked(operation_id, owner) as (c, row):
            if any(e.get('kind') == 'PROVIDER_FINISHED' and e.get('attempt') == attempt for e in row['events']):
                raise GenerationBudgetClosed('PROVIDER_COMPLETION_ALREADY_RECORDED')
            if not any(e.get('kind') == 'PROVIDER_STARTED' and e.get('attempt') == attempt for e in row['events']):
                raise GenerationBudgetClosed('PROVIDER_ATTEMPT_NOT_RESERVED')
            candidate = row['candidate_count'] + bool(str(text).strip())
            event = {'kind': 'PROVIDER_FINISHED', 'attempt': attempt,
                     'candidateNumber': candidate if str(text).strip() else None,
                     'outcome': 'CANDIDATE' if str(text).strip() else 'ERROR' if error else 'EMPTY',
                     'errorType': error, 'usage': usage}
            c.execute('''UPDATE ordinary_generation_budgets SET candidate_count=%s,
                events=events||%s::jsonb,updated_at=now() WHERE operation_id=%s''',
                (candidate, json.dumps([event]), operation_id))
            return candidate
