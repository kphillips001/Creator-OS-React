"""Sanitized current-turn fixtures; all commerce, provider and sends are fake."""
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace as NS
import ast
import inspect
import pytest

from app.services.commercial_momentum_contract import CommercialMomentumContract as C
from app.services.customer_sales_brain_service import CustomerSalesBrainService as SalesBrain
from app.services.conversational_sales_progression_service import ConversationalSalesProgressionService as Progression
from app.services.conversation_gateway import ConversationGateway as Gateway
from app.services.customer_heat_signal_service import CustomerHeatSignalService as Heat
from app.services.customer_sales_brain_config import CustomerSalesBrainConfig
from app.services.sexual_sales_opportunity_service import SexualSalesOpportunityService
from app.models.customer_sales_decision import CustomerSalesDecisionType as D
from app.test_conversational_sales_progression import decision
from app.test_customer_sales_brain_conversation_integration import execute, offering, sales_decision


MESSAGE = 'I am describing a much more intimate scene with you, then what happens?'
SEMANTICS = {'sexual_engagement': True, 'escalation_ready': True,
             'explicit_without_buying_intent': True, 'confidence': .95, 'engagement_level': 'high'}


def context(message=MESSAGE, classifier=None):
    c = {'latest_message': message, 'classifier_result': SEMANTICS if classifier is None else classifier,
         'commercial_turn_id': 'fixture-turn', 'inbound_message_count': 46, 'sexual_engagement_count': 3,
         'recent_transcript': [{'role': 'assistant', 'content': 'You are trouble'}],
         'effective_content_selling_allowed': True, 'sales_progression': {'phase': 'PRESENT_OFFER'}}
    SalesBrain._apply_customer_heat_signal(c)
    return c


def assess(c, *, active=False):
    brain = object.__new__(SalesBrain)
    brain.config = CustomerSalesBrainConfig.from_environment()
    return brain._proactive_hot_opportunity_assessment(c, active_purchase_intent=active, active_sales_session=False)


def canonical(c=None):
    c = c or context()
    hot = assess(c)
    c['proactive_hot_opportunity'] = hot
    selected = replace(decision(), decision_metadata={
        'currentTurnCommercialEvidence': C.current_evidence(c), 'proactiveHotOpportunity': hot})
    return Progression().refine(selected, c)


def inbound(**preliminary):
    return NS(correlation_id='fixture-turn', message_text=MESSAGE, quality_correction_context={
        'preGenerationCommercialDecision': {'commercial_bypass_eligible': False, **preliminary}})


def test_stu_strong_current_turn_survives_preliminary_direct_intent_negative():
    c = context()
    assert c['customer_heat_signal']['type'] == 'PLAYFUL_SUGGESTIVE'
    assert c['customer_heat_signal']['strength'] == 'STRONG'
    assert c['customer_heat_signal']['initiationSource'] == 'CUSTOMER_ESCALATED'
    assert c['sexual_engagement_count'] < CustomerSalesBrainConfig.from_environment().sexual_receptiveness_min_engagements
    result = canonical(c)
    assert result.decision is D.PRESENT_OFFER and result.sell_allowed
    final = Gateway._apply_current_turn_commercial_authority(result, gateway_input=inbound())
    assert final.decision is D.PRESENT_OFFER and final.sell_allowed
    assert final.recommended_offering_id == result.recommended_offering_id


@pytest.mark.parametrize('message,classifier', [('hello', {}), ('You are beautiful', {}),
    ('hey cutie', {'sexual_engagement': True, 'confidence': .55})])
def test_low_compliment_and_weak_sexual_signals_do_not_authorize(message, classifier):
    c = context(message, classifier)
    c['sales_progression'] = {}
    assert not assess(c)['proactiveHotOpportunityAuthorized']


@pytest.mark.parametrize('key,value,reason', [
    ('purchase_cooldown_active', True, 'COMMERCIAL_OR_PROACTIVE_COOLDOWN'),
    ('sales_progression', {'phase': 'BACK_OFF'}, 'BACK_OFF'),
    ('effective_content_selling_allowed', False, 'CONTENT_SELLING_NOT_ALLOWED'),
    ('relationship_control_mode', 'HUMAN_OPERATOR', 'HUMAN_OPERATOR'),
])
def test_current_safeguards_block_strong_heat(key, value, reason):
    c = context(); c[key] = value
    result = assess(c)
    assert not result['proactiveHotOpportunityAuthorized']
    assert reason in result['hotOpportunityBlockers']


def test_active_presentation_blocks_duplicate_evaluation():
    result = assess(context(), active=True)
    assert not result['proactiveHotOpportunityAuthorized']
    assert 'ACTIVE_PURCHASE_INTENT' in result['hotOpportunityBlockers']


@pytest.mark.parametrize('change', ['turn', 'message', 'heat', 'safeguard', 'history_only', 'selection', 'permission'])
def test_stale_or_incomplete_evidence_cannot_preserve_offer(change):
    d = canonical(); metadata = dict(d.decision_metadata)
    if change == 'turn': metadata['currentTurnCommercialEvidence'] = {**metadata['currentTurnCommercialEvidence'], 'turnId': 'old'}
    if change == 'message': metadata['currentTurnCommercialEvidence'] = {**metadata['currentTurnCommercialEvidence'], 'messageDigest': C.message_digest('old')}
    if change == 'heat': metadata['proactiveHotOpportunity'] = {**metadata['proactiveHotOpportunity'], 'customerHeatSignal': {}}
    if change == 'safeguard': metadata['proactiveHotOpportunity'] = {**metadata['proactiveHotOpportunity'], 'hotOpportunityBlockers': ['COOLDOWN']}
    if change == 'history_only': metadata = {'salesProgression': {'phase': 'PRESENT_OFFER'}}
    d = replace(d, decision_metadata=metadata,
                recommended_offering_id=None if change == 'selection' else d.recommended_offering_id,
                sell_allowed=False if change == 'permission' else d.sell_allowed)
    assert not Gateway._apply_current_turn_commercial_authority(d, gateway_input=inbound()).sell_allowed


