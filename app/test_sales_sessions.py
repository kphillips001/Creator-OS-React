from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import sales_sessions as sales_session_api
from app.models.purchase_intent import AttributionResult, PurchaseIntentStatus
from app.models.sales_session import (
    SalesSession,
    SalesSessionActorType,
    SalesSessionFoundationType,
    SalesSessionHistoryEntry,
    SalesSessionOutcome,
    SalesSessionProgression,
    SalesSessionState,
)
from app.services.sales_session_service import (
    SalesSessionError,
    SalesSessionService,
)


NOW = datetime.now(timezone.utc)
CUSTOMER_UUID = uuid4()


class FakeRepository:
    def __init__(self):
        self.item = None
        self.events = []
        self.links = []

    def create(self, **values):
        values["started_by_type"] = values.pop("actor_type")
        values["started_by_identifier"] = values.pop("actor_identifier")
        values["commercial_foundation_type"] = SalesSessionFoundationType(
            values["commercial_foundation_type"]
        )
        self.item = SalesSession(
            sales_session_id=uuid4(), state=SalesSessionState.ACTIVE,
            progression_stage=SalesSessionProgression.DISCOVERY,
            outcome=None, terminal_reason=None, started_at=NOW,
            last_activity_at=NOW, created_at=NOW, updated_at=NOW,
            **values,
        )
        self._event("STARTED", None, None, values["started_by_type"])
        return self.item

    def get(self, session_id, *, creator_profile_id):
        if (
            self.item and self.item.sales_session_id == session_id
            and self.item.creator_profile_id == creator_profile_id
        ):
            return self.item
        return None

    def get_active_for_customer(self, **values):
        if (
            self.item
            and self.item.state in {
                SalesSessionState.ACTIVE, SalesSessionState.OFFERING,
                SalesSessionState.AWAITING_PAYMENT,
                SalesSessionState.CONTINUING,
            }
            and all(getattr(self.item, key) == value for key, value in values.items())
        ):
            return self.item
        return None

    def list_for_creator(self, *, creator_profile_id, limit):
        return (
            (self.item,) if self.item
            and self.item.creator_profile_id == creator_profile_id else ()
        )

    def conversation_belongs_to_customer(
        self, *, conversation_thread_id, fanvue_account_id, fanvue_user_id,
    ):
        return (
            conversation_thread_id, fanvue_account_id, fanvue_user_id
        ) == (11, 2, 3)

    def transition(
        self, *, expected_state, new_state, progression_stage, outcome,
        terminal_reason, event_type, actor_type, purchase_intent_id=None,
        **_values,
    ):
        if self.item is None or self.item.state is not expected_state:
            return None
        previous_state = self.item.state
        previous_stage = self.item.progression_stage
        self.item = replace(
            self.item, state=new_state,
            progression_stage=progression_stage, outcome=outcome,
            terminal_reason=terminal_reason,
            ended_at=(NOW if new_state not in {
                SalesSessionState.ACTIVE, SalesSessionState.OFFERING,
                SalesSessionState.AWAITING_PAYMENT,
                SalesSessionState.CONTINUING,
            } else None),
        )
        self._event(
            event_type, previous_state, previous_stage, actor_type,
            purchase_intent_id=purchase_intent_id,
        )
        return self.item

    def update_progression(
        self, *, expected_state, progression_stage, actor_type, **values,
    ):
        return self.transition(
            expected_state=expected_state, new_state=expected_state,
            progression_stage=progression_stage, outcome=None,
            terminal_reason=None, event_type="PROGRESSION_CHANGED",
            actor_type=actor_type, **values,
        )

    def associate_purchase_intent(
        self, *, session, purchase_intent_id, actor_type, **_values,
    ):
        if purchase_intent_id not in self.links:
            self.links.append(purchase_intent_id)
            self._event(
                "PURCHASE_INTENT_ASSOCIATED", session.state,
                session.progression_stage, actor_type,
                purchase_intent_id=purchase_intent_id,
            )
        return self.links.index(purchase_intent_id) + 1

    def list_purchase_intents(self, **_values):
        return tuple({
            "purchase_intent_id": value,
            "status": "PURCHASED",
            "attribution_result": "ATTRIBUTED",
        } for value in self.links)

    def purchase_intent_association(self, purchase_intent_id):
        return (
            (self.item.sales_session_id, self.links.index(purchase_intent_id) + 1)
            if purchase_intent_id in self.links else None
        )

    def history(self, **_values):
        return tuple(self.events)

    def commercial_guidance(self, **_values):
        return {
            "assets": ({
                "asset_id": 42,
                "effective_commercial_roles": ["DISCOVERY", "CORE"],
            },),
            "photoshoot_intelligence": {"theme": "bedroom"},
        }

    def _event(
        self, event_type, previous_state, previous_stage, actor_type,
        purchase_intent_id=None,
    ):
        self.events.append(SalesSessionHistoryEntry(
            history_id=len(self.events) + 1,
            sales_session_id=self.item.sales_session_id,
            creator_profile_id=self.item.creator_profile_id,
            event_type=event_type, previous_state=previous_state,
            new_state=self.item.state,
            previous_progression_stage=previous_stage,
            new_progression_stage=self.item.progression_stage,
            purchase_intent_id=purchase_intent_id,
            actor_type=actor_type, actor_identifier=None,
            reason=None, occurred_at=NOW,
        ))


