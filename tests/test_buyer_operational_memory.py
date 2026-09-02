from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID

from app.services.buyer_memory_priority_service import BuyerMemoryPriorityService
from app.services.conversational_memory_service import ConversationalMemoryService
from app.models.conversation_gateway import ConversationGatewayOutput
from app.models.telegram_inbound import TelegramInboundPayload
from app.services.telegram_identity_adapter import TelegramIdentityAdapter
from app.services.telegram_inbound_adapter import TelegramInboundAdapter


NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)


def profile(*, purchases, gross, last_purchase=NOW):
    return SimpleNamespace(
        purchase_count=purchases,
        lifetime_gross_minor=gross,
        lifetime_net_minor=gross,
        average_order_value_minor=(gross // purchases if purchases else 0),
        largest_purchase_minor=gross,
        last_purchase_at=last_purchase,
    )


def test_canonical_buyer_profile_resolves_operational_memory_levels():
    identity = SimpleNamespace(
        external_fanvue_user_uuid=UUID("00000000-0000-0000-0000-000000000123")
    )
    expected = (
        (profile(purchases=0, gross=0), "STANDARD"),
        (profile(purchases=1, gross=300), "ELEVATED"),
        (profile(purchases=2, gross=1800), "HIGH"),
        (profile(purchases=8, gross=60000), "HIGHEST"),
    )
    for value, priority in expected:
        repository = SimpleNamespace(get_by_buyer_uuid=lambda **_values: value)
        assert BuyerMemoryPriorityService(
            customer_repository=repository
        ).resolve(creator_profile_id=7, canonical_identity=identity) == priority


def test_memory_priority_changes_candidate_depth_not_truth_or_callback_policy():
    service = ConversationalMemoryService
    state = service._normalize_state({})
    for index in range(12):
        record = service._record(
            "preference", f"artist_{index}", f"rock artist {index}",
            f"I like rock artist {index}", NOW, .92,
            {"domain": "music", "retrievalEligible": True},
        )
        service._merge_records(state, [record])

    standard = service.retrieve(
        state, "what rock music have I told you I like?",
        now=NOW, memory_priority="STANDARD",
    )
    highest = service.retrieve(
        state, "what rock music have I told you I like?",
        now=NOW, memory_priority="HIGHEST",
    )

    assert standard["memoryDiagnostics"]["retrievedCount"] == 6
    assert highest["memoryDiagnostics"]["retrievedCount"] == 12
    policy = highest["memoryDiagnostics"]["operationalMemoryPolicy"]
    assert policy == {
        "authority": "ConversationalMemoryService",
        "policy": "RELEVANCE_PRESERVING_CANDIDATE_DEPTH",
        "retrievalCandidateLimit": 12,
        "defaultCandidateLimit": 6,
        "truthThresholdChanged": False,
        "persistenceEligibilityChanged": False,
        "callbackRequirementChanged": False,
    }
    assert highest["memoryDiagnostics"]["continuityGuidance"]["maximumCallbacks"] == 1


def test_priority_does_not_retrieve_irrelevant_or_expired_memory():
    service = ConversationalMemoryService
    state = service._normalize_state({})
    service._merge_records(
        state, service.extract_records("I like hiking and rock music.", observed_at=NOW),
    )
    unrelated = service.retrieve(
        state, "what are you eating?", now=NOW, memory_priority="HIGHEST",
    )
    assert unrelated["memoryDiagnostics"]["retrievedCount"] == 0

    event_state = service._normalize_state({})
    event = service._record(
        "event", "old_vet", {
            "event": "vet appointment", "subject": "Charlie",
            "scheduledFor": (NOW - timedelta(days=10)).isoformat(),
            "status": "upcoming", "temporalCertainty": "STATED",
            "resolutionPrecision": "DATE",
        }, "Charlie has a vet appointment", NOW - timedelta(days=20), .95,
        {"temporal": True, "subjectDomain": "pet"},
    )
    service._merge_records(event_state, [event])
    result = service.retrieve(
        event_state, "what is happening tomorrow?", now=NOW,
        memory_priority="HIGHEST",
    )
    assert result["memoryDiagnostics"]["retrievedCount"] == 0


def test_mapped_telegram_inbound_supplies_canonical_priority_to_memory():
    calls = []
    identity = SimpleNamespace(
        engine_user_id="2:9", fanvue_account_id=2, local_fanvue_user_id=9,
        external_fanvue_user_uuid=UUID(
            "00000000-0000-0000-0000-000000000009"
        ),
    )
    memory = SimpleNamespace(learn=lambda **values: (
        calls.append(values) or {"memoryDiagnostics": {}}
    ))
    gateway = SimpleNamespace(execute=lambda request: ConversationGatewayOutput(
        correlation_id=request.correlation_id, response_text="hey",
        offer_authorized=False, offer_link=None, blocked=False, error_code=None,
    ))
    adapter = TelegramInboundAdapter(
        identity_adapter=TelegramIdentityAdapter(engine_account_id=2),
        conversation_gateway=gateway, creator_profile_id=7, fanvue_account_id=2,
        telegram_identity_service=SimpleNamespace(
            observe=lambda **_values: None,
            resolve_telegram_identity=lambda _user_id: identity,
        ),
        customer_safety_service=SimpleNamespace(
            decide=lambda **_values: SimpleNamespace(allowed=True)
        ),
        conversational_memory_service=memory,
        buyer_memory_priority_resolver=lambda **_values: "HIGH",
    )
    adapter.execute(TelegramInboundPayload(
        telegram_user_id=123, telegram_chat_id=123,
        message_text="I like hiking", message_id=44, chat_history=[],
    ))
    assert calls[0]["memory_priority"] == "HIGH"
