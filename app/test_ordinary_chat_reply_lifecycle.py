from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

from app.models.telegram_inbound import TelegramInboundResult
from app.models.ordinary_chat_reply_operation import OrdinaryChatReplyState
from app.services.ordinary_chat_reply_service import (
    OrdinaryChatReplyService,
    durable_plain_data,
)


def inbound_result(*, text="Hi there", blocked=False, error_code=None):
    return TelegramInboundResult(
        correlation_id="telegram:12:34", telegram_chat_id=12,
        telegram_user_id=34, message_id=56, engine_user_id="2:-34",
        response_text=text, offer_authorized=False, offer_link=None,
        blocked=blocked, error_code=error_code,
        delivery_payload={"message_text": text} if text else {},
        diagnostic_metadata={
            "status": "blocked" if blocked else "ok",
            **({"paid_presentation_block_reason": error_code}
               if error_code else {}),
        },
    )


def test_nonempty_generation_remains_sendable_generated():
    repository = Mock()
    repository.store_generated.return_value = "generated"
    service = OrdinaryChatReplyService(repository=repository, worker_id="worker")

    stored = service.generated(SimpleNamespace(operation_id="operation"), inbound_result())

    assert stored == "generated"
    repository.store_generated.assert_called_once()
    repository.store_suppressed_generation.assert_not_called()


def test_blocked_empty_generation_is_terminal_suppression_with_reason():
    repository = Mock()
    repository.store_suppressed_generation.return_value = "suppressed"
    service = OrdinaryChatReplyService(repository=repository, worker_id="worker")

    stored = service.generated(
        SimpleNamespace(operation_id="operation"),
        inbound_result(
            text="", blocked=True,
            error_code="PAID_PRESENTATION_UNMAPPED_EXPLICIT_PRICE",
        ),
    )

    assert stored == "suppressed"
    repository.store_generated.assert_not_called()
    call = repository.store_suppressed_generation.call_args
    assert call.kwargs["reason"] == (
        "intentional_suppression:PAID_PRESENTATION_UNMAPPED_EXPLICIT_PRICE"
    )
    assert call.kwargs["response_text"] == ""
    assert call.kwargs["response_payload"]["blocked"] is True
    assert call.kwargs["response_payload"]["diagnostic_metadata"][
        "paid_presentation_block_reason"
    ] == "PAID_PRESENTATION_UNMAPPED_EXPLICIT_PRICE"


def test_empty_unblocked_result_uses_bounded_sendable_fallback():
    repository = Mock()
    repository.store_generated.return_value = "generated"
    service = OrdinaryChatReplyService(repository=repository, worker_id="worker")

    stored = service.generated(
        SimpleNamespace(operation_id="operation"),
        inbound_result(text="", blocked=False),
    )

    assert stored == "generated"
    repository.fail_empty_generation.assert_not_called()
    assert repository.store_generated.call_args.kwargs["response_text"]
    assert repository.store_generated.call_args.kwargs["response_payload"][
        "diagnostic_metadata"]["generation_fallback"]["reason"] == "EMPTY_GENERATION"
    repository.store_suppressed_generation.assert_not_called()


def test_provider_failure_uses_generation_failure_not_policy_suppression():
    repository = Mock()
    repository.fail_generation.return_value = "retryable"
    service = OrdinaryChatReplyService(repository=repository, worker_id="worker")

    stored = service.generation_failed(
        SimpleNamespace(operation_id="operation"),
        TimeoutError("provider timeout"),
    )

    assert stored == "retryable"
    repository.fail_generation.assert_called_once_with(
        "operation", owner="worker", reason="TimeoutError: provider timeout",
    )
    repository.store_suppressed_generation.assert_not_called()


def test_durable_plain_data_recursively_copies_immutable_mappings():
    class Signal(Enum):
        FUTURE = "FUTURE_COMMERCIAL_INTEREST"

    nested_dict = {"preference": "outdoor shots"}
    source = MappingProxyType({
        "direct": MappingProxyType({"buyerStatus": "VERIFIED_BUYER"}),
        "sequence": [
            MappingProxyType({"commercialInterestType": Signal.FUTURE}),
            (MappingProxyType({"purchaseCount": 1}),),
        ],
        "ordinary": nested_dict,
        "identity": UUID("00000000-0000-0000-0000-000000000011"),
        "observedAt": datetime(2026, 9, 3, tzinfo=timezone.utc),
        "evidence": frozenset({"BUYER", "PREFERENCE"}),
    })

    durable = durable_plain_data(source)

    assert durable == {
        "direct": {"buyerStatus": "VERIFIED_BUYER"},
        "sequence": [
            {"commercialInterestType": "FUTURE_COMMERCIAL_INTEREST"},
            [{"purchaseCount": 1}],
        ],
        "ordinary": {"preference": "outdoor shots"},
        "identity": "00000000-0000-0000-0000-000000000011",
        "observedAt": "2026-09-03T00:00:00+00:00",
        "evidence": ["BUYER", "PREFERENCE"],
    }
    durable["direct"]["buyerStatus"] = "CHANGED"
    durable["ordinary"]["preference"] = "changed"
    assert source["direct"]["buyerStatus"] == "VERIFIED_BUYER"
    assert nested_dict["preference"] == "outdoor shots"