class FakeIdentity:
    def get_by_telegram_user_id(self, telegram_user_id):
        if telegram_user_id != 99:
            return None
        return SimpleNamespace(
            id=5, telegram_user_id=99, fanvue_account_id=2,
            local_fanvue_user_id=3, external_fanvue_user_uuid=CUSTOMER_UUID,
        )

    def get_by_id(self, mapping_id):
        return self.get_by_telegram_user_id(99) if mapping_id == 5 else None


class FakePhotoshoots:
    def get_by_session(self, session_id):
        return (
            {"photoshoot_session_id": session_id, "creator_profile_id": 7}
            if session_id == "photoshoot-1" else None
        )


class FakePurchaseIntents:
    def __init__(self):
        self.intent = SimpleNamespace(
            purchase_intent_id=uuid4(), creator_profile_id=7,
            fanvue_account_id=2, telegram_identity_mapping_id=5,
            telegram_user_id=99, external_fanvue_user_uuid=CUSTOMER_UUID,
            status=PurchaseIntentStatus.PURCHASED,
            attribution_result=AttributionResult.ATTRIBUTED,
        )

    def get(self, intent_id, *, creator_profile_id):
        return (
            self.intent if intent_id == self.intent.purchase_intent_id
            and creator_profile_id == self.intent.creator_profile_id else None
        )


class Compatibility:
    def __init__(self):
        self.started_items = []
        self.ended_items = []

    def started(self, session):
        self.started_items.append(session)

    def ended(self, session):
        self.ended_items.append(session)


@pytest.fixture
def setup():
    repository = FakeRepository()
    intents = FakePurchaseIntents()
    compatibility = Compatibility()
    service = SalesSessionService(
        repository=repository, identity_repository=FakeIdentity(),
        purchase_intent_repository=intents,
        photoshoot_repository=FakePhotoshoots(),
        customer_fetcher=lambda account, user: {
            "id": user, "fanvue_account_id": account,
            "fanvue_user_uuid": CUSTOMER_UUID,
        } if (account, user) == (2, 3) else None,
        creator_profile_resolver=lambda account: (
            {"id": 7} if str(account) == "2" else None
        ),
        compatibility=compatibility,
    )
    return service, repository, intents, compatibility


def start(service, **changes):
    values = {
        "creator_profile_id": 7, "fanvue_account_id": 2,
        "fanvue_user_id": 3, "telegram_user_id": 99,
        "conversation_thread_id": 11,
        "commercial_foundation_type": "PHOTOSHOOT",
        "commercial_foundation_reference": "photoshoot-1",
        "objective": "Bedroom commercial arc",
        "commercial_context": {"current_posture": "ready"},
        "actor_type": "AI", "actor_identifier": "customer-sales-brain",
    }
    values.update(changes)
    return service.start(**values)


def test_ai_can_start_one_canonical_session_and_legacy_projection_runs(setup):
    service, repository, _, compatibility = setup
    session = start(service)
    duplicate = start(service)
    assert duplicate.sales_session_id == session.sales_session_id
    assert session.state is SalesSessionState.ACTIVE
    assert session.progression_stage is SalesSessionProgression.DISCOVERY
    assert session.started_by_type is SalesSessionActorType.AI
    assert len(repository.events) == 1
    assert compatibility.started_items == [session]


def test_conversation_orchestration_reuses_active_session(setup):
    service, _, _, compatibility = setup
    first = service.resolve_or_start_conversation(
        creator_profile_id=7, fanvue_account_id=2, fanvue_user_id=3,
        telegram_user_id=99, conversation_thread_id=11,
        actor_identifier="conversation-gateway",
    )
    second = service.resolve_or_start_conversation(
        creator_profile_id=7, fanvue_account_id=2, fanvue_user_id=3,
        telegram_user_id=99, conversation_thread_id=11,
        actor_identifier="conversation-gateway",
    )
    assert second.sales_session_id == first.sales_session_id
    assert len(compatibility.started_items) == 1


