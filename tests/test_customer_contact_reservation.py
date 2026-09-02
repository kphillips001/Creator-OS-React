from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Lock
from uuid import uuid4

from app.models.customer_contact import ContactPolicyResult, ContactPurpose
from app.models.customer_contact_reservation import CustomerContactReservation
from app.services.customer_contact_authority_service import CustomerContactAuthorityService
from app.services.autonomous_engagement_teaser_service import AutonomousEngagementTeaserService


class AtomicMemoryReservations:
    def __init__(self):
        self.lock = Lock(); self.active = {}; self.history = []

    def try_acquire(self, **values):
        key = (values["fanvue_account_id"], values["customer_scope"])
        with self.lock:
            current = self.active.get(key)
            if current and current.state in {"ACTIVE", "SEND_UNCERTAIN"}:
                return None, current
            now = datetime.now(timezone.utc)
            item = CustomerContactReservation(
                reservation_id=uuid4(), fanvue_account_id=key[0],
                customer_scope=key[1], contact_purpose=values["contact_purpose"],
                state="ACTIVE", owner_id=values["owner_id"], reserved_at=now,
                lease_expires_at=now + timedelta(seconds=values["lease_seconds"]),
                correlation_id=values.get("correlation_id"),
            )
            self.active[key] = item; self.history.append(item)
            return item, None

    def finalize(self, reservation_id, *, owner_id, state,
                 delivery_reference=None, last_error=None):
        with self.lock:
            key, current = next((pair for pair in self.active.items()
                                 if pair[1].reservation_id == reservation_id), (None, None))
            if current is None or current.owner_id != owner_id: return None
            updated = CustomerContactReservation(
                **{**current.__dict__, "state": state,
                   "delivery_reference": delivery_reference})
            if state not in {"ACTIVE", "SEND_UNCERTAIN"}: self.active.pop(key)
            else: self.active[key] = updated
            self.history.append(updated); return updated


def authorize(service, purpose, customer="fanvue:7", owner=None):
    return service.authorize_proactive(
        purpose=purpose, fanvue_account_id=2, customer_scope=customer,
        owner_id=owner or str(uuid4()), correlation_id=str(uuid4()),
    )


def test_two_concurrent_purposes_exactly_one_reserves_same_customer():
    service = CustomerContactAuthorityService(AtomicMemoryReservations())
    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(
            lambda purpose: authorize(service, purpose),
            (ContactPurpose.FREE_ENGAGEMENT, ContactPurpose.OUTREACH),
        ))
    assert sum(reservation is not None for _, reservation in values) == 1
    denied = next(decision for decision, reservation in values if reservation is None)
    assert denied.result is ContactPolicyResult.DEFER
    assert denied.reason == "PROACTIVE_CONTACT_RESERVATION_HELD"


def test_different_customers_do_not_block_and_failure_releases():
    service = CustomerContactAuthorityService(AtomicMemoryReservations())
    first_decision, first = authorize(service, ContactPurpose.FREE_ENGAGEMENT, "fanvue:7")
    second_decision, second = authorize(service, ContactPurpose.OUTREACH, "fanvue:8")
    assert first and second
    service.finalize_reservation(first, outcome="FAILED", error="provider rejected")
    retry_decision, retry = authorize(service, ContactPurpose.RE_ENGAGEMENT, "fanvue:7")
    assert retry and retry_decision.result is ContactPolicyResult.ALLOW


def test_uncertain_remains_exclusive_while_confirmed_is_finalized():
    repository = AtomicMemoryReservations()
    service = CustomerContactAuthorityService(repository)
    _, first = authorize(service, ContactPurpose.FREE_ENGAGEMENT)
    service.finalize_reservation(first, outcome="SEND_UNCERTAIN")
    denied, duplicate = authorize(service, ContactPurpose.OUTREACH)
    assert duplicate is None and denied.result is ContactPolicyResult.DEFER

    other = CustomerContactAuthorityService(AtomicMemoryReservations())
    _, confirmed = authorize(other, ContactPurpose.FREE_ENGAGEMENT)
    result = other.finalize_reservation(
        confirmed, outcome="CONFIRMED", delivery_reference="telegram:99")
    assert result.state == "CONFIRMED" and result.delivery_reference == "telegram:99"


def test_reactive_and_transactional_contact_do_not_require_proactive_lease():
    repository = AtomicMemoryReservations()
    service = CustomerContactAuthorityService(repository)
    assert service.decide(purpose=ContactPurpose.REACTIVE_CONVERSATION,
                          evidence={"cooldown_active": True}).result is ContactPolicyResult.ALLOW
    assert service.decide(purpose=ContactPurpose.PURCHASE_ACKNOWLEDGEMENT,
                          evidence={"recent_purchase": True}).result is ContactPolicyResult.ALLOW
    assert repository.history == []


def test_free_engagement_remains_reservable():
    decision, reservation = authorize(
        CustomerContactAuthorityService(AtomicMemoryReservations()),
        ContactPurpose.FREE_ENGAGEMENT,
    )
    assert decision.result is ContactPolicyResult.ALLOW
    assert reservation.contact_purpose == "FREE_ENGAGEMENT"


def test_free_engagement_orchestrator_reserves_then_confirms_delivery():
    from types import SimpleNamespace
    import asyncio

    reservations = AtomicMemoryReservations()
    authority = CustomerContactAuthorityService(reservations)
    decision = SimpleNamespace(
        decision="SEND_FREE_ENGAGEMENT_TEASER",
        strategy=SimpleNamespace(value="WARM_UP"),
        reason_code="NEWER_CUSTOMER_HEALTHY_CONVERSATION",
        evidence={}, policy_version=1,
    )
    operation = SimpleNamespace(operation_id=uuid4(), teaser_asset_id=400)

    class DeliveryRepository:
        def update_caption(self, _operation_id, _caption): return operation
        def failed(self, *_): raise AssertionError("unexpected failure")

    class Delivery:
        repository = DeliveryRepository()
        def prepare(self, **_): return SimpleNamespace(operation=operation, reason=None, status="CREATED")
        async def execute_async(self, *_args, **_kwargs):
            return SimpleNamespace(status="CONFIRMED", provider_message_id=77)

    service = AutonomousEngagementTeaserService(
        policy_service=SimpleNamespace(evaluate=lambda **_: decision),
        delivery_service=Delivery(),
        caption_service=SimpleNamespace(generate=lambda **_: "thought you might like this"),
        policy_repository=SimpleNamespace(persist_decision=lambda *_, **__: None),
        contact_authority=authority,
    )
    result = SimpleNamespace(
        correlation_id="inbound:1",
        diagnostic_metadata={"creator_profile_id": 1, "fanvue_account_id": 2,
                             "fanvue_user_id": 7, "conversation_thread_id": 9},
        blocked=False, error_code=None, offer_authorized=False,
        offer_link=None, delivery_requires_payment=False,
    )
    payload = SimpleNamespace(telegram_user_id=8, telegram_chat_id=8,
                              message_id=1, chat_history=[])
    outcome = asyncio.run(service.handle_active_inbound(
        result=result, payload=payload, transport=object()))
    assert outcome["status"] == "CONFIRMED"
    assert any(item.state == "CONFIRMED" and
               item.contact_purpose == "FREE_ENGAGEMENT"
               for item in reservations.history)
