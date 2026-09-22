"""Sanitized Session 1 regressions; real durable claims, fake provider only."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
import os
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
import pytest

from app.models.telegram_inbound import TelegramInboundPayload, TelegramInboundResult
from app.repositories.ordinary_chat_reply_repository import OrdinaryChatReplyRepository
from app.repositories.ordinary_generation_budget_repository import OrdinaryGenerationBudgetRepository, GenerationBudgetClosed
from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService
from app.services.ordinary_generation_context import current_generation, generation_scope, OrdinaryGenerationSession, EmptyProviderResponse
from app.services.ordinary_reply_generation_service import OrdinaryReplyGenerationService
from app.services.ordinary_response_obligation_service import OrdinaryResponseObligationService as Obligations
from app.services.gpt_service import GPTService
from app.testing.postgres_safety import require_isolated_test_database_url


@contextmanager
def connection():
    url = require_isolated_test_database_url(os.environ['TEST_DATABASE_URL'], os.environ.get('CREATOR_OS_PRODUCTION_DATABASE_URL') or os.environ['DATABASE_URL'])
    with psycopg.connect(url, row_factory=dict_row) as c:
        yield c


class Provider:
    def __init__(self, *outputs):
        self.outputs = iter(outputs)
        self.calls = []
        self.options = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def with_options(self, **kwargs):
        self.options.append(kwargs)
        return self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        value = next(self.outputs)
        if isinstance(value, Exception):
            raise value
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=value))], usage=None)


@pytest.fixture
def setup():
    ordinary = OrdinaryChatReplyRepository(connection_factory=connection)
    budget = OrdinaryGenerationBudgetRepository(connection)
    owner = str(uuid4())
    def make(text='Hey', obligations=(), *, chat=None, message=100):
        chat = chat or -(uuid4().int % 100000000000)
        op, _ = ordinary.get_or_create(account_scope='SESSION1_TEST', chat_id=chat,
            inbound_message_id=message, sender_user_id=abs(chat), correlation_id=str(uuid4()),
            inbound_message_text=text, turn_obligations=obligations)
        return ordinary.claim_generation(op.operation_id, owner=owner)
    return ordinary, budget, owner, make


def result(op, text, reasons=()):
    return TelegramInboundResult(correlation_id=op.correlation_id, telegram_chat_id=op.telegram_chat_id,
        telegram_user_id=op.inbound_sender_telegram_user_id, message_id=op.inbound_telegram_message_id,
        engine_user_id='sanitized', response_text=text, offer_authorized=False, offer_link=None,
        blocked=False, error_code=None, delivery_type='MESSAGE_TEXT',
        delivery_payload={'type': 'MESSAGE_TEXT', 'message_text': text},
        diagnostic_metadata={'conversationQualityReasons': list(reasons),
            'conversationStyle': {'turnObligations': list(Obligations.decide(op)['obligations'])}})


def pipeline(op, provider, reasons=(), nested=0):
    def initial(payload):
        session = current_generation()
        session.snapshot({'version': 'ORDINARY_CONTEXT_V1', 'model': 'fake', 'provider': 'OPENAI',
            'messages': [{'role': 'system', 'content': 'Preserve safety and facts.'},
                         {'role': 'user', 'content': op.inbound_message_text}],
            'pressure': {}, 'recentResponses': [], 'newRelationship': False,
            'userMemory': {'semanticClassification': 'retained', 'salesDecision': 'CONVERSATION_ONLY'}})
        response = GPTService._response_completion(provider, provider='OPENAI', model='fake', messages=[])
        for _ in range(nested):
            GPTService._response_completion(provider, provider='OPENAI', model='fake', messages=[])
        return result(op, response.choices[0].message.content, reasons)
    return initial


def run_first(setup, op, provider, reasons=(), nested=0):
    ordinary, budget, owner, _ = setup
    authorize = Mock()
    service = OrdinaryReplyGenerationService(budget, authorize=authorize, client_factory=lambda _: provider)
    initial = Mock(side_effect=pipeline(op, provider, reasons, nested))
    output = service.execute(op, None, owner=owner, initial=initial)
    return service, output, initial, authorize


def claim_correction(setup, op, output):
    ordinary, budget, owner, _ = setup
    lifecycle = OrdinaryChatReplyService(repository=ordinary, worker_id=owner)
    scheduled = lifecycle.generated(op, output)
    assert scheduled.state.value == 'RETRYABLE'
    with connection() as c:
        c.execute('UPDATE ordinary_chat_reply_operations SET next_retry_at=now() WHERE operation_id=%s', (op.operation_id,))
    return lifecycle, ordinary.claim_generation(op.operation_id, owner=owner)


@pytest.mark.parametrize('text,kind', [('Would you like me to make breakfast?', 'ANSWER_DIRECT_QUESTION'),
    ('Hey','RESPOND_TO_GREETING'),('You look beautiful','ACKNOWLEDGE_COMPLIMENT')])
def test_canonical_obligations_override_negative_attention(text, kind):
    op = SimpleNamespace(inbound_message_text=text, delivery_payload={'attentionInvestment': {'meaningfulObligation': False}})
    decision = Obligations.decide(op)
    assert decision['required'] and kind in decision['obligations']
    assert decision['contradictionResolved'] and decision['version']
    assert not Obligations.decide(op, fresh=False)['required']


def test_optional_turn_has_no_obligation():
    assert not Obligations.decide(SimpleNamespace(inbound_message_text='lol', delivery_payload={}))['required']


@pytest.mark.parametrize('nested', [0,1,3,10])
def test_nested_rewrites_never_create_extra_candidates(setup, nested):
    _, budget, _, make = setup
    op = make()
    provider = Provider('Hey there!')
    _, output, initial, _ = run_first(setup, op, provider, nested=nested)
    assert len(provider.calls) == 1
    assert budget.read(op.operation_id)['candidate_count'] == 1
    assert provider.options == [{'max_retries': 0}]
    assert initial.call_count == 1


def test_novi_greeting_manufactured_question_single_lightweight_correction(setup):
    ordinary, budget, owner, make = setup
    op = make('Hey', ['RESPOND_TO_GREETING'])
    provider = Provider('Hey! What keeps you entertained?', 'Hey there, good to hear from you.')
    service, first, initial, authorize = run_first(setup, op, provider, ['MANUFACTURED_ENGAGEMENT_QUESTION'])
    lifecycle, second_op = claim_correction(setup, op, first)
    second = service.execute(second_op, None, owner=owner, initial=initial)
    final = lifecycle.generated(second_op, second)
    assert final.state.value == 'GENERATED'
    assert initial.call_count == 1 and authorize.call_count == 2
    assert len(provider.calls) == 2 and budget.read(op.operation_id)['candidate_count'] == 2
    assert second.diagnostic_metadata['ordinaryGeneration']['contextSnapshotReused']
    assert provider.calls[1]['messages'][0] == {'role':'system','content':'Preserve safety and facts.'}


@pytest.mark.parametrize('reason,text', [('FINAL_REPETITION_FAILURE','How are you?'),
                                      ('MANUFACTURED_ENGAGEMENT_QUESTION','Hey')])
def test_eric_or_second_manufactured_failure_has_no_candidate_three(setup, reason, text):
    _, budget, owner, make = setup
    op = make(text)
    candidate = "What would you like to talk about?"
    provider = Provider(candidate, candidate)
    service, first, initial, _ = run_first(setup, op, provider, [reason])
    lifecycle, op2 = claim_correction(setup, op, first)
    second = service.execute(op2, None, owner=owner, initial=initial)
    final = lifecycle.generated(op2, second)
    assert final.state.value == 'SUPPRESSED'
    with pytest.raises(GenerationBudgetClosed):
        service.execute(op2, None, owner=owner, initial=initial)
    assert budget.read(op.operation_id)['candidate_count'] == 2 and len(provider.calls) == 2


def test_no_obligation_block_has_zero_extra_calls(setup):
    ordinary, budget, owner, make = setup
    op = make('lol')
    provider = Provider('What do you like most?')
    _, output, _, _ = run_first(setup, op, provider, ['MANUFACTURED_ENGAGEMENT_QUESTION'], nested=6)
    final = OrdinaryChatReplyService(repository=ordinary, worker_id=owner).generated(op, output)
    assert final.state.value == 'SUPPRESSED'
    assert final.next_retry_at is None and len(provider.calls) == 1
    assert budget.read(op.operation_id)['obligation']['required'] is False


@pytest.mark.parametrize('outputs,expected', [(('', ''),0), ((TimeoutError(), 'Hello'),1),
    ((TimeoutError(), TimeoutError()),0), (('', 'Hello'),1)])
def test_johnny_provider_resilience_is_two_calls_not_five_pipelines(setup, outputs, expected):
    ordinary, budget, owner, make = setup
    op = make('How are you?')
    budget.begin(op.operation_id, owner, Obligations.decide(op))
    session = OrdinaryGenerationSession(budget, op, owner)
    provider = Provider(*outputs)
    with generation_scope(session):
        call = lambda: GPTService._response_completion(provider, provider='OPENAI', model='fake', messages=[])
        try:
            GPTService._execute_provider_completion(selected_provider='OPENAI', primary_complete=call,
                fallback_complete=call, provider_preview={}, logger=Mock())
        except (TimeoutError, EmptyProviderResponse):
            ordinary.fail_generation(op.operation_id, owner=owner, reason='EMPTY_GENERATION')
    row = budget.read(op.operation_id)
    assert row['candidate_count'] == expected and row['provider_attempt_count'] == 2
    assert len(provider.calls) == 2 and all(v == {'max_retries':0} for v in provider.options)
    if not expected:
        assert ordinary.get(op.operation_id).state.value == 'TERMINAL_FAILED'
        assert ordinary.claim_generation(op.operation_id, owner=owner) is None


def test_grok_fallback_identity_is_durable(setup):
    _, budget, owner, make = setup
    op = make()
    budget.begin(op.operation_id, owner, Obligations.decide(op))
    session = OrdinaryGenerationSession(budget, op, owner)
    grok, openai = Provider(TimeoutError()), Provider('Hey!')
    with generation_scope(session):
        GPTService._execute_provider_completion(selected_provider='GROK',
            primary_complete=lambda: session.complete(grok, provider='GROK'),
            fallback_complete=lambda: session.complete(openai, provider='OPENAI'), provider_preview={}, logger=Mock())
    started = [e for e in budget.read(op.operation_id)['events'] if e['kind']=='PROVIDER_STARTED']
    assert [(e['provider'],e['fallback']) for e in started] == [('GROK',False),('OPENAI',True)]


@pytest.mark.parametrize('text', ['Good morning', 'You look beautiful'])
def test_richard_joseph_engine_failure_never_reenters_pipeline(setup, text):
    ordinary, budget, owner, make = setup
    op = make(text)
    op = replace(op, delivery_payload={'attentionInvestment':{'meaningfulObligation':False}})
    initial = Mock(side_effect=RuntimeError('sanitized engine failure'))
    service = OrdinaryReplyGenerationService(budget, authorize=Mock())
    with pytest.raises(RuntimeError):
        service.execute(op, None, owner=owner, initial=initial)
    ordinary.fail_generation(op.operation_id, owner=owner, reason='DECISION_ENGINE_EXCEPTION')
    assert ordinary.claim_generation(op.operation_id, owner=owner) is None
    row = budget.read(op.operation_id)
    assert row['candidate_count'] == 0 and row['obligation']['required']
    assert initial.call_count == 1


def test_restart_cannot_reset_lifetime_budget(setup):
    ordinary, budget, owner, make = setup
    op = make()
    _, _, initial, _ = run_first(setup, op, Provider('Hey!'))
    with connection() as c:
        c.execute('UPDATE ordinary_chat_reply_operations SET generation_attempt_count=0 WHERE operation_id=%s', (op.operation_id,))
    restarted = OrdinaryReplyGenerationService(OrdinaryGenerationBudgetRepository(connection), authorize=Mock())
    with pytest.raises(GenerationBudgetClosed, match='ALREADY_STARTED'):
        restarted.execute(op, None, owner=owner, initial=initial)
    assert initial.call_count == 1 and budget.read(op.operation_id)['candidate_count'] == 1


def test_provider_crash_window_never_resends_request(setup):
    _, budget, owner, make = setup
    op = make()
    budget.begin(op.operation_id, owner, Obligations.decide(op))
    budget.reserve_provider(op.operation_id, owner, provider='OPENAI', correction=False)
    with pytest.raises(GenerationBudgetClosed, match='OUTCOME_NOT_DURABLE'):
        budget.reserve_provider(op.operation_id, owner, provider='OPENAI', correction=False)
    assert budget.read(op.operation_id)['candidate_count'] == 0


def test_concurrent_claims_allow_one_provider_invocation(setup):
    _, budget, owner, make = setup
    op = make()
    budget.begin(op.operation_id, owner, Obligations.decide(op))
    def reserve(_):
        try: return budget.reserve_provider(op.operation_id, owner, provider='OPENAI', correction=False)
        except GenerationBudgetClosed: return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(reserve, range(4)))
    assert outcomes.count(1) == 1 and outcomes.count(None) == 3


def test_newer_inbound_blocks_correction(setup):
    _, budget, owner, make = setup
    op = make()
    service, first, initial, _ = run_first(setup, op, Provider('What else?'), ['MANUFACTURED_ENGAGEMENT_QUESTION'])
    _, second = claim_correction(setup, op, first)
    make('Newer turn', chat=op.telegram_chat_id, message=101)
    with pytest.raises(GenerationBudgetClosed, match='NEWER_INBOUND'):
        service.execute(second, None, owner=owner, initial=initial)
    assert budget.read(op.operation_id)['candidate_count'] == 1


def test_current_authorization_blocks_correction_before_provider(setup):
    _, budget, owner, make = setup
    op = make()
    provider = Provider('What else?')
    service, first, initial, authorize = run_first(setup, op, provider, ['MANUFACTURED_ENGAGEMENT_QUESTION'])
    _, second = claim_correction(setup, op, first)
    authorize.side_effect = PermissionError('Manual takeover')
    with pytest.raises(PermissionError):
        service.execute(second, None, owner=owner, initial=initial)
    assert len(provider.calls) == 1


def test_analysis_sdk_retries_disabled_and_correction_has_no_analysis(setup):
    _, budget, owner, make = setup
    op = make()
    budget.begin(op.operation_id, owner, Obligations.decide(op))
    session = OrdinaryGenerationSession(budget, op, owner)
    provider = Provider(*(['{}']*5))
    for _ in range(5):
        session.analysis(provider, provider='OPENAI')
    with pytest.raises(GenerationBudgetClosed, match='ANALYSIS_BUDGET'):
        session.analysis(provider, provider='OPENAI')
    assert budget.read(op.operation_id)['candidate_count'] == 0
    assert len(provider.calls) == 5 and provider.options == [{'max_retries':0}]*5


def test_full_gpt_pipeline_cannot_issue_independent_rewrites(setup):
    _, budget, owner, make = setup
    op = make('Hey')
    budget.begin(op.operation_id, owner, Obligations.decide(op))
    provider = Provider('What keeps you entertained?')
    training = SimpleNamespace(runtime_prompt_block=lambda **kwargs: '')
    gpt = GPTService(api_key='isolated-test', global_training_service=training)
    gpt.openai_client = provider
    memory = {'creator_profile': {'id': 2, 'persona_name': 'Ava', 'system_prompt': 'Stay natural.'}}
    with generation_scope(OrdinaryGenerationSession(budget, op, owner)):
        gpt.generate_response('default', 'casual', 'Hey', memory, False, chat_history=[])
    assert len(provider.calls) == 1
    assert budget.read(op.operation_id)['context_snapshot']['version'] == 'ORDINARY_CONTEXT_V1'
    assert budget.read(op.operation_id)['candidate_count'] == 1


def test_deterministic_support_shortcut_has_zero_response_calls(setup):
    _, budget, owner, make = setup
    op = make('The payment link is not working')
    budget.begin(op.operation_id, owner, Obligations.decide(op))
    gpt = GPTService(api_key='isolated-test', global_training_service=SimpleNamespace(runtime_prompt_block=lambda **kwargs: ''))
    provider = Provider()
    gpt.openai_client = provider
    with generation_scope(OrdinaryGenerationSession(budget, op, owner)):
        text = gpt.generate_response('default','casual',op.inbound_message_text,{},False)
    assert text == 'Let me check into it.'
    assert not provider.calls and budget.read(op.operation_id)['candidate_count'] == 0


def test_legacy_operation_not_enrolled_or_claimed(setup):
    ordinary, budget, owner, make = setup
    op = make()
    with connection() as c:
        c.execute('DELETE FROM ordinary_generation_budgets WHERE operation_id=%s', (op.operation_id,))
        c.execute("UPDATE ordinary_chat_reply_operations SET state='PENDING_GENERATION',generation_attempt_count=0,created_at='2020-01-01' WHERE operation_id=%s",(op.operation_id,))
    assert ordinary.claim_generation(op.operation_id, owner=owner) is None
    assert budget.read(op.operation_id) is None


def test_recovery_descendant_cannot_receive_fresh_budget(setup):
    ordinary, budget, owner, make = setup
    parent = make()
    child = make()
    with connection() as c:
        c.execute("UPDATE ordinary_chat_reply_operations SET operation_kind='HISTORICAL_CORRECTIVE',causal_operation_id=%s,recovery_attention_occurrence_id='sanitized',recovery_resolution_plan_id=%s,recovery_idempotency_key=%s WHERE operation_id=%s",(parent.operation_id,uuid4(),str(uuid4()),child.operation_id))
    with pytest.raises(GenerationBudgetClosed, match='LEGACY_OPERATION'):
        budget.begin(child.operation_id, owner, Obligations.decide(child))


def test_provider_ack_persistence_failure_stops_all_fallback(setup, monkeypatch):
    _, budget, owner, make = setup
    op = make()
    budget.begin(op.operation_id, owner, Obligations.decide(op))
    session = OrdinaryGenerationSession(budget,op,owner)
    provider = Provider('Hey there!')
    original = budget.finish_provider
    monkeypatch.setattr(budget,'finish_provider',Mock(side_effect=RuntimeError('persistence failed')))
    with pytest.raises(RuntimeError):
        session.complete(provider,provider='OPENAI')
    monkeypatch.setattr(budget,'finish_provider',original)
    with pytest.raises(GenerationBudgetClosed,match='OUTCOME_NOT_DURABLE'):
        session.complete(provider,provider='OPENAI')
    assert len(provider.calls) == 1


def test_crash_before_pipeline_can_resume_once_without_reset(setup):
    ordinary, budget, owner, make = setup
    op = make()
    with connection() as c:
        c.execute("UPDATE ordinary_chat_reply_operations SET lease_expires_at=now()-interval '1 second' WHERE operation_id=%s", (op.operation_id,))
    resumed = ordinary.claim_generation(op.operation_id, owner=owner)
    assert resumed.generation_attempt_count == 2
    provider = Provider('Hey there!')
    run_first(setup, resumed, provider)
    assert len(provider.calls) == 1 and budget.read(op.operation_id)['candidate_count'] == 1


@pytest.mark.parametrize('column,value', [('candidate_count',3),('provider_attempt_count',4)])
def test_database_enforces_hard_budget_constraints(setup, column, value):
    _, _, _, make = setup
    op = make()
    with pytest.raises(psycopg.errors.CheckViolation):
        with connection() as c:
            c.execute(f'UPDATE ordinary_generation_budgets SET {column}=%s WHERE operation_id=%s',(value,op.operation_id))


def test_new_ledger_is_registered_with_schema_governance():
    from app.services.schema_manager_service import SchemaManagerService
    manager = SchemaManagerService(connection_factory=connection)
    report = manager.reconcile_one('20260920_148_ordinary_generation_budget.sql')
    assert report.status == 'PASS', report.drift


def test_lifetime_counts_cannot_be_reset_in_database(setup):
    _, budget, owner, make = setup
    op = make()
    run_first(setup, op, Provider('Hey!'))
    for change in ('candidate_count=0','provider_attempt_count=0','initial_started=false'):
        with pytest.raises(psycopg.errors.CheckViolation):
            with connection() as c:
                c.execute(f'UPDATE ordinary_generation_budgets SET {change} WHERE operation_id=%s',(op.operation_id,))
    assert budget.read(op.operation_id)['candidate_count'] == 1


def test_crash_claims_do_not_consume_correction_candidate(setup):
    ordinary, budget, owner, make = setup
    op = make('Hey')
    with connection() as c:
        c.execute("UPDATE ordinary_chat_reply_operations SET lease_expires_at=now()-interval '1 second' WHERE operation_id=%s", (op.operation_id,))
    resumed = ordinary.claim_generation(op.operation_id, owner=owner)
    provider = Provider('What else?', 'Hey there, good to hear from you.')
    service, output, initial, _ = run_first(setup, resumed, provider, ['MANUFACTURED_ENGAGEMENT_QUESTION'])
    lifecycle, correction = claim_correction(setup, resumed, output)
    corrected = service.execute(correction,None,owner=owner,initial=initial)
    assert lifecycle.generated(correction,corrected).state.value == 'GENERATED'
    assert correction.generation_attempt_count == 3
    assert budget.read(op.operation_id)['candidate_count'] == 2
    assert initial.call_count == 1


def test_actual_intent_classifier_uses_explicit_analysis_budget(setup):
    from app.services.gpt_intent_classifier_service import GPTIntentClassifierService
    _, budget, owner, make = setup
    op = make()
    budget.begin(op.operation_id,owner,Obligations.decide(op))
    classifier = GPTIntentClassifierService(api_key='isolated-test')
    provider = Provider('not json','{}')
    classifier.client = provider
    with generation_scope(OrdinaryGenerationSession(budget,op,owner)):
        classifier.classify_message('Hey')
    assert len(provider.calls) == 2
    assert provider.options == [{'max_retries':0}]*2
    events = budget.read(op.operation_id)['events']
    assert sum(e['kind']=='ANALYSIS_STARTED' for e in events) == 2
    assert budget.read(op.operation_id)['candidate_count'] == 0


def test_migration_148_clean_install_is_transactional(setup):
    from pathlib import Path
    name = 'session1_schema_'+uuid4().hex
    with connection() as c:
        c.execute(f'CREATE SCHEMA {name}')
        c.execute(f'SET LOCAL search_path TO {name},public')
        c.execute(Path('migrations/forward/20260920_148_ordinary_generation_budget.sql').read_text())
        assert c.execute('SELECT count(*) n FROM ordinary_generation_policy').fetchone()['n'] == 1
        assert c.execute("SELECT 1 FROM pg_trigger WHERE tgname='ordinary_generation_budget_monotonic' AND tgrelid='ordinary_generation_budgets'::regclass").fetchone()
        c.rollback()
