from types import SimpleNamespace
from unittest.mock import Mock

from app.models.telegram_inbound import TelegramInboundResult
from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService


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


def test_empty_unblocked_result_is_not_misclassified_as_policy_suppression():
    repository = Mock()
    repository.store_generated.return_value = "generated"
    service = OrdinaryChatReplyService(repository=repository, worker_id="worker")

    service.generated(
        SimpleNamespace(operation_id="operation"),
        inbound_result(text="", blocked=False),
    )

    repository.store_generated.assert_called_once()
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
