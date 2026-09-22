"""Single initial pipeline plus one snapshot-based, text-only correction."""
from copy import deepcopy
from dataclasses import replace
import json
import os

from app.models.telegram_inbound import TelegramInboundResult
from app.repositories.ordinary_generation_budget_repository import GenerationBudgetClosed
from app.services.ordinary_generation_context import OrdinaryGenerationSession, generation_scope
from app.services.ordinary_response_obligation_service import OrdinaryResponseObligationService


class OrdinaryReplyGenerationService:
    def __init__(self, repository, *, authorize, client_factory=None):
        self.repository = repository
        self.authorize = authorize
        self.client_factory = client_factory or self._client

    @staticmethod
    def _client(provider):
        from openai import OpenAI
        return OpenAI(api_key=os.getenv('GROK_API_KEY' if provider == 'GROK' else 'OPENAI_API_KEY'),
                      **({'base_url': os.getenv('GROK_BASE_URL', 'https://api.x.ai/v1')}
                         if provider == 'GROK' else {}), max_retries=0)

    def execute(self, operation, payload, *, owner, initial):
        from app.services.ordinary_chat_reply_service import durable_plain_data
        correction = dict((operation.delivery_payload or {}).get('qualityCorrectiveRetry') or {})
        is_correction = correction.get('required') is True
        old = self.repository.read(operation.operation_id)
        previous = dict((old or {}).get('result_snapshot') or {})
        obligation = OrdinaryResponseObligationService.decide(operation, previous.get('diagnostic_metadata'))
        self.authorize(operation, previous.get('diagnostic_metadata') or {})
        row = self.repository.begin(operation.operation_id, owner, obligation, correction=is_correction)
        session = OrdinaryGenerationSession(self.repository, operation, owner, correction=is_correction)
        with generation_scope(session):
            if is_correction:
                result = self._correct(operation, row, correction, session)
            else:
                result = initial(payload)
        from app.services.ordinary_quality_rejection import normalize
        result = normalize(result)
        evidence = self.repository.read(operation.operation_id)
        if str(result.response_text or '').strip() and evidence['candidate_count'] == 0:
            self.repository.record_deterministic_candidate(operation.operation_id, owner)
            evidence = self.repository.read(operation.operation_id)
        diagnostics = dict(result.diagnostic_metadata or {})
        obligation = OrdinaryResponseObligationService.decide(operation, diagnostics)
        diagnostics['conversationStyle'] = OrdinaryResponseObligationService.validate_self_photo(
            diagnostics.get('conversationStyle') or {}, result.response_text, obligation)
        diagnostics['ordinaryGeneration'] = {
            'version': 'ORDINARY_RECOVERY_V1', 'obligation': obligation,
            'customerFacingCandidates': evidence['candidate_count'], 'maximumCandidates': 2,
            'providerRequestAttempts': evidence['provider_attempt_count'] + sum(e.get('kind') == 'ANALYSIS_STARTED' for e in evidence['events']),
            'maximumProviderRequests': 8,
            'responseProviderRequestAttempts': evidence['provider_attempt_count'], 'maximumResponseProviderRequests': 3,
            'analysisProviderAttempts': sum(e.get('kind') == 'ANALYSIS_STARTED' for e in evidence['events']),
            'maximumAnalysisProviderRequests': 5,
            'sdkRetries': 0, 'correctionRequested': is_correction, 'correctionExecuted': is_correction,
            'nestedRewriteRequestsSuppressed': sum(e.get('kind') == 'REWRITE_DEFERRED' for e in evidence['events']),
            'correctionReasons': list(correction.get('blockingReasons') or ()),
            'contextSnapshotReused': is_correction,
            'contextSnapshotVersion': row['context_snapshot'].get('version') if is_correction else 'ORDINARY_CONTEXT_V1',
        }
        result = replace(result, diagnostic_metadata=diagnostics)
        self.repository.save(operation.operation_id, owner, result=durable_plain_data(result), obligation=obligation)
        return result

    def _correct(self, operation, row, correction, session):
        from app.services.gpt_service import GPTService
        from app.services.corrective_generation_evidence_service import CorrectiveGenerationEvidenceService
        snapshot = row['context_snapshot']
        if snapshot.get('version') != 'ORDINARY_CONTEXT_V1' or not snapshot.get('messages'):
            raise GenerationBudgetClosed('CORRECTION_CONTEXT_UNAVAILABLE')
        old = deepcopy(row['result_snapshot'])
        diagnostics = dict(old.get('diagnostic_metadata') or {})
        reasons = list(correction.get('blockingReasons') or ())
        exclusions = list(correction.get('excludedExactResponses') or ())
        from app.services.question_obligation_contract import QuestionObligationContract
        question_contract = QuestionObligationContract.for_message(
            operation.inbound_message_text or '', snapshot.get('questionObligation')
            or dict(snapshot.get('pressure') or {}).get('questionObligation')
            or row['obligation'].get('questionObligation'), snapshot.get('messages') or ())
        request = {
            'questionObligation': question_contract,
            'operationId': str(operation.operation_id),
            'inboundId': operation.inbound_telegram_message_id,
            'rejectedCandidate': old.get('response_text'),
            'blockingReasons': reasons, 'obligations': row['obligation']['obligations'],
            'excludedExactResponses': exclusions,
            'commercialAuthority': (operation.delivery_payload or {}).get('preGenerationCommercialDecision'),
            'candidateBudgetRemaining': 1, 'providerBudgetRemaining': 3-row['provider_attempt_count'],
            'qualityRepairGuidance': (
                'Address the current customer disclosure concretely. Contribute a relevant observation '
                'instead of repeating a generic acknowledgement or adding an engagement question.'
                if diagnostics.get('qualityRejectionHandoff') else None),
        }
        messages = [*snapshot['messages'], {'role': 'assistant', 'content': old.get('response_text') or ''},
            {'role': 'system', 'content': (
                'Produce the single final corrective response, text only. Preserve all existing safety, persona, '
                'factual and policy constraints. Satisfy every surviving obligation naturally. '
                'Answer the existing customer prompt first according to the resolved question contract. '
                'Do not manufacture a question merely to prolong engagement. Do not repeat excluded wording. '
                'No commercial offer, media, payment link, new commercial authority or invented facts. '
                'For ACKNOWLEDGE_SELF_PHOTO, acknowledge the self-photo naturally and positively; no question is required. '
                'Return only the corrected response. Correction evidence: '+json.dumps(request))}]
        provider = snapshot.get('provider') or 'OPENAI'
        completion = session.complete(self.client_factory(provider), provider=provider,
            model=snapshot['model'], messages=messages, temperature=0.7, max_tokens=90)
        text = str(completion.choices[0].message.content or '').strip()
        return self.validate_saved_candidate(operation, row, correction, text)

    @staticmethod
    def validate_saved_candidate(operation, row, correction, text):
        """Pure final candidate checks, shared by correction and explicit revalidation.

        No provider/client access and no generation-budget reservation.
        """
        from app.services.gpt_service import GPTService
        from app.services.corrective_generation_evidence_service import CorrectiveGenerationEvidenceService
        snapshot = row['context_snapshot']
        old = deepcopy(row['result_snapshot'])
        diagnostics = dict(old.get('diagnostic_metadata') or {})
        reasons = list(correction.get('blockingReasons') or ())
        exclusions = list(correction.get('excludedExactResponses') or ())
        provider = snapshot.get('provider') or 'OPENAI'
        # Recompute canonical deterministic candidate checks. Do not carry failed
        # candidate-1 style flags onto candidate 2 or trust model self-validation.
        from app.services.question_obligation_contract import QuestionObligationContract
        question_contract = QuestionObligationContract.for_message(
            operation.inbound_message_text or '', snapshot.get('questionObligation')
            or dict(snapshot.get('pressure') or {}).get('questionObligation')
            or row['obligation'].get('questionObligation'), snapshot.get('messages') or ())
        style = GPTService._style_analysis(text, operation.inbound_message_text or '',
            pressure={**(snapshot.get('pressure') or {}), 'questionObligation': question_contract}, ordinary=True, memory_callback=False,
            new_relationship=bool(snapshot.get('newRelationship')),
            recent_responses=list(snapshot.get('recentResponses') or [])+exclusions)
        norm = CorrectiveGenerationEvidenceService.normalize_exact
        novelty = not any(norm(text) == norm(item) for item in exclusions)
        style['finalResponseRepetitionSatisfied'] = bool(novelty and not style.get('recentPhraseRepetitionRisk'))
        missing = set(row['obligation']['obligations']) - set(style.get('satisfiedTurnObligations') or ())
        style['turnObligations'] = row['obligation']['obligations']
        style['unsatisfiedTurnObligations'] = sorted(missing)
        style['turnObligationsSatisfied'] = not missing
        # The existing gate/natural-conversation and commercial revocation checks
        # still run in OrdinaryChatReplyService.generated and again before send.
        style = OrdinaryResponseObligationService.validate_self_photo(style, text, row['obligation'])
        momentum = style.get('conversationMomentum') or {}
        momentum.update(styleIntervention=True, candidateReplaced=text != old.get('response_text'), fallbackUsed=False)
        style['conversationMomentum'] = momentum
        diagnostics['conversationStyle'] = style
        diagnostics['conversationQualityReasons'] = [r for r in diagnostics.get('conversationQualityReasons', [])
            if r not in reasons]
        if diagnostics.get('qualityRejectionHandoff'):
            from app.services.conversation_progression_quality_service import ConversationProgressionQualityService
            progression = ConversationProgressionQualityService.assess(
                customer_message=operation.inbound_message_text or '', candidate=text,
                recent_ava_responses=snapshot.get('recentResponses') or [])
            relevance = GPTService._foreground_semantic_relevance(
                operation.inbound_message_text or '', text, {})
            diagnostics['correctedProgression'] = progression.diagnostics()
            diagnostics['correctedForegroundRelevance'] = relevance
            if not progression.accepted:
                diagnostics['conversationQualityReasons'].append(progression.rejection_reason)
            if relevance['required'] and not relevance['satisfied']:
                diagnostics['conversationQualityReasons'].append('FOREGROUND_SEMANTIC_RELEVANCE')
        for key in ('delivery_quality_gate', 'conversationQualityDisposition', 'offlineAccessValidation', 'naturalConversation'):
            diagnostics.pop(key, None)
        diagnostics['selected_provider'] = provider
        diagnostics['customer_sales_decision'] = 'CONTINUE_CONVERSATION'
        diagnostics['paidPresentationAuthorized'] = False
        diagnostics['commercialTeaseAuthorized'] = False
        diagnostics['ordinaryCorrection'] = {'version': 'ORDINARY_CONTEXT_V1', 'reasons': reasons,
            'obligations': row['obligation']['obligations'], 'fullPipelineReentered': False}
        old.update(response_text=text, offer_authorized=False, offer_link=None, blocked=False, error_code=None,
            delivery_type='MESSAGE_TEXT', delivery_mode=None, delivery_requires_payment=False,
            delivery_payload={'type': 'MESSAGE_TEXT', 'message_text': text}, diagnostic_metadata=diagnostics)
        return TelegramInboundResult(**old)