def test_active_conversation_lookup_does_not_start_for_unmapped_customer(setup):
    service, repository, _, compatibility = setup
    assert service.resolve_active_conversation(
        creator_profile_id=7, fanvue_account_id=2, fanvue_user_id=3,
        telegram_user_id=100, conversation_thread_id=11,
    ) is None
    assert repository.get_active_for_customer(
        creator_profile_id=7, fanvue_account_id=2, fanvue_user_id=3,
    ) is None
    assert compatibility.started_items == []


def test_active_conversation_lookup_keeps_mapped_identity_strict(setup):
    service, _, _, _ = setup
    session = start(service)
    assert service.resolve_active_conversation(
        creator_profile_id=7, fanvue_account_id=2, fanvue_user_id=3,
        telegram_user_id=99, conversation_thread_id=11,
    ).sales_session_id == session.sales_session_id
    with pytest.raises(SalesSessionError, match="Telegram identity"):
        service.resolve_active_conversation(
            creator_profile_id=7, fanvue_account_id=2, fanvue_user_id=3,
            telegram_user_id=100, conversation_thread_id=11,
        )


def test_terminal_session_stays_closed_and_later_conversation_can_start(setup):
    service, _, _, _ = setup
    first = service.resolve_or_start_conversation(
        creator_profile_id=7, fanvue_account_id=2, fanvue_user_id=3,
        telegram_user_id=99, conversation_thread_id=11,
    )
    closed = service.complete(
        session_id=first.sales_session_id, creator_profile_id=7,
        with_purchase=False,
    )
    later = service.resolve_or_start_conversation(
        creator_profile_id=7, fanvue_account_id=2, fanvue_user_id=3,
        telegram_user_id=99, conversation_thread_id=11,
    )
    assert closed.state is SalesSessionState.COMPLETED
    assert later.sales_session_id != first.sales_session_id
    assert later.state is SalesSessionState.ACTIVE


def test_identity_and_foundation_are_authoritative(setup):
    service, _, _, _ = setup
    with pytest.raises(SalesSessionError, match="Telegram identity"):
        start(service, telegram_user_id=100)
    with pytest.raises(KeyError, match="foundation"):
        start(service, commercial_foundation_reference="missing")
    with pytest.raises(KeyError, match="Customer"):
        start(service, fanvue_user_id=4)
    with pytest.raises(SalesSessionError, match="Conversation"):
        start(service, conversation_thread_id=12)


def test_conversation_foundation_uses_thread_identity_without_reference(setup):
    service, _, _, _ = setup
    session = start(
        service,
        commercial_foundation_type="CONVERSATION",
        commercial_foundation_reference=None,
    )

    assert (
        session.commercial_foundation_type
        is SalesSessionFoundationType.CONVERSATION
    )
    assert session.commercial_foundation_reference is None
    assert session.conversation_thread_id == 11
    guidance = service.commercial_guidance(session=session)
    assert guidance["foundation_type"] == "CONVERSATION"
    assert guidance["conversation"]["conversation_thread_id"] == 11
    assert guidance["assets"] == ()


@pytest.mark.parametrize("changes, message", [
    ({
        "commercial_foundation_type": "CONVERSATION",
        "commercial_foundation_reference": "not-allowed",
    }, "cannot store"),
    ({
        "commercial_foundation_type": "CONVERSATION",
        "commercial_foundation_reference": None,
        "conversation_thread_id": None,
    }, "conversation thread"),
    ({"commercial_foundation_type": "BUNDLE"}, "Unsupported"),
])
def test_foundation_shape_fails_explicitly(setup, changes, message):
    service, _, _, _ = setup
    with pytest.raises(SalesSessionError, match=message):
        start(service, **changes)


def test_conversation_foundation_validates_creator_scope(setup):
    service, _, _, _ = setup
    service.creator_profile_resolver = lambda _account: {"id": 8}
    with pytest.raises(SalesSessionError, match="creator scope"):
        start(
            service,
            commercial_foundation_type="CONVERSATION",
            commercial_foundation_reference=None,
        )


def test_context_rejects_copies_of_authoritative_domains(setup):
    service, _, _, _ = setup
    with pytest.raises(SalesSessionError, match="cannot duplicate"):
        start(service, commercial_context={"commercial_roles": ["CORE"]})


