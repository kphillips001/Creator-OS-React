from app.services.corrective_generation_evidence_service import (
    CorrectiveGenerationEvidenceService,
)


def payload(candidate="then don't make it too easy for me"):
    return {
        "response_text": candidate,
        "diagnostic_metadata": {
            "conversationStyle": {
                "turnObligations": ["ANSWER_DIRECT_QUESTION"],
                "finalResponseRepetitionSatisfied": False,
            },
            "conversationCoherence": {
                "resolvedCustomerMeaning": "How effective is my teasing today?",
                "resolvedPersonaDomain": "ordinary",
            },
            "provider": "OPENAI",
        },
    }


def test_clay_shaped_repetition_evidence_uses_hard_normalized_exclusions():
    rejected = "then don't make it too easy for me"
    evidence = CorrectiveGenerationEvidenceService.build(
        response_payload=payload(rejected),
        reasons=["FINAL_REPETITION_FAILURE"],
        recent_ava_responses=[
            "Then, don't make it too easy for me!",
            "You definitely keep me curious.",
        ],
        source="OPERATOR_APPROVED_HISTORICAL_CORRECTION",
        original_operation_id="e77d363f-195c-42c8-a028-5ccd0e7fd887",
        original_inbound_message_id=6767,
        require_rejected_candidate=True,
    )
    assert evidence["previousCandidateFailure"] == "FINAL_REPETITION_FAILURE"
    assert evidence["previousCandidateText"] == rejected
    assert evidence["blockingReasons"] == ["FINAL_REPETITION_FAILURE"]
    assert evidence["excludedExactResponses"] == [
        rejected, "You definitely keep me curious.",
    ]
    assert evidence["exclusionAuthority"] == "FINAL_RESPONSE_EXACT_NOVELTY"
    assert evidence["turnObligations"] == ["ANSWER_DIRECT_QUESTION"]
    assert evidence["previousCandidateDiagnostics"]["provider"] == "OPENAI"
    assert evidence["originalInboundMessageId"] == 6767


def test_historical_repetition_missing_candidate_fails_closed():
    try:
        CorrectiveGenerationEvidenceService.build(
            response_payload={"diagnostic_metadata": {}},
            reasons=["FINAL_REPETITION_FAILURE"],
            require_rejected_candidate=True,
        )
    except ValueError as exc:
        assert str(exc) == (
            "HISTORICAL_CORRECTIVE_REJECTED_CANDIDATE_EVIDENCE_REQUIRED"
        )
    else:
        raise AssertionError("missing rejected candidate did not fail closed")


def test_non_answer_without_candidate_remains_supported():
    evidence = CorrectiveGenerationEvidenceService.build(
        response_payload={"diagnostic_metadata": {}},
        reasons=["CUSTOMER_QUESTION_UNANSWERED"],
        require_rejected_candidate=False,
    )
    assert evidence["previousCandidateFailure"] == "CUSTOMER_QUESTION_UNANSWERED"
    assert evidence["excludedExactResponses"] == []
