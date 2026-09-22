"""Read-only recovery assessment. An assessment is never a generation/send claim.

Inputs are persisted evidence plus explicit current authority, not generated flags.
Serialized evidence digests permit the activation session to compare assessments;
execution must reacquire existing operation leases and recheck all authorities.
"""
from dataclasses import dataclass, asdict
import hashlib
import json


@dataclass(frozen=True)
class StrandedReplyEvidence:
    operation_id: str
    state: str
    reason: str
    obligations: tuple[str, ...]
    fresh: bool | None
    control_eligible: bool | None
    market_allowed: bool | None
    candidate_count: int | None = None
    provider_attempt_count: int | None = None
    complete_lifetime_evidence: bool = False
    correction_started: bool | None = None
    send_attempt_count: int = 0
    delivery_uncertain: bool = False
    active_owner: bool = False
    initial_started: bool = False
    provider_in_flight: bool = False
    retained_candidate_hash: str | None = None
    certified_revalidation_mechanism: str | None = None
    legacy_generation_attempts: int | None = None
    candidate_lower_bound: int = 0


class StrandedReplyAssessment:
    VERSION = 'STRANDED_LINEAGE_V1'
    REVALIDATION = 'FOREGROUND_SAVED_CANDIDATE_REVALIDATION'

    @classmethod
    def assess(cls, evidence: StrandedReplyEvidence):
        e = evidence
        count = e.candidate_count if e.complete_lifetime_evidence else None
        providers = e.provider_attempt_count if e.complete_lifetime_evidence else None
        remaining = max(0, 2-count) if count is not None else None
        category = 'UNKNOWN_LINEAGE_HUMAN_REQUIRED'
        mechanism = None
        reason = 'LIFETIME_CONSUMPTION_NOT_PROVEN'
        if (e.delivery_uncertain or e.state in {'SEND_UNCERTAIN', 'SENDING', 'SENT_CONFIRMED'}
                or e.send_attempt_count or e.active_owner or e.provider_in_flight):
            category, reason = 'POLICY_BLOCKED', 'DELIVERY_OR_OWNER_NOT_SAFE'
        elif 'OPERATOR_CANCELLED' in e.reason or e.control_eligible is False:
            category, reason = 'POLICY_BLOCKED', 'CURRENT_CONTROL_OR_OPERATOR_CANCELLATION'
        elif not e.obligations or e.fresh is False:
            category, reason = 'POLICY_BLOCKED', 'NO_CURRENT_REQUIRED_RESPONSE'
        elif (e.certified_revalidation_mechanism == cls.REVALIDATION
              and e.reason.endswith('FOREGROUND_SEMANTIC_RELEVANCE')
              and e.retained_candidate_hash and count is not None
              and e.control_eligible is True and e.fresh is True and e.market_allowed is True):
            category, reason, mechanism = ('REVALIDATABLE_EXISTING_CANDIDATE',
                'EXACT_CANDIDATE_EXISTING_CERTIFIED_MECHANISM', cls.REVALIDATION)
        elif (count is not None and count >= 2) or e.candidate_lower_bound >= 2 or 'quality_corrective_retry_exhausted:' in e.reason:
            category, reason = 'EXHAUSTED', 'LIFETIME_CANDIDATE_OR_CORRECTION_EXHAUSTED'
            remaining = 0
        elif providers is not None and providers >= 3:
            category, reason = 'EXHAUSTED', 'RESPONSE_PROVIDER_BUDGET_EXHAUSTED'
        elif e.market_allowed is False:
            category, reason = 'POLICY_BLOCKED', 'CURRENT_MARKET_AUTHORITY_DENIED'
        elif count is not None and providers is not None:
            if e.control_eligible is not True or e.fresh is not True or e.market_allowed is not True:
                category, reason = 'POLICY_BLOCKED', 'CURRENT_AUTHORITY_NOT_PROVEN'
            elif e.correction_started is True:
                category, reason = 'EXHAUSTED', 'CORRECTION_ALREADY_CONSUMED_NO_REPLAY'
            elif count == 1:
                category, reason, mechanism = ('RECOVERABLE_WITH_REMAINING_BUDGET',
                    'ONE_CORRECTION_REMAINS_SUBJECT_TO_CANONICAL_CLAIM', 'CANONICAL_SNAPSHOT_CORRECTION')
            elif count == 0 and providers == 0 and not e.initial_started:
                category, reason, mechanism = ('RECOVERABLE_WITH_REMAINING_BUDGET',
                    'PROVEN_UNUSED_INITIAL_PHASE_SUBJECT_TO_CANONICAL_CLAIM', 'CANONICAL_INITIAL_GENERATION')
            else:
                category, reason = 'POLICY_BLOCKED', 'STARTED_PHASE_REQUIRES_EXPLICIT_CONTINUATION_AUTHORITY'
        data = asdict(e)
        digest = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        return dict(version=cls.VERSION, operationId=e.operation_id, classification=category,
            historicalCandidateConsumption=count, historicalProviderAttempts=providers,
            provenCandidateLowerBound=max(e.candidate_lower_bound, count or 0),
            remainingProvenCandidateBudget=remaining, obligations=list(e.obligations),
            fresh=e.fresh, controlEligible=e.control_eligible, currentMarketAllowed=e.market_allowed,
            recoveryMechanism=mechanism, reason=reason, evidenceSha256=digest,
            executionAuthorized=False, historicalOfferAuthority=False,
            commercialReevaluation='CURRENT_BUILD2_AUTHORITY_REQUIRED',
            claimRequirement='EXISTING_OPERATION_LEASE_AND_CURRENT_AUTHORITY_RECHECK')

    @classmethod
    def from_persisted(cls, operation, budget, attempts, *, obligations, fresh,
                       control_eligible, market_allowed, active_owner=False,
                       delivery_uncertain=False):
        """No inference of complete coverage from a legacy attempt counter.

        Candidate rows prove a lower bound, not missing provider/correction events.
        Modern budget evidence is used only for its original operation identity.
        This reader does not create a modern budget or certify a saved candidate.
        """
        valid = bool(budget and str(budget['operation_id']) == str(operation['operation_id']))
        b = budget if valid else {}
        events = b.get('events') or []
        finished = {event.get('attempt') for event in events if event.get('kind') == 'PROVIDER_FINISHED'}
        lower = sum(bool(str(row.get('candidate_text') or '').strip()) for row in attempts
                    if str(row.get('operation_id')) == str(operation['operation_id']))
        e = StrandedReplyEvidence(operation_id=str(operation['operation_id']),
            state=operation['state'], reason=operation.get('last_error') or '',
            obligations=tuple(obligations), fresh=fresh, control_eligible=control_eligible,
            market_allowed=market_allowed, complete_lifetime_evidence=valid,
            candidate_count=b.get('candidate_count'),provider_attempt_count=b.get('provider_attempt_count'),
            correction_started=b.get('correction_started'),initial_started=bool(b.get('initial_started')),
            candidate_lower_bound=lower,legacy_generation_attempts=operation.get('generation_attempt_count'),
            send_attempt_count=operation.get('send_attempt_count') or 0,
            delivery_uncertain=delivery_uncertain or bool(operation.get('uncertain_at')),
            active_owner=active_owner,
            provider_in_flight=any(event.get('kind') == 'PROVIDER_STARTED' and event.get('attempt') not in finished for event in events))
        return cls.assess(e)
