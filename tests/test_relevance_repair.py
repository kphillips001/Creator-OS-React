import pytest
from app.services.gpt_service import GPTService

WORK='I have my own business administration office, where we manage luxury condominiums for owners. The owners want to give me more to manage, but I do not want more anymore.'
CANDIDATE='Managing luxury condos sounds like a lot of responsibility—and knowing when to say no takes real wisdom.'

@pytest.mark.parametrize('foreground,candidate',[
    (WORK,CANDIDATE),
    ('I have never seen anything as beautiful as you.', 'That’s sweet of you to say.'),
    ('How much have you been thinking about me!', 'More than I probably should… but hey, some thoughts are worth holding onto.'),
])
def test_audited_false_rejections(foreground,candidate):
    result=GPTService._foreground_semantic_relevance(foreground,candidate,{})
    assert result['satisfied'],result

@pytest.mark.parametrize('foreground,candidate',[
    ('Do you have any new videos?', 'You are lovely.'),
    ('How much is it?', 'The weather is lovely.'),
    ('Where do you live?', 'The weather is lovely.'),
    (WORK,'The weather is lovely.'),
])
def test_genuine_failures(foreground,candidate):
    result=GPTService._foreground_semantic_relevance(foreground,candidate,{})
    assert result['required'] and not result['satisfied'],result

@pytest.mark.parametrize('foreground,candidate',[
    ('I run my own business.', 'That is a lot of responsibility.'),
    ('I manage properties for clients.', 'Knowing when to say no is valuable.'),
    ('My workload is exhausting.', 'Keeping your workload manageable matters.'),
    ('I work with demanding clients.', 'Setting boundaries with clients sounds sensible.'),
    ('Where do you live?', "I'm based in Chicago."),
])
def test_grounded_context(foreground,candidate):
    assert GPTService._foreground_semantic_relevance(foreground,candidate,{})['satisfied']

@pytest.mark.parametrize('message',[
    'You do not know how much that means.', 'How much do you like hiking?',
    'How much have you been thinking about me!',
])
def test_noncommercial_quantity_shared_consumers(message):
    from app.services.foreground_relevance_contract import ForegroundRelevanceContract as C
    from app.services.commercial_receptiveness_service import CommercialReceptivenessService as R
    assert not C.pricing_question(message)
    assert R.commercial_interest_type(message) != 'PRICE_REQUEST'
    assert R.active_offer_continuation_type(message) != 'PRICE_REQUEST'

@pytest.mark.parametrize('message',['How much is it?','What is the price?','How much for the video?','How much do you charge?'])
def test_real_price(message):
    from app.services.foreground_relevance_contract import ForegroundRelevanceContract as C
    assert C.pricing_question(message)

@pytest.mark.parametrize('message',['You look beautiful in that photo.', 'I have never seen anything as beautiful as you.'])
def test_compliment_not_inventory(message):
    assert not GPTService._inventory_existence_grounding(message,'Thank you!',{})['required']
