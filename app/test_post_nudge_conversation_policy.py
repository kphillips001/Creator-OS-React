from datetime import datetime,timezone
from types import SimpleNamespace
import pytest
from app.services.post_nudge_conversation_policy_service import PostNudgeConversationPolicyService

SCOPE=dict(creator_profile_id=1,fanvue_account_id=2)
class Ledger:
 def __init__(self,count=1):self.count=count
 def relationship_nonconversion(self,**_):return {'nonconversion_count':self.count}
class Operations:
 def __init__(self,boundary=False,attempts=0):self.boundary=boundary;self.attempts=attempts
 def post_nudge_policy_history(self,**_):return {'supporter_boundary_confirmed':self.boundary,'sexual_attempts_after_boundary':self.attempts}
class Accounting:
 def __init__(self,used=0):self.used=used
 def today(self,**_):return {'replies_used_today':self.used,'next_reset_at':datetime(2026,9,16,5,tzinfo=timezone.utc)}
def op(text):return SimpleNamespace(inbound_message_text=text,inbound_sender_telegram_user_id=3,telegram_chat_id=4)
def decision(direct=False):return SimpleNamespace(commercial_bypass_eligible=direct)
class Intents:
 def list_confirmed_presentations_for_buyer(self,**_):return []
def policy(*,boundary=False,attempts=0,used=0,count=1):return PostNudgeConversationPolicyService(ledger=Ledger(count),operations=Operations(boundary,attempts),accounting=Accounting(used),intents=Intents())

def test_casual_backoff_remains_provider_eligible_at_reduced_scope():
 result=policy().evaluate(operation=op('How was your day?'),commercial_decision=decision(),verified_buyer=False,**SCOPE)
 assert result.response_purpose=='CASUAL_BACKOFF_CONVERSATION' and result.provider_allowed and not result.suppress_optional_reply
 assert result.time_waster is False

def test_first_sexual_attempt_remains_provider_led_after_nonconversion():
 result=policy().evaluate(operation=op("You're so sexy"),commercial_decision=decision(),verified_buyer=False,**SCOPE)
 assert result.response_purpose=='POST_PPV_RELATIONSHIP_CONTINUATION'
 assert result.provider_allowed and result.sexual_access_gated
 assert result.evidence['nonconversionScope']=='PRESENTATION_SPECIFIC'
 assert result.evidence['supporterBoundaryEligible'] is False

def test_historical_boundary_does_not_reactivate_relationship_wide_mode():
 result=policy(boundary=True,attempts=1).evaluate(operation=op("I'd love to touch you"),commercial_decision=decision(),verified_buyer=False,**SCOPE)
 assert result.response_purpose=='POST_PPV_RELATIONSHIP_CONTINUATION'
 assert result.provider_allowed and not result.suppress_optional_reply

def test_nonconversion_does_not_create_relationship_wide_daily_suppression():
 result=policy(boundary=True,attempts=9,used=9).evaluate(operation=op('hello'),commercial_decision=decision(),verified_buyer=False,**SCOPE)
 assert result.response_purpose=='CASUAL_BACKOFF_CONVERSATION'
 assert result.provider_allowed and not result.time_waster
 assert not result.suppress_optional_reply

def test_repeated_sexual_engagement_preserves_provider_generation():
 result=policy(boundary=True,attempts=2).evaluate(operation=op("You're so sexy"),commercial_decision=decision(),verified_buyer=False,**SCOPE)
 assert result.provider_allowed and not result.time_waster
 assert result.evidence['providerSemanticGuidance']['policyNarrationAllowed'] is False

def test_second_failed_presentation_reduces_intensity_without_boundary():
 result=policy(count=2).evaluate(operation=op("I'm feeling frisky"),commercial_decision=decision(),verified_buyer=False,**SCOPE)
 assert result.response_purpose=='REDUCED_FREE_INTENSITY'
 assert result.evidence['investmentTreatment']=='REDUCED_FREE_INTENSITY'
 assert result.evidence['freeHighIntensityInvestmentReduced'] is True
 assert result.evidence['premiumValueBoundaryAuthorized'] is False
 assert not result.time_waster

def test_three_failed_presentations_authorize_value_boundary_not_ignore():
 result=policy(count=3).evaluate(operation=op("I'm feeling frisky"),commercial_decision=decision(),verified_buyer=False,**SCOPE)
 assert result.response_purpose=='PREMIUM_VALUE_BOUNDARY'
 assert result.evidence['premiumValueBoundaryAuthorized'] is True
 assert result.evidence['relationshipRemainsActive'] is True
 assert result.evidence['ignoreChanged'] is False
 assert result.time_waster is False
 assert result.evidence['timeWasterMeaning']=='THRESHOLD_NOT_REACHED'

@pytest.mark.parametrize('count',[4,7])
def test_premium_boundary_does_not_prematurely_classify_time_waster(count):
 result=policy(count=count).evaluate(operation=op("I'm feeling frisky"),commercial_decision=decision(),verified_buyer=False,**SCOPE)
 assert result.response_purpose=='PREMIUM_VALUE_BOUNDARY'
 assert result.evidence['premiumValueBoundaryAuthorized'] is True
 assert result.time_waster is False
 assert result.evidence['timeWasterThreshold']==8

def test_eight_distinct_failed_presentations_activate_reduced_investment_not_disengagement():
 result=policy(count=8).evaluate(operation=op("Can you send me a sexy photo?"),commercial_decision=decision(),verified_buyer=False,**SCOPE)
 assert result.time_waster is True
 assert result.provider_allowed is True
 assert result.suppress_optional_reply is False
 assert result.evidence['customerHeatDetected'] is True
 assert result.evidence['relationshipRemainsActive'] is True
 assert result.evidence['ignoreChanged'] is False

def test_commercial_reentry_and_buyer_precede_nonbuyer_policy():
 commercial=policy(boundary=True,attempts=9,used=9).evaluate(operation=op('send me the link'),commercial_decision=decision(True),verified_buyer=False,**SCOPE)
 buyer=policy(boundary=True,attempts=9,used=9).evaluate(operation=op("you're sexy"),commercial_decision=decision(),verified_buyer=True,**SCOPE)
 assert commercial.response_purpose=='COMMERCIAL_REENTRY' and not commercial.suppress_optional_reply
 assert not buyer.active and buyer.provider_allowed

@pytest.mark.parametrize('text',["You're so sexy","I'd love to touch you","I want to suck your cock"])
def test_sexual_only_never_becomes_commercial_reentry_or_policy_narration(text):
 result=policy(boundary=True).evaluate(operation=op(text),commercial_decision=decision(False),verified_buyer=False,**SCOPE)
 assert result.response_purpose=='POST_PPV_RELATIONSHIP_CONTINUATION'
 assert result.sexual_access_gated and result.provider_allowed
 assert result.evidence['commercialReentry'] is False
