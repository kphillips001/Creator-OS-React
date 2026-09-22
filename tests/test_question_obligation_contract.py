import json
from types import SimpleNamespace

import pytest

from app.services.question_obligation_contract import QuestionObligationContract as Contract
from app.services.gpt_service import GPTService
from app.services.ordinary_response_obligation_service import OrdinaryResponseObligationService
from app.repositories.ordinary_generation_budget_repository import GenerationBudgetClosed
from test_ordinary_generation_budget import setup, Provider, run_first, claim_correction


@pytest.mark.parametrize('message,meaning', [
    ('Where are you from?', 'LOCATION'),
    ('Do you like hiking?', 'PREFERENCE'),
    ('I finished my work, then?', 'CONTINUATION'),
    ('What do you want from me?', 'CLARIFICATION'),
    ('That?', 'CLARIFICATION'),
])
def test_resolved_meaning(message, meaning):
    c = Contract.resolve(message)
    assert c['meaning'] == meaning
    assert c['answerCriteria'] and c['requiredAct'] and c['foreground'] == message
    assert c['clarificationRequired'] == (meaning == 'CLARIFICATION')


def test_contextual_then():
    history = [{'role': 'user', 'content': 'I finished the long project.'}]
    c = Contract.resolve('then?', history)
    assert c['meaning'] == 'CONTINUATION' and c['subject'] == history[0]['content']
    assert Contract.resolve('then?')['clarificationRequired']


def test_non_location_from():
    c = Contract.resolve('What do you want from me?')
    assert c['meaning'] != 'LOCATION'
    style = GPTService._style_analysis('What do you mean by that?', c['foreground'], pressure={'questionObligation': c}, ordinary=True, memory_callback=False)
    assert style['customerQuestionDomain'] is None
    assert style['customerQuestionAnswered']


@pytest.mark.parametrize('message,answer', [
    ('Where are you from?', "I'm from the coastal East Coast."),
    ('Do you like hiking?', 'Yes, I enjoy hiking.'),
    ('I finished my work, then?', "Then we can take a breather."),
    ('What do you want from me?', 'What do you mean by that?'),
])
def test_validator_same_contract_and_relevant_answer(message, answer):
    c = Contract.resolve(message)
    style = GPTService._style_analysis(answer, message, pressure={'questionObligation': c}, ordinary=True, memory_callback=False)
    assert style['questionObligation'] == c
    assert style['customerQuestionAnswered']
    assert 'ANSWER_DIRECT_QUESTION' in style['satisfiedTurnObligations']
    assert 'MANUFACTURED_ENGAGEMENT_QUESTION' not in style['styleRewriteReasons']


def test_deflection_and_manufactured_question_rejected():
    message = 'I finished my work, then?'
    style = GPTService._style_analysis('Quite the picture. What made you think of that?', message, pressure={}, ordinary=True, memory_callback=False)
    assert not style['customerQuestionAnswered']
    assert 'MANUFACTURED_ENGAGEMENT_QUESTION' in style['styleRewriteReasons']
    assert 'ANSWER_DIRECT_QUESTION' in style['unsatisfiedTurnObligations']


def test_correction_evidence_durable_and_no_third_call(setup):
    _, budget, owner, make = setup
    op = make('Do you like hiking?', ['ANSWER_DIRECT_QUESTION'])
    provider = Provider('What makes you ask?', 'What makes you ask?')
    service, first, initial, _ = run_first(setup, op, provider, ['CUSTOMER_QUESTION_UNANSWERED'])
    lifecycle, op2 = claim_correction(setup, op, first)
    second = service.execute(op2, None, owner=owner, initial=initial)
    final = lifecycle.generated(op2, second)
    assert final.state.value == 'SUPPRESSED'
    request = json.loads(provider.calls[1]['messages'][-1]['content'].split('Correction evidence: ')[1])
    contract = request['questionObligation']
    assert contract['meaning'] == 'PREFERENCE' and contract['answerCriteria']
    assert request['blockingReasons'] and request['obligations'] == ['ANSWER_DIRECT_QUESTION']
    assert second.diagnostic_metadata['conversationStyle']['questionObligation'] == contract
    assert budget.read(op.operation_id)['obligation']['questionObligation']['meaning'] == 'PREFERENCE'
    with pytest.raises(GenerationBudgetClosed):
        service.execute(op2, None, owner=owner, initial=initial)
    assert len(provider.calls) == 2 and initial.call_count == 1
    assert budget.read(op.operation_id)['candidate_count'] == 2


def test_stale_foreground_contract_not_applied():
    stale = Contract.resolve('Where are you from?')
    assert Contract.for_message('Do you like hiking?', stale)['meaning'] == 'PREFERENCE'


def test_ambiguous_punctuation_requires_clarification():
    assert Contract.resolve('Blue?')['meaning'] == 'CLARIFICATION'


def test_expectation_resolved_from_actual_context():
    c = Contract.resolve('What do you want from me?', [{'role': 'assistant', 'content': 'I need some space.'}])
    assert c['meaning'] == 'CONTEXTUAL_EXPECTATION'
    assert Contract.accepts(c, 'I just need some space.')
    assert not Contract.accepts(c, 'I want a holiday.')
