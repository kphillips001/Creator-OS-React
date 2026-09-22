"""Sanitized audit fixtures; no live conversations or model requests."""
from types import SimpleNamespace
import inspect
import pytest
from app.services.conversation_momentum_strategy import ConversationMomentumStrategy as M
from app.services.gpt_service import GPTService
from app.services.ordinary_reply_delivery_quality_gate import OrdinaryReplyDeliveryQualityGate as Gate


def style(customer, response, **pressure):
    return GPTService._style_analysis(response, customer, pressure=pressure,
        ordinary=True, memory_callback=False, recent_responses=[])


@pytest.mark.parametrize('customer,response', [
    ('Lucky friend', 'Maybe they just know when to be in the right place at the right time.'),
    ('You look gorgeous', 'Aww, sweet talk and good timing? Quite a combination.'),
    ('I bet I can beat you at chess', 'Bold claim. I take my chess grudges seriously.'),
    ('That comeback was pretty good', 'Fine, you win that round. I am keeping score though.'),
])
def test_playful_contributions_and_varied_texture_allowed(customer, response):
    s = style(customer, response)
    assert not s['conversationMomentum']['blockingReasons']
    assert s['conversationMomentum']['momentumIntent'] in {'BUILD', 'MAINTAIN'}


@pytest.mark.parametrize('response', ['okayyy... I felt that', 'well then... message received'])
def test_audited_dead_end_is_blocked_even_when_exactly_novel(response):
    s = style('You are so sexy, I want to kiss you', response)
    assert 'INERT_ENGAGED_RESPONSE' in s['styleRewriteReasons']
    result = SimpleNamespace(response_text=response, diagnostic_metadata={'conversationStyle': s})
    assert 'INERT_ENGAGED_RESPONSE' in Gate().evaluate(result).reasons


def test_existing_semantic_energy_beats_missing_policy_heat():
    p = M.plan('A short reply', evidence={'heat': 'NONE', 'classifier': {'sexual_engagement': True}})
    assert p['customerEnergyUsed'] == 'HOT'
    assert p['momentumIntent'] == 'BUILD'
    assert 'mechanical explicitness' in M.prompt(p)


def test_richer_valid_flirt_not_rejected_for_old_18_word_limit():
    customer = 'You are sweet and so cute'
    response = 'Aww, you are sweet too, but I suspect that innocent smile is hiding a rather competitive streak behind all that charm.'
    s = style(customer, response)
    assert 'EXCESSIVE_ORDINARY_LENGTH' not in s['styleRewriteReasons']
    selected = GPTService._function_first_flirt_fallback(customer, candidates=[response])
    assert selected['response'] == response


def test_stock_pool_never_rescues_without_existing_valid_candidate():
    selected = GPTService._function_first_flirt_fallback('You look so sexy')
    assert selected['response'] == ''
    assert selected['function'] == 'NO_VALID_SAVED_CANDIDATE'


@pytest.mark.parametrize('customer,response', [
    ('I finally finished my painting', 'Which part of the painting surprised you most?'),
    ('I bet I can beat you at chess', 'Is that chess confidence earned or are you bluffing?'),
])
def test_contextual_curiosity_and_playful_challenge_allowed(customer, response):
    s = style(customer, response)
    assert not s['manufacturedQuestionRisk']
    assert s['conversationMomentum']['questionCategory'] == 'ORGANIC_CONTEXTUAL'


def test_generic_question_cannot_hide_behind_specific_acknowledgement():
    s = style('I finally finished my painting', 'That painting sounds great. What are you up to?')
    assert s['manufacturedQuestionRisk']
    assert s['conversationMomentum']['questionCategory'] == 'MANUFACTURED_BLOCKED'


def test_contextual_question_cannot_override_pressure_or_known_answer():
    assert not M.contextual_question('My painting is finished', 'How is your painting?', pressure={'questionStreak': 2})
    assert not M.contextual_question('My painting is finished', 'How is your painting?', pressure={
        'relationshipDiscovery': {'allowed': False, 'suppressionReason': 'DOMAIN_ALREADY_KNOWN'}})


def test_question_optional_and_short_simple_response_valid():
    s = style('Goodnight', 'Sleep well.')
    assert s['conversationMomentum']['momentumIntent'] == 'END'
    assert not s['conversationMomentum']['blockingReasons']
    assert s['conversationMomentum']['questionCategory'] == 'NONE'
    assert not style('Okay', 'Gotcha')['conversationMomentum']['blockingReasons']


