import asyncio
import pytest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.models.free_engagement_teaser import (
    SEND_FREE_ENGAGEMENT_TEASER,
    FreeEngagementTeaserDeliveryState as State,
    FreeEngagementTeaserOperation,
)
from app.services.free_engagement_teaser_service import FreeEngagementTeaserService
from app.services.telegram_delivery_executor import TelegramDeliveryExecutionResult


def operation(state=State.CREATED, *, asset_id=400, customer_id=30):
    return FreeEngagementTeaserOperation(
        operation_id=uuid4(), correlation_id=str(uuid4()), creator_profile_id=1,
        fanvue_account_id=2, fanvue_user_id=customer_id,
        conversation_thread_id=4, telegram_chat_id=5,
        inbound_telegram_message_id=6, teaser_asset_id=asset_id,
        media_reference="C:/safe/teaser.jpg", caption="hello", state=state,
        engagement_strategy="WARM_UP",
    )


class MemoryRepository:
    def __init__(self, item=None):
        self.item = item
        self.context_error = None
        self.conflict = None
        self.reservations = set()
        self.accepted_items = []

    def validate_context(self, **_): return self.context_error
    def funnel_conflict(self, **_): return self.conflict
    def reserve_next(self, **kwargs):
        key = (kwargs["fanvue_user_id"], 400)
        if key in self.reservations: return None
        self.reservations.add(key)
        self.item = operation(customer_id=kwargs["fanvue_user_id"])
        return self.item
    def get(self, _): return self.item
    def claim(self, _):
        self.item = replace(self.item, state=State.SENDING); return self.item
    def accepted(self, _, message_id):
        self.item = replace(self.item, state=State.TELEGRAM_ACCEPTED,
                            outbound_telegram_message_id=message_id)
        return self.item
    def confirmed(self, _):
        self.item = replace(self.item, state=State.CONFIRMED); return self.item
    def failed(self, _, reason):
        self.item = replace(self.item, state=State.FAILED, failure_reason=reason); return self.item
    def ambiguous(self, _, reason):
        self.item = replace(self.item, state=State.AMBIGUOUS, failure_reason=reason); return self.item
    def mark_sending_ambiguous(self):
        if self.item and self.item.state is State.SENDING:
            self.item = replace(self.item, state=State.AMBIGUOUS)
            return (self.item,)
        return ()
    def list_accepted(self): return tuple(self.accepted_items)


class AllowedSafety:
    def __init__(self, allowed=True, code="ALLOWED"): self.allowed, self.code = allowed, code
    def decide(self, **_): return SimpleNamespace(allowed=self.allowed, code=self.code)


class GlobalSafety:
    def __init__(self, allowed=True): self.allowed = allowed
    def check_global_safety(self): return {"allowed": self.allowed, "reason": "RUNTIME_OFFLINE"}


class Delivery:
    def __init__(self, result=None, error=None):
        self.calls = 0; self.error = error
        self.result = result or TelegramDeliveryExecutionResult(
            status="success", executed=True, metadata={"telegram_message_id": 901})
    async def execute_async(self, payload, *, context):
        self.calls += 1
        assert payload["metadata"]["action"] == SEND_FREE_ENGAGEMENT_TEASER
        assert payload["metadata"]["free"] is True
        assert "price" not in payload and "delivery_url" not in payload
        if self.error: raise self.error
        return self.result


def service(repo, *, safety=None, global_safety=None, delivery=None, saver=None):
    return FreeEngagementTeaserService(
        repository=repo, asset_repository=SimpleNamespace(), media_resolver=SimpleNamespace(),
        customer_safety_service=safety or AllowedSafety(),
        global_safety_service=global_safety or GlobalSafety(),
        delivery_executor=delivery or Delivery(),
        conversation_message_saver=saver or (lambda **_: None),
    )


def prepare(subject, customer_id=30):
    return subject.prepare(creator_profile_id=1, fanvue_account_id=2,
        fanvue_user_id=customer_id, telegram_user_id=5, telegram_chat_id=5,
        conversation_thread_id=4, correlation_id=str(uuid4()))


def test_distinct_noncommercial_action_and_per_customer_per_asset_no_repeat():
    repo = MemoryRepository(); subject = service(repo)
    first = prepare(subject, 30)
    assert first.action == SEND_FREE_ENGAGEMENT_TEASER and first.status == "CREATED"
    assert prepare(subject, 30).status == "NO_ELIGIBLE_TEASER"
    assert prepare(subject, 31).status == "CREATED"


def test_safety_identity_and_funnel_conflicts_suppress_before_reservation():
    repo = MemoryRepository(); repo.context_error = "IDENTITY_UNRESOLVED"
    assert prepare(service(repo)).reason == "IDENTITY_UNRESOLVED"
    repo.context_error = None; repo.conflict = "ACTIVE_PURCHASE_INTENT"
    assert prepare(service(repo)).reason == "ACTIVE_PURCHASE_INTENT"
    repo.conflict = None
    assert prepare(service(repo, safety=AllowedSafety(False, "BLOCKED_UNDERAGE"))).reason == "BLOCKED_UNDERAGE"
    assert prepare(service(repo, global_safety=GlobalSafety(False))).reason == "RUNTIME_OFFLINE"
    assert not repo.reservations


