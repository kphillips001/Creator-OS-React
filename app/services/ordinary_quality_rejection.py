"""Typed progression rejection handed to the existing bounded final gate."""
from dataclasses import replace

PROGRESSION_REASONS = frozenset({
    'SEQUENTIAL_LOW_NOVELTY_DIALOGUE_FUNCTION_LOOP',
    'FOREGROUND_SEMANTIC_RELEVANCE', 'MIRRORING_WITH_GENERIC_AFFECT',
    'GENERIC_APHORISM_UNDER_PROGRESSION_PRESSURE',
})

def obligation_failure(result):
    """Recover the saved rejected draft, never interpret empty text as a draft."""
    diagnostics = dict(result.diagnostic_metadata or {})
    style = dict(diagnostics.get('conversationStyle') or {})
    reasons = list(style.get('combinedObligationInitialViolations') or ())
    text = str(style.get('finalValidationOriginalCandidate') or '')
    if (not str(result.response_text or '').strip()
            and style.get('combinedObligationRepairOutcome') == 'UNRESOLVED_OPTIONAL_RESPONSE_WITHHELD'
            and style.get('providerReturnedUsableText') is True
            and int(style.get('providerCandidateCount') or 0) >= 1
            and text.strip() and reasons
            and all(r.startswith('FOREGROUND_OBLIGATION_') or r == 'FOREGROUND_SEMANTIC_RELEVANCE' for r in reasons)):
        return {'authority': 'FINAL_OBLIGATION_VALIDATION', 'rejectedCandidateText': text,
                'finalBlockingReasons': reasons}
    return None


def recoverable_failure(result):
    if obligation_failure(result):
        return True
    diagnostics = dict(result.diagnostic_metadata or {})
    failure = dict(diagnostics.get('conversationProgressionFailure') or {})
    reasons = set(failure.get('finalBlockingReasons') or ())
    return bool(result.error_code == 'decision_engine_exception'
        and not str(result.response_text or '').strip()
        and failure.get('authority') == 'ConversationProgressionQualityService'
        and str(failure.get('rejectedCandidateText') or '').strip()
        and reasons and reasons.issubset(PROGRESSION_REASONS))

def normalize(result):
    if not recoverable_failure(result):
        return result
    diagnostics = dict(result.diagnostic_metadata or {})
    failure = obligation_failure(result) or diagnostics['conversationProgressionFailure']
    diagnostics['qualityRejectionHandoff'] = {
        'version': 'ORDINARY_QUALITY_HANDOFF_V1',
        'originalErrorCode': result.error_code,
        'originalFailure': dict(diagnostics),
    }
    for key in ('internal_generation_failure', 'generation_fallback', 'status'):
        diagnostics.pop(key, None)
    diagnostics['conversationQualityReasons'] = list(dict.fromkeys([
        *(diagnostics.get('conversationQualityReasons') or ()),
        *(('TURN_OBLIGATIONS_UNSATISFIED' if r.startswith('FOREGROUND_OBLIGATION_') else r)
          for r in failure['finalBlockingReasons']),
    ]))
    text = failure['rejectedCandidateText']
    return replace(result, response_text=text, blocked=False, error_code=None,
        offer_authorized=False, offer_link=None, delivery_type='MESSAGE_TEXT',
        delivery_mode=None, delivery_requires_payment=False,
        delivery_payload={'type': 'MESSAGE_TEXT', 'message_text': text},
        diagnostic_metadata=diagnostics)