def test_progression_and_lifecycle_are_separate(setup):
    service, repository, _, _ = setup
    session = start(service)
    session = service.set_progression(
        session_id=session.sales_session_id, creator_profile_id=7,
        progression_stage="PREMIUM", actor_type="OPERATOR",
    )
    assert session.state is SalesSessionState.ACTIVE
    assert session.progression_stage is SalesSessionProgression.PREMIUM
    session = service.advance(
        session_id=session.sales_session_id, creator_profile_id=7,
        state="OFFERING", actor_type="AI",
    )
    assert session.state is SalesSessionState.OFFERING
    assert [item.event_type for item in repository.events] == [
        "STARTED", "PROGRESSION_CHANGED", "OFFERING",
    ]


def test_invalid_lifecycle_transition_fails_explicitly(setup):
    service, _, _, _ = setup
    session = start(service)
    with pytest.raises(SalesSessionError, match="cannot transition"):
        service.advance(
            session_id=session.sales_session_id, creator_profile_id=7,
            state="AWAITING_PAYMENT",
        )


def test_purchase_intent_is_associated_without_becoming_session_owned(setup):
    service, repository, intents, _ = setup
    session = start(service)
    result = service.associate_purchase_intent(
        session_id=session.sales_session_id, creator_profile_id=7,
        purchase_intent_id=intents.intent.purchase_intent_id,
    )
    assert result["purchase_intent"] is intents.intent
    assert result["sequence"] == 1
    assert repository.links == [intents.intent.purchase_intent_id]
    duplicate = service.associate_purchase_intent(
        session_id=session.sales_session_id, creator_profile_id=7,
        purchase_intent_id=intents.intent.purchase_intent_id,
    )
    assert duplicate["sequence"] == 1
    assert len([
        event for event in repository.events
        if event.event_type == "PURCHASE_INTENT_ASSOCIATED"
    ]) == 1


def test_completion_with_purchase_requires_attributed_link(setup):
    service, _, intents, compatibility = setup
    session = start(service)
    with pytest.raises(SalesSessionError, match="attributed"):
        service.complete(
            session_id=session.sales_session_id, creator_profile_id=7,
            with_purchase=True,
        )
    service.associate_purchase_intent(
        session_id=session.sales_session_id, creator_profile_id=7,
        purchase_intent_id=intents.intent.purchase_intent_id,
    )
    completed = service.complete(
        session_id=session.sales_session_id, creator_profile_id=7,
        with_purchase=True, reason="Commercial objective achieved.",
    )
    assert completed.state is SalesSessionState.COMPLETED
    assert completed.outcome is SalesSessionOutcome.COMPLETED_WITH_PURCHASE
    assert compatibility.ended_items == [completed]


def test_effective_commercial_roles_are_read_only_context(setup, monkeypatch):
    service, _, _, _ = setup
    session = start(service)
    customer = SimpleNamespace(customer_id="2:3")
    monkeypatch.setattr(
        "app.services.sales_session_service.CustomerRepository",
        lambda: SimpleNamespace(
            get_by_legacy_fanvue_user=lambda **_values: customer
        ),
    )
    context = service.commercial_context(
        session_id=session.sales_session_id, creator_profile_id=7
    )
    assert context["customer"] is customer
    assert context["commercial_guidance"]["assets"][0][
        "effective_commercial_roles"
    ] == ["DISCOVERY", "CORE"]


def test_creator_scoped_api_exposes_operational_lifecycle(setup, monkeypatch):
    service, _, _, _ = setup
    monkeypatch.setattr(sales_session_api, "_service", lambda: service)
    monkeypatch.setattr(sales_session_api, "_creator_profile", lambda: {"id": 7})
    app = FastAPI()
    app.include_router(sales_session_api.router)
    client = TestClient(app)
    started = client.post("/api/v1/sales-sessions", json={
        "fanvueAccountId": 2,
        "fanvueUserId": 3,
        "telegramUserId": 99,
        "conversationThreadId": 11,
        "commercialFoundationType": "PHOTOSHOOT",
        "commercialFoundationReference": "photoshoot-1",
        "objective": "Bedroom commercial arc",
        "commercialContext": {"current_posture": "ready"},
        "actorType": "OPERATOR",
    })
    assert started.status_code == 200
    session_id = started.json()["salesSessionId"]
    progressed = client.post(
        f"/api/v1/sales-sessions/{session_id}/progression",
        json={"progressionStage": "CORE", "actorType": "OPERATOR"},
    )
    assert progressed.status_code == 200
    assert progressed.json()["progressionStage"] == "CORE"
    history = client.get(
        f"/api/v1/sales-sessions/{session_id}/history"
    )
    assert history.status_code == 200
    assert [item["eventType"] for item in history.json()["items"]] == [
        "STARTED", "PROGRESSION_CHANGED",
    ]
