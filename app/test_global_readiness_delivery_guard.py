from types import SimpleNamespace

from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService


class _Permissions:
    def __init__(self, *, allowed, reason=None):
        self.allowed = allowed
        self.reason = reason

    def read(self, **_scope):
        return {"effective": {
            "chatAllowed": self.allowed,
            "chatReason": self.reason,
        }}


class _Repository:
    def __init__(self):
        self.deferred = []
        self.blocked = []

    def defer_for_global_readiness(self, operation_id, *, reason):
        self.deferred.append((operation_id, reason))
        return SimpleNamespace(operation_id=operation_id, state="RETRYABLE")

    def record_deterministic_delivery_block(self, operation_id, *, owner,
                                            reason, metadata):
        self.blocked.append((operation_id, owner, reason, metadata))
        return SimpleNamespace(operation_id=operation_id, state="RETRYABLE")


def _operation():
    return SimpleNamespace(
        operation_id="operation-1",
        inbound_sender_telegram_user_id=101,
        telegram_chat_id=101,
    )


def test_global_attention_defers_before_generation():
    repository = _Repository()
    service = OrdinaryChatReplyService(
        repository=repository, creator_profile_id=2, fanvue_account_id=2,
        effective_permissions=_Permissions(
            allowed=False, reason="GLOBAL_AVA_BOT_ATTENTION"),
    )

    deferred = service.defer_if_global_delivery_prohibited(_operation())

    assert deferred is not None
    assert repository.deferred == [
        ("operation-1", "GLOBAL_AVA_BOT_ATTENTION")]


def test_healthy_readiness_does_not_defer_generation():
    repository = _Repository()
    service = OrdinaryChatReplyService(
        repository=repository, creator_profile_id=2, fanvue_account_id=2,
        effective_permissions=_Permissions(allowed=True),
    )

    assert service.defer_if_global_delivery_prohibited(_operation()) is None
    assert repository.deferred == []


def test_deterministic_permission_block_has_distinct_persistence_boundary():
    repository = _Repository()
    service = OrdinaryChatReplyService(
        repository=repository, worker_id="worker-1",
    )

    result = service.deterministic_delivery_blocked(
        _operation(), reason="GLOBAL_AVA_BOT_ATTENTION",
        metadata={"execution_state": "blocked"},
    )

    assert result.state == "RETRYABLE"
    assert repository.blocked == [(
        "operation-1", "worker-1", "GLOBAL_AVA_BOT_ATTENTION",
        {"execution_state": "blocked"},
    )]