def test_success_persists_acceptance_then_one_canonical_media_transcript():
    repo = MemoryRepository(operation()); delivery = Delivery(); transcripts = []
    result = asyncio.run(service(repo, delivery=delivery, saver=lambda **row: transcripts.append(row))
                         .execute_async(repo.item.operation_id, transport=object()))
    assert result.status == "CONFIRMED" and delivery.calls == 1
    assert len(transcripts) == 1
    assert transcripts[0]["has_media"] is True
    assert transcripts[0]["raw_payload"]["delivery_kind"] == "FREE_ENGAGEMENT_TEASER"
    assert transcripts[0]["raw_payload"]["telegram_message_id"] == 901
    assert transcripts[0]["raw_payload"]["engagement_strategy"] == "WARM_UP"
    assert transcripts[0]["text"] == "hello"
    assert transcripts[0]["media_uuids"] == ["asset:400"]
    replay = asyncio.run(service(repo, delivery=delivery).execute_async(repo.item.operation_id, transport=object()))
    assert replay.status == "CONFIRMED" and replay.executed is False and delivery.calls == 1


def test_accepted_crash_is_repaired_without_resend_and_sending_is_ambiguous():
    accepted = operation(State.TELEGRAM_ACCEPTED)
    accepted = replace(accepted, outbound_telegram_message_id=902)
    repo = MemoryRepository(accepted); repo.accepted_items = [accepted]
    delivery = Delivery(); transcripts = []
    recovered = service(repo, delivery=delivery, saver=lambda **row: transcripts.append(row)).recover_startup()
    assert recovered["confirmed"][0].state is State.CONFIRMED
    assert delivery.calls == 0 and len(transcripts) == 1
    repo = MemoryRepository(operation(State.SENDING))
    recovered = service(repo, delivery=delivery).recover_startup()
    assert recovered["ambiguous"][0].state is State.AMBIGUOUS and delivery.calls == 0


def test_repeated_accepted_recovery_uses_deterministic_transcript_identity():
    accepted = replace(operation(State.TELEGRAM_ACCEPTED), outbound_telegram_message_id=903)
    repo = MemoryRepository(accepted); repo.accepted_items = [accepted]
    rows = {}
    def idempotent_saver(**row):
        rows.setdefault(row["fanvue_message_uuid"], row)
    first = service(repo, saver=idempotent_saver).recover_startup()
    assert first["confirmed"][0].state is State.CONFIRMED
    repo.item = accepted
    service(repo, saver=idempotent_saver).recover_startup()
    assert len(rows) == 1


@pytest.mark.parametrize("strategy", ["WARM_UP", "RE_ENGAGE", "RELATIONSHIP"])
def test_all_engagement_strategies_persist_canonical_media_metadata(strategy):
    item = replace(operation(), engagement_strategy=strategy)
    repo = MemoryRepository(item); transcripts = []
    result = asyncio.run(service(repo, saver=lambda **row: transcripts.append(row))
                         .execute_async(item.operation_id, transport=object()))
    assert result.status == "CONFIRMED"
    assert transcripts[0]["raw_payload"]["engagement_strategy"] == strategy
    assert transcripts[0]["has_media"] is True


def test_definite_failure_has_no_transcript_and_unknown_failure_is_ambiguous():
    transcripts = []; repo = MemoryRepository(operation())
    failed = asyncio.run(service(repo, delivery=Delivery(error=ValueError("rejected")),
        saver=lambda **row: transcripts.append(row)).execute_async(repo.item.operation_id, transport=object()))
    assert failed.status == "FAILED" and transcripts == []
    repo = MemoryRepository(operation())
    ambiguous = asyncio.run(service(repo, delivery=Delivery(error=TimeoutError()),
        saver=lambda **row: transcripts.append(row)).execute_async(repo.item.operation_id, transport=object()))
    assert ambiguous.status == "AMBIGUOUS" and transcripts == []


def test_migration_and_selector_encode_authoritative_inventory_and_db_uniqueness():
    migration = Path("migrations/forward/20260824_085_free_engagement_teaser_delivery.sql").read_text()
    repository = Path("app/repositories/free_engagement_teaser_repository.py").read_text()
    assert "engagement_teaser_customer_asset_never_repeat UNIQUE" in migration
    for predicate in ("destination='TEASER'", "ENGAGEMENT_TEASER", "is_active", "is_test",
                      "photoshoot_asset_memberships", "commercial_role_assignments",
                      "commercial_offering_assets", "chat_enabled", "SKIP LOCKED"):
        assert predicate in repository