def test_grounded_memory_allowed_and_explicit_fabrication_rejected():
    kwargs = dict(known_context='My trip to Maine is in October', memory_callback=True)
    assert not M.assess('Goodnight', 'I remember your trip. Sleep well!', **kwargs)['blockingReasons']
    assert M.assess('Goodnight', 'I remember your yacht.', **kwargs)['blockingReasons'] == ['UNSUPPORTED_EXPLICIT_CALLBACK']
    assert M.assess('Goodnight', 'Sleep well.', **kwargs)['contributionStrategy'] == 'MEMORY_CALLBACK'


def test_compliment_loop_suggests_strategy_change_not_language_blacklist():
    p = M.plan('You look gorgeous', recent=['Thank you!', 'You made me blush.'])
    assert p['varyRecentStrategy'] == 'COMPLIMENT_REACTION'
    assert M.assess('You look gorgeous', 'Thanks', plan=p)['variationSuggested']
    assert not M.assess('You look gorgeous', 'Bold opening.', plan=p)['variationSuggested']


def test_meaning_not_character_count_drives_investment():
    p = M.plan('I lost him', evidence={'affect': {'emotionalDisclosureDetected': True}})
    assert p['meaningfulInvestment']
    assert 'INERT_ENGAGED_RESPONSE' in M.assess('I lost him', 'Good to know', plan=p)['blockingReasons']
    assert not M.plan('okay')['meaningfulInvestment']
    assert 'tiny input needs no paragraph' in M.prompt(p)


def test_backoff_keeps_existing_authority_and_closure_is_not_escalation():
    p = M.plan('You are sexy', evidence={'classifier': {'sexual_engagement': True}, 'backoff': True})
    assert p['momentumIntent'] == 'COOL'
    assert not M.assess('You are sexy', 'Thanks', plan=p)['blockingReasons']


def test_new_strategy_has_no_provider_or_external_dependency():
    import ast
    tree = ast.parse(inspect.getsource(__import__(M.__module__, fromlist=['*'])))
    imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert {n.module if isinstance(n, ast.ImportFrom) else n.names[0].name for n in imports} == {'__future__', 're'}
    before = {'classifier': {'sexual_engagement': True}}
    assert M.plan('hello', evidence=before) == M.plan('hello', evidence=before)
    assert before == {'classifier': {'sexual_engagement': True}}


def test_full_generation_preserves_rich_candidate_and_records_guidance(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER', 'OPENAI')
    calls = []
    response = 'Aww, you are sweet too, but I suspect that innocent smile is hiding a rather competitive streak behind all that charm.'
    class Training:
        def runtime_prompt_block(self, **kwargs): return ''
    def complete(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=response))])
    service = GPTService(api_key='isolated', global_training_service=Training())
    service.openai_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=complete)))
    memory = {'creator_profile': {'id': 2, 'persona_name': 'Ava', 'system_prompt': 'Stay natural.'},
              'gpt_classifier_result': {'sexual_engagement': True}}
    actual = service.generate_response('default', 'casual', 'You are sweet and so cute', memory, False, chat_history=[])
    assert actual == response
    assert len(calls) == 1
    prompt = calls[0]['messages'][0]['content']
    assert 'ACKNOWLEDGE this turn' in prompt and 'CREATE MOMENTUM' in prompt
    assert 'ONE COMPLETE BEAT BY DEFAULT' not in prompt


def test_saved_correction_reuses_momentum_and_persists_final_diagnostics():
    from dataclasses import asdict
    from app.models.telegram_inbound import TelegramInboundResult
    from app.services.ordinary_reply_generation_service import OrdinaryReplyGenerationService
    original = TelegramInboundResult(correlation_id='test', telegram_chat_id=1, telegram_user_id=1, message_id=1, engine_user_id=1, offer_link=None, blocked=False, error_code=None, response_text='message received', offer_authorized=False,
        diagnostic_metadata={'conversationStyle': {}})
    plan = M.plan('You look sexy', evidence={'classifier': {'sexual_engagement': True}})
    row = {'context_snapshot': {'pressure': {'momentumPlan': plan}, 'messages': [], 'recentResponses': []},
           'result_snapshot': asdict(original), 'obligation': {'obligations': []}}
    result = OrdinaryReplyGenerationService.validate_saved_candidate(
        SimpleNamespace(inbound_message_text='You look sexy'), row,
        {'blockingReasons': ['INERT_ENGAGED_RESPONSE']}, 'Aww, that sweet talk is dangerously persuasive.')
    diagnostic = result.diagnostic_metadata['conversationStyle']['conversationMomentum']
    assert diagnostic['customerEnergyUsed'] == 'HOT'
    assert diagnostic['candidateReplaced'] and diagnostic['styleIntervention']
    assert not diagnostic['fallbackUsed'] and not diagnostic['blockingReasons']
