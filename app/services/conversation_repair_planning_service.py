"""Frozen repair planning and approval; deliberately contains no executor."""
from __future__ import annotations
import hashlib,hmac,json,os
from uuid import UUID,uuid4

from app.models.conversation_repair_proposal import ROOT_CAUSE_REPAIR_CATEGORY,RepairCategory
from app.repositories.conversation_analysis_repository import ConversationAnalysisRepository
from app.repositories.conversation_repair_proposal_repository import ConversationRepairProposalRepository
from app.services.conversation_analysis_service import ConversationAnalysisService


class ConversationRepairPlanningService:
 COMMERCIAL=frozenset({'COMMERCIAL_CLASSIFICATION_POLICY','COMMERCIAL_PROGRESSION_POLICY','SALES_BRAIN_POLICY'})
 def __init__(self,*,analyses=None,analysis_repository=None,repository=None,secret=None):
  self.analyses=analyses or ConversationAnalysisService()
  self.analysis_repository=analysis_repository or ConversationAnalysisRepository()
  self.repository=repository or ConversationRepairProposalRepository()
  self.secret=(secret or os.getenv('CONVERSATION_REPAIR_PROPOSAL_SECRET') or
               os.getenv('CONVERSATION_RESOLUTION_PLAN_SECRET') or '').encode()

 def plan(self,analysis_id,*,finding_id,operator,**scope):
  analysis=self.analyses.retrieve(analysis_id,**scope)
  if analysis['staleState']!='CURRENT':raise RuntimeError('RE-ANALYZE: analysis evidence is STALE.')
  finding=next((f for f in analysis['findings'] if f['findingId']==finding_id),None)
  if not finding:raise LookupError('Conversation analysis finding was not found.')
  validated=finding['validatedScope']
  if validated in {'CONVERSATION_ONLY','OBSOLETE','AMBIGUOUS'}:
   reason={'CONVERSATION_ONLY':'No structural evidence supports a system-wide defect.',
           'OBSOLETE':'Current system evidence indicates the issue is superseded or repaired.',
           'AMBIGUOUS':'Manual review and re-analysis are required.'}[validated]
   return {'proposal':None,'scope':validated,'globalRepair':'NOT_RECOMMENDED',
           'reason':reason,'suggestedAction':'No global change.'}
  signature=self._finding_signature(analysis,finding)
  similar=self._similar_count(signature,scope)
  if validated=='MULTIPLE_CUSTOMERS' and similar<1:
   return {'proposal':None,'scope':validated,'globalRepair':'NOT_RECOMMENDED',
           'reason':'No shared structural cause remains established.','suggestedAction':'Re-analyze.'}
  category=ROOT_CAUSE_REPAIR_CATEGORY.get(finding['rootCauseCategory'])
  if not category:raise ValueError('Finding root cause has no compatible repair category.')
  if not self.secret:raise RuntimeError('Repair proposal signing secret is not configured.')
  proposal_id=uuid4();affected=1+similar
  invariant=self._invariant(signature,category,finding)
  regression=self._regressions(category,signature)
  risk=self._risk(category,validated)
  frozen={'proposalId':str(proposal_id),'analysisId':str(analysis_id),'findingId':finding_id,
    'evidenceFingerprint':self._fingerprint(analysis_id,scope),'failureSignature':signature,
    'validatedScope':validated,'repairCategory':category,'proposedInvariant':invariant,
    'affectedRelationshipCount':affected,'risk':risk,'regressionRequirements':regression}
  frozen['signature']=self._sign(frozen)
  stored=self.repository.create(proposal_id=proposal_id,analysis_id=analysis_id,finding_id=finding_id,
   creator_profile_id=scope['creator_profile_id'],fanvue_account_id=scope['fanvue_account_id'],
   relationship_key=scope['relationship_key'],validated_scope=validated,
   root_cause_category=finding['rootCauseCategory'],failure_signature=signature,
   affected_relationship_count=affected,violated_invariant=finding['whatHappened'],
   proposed_invariant=invariant,expected_effect=self._expected(category),
   preserved_behavior=self._preserve(category),known_risks=self._risks(category,validated),
   regression_requirements=regression,repair_category=category,
   evidence_fingerprint=frozen['evidenceFingerprint'],risk=risk,signature=frozen['signature'])
  self.repository.event('PROPOSED',proposal_id=proposal_id,data={'operator':operator,'scope':validated})
  return {'proposal':self._safe(stored),'scope':validated,'globalRepair':'CANDIDATE'}

 def get(self,proposal_id,**scope):
  row=self.repository.get(proposal_id,creator_profile_id=scope['creator_profile_id'],
      fanvue_account_id=scope['fanvue_account_id'],relationship_key=scope.get('relationship_key'))
  if not row:raise LookupError('Repair proposal was not found.')
  return self._safe(row)

 def reject(self,proposal_id,*,operator,**scope):
  row=self.repository.reject(proposal_id,creator_profile_id=scope['creator_profile_id'],
      fanvue_account_id=scope['fanvue_account_id'],operator=operator)
  if not row:raise RuntimeError('Repair proposal is unavailable or already reviewed.')
  return self._safe(row)

 def approve(self,proposal_id,*,operator,**scope):
  proposal=self.repository.get(proposal_id,creator_profile_id=scope['creator_profile_id'],
      fanvue_account_id=scope['fanvue_account_id'],relationship_key=scope.get('relationship_key'))
  if not proposal:raise LookupError('Repair proposal was not found.')
  analysis=self.analyses.retrieve(proposal['analysis_id'],**scope)
  if analysis['staleState']!='CURRENT':raise RuntimeError('REPAIR PROPOSAL OUT OF DATE')
  finding=next((f for f in analysis['findings'] if f['findingId']==proposal['finding_id']),None)
  if not finding:raise RuntimeError('REPAIR PROPOSAL OUT OF DATE')
  current_signature=self._finding_signature(analysis,finding)
  similar=self._similar_count(current_signature,scope)
  frozen={'proposalId':str(proposal_id),'analysisId':str(proposal['analysis_id']),
    'findingId':proposal['finding_id'],'evidenceFingerprint':proposal['evidence_fingerprint'],
    'failureSignature':current_signature,'validatedScope':finding['validatedScope'],
    'repairCategory':proposal['repair_category'],'proposedInvariant':proposal['proposed_invariant'],
    'affectedRelationshipCount':proposal['affected_relationship_count'],'risk':proposal['risk'],
    'regressionRequirements':proposal['regression_requirements']}
  current={'evidence_fingerprint':self._fingerprint(proposal['analysis_id'],scope),
    'failure_signature':current_signature,'validated_scope':finding['validatedScope'],
    'similar_case_count':similar,'signature':self._sign(frozen)}
  authorization,reused=self.repository.approve(proposal_id,
    creator_profile_id=scope['creator_profile_id'],fanvue_account_id=scope['fanvue_account_id'],
    operator=operator,current=current)
  return {'authorization':self._safe_authorization(authorization),'idempotentReplay':reused,
          'status':'APPROVED_FOR_EXECUTION'}

 def authorization(self,authorization_id,**scope):
  row=self.repository.authorization(authorization_id,creator_profile_id=scope['creator_profile_id'],
                                    fanvue_account_id=scope['fanvue_account_id'])
  if not row:raise LookupError('Repair execution authorization was not found.')
  return self._safe_authorization(row)

 def _similar_count(self,signature,scope):
  rows=self.analysis_repository.similar([signature],creator_profile_id=scope['creator_profile_id'],
    fanvue_account_id=scope['fanvue_account_id'],exclude_relationship_key=scope['relationship_key'])
  structural=getattr(self.analysis_repository,'structural_similar',lambda *a,**k:[])([signature],
    creator_profile_id=scope['creator_profile_id'],fanvue_account_id=scope['fanvue_account_id'],
    exclude_telegram_user_id=scope['telegram_user_id'])
  return len({row['relationship_key'] for row in [*rows,*structural]})
 def _fingerprint(self,analysis_id,scope):
  stored=self.analysis_repository.get(analysis_id,creator_profile_id=scope['creator_profile_id'],
    fanvue_account_id=scope['fanvue_account_id'],relationship_key=scope['relationship_key'])
  if not stored:raise LookupError('Conversation analysis was not found.')
  return stored['evidence_fingerprint']
 @staticmethod
 def _finding_signature(analysis,finding):
  value=finding.get('authoritativeEvidenceSummary')
  if not value or value.startswith('No server'):raise ValueError('Finding lacks a structural failure signature.')
  return value
 @staticmethod
 def _invariant(signature,category,finding):
  if signature=='COMPLIMENT_AVAILABILITY_CONTRADICTION':
   return 'Content-availability language requires authoritative current commercial evidence.'
  return finding['suggestedCorrection']
 @classmethod
 def _regressions(cls,category,signature):
  values=['Original failing structural behavior no longer occurs.',
          'Similar structural cases are corrected.','Legitimate neighboring behavior remains valid.']
  if category in cls.COMMERCIAL:values += [
   'Preserve genuine price inquiries, content inquiries, unlock/link requests, and grounded purchase acceptance.',
   'Do not activate commercial behavior from compliments, flirting, sexual attraction alone, or generic personal desire.']
  return values
 @classmethod
 def _preserve(cls,category):return (['Genuine price and content inquiries','Unlock/link requests','Grounded purchase acceptance'] if category in cls.COMMERCIAL else ['Unrelated validated behavior'])
 @staticmethod
 def _risks(category,scope):return [f'{scope} blast radius',f'{category} behavioral regression risk','Customer communication impact']
 @staticmethod
 def _risk(category,scope):return 'HIGH' if category in {'SALES_BRAIN_POLICY','DELIVERY_LIFECYCLE_POLICY'} or scope=='GLOBAL_SYSTEM' else 'MEDIUM'
 @staticmethod
 def _expected(category):return f'The shared {category} authority enforces the proposed invariant without customer-record mutation.'
 def _sign(self,value):return hmac.new(self.secret,json.dumps(value,sort_keys=True,separators=(',',':'),default=str).encode(),hashlib.sha256).hexdigest()
 @staticmethod
 def _safe(row):
  return {k:row.get(k) for k in ('proposal_id','analysis_id','finding_id','validated_scope','root_cause_category','failure_signature','affected_relationship_count','violated_invariant','proposed_invariant','expected_effect','preserved_behavior','known_risks','regression_requirements','repair_category','evidence_fingerprint','risk','created_at','expires_at','status','approved_by','approved_at','rejected_by','rejected_at','stale_reason')}
 @staticmethod
 def _safe_authorization(row):
  return {k:row.get(k) for k in ('authorization_id','proposal_id','repair_category','validated_scope','behavioral_invariant','regression_requirements','risk','evidence_fingerprint','approved_by','approved_at','expires_at','consumed_at')}
