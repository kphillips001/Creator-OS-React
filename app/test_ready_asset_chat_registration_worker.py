from pathlib import Path
from types import SimpleNamespace

from app.models.chat_commerce_registration import (
    ChatAvailabilityState, ChatCommerceRegistrationResult,
)
from app.repositories.ready_asset_chat_registration_job_repository import (
    ReadyAssetChatRegistrationJob, ReadyAssetChatRegistrationJobRepository,
)
from app.services.ready_asset_chat_registration_worker_service import (
    ReadyAssetChatRegistrationWorkerService,
)


class Jobs:
    def __init__(self, job=ReadyAssetChatRegistrationJob(42, 1)):
        self.job, self.completed, self.failed = job, [], []
    def claim_next(self, worker): job, self.job = self.job, None; return job
    def complete(self, asset_id, worker, result): self.completed.append((asset_id, worker, result)); return True
    def fail(self, asset_id, worker, error): self.failed.append((asset_id, worker, error)); return True


class Chat:
    def __init__(self, *, ready=False): self.calls, self.ready = [], ready
    def register_fulfilled_asset(self, asset_id, **kwargs):
        self.calls.append((asset_id, kwargs))
        state = ChatAvailabilityState.CHAT_READY if self.ready else ChatAvailabilityState.BLOCKED
        reasons = () if self.ready else ("invalid_destination", "fulfillment_record_not_found")
        return ChatCommerceRegistrationResult(
            success=self.ready, asset_id=asset_id, availability_state=state,
            chat_ready=self.ready, recommendation_eligible=self.ready,
            delivery_eligible=self.ready, block_reasons=reasons,
            record=SimpleNamespace(chat_registration_id=None),
        )


class Runtime:
    def __init__(self, exists=True): self.exists = exists
    def resolve_original(self, asset, *, require_exists):
        assert require_exists is True
        return SimpleNamespace(exists=self.exists, path=Path("asset.jpg") if self.exists else None)


def worker(*, ready=False, media=True, asset_owner=7, business_owner=7):
    jobs, chat = Jobs(), Chat(ready=ready)
    service = ReadyAssetChatRegistrationWorkerService(
        worker_instance_id="chat-1", jobs=jobs, chat_registration=chat,
        assets=SimpleNamespace(get_by_id=lambda asset_id: SimpleNamespace(id=asset_id, creator_profile_id=asset_owner)),
        registrations=SimpleNamespace(get_by_asset_id=lambda asset_id: SimpleNamespace(creator_profile_id=business_owner)),
        runtime_media=Runtime(media),
    )
    return service, jobs, chat


def test_ready_asset_is_registered_through_existing_service_and_can_be_chat_ready():
    service, jobs, chat = worker(ready=True)
    result = service.process_one()
    assert result == {"processed": True, "asset_id": 42, "status": "CHAT_READY", "chat_ready": True, "missing_requirements": []}
    assert chat.calls[0][0] == 42
    assert chat.calls[0][1]["idempotency_key"] == "ready-asset-chat-registration:42"
    assert jobs.completed and not jobs.failed


def test_destination_and_fulfillment_are_reported_truthfully_without_external_work():
    service, _, chat = worker()
    result = service.process_one()
    assert result["chat_ready"] is False
    assert result["missing_requirements"] == ["invalid_destination", "fulfillment_record_not_found"]
    assert not hasattr(chat, "upload") and not hasattr(chat, "send")


def test_missing_runtime_media_and_owner_mismatch_are_forwarded_as_blocks():
    service, _, chat = worker(media=False, business_owner=8)
    service.process_one()
    reasons = chat.calls[0][1]["additional_block_reasons"]
    assert reasons == ("runtime_media_missing", "creator_ownership_mismatch")


def test_idle_retry_does_not_process_duplicate_job():
    service, jobs, chat = worker()
    service.process_one()
    assert service.process_one() == {"processed": False, "status": "IDLE"}
    assert len(chat.calls) == 1 and len(jobs.completed) == 1


def test_claim_query_enforces_ready_completed_registered_and_is_restart_safe():
    import inspect
    source = inspect.getsource(ReadyAssetChatRegistrationJobRepository.claim_next)
    assert "analysis_status = 'READY'" in source
    assert "content_intelligence_status = 'COMPLETE'" in source
    assert "c.status = 'COMPLETE'" in source
    assert "commerce_registration_status = 'REGISTERED'" in source
    assert "business_lifecycle_state <> 'RETIRED'" in source
    assert "FOR UPDATE OF j SKIP LOCKED" in source and "lease_expires_at <= now()" in source
    assert "ON CONFLICT (asset_id) DO NOTHING" in source


def test_worker_does_not_invoke_fulfillment_delivery_or_publishing():
    import inspect
    source = inspect.getsource(ReadyAssetChatRegistrationWorkerService)
    for forbidden in ("FulfillmentRegistrationService", "ChatCommerceDeliveryService", "PublishingService", "upload_", "send_"):
        assert forbidden not in source