@pytest.mark.parametrize('flag', ['no_buy_boundary', 'temporal_deferred'])
def test_preliminary_explicit_boundary_still_blocks(flag):
    assert not Gateway._apply_current_turn_commercial_authority(canonical(), gateway_input=inbound(**{flag: True})).sell_allowed


def test_ordinary_exhaustion_is_not_a_commercial_input_or_permission():
    c = context(); before = assess(c)
    c.update(ordinary_candidate_count=2, ordinary_failure=True)
    assert assess(c) == before
    cold = context('hello', {}); cold.update(ordinary_candidate_count=2, ordinary_failure=True)
    assert not assess(cold)['proactiveHotOpportunityAuthorized']


def test_joseph_improved_flirt_is_not_itself_offer_authority():
    c = context('You look gorgeous', {'sexual_engagement': True, 'confidence': .55})
    c['ordinary_response_momentum'] = {'momentumIntent': 'BUILD', 'offer_authorized': True}
    assert not assess(c)['proactiveHotOpportunityAuthorized']
    d = Progression().refine(decision(), c)
    assert d.decision in {D.TEASE, D.BUILD_INTEREST, D.CONTINUE_CONVERSATION}
    assert not d.sell_allowed


def test_offer_handoff_has_one_customer_visible_payload_no_flirt_prelude():
    selected = offering(); d = sales_decision(D.PRESENT_OFFER, selected=selected)
    output, engine, sales, brain = execute(d, selected=selected, response_text='Another escalating flirt first.')
    assert output.offer_authorized and not output.blocked
    assert 'Another escalating flirt first.' not in output.response_text
    assert len(engine.calls) == 1 and len(brain.calls) == 1
    observed = output.diagnostic_metadata['commercialOpportunityLifecycle']
    assert observed['actionOwner'] == 'CANONICAL_OFFER_PRESENTATION'
    assert observed['ordinaryPreludeAllowed'] is False
    assert observed['selectedOffering'] == str(selected.offering_id)


def test_ordinary_generator_cannot_fabricate_offer_authority():
    output, _, _, _ = execute(sales_decision(D.CONTINUE_CONVERSATION), engine_send_offer=True)
    assert not output.offer_authorized
    assert output.diagnostic_metadata['commercialOpportunityLifecycle']['actionOwner'] == 'ORDINARY'


@pytest.mark.parametrize('action', [D.BACK_OFF, D.CONGRATULATE_PURCHASE])
def test_backoff_and_verified_purchase_return_conversation_without_resale(action):
    output, _, _, _ = execute(sales_decision(action, congratulate=action is D.CONGRATULATE_PURCHASE),
        engine_send_offer=False, response_text='Glad we can keep chatting.')
    assert not output.offer_authorized
    assert output.diagnostic_metadata['commercialOpportunityLifecycle']['actionOwner'] == 'ORDINARY'


@pytest.mark.parametrize('transport', ['TELEGRAM_BUSINESS', 'TELETHON'])
def test_existing_first_party_presentation_is_price_free(transport, monkeypatch):
    from app.models.telegram_unlock_action import TelegramUnlockAction
    monkeypatch.setenv('CREATOR_OS_PUBLIC_API_URL', 'https://unlock.example.test')
    alias = 'https://unlock.example.test/u/AAAAAAAAAAAAAAAAAAAAAA'
    caption = 'A little something to keep that smile going.'
    rendered = TelegramUnlockAction(alias).render(caption, transport=transport, button_label='Unlock')
    assert '$' not in rendered['message_text'] and 'http' not in rendered['message_text']
    if transport == 'TELEGRAM_BUSINESS': assert rendered['button_url'] == alias
    else: assert rendered['caption_entities'][0]['url'] == alias


def test_no_provider_dependency_and_momentum_does_not_authorize():
    tree = ast.parse(inspect.getsource(__import__(C.__module__, fromlist=['*'])))
    assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                   and n.func.attr in {'create', 'complete', 'send_message', 'send_file'} for n in ast.walk(tree))
    c = context()
    assert c['conversation_momentum']['momentumIntent'] == 'BUILD'
    assert 'sell_allowed' not in c['conversation_momentum']


def test_canonical_evaluation_persists_turn_evidence_and_supplies_selection_context():
    from app.test_customer_sales_brain import brain, profile, signal, offering as selected_offering, evaluate
    service = brain(customer=profile(), commerce_signal=signal(), eligible=selected_offering())
    result = evaluate(service, {**context(), 'latest_message': 'What private content do you have available?'})
    assert result.sell_allowed
    evidence = result.decision_metadata['currentTurnCommercialEvidence']
    assert evidence['turnId'] == 'fixture-turn'
    assert evidence['messageDigest'] == C.message_digest('What private content do you have available?')
    assert service.offering_selector.calls[-1]['conversation_context']['conversation_momentum']['turnId'] == 'fixture-turn'


def test_canonical_offer_service_repeated_request_creates_at_most_one_presentation(monkeypatch):
    monkeypatch.setenv("CREATOR_OS_PUBLIC_API_URL", "https://unlock.example.test")
    # Existing canonical idempotency contract, fake repositories and sender only.
    from test_prospect_manual_offers import test_sanitized_prospect_fresh_offer_and_repeat_request
    test_sanitized_prospect_fresh_offer_and_repeat_request()