def test_generated_persists_turn6_shaped_immutable_diagnostics_without_loss():
    repository = Mock()
    repository.store_generated.return_value = "generated"
    service = OrdinaryChatReplyService(repository=repository, worker_id="worker")
    result = inbound_result(text="I’ll keep that in mind for next time")
    result.diagnostic_metadata.update({
        "customer_value_attention": MappingProxyType({
            "buyerStatus": "VERIFIED_BUYER",
            "purchaseCount": 1,
            "ownershipCount": 1,
        }),
        "conversational_memory": MappingProxyType({
            "retrieved": (
                MappingProxyType({
                    "key": "content_style_preference",
                    "value": "outdoor shots",
                }),
            ),
        }),
        "commercial_receptiveness": MappingProxyType({
            "commercialInterestType": "FUTURE_COMMERCIAL_INTEREST",
            "continuationEligible": True,
        }),
    })
    result.delivery_payload["metadata"] = MappingProxyType({
        "transport": MappingProxyType({"mode": "TEST_TRANSPORT_NO_WAIT"}),
    })

    stored = service.generated(SimpleNamespace(operation_id="operation"), result)

    assert stored == "generated"
    payload = repository.store_generated.call_args.kwargs["response_payload"]
    assert payload["diagnostic_metadata"]["customer_value_attention"] == {
        "buyerStatus": "VERIFIED_BUYER",
        "purchaseCount": 1,
        "ownershipCount": 1,
    }
    assert payload["diagnostic_metadata"]["conversational_memory"]["retrieved"] == [{
        "key": "content_style_preference",
        "value": "outdoor shots",
    }]
    assert payload["diagnostic_metadata"]["commercial_receptiveness"] == {
        "commercialInterestType": "FUTURE_COMMERCIAL_INTEREST",
        "continuationEligible": True,
    }
    assert repository.store_generated.call_args.kwargs["delivery_payload"] == {
        "message_text": "I’ll keep that in mind for next time",
        "metadata": {"transport": {"mode": "TEST_TRANSPORT_NO_WAIT"}},
    }
    assert isinstance(
        result.diagnostic_metadata["commercial_receptiveness"],
        type(MappingProxyType({})),
    )


def test_suppressed_generation_accepts_nested_immutable_diagnostics():
    repository = Mock()
    repository.store_suppressed_generation.return_value = "suppressed"
    service = OrdinaryChatReplyService(repository=repository, worker_id="worker")
    result = inbound_result(
        text="", blocked=True, error_code="AUTHORITATIVE_REPLY_SUPPRESSION",
    )
    result.diagnostic_metadata["commercial_summary"] = MappingProxyType({
        "outboundSuppression": MappingProxyType({"suppressed": True}),
    })

    assert service.generated(
        SimpleNamespace(operation_id="operation"), result,
    ) == "suppressed"
    payload = repository.store_suppressed_generation.call_args.kwargs[
        "response_payload"
    ]
    assert payload["diagnostic_metadata"]["commercial_summary"] == {
        "outboundSuppression": {"suppressed": True},
    }


def test_image_boundary_is_recorded_only_after_confirmed_delivery():
    repository=Mock();boundary=Mock()
    confirmed=SimpleNamespace(
        state=OrdinaryChatReplyState.SENT_CONFIRMED,
        sent_confirmed_at=datetime.now(timezone.utc),
        response_payload={'diagnostic_metadata':{'current_turn_visual_context':{
            'operation_id':'00000000-0000-0000-0000-000000000001',
            'creator_profile_id':1,'fanvue_account_id':2,'telegram_user_id':3,
            'response_policy':'POLITE_EXPLICIT_BOUNDARY'}}})
    repository.confirm_sent.return_value=confirmed
    service=OrdinaryChatReplyService(repository=repository,worker_id='worker',
        image_boundary_repository=boundary)
    assert service.confirmed(SimpleNamespace(operation_id='reply'),9001) is confirmed
    boundary.record_boundary_delivered.assert_called_once_with(
        operation_id='00000000-0000-0000-0000-000000000001',
        creator_profile_id=1,fanvue_account_id=2,telegram_user_id=3,
        policy='POLITE_EXPLICIT_BOUNDARY',delivered_at=confirmed.sent_confirmed_at)


def test_unconfirmed_media_reply_never_records_boundary():
    repository=Mock();boundary=Mock()
    service=OrdinaryChatReplyService(repository=repository,worker_id='worker',
        image_boundary_repository=boundary)
    service.generation_failed(SimpleNamespace(operation_id='reply'),TimeoutError())
    boundary.record_boundary_delivered.assert_not_called()


def test_visual_attestation_survives_durable_response_serialization_without_raw_observations():
    repository=Mock();repository.store_generated.return_value="generated"
    service=OrdinaryChatReplyService(repository=repository,worker_id="worker")
    result=inbound_result(text="Nice smile.")
    result.diagnostic_metadata["visual_analysis"]={
        "status":"READY","visual_attestation":{
            "structured_schema_valid":True,"attachment_correlation_valid":True,
            "provider_status_completed":True,"person_visible":True,
            "smiling_visible":True,"person_count_bucket":"ONE",
            "self_presentation_authority":True,"customer_presented_self_image":True,
            "visual_response_policy":"SELFIE_COMPLIMENT_ELIGIBLE",
            "visual_evidence_class":"EPHEMERAL_VISUAL_CONTEXT"}}
    service.generated(SimpleNamespace(operation_id="operation"),result)
    payload=repository.store_generated.call_args.kwargs["response_payload"]
    assert payload["diagnostic_metadata"]["visual_analysis"]["visual_attestation"]["person_visible"] is True
    assert "observations" not in str(payload).lower()
