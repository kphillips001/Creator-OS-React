from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.services.conversational_memory_service import ConversationalMemoryService
from app.services.customer_value_attention_service import CustomerValueAttentionService
from app.services.gpt_service import GPTService


NOW = datetime(2026, 9, 3, tzinfo=timezone.utc)


class MemoryRepository:
    def __init__(self):
        self.rows = {}

    @staticmethod
    def _key(values):
        return (
            values["creator_profile_id"], values["fanvue_account_id"],
            values["telegram_user_id"],
        )

    def get(self, **values):
        state = self.rows.get(self._key(values))
        return None if state is None else SimpleNamespace(
            preference_state=deepcopy(state)
        )

    def observe(self, **values):
        self.rows.setdefault(self._key(values), {})
        return SimpleNamespace(preference_state={})

    def merge_conversational_memory(self, *, values, **identity):
        self.rows[self._key(identity)] = deepcopy(values)
        return SimpleNamespace(preference_state=deepcopy(values))


def learn(service, message, *, customer=101):
    return service.learn(
        creator_profile_id=1, fanvue_account_id=2,
        telegram_user_id=customer, telegram_chat_id=customer,
        message_text=message, observed_at=NOW,
    )


def current_values(repository, customer=101, category=None):
    return [
        record["value"] for record in repository.rows[(1, 2, customer)]["records"]
        if record["status"] == "current"
        and (category is None or record["category"] == category)
    ]


@pytest.mark.parametrize(("message", "expected"), (
    ("the outdoor shots were my favorite", "outdoor shots"),
    ("I like the outdoor ones best", "outdoor ones"),
    ("I prefer the natural-looking sets", "natural-looking sets"),
))
def test_strong_content_preferences_are_durable(message, expected):
    repository = MemoryRepository()
    service = ConversationalMemoryService(repository=repository)
    result = learn(service, message)
    disclosure = result["memoryDiagnostics"]["customerSelfDisclosure"]

    assert disclosure["detected"] is True
    assert disclosure["domain"] == "PREFERENCE"
    assert disclosure["significance"] == "DURABLE"
    assert disclosure["persistenceDecision"] == "PERSIST"
    assert disclosure["memoryCandidateCreated"] is True
    assert disclosure["memoryPersisted"] is True
    assert disclosure["memoryRetrievalEligible"] is True
    assert current_values(repository, category="preference") == [expected]


def test_comparative_preference_is_bounded_and_retrievable_after_reload():
    repository = MemoryRepository()
    service = ConversationalMemoryService(repository=repository)
    learn(service, "I like beach shots more than studio shots")

    reloaded = service.retrieve(
        repository.rows[(1, 2, 101)], "another beach photo style", now=NOW,
    )

    assert reloaded["memoryDiagnostics"]["retrievedCount"] == 1
    assert reloaded["retrievedMemories"][0]["value"] == (
        "prefers beach shots over studio shots"
    )
    assert reloaded["retrievedMemories"][0]["key"] == "content_style_preference"


@pytest.mark.parametrize("message", (
    "those outdoor shots were cool", "looks good", "nice shot",
    "lol I like that", "not bad",
))
def test_casual_reactions_do_not_become_durable_preferences(message):
    repository = MemoryRepository()
    service = ConversationalMemoryService(repository=repository)
    result = learn(service, message)
    disclosure = result["memoryDiagnostics"]["customerSelfDisclosure"]
    assert disclosure["persistenceDecision"] == "DO_NOT_PERSIST"
    assert result["durableRecordCount"] == 0


def test_global_hobby_preference_remains_durable_without_purchase_state():
    repository = MemoryRepository()
    service = ConversationalMemoryService(repository=repository)
    result = learn(service, "I really like hiking")
    disclosure = result["memoryDiagnostics"]["customerSelfDisclosure"]
    assert disclosure["domain"] == "HOBBY_INTEREST"
    assert disclosure["memoryPersisted"] is True
    assert current_values(repository, category="hobby") == ["hiking"]


def test_repeat_updates_existing_preference_without_duplicate():
    repository = MemoryRepository()
    service = ConversationalMemoryService(repository=repository)
    learn(service, "the outdoor shots were my favorite")
    repeat = learn(service, "yeah, outdoor shots are still my favorite")
    current = [record for record in repository.rows[(1, 2, 101)]["records"]
               if record["status"] == "current"]
    assert len(current) == 1
    assert repeat["durableRecordCount"] == 1


def test_changed_content_preference_supersedes_old_current_value():
    repository = MemoryRepository()
    service = ConversationalMemoryService(repository=repository)
    learn(service, "the outdoor shots were my favorite")
    changed = learn(service, "actually I think I like the indoor ones better now")
    records = repository.rows[(1, 2, 101)]["records"]
    assert [r["value"] for r in records if r["status"] == "current"] == [
        "indoor ones"
    ]
    assert changed["memoryDiagnostics"]["correctionsApplied"] == 1


def test_negative_preference_preserves_polarity():
    repository = MemoryRepository()
    service = ConversationalMemoryService(repository=repository)
    result = learn(service, "I don't really like studio shots")
    assert current_values(repository, category="preference") == [
        "dislikes studio shots"
    ]


def test_customer_memory_isolation_uses_canonical_repository_scope():
    repository = MemoryRepository()
    service = ConversationalMemoryService(repository=repository)
    learn(service, "the outdoor shots were my favorite", customer=101)
    empty = repository.rows.get((1, 2, 202), {})
    other = service.retrieve(empty, "outdoor photo styles", now=NOW)
    assert other["durableRecordCount"] == 0
    assert other["retrievedMemories"] == []


def test_usually_fishing_is_a_durable_existing_policy_hobby_memory():
    repository = MemoryRepository()
    service = ConversationalMemoryService(repository=repository)

    result = learn(service, "yeah I usually fish when I'm out there")

    disclosure = result["memoryDiagnostics"]["customerSelfDisclosure"]
    assert disclosure["domain"] == "HOBBY_INTEREST"
    assert disclosure["persistenceDecision"] == "PERSIST"
    assert disclosure["memoryPersisted"] is True
    assert current_values(repository, category="hobby") == ["fishing"]


def test_future_free_weekend_retrieves_customer_scoped_fishing_memory():
    repository = MemoryRepository()
    service = ConversationalMemoryService(repository=repository)
    learn(service, "yeah I usually fish when I'm out there", customer=101)

    same = service.retrieve(
        repository.rows[(1, 2, 101)], "finally have another free weekend",
        now=NOW, memory_priority="HIGHEST",
    )
    other = service.retrieve(
        repository.rows.get((1, 2, 202), {}),
        "finally have another free weekend", now=NOW,
        memory_priority="HIGHEST",
    )

    assert same["memoryDiagnostics"]["retrievedKeys"] == ["fishing"]
    assert other["memoryDiagnostics"]["retrievedKeys"] == []


def test_transient_busy_statement_is_not_automatically_durable():
    assert ConversationalMemoryService.extract_records(
        "work's been crazy lately"
    ) == []


def test_rewarming_retrieval_remains_relevant_scoped_and_priority_driven():
    repository = MemoryRepository()
    service = ConversationalMemoryService(repository=repository)
    learn(service, "yeah I usually fish when I'm out there", customer=101)

    relevant = service.retrieve(
        repository.rows[(1, 2, 101)], "finally have another free weekend",
        now=NOW, memory_priority="ELEVATED",
    )
    unrelated = service.retrieve(
        repository.rows[(1, 2, 101)], "my car battery died",
        now=NOW, memory_priority="ELEVATED",
    )
    other_customer = service.retrieve(
        repository.rows.get((1, 2, 202), {}),
        "finally have another free weekend", now=NOW,
        memory_priority="ELEVATED",
    )

    assert relevant["memoryDiagnostics"]["retrievedKeys"] == ["fishing"]
    assert relevant["memoryDiagnostics"]["memoryPriority"] == "ELEVATED"
    assert relevant["memoryDiagnostics"]["continuityGuidance"]["maximumCallbacks"] == 1
    assert unrelated["retrievedMemories"] == []
    assert other_customer["retrievedMemories"] == []


def test_rewarming_generation_guidance_preserves_memory_and_question_boundaries():
    instruction = GPTService._build_retention_instruction({
        "customer_value_attention": {
            "authority": "COMMERCE_BACKED_AUTHORITATIVE_VALUE",
            "buyerStatus": "VERIFIED_BUYER",
            "retentionLifecycle": "DORMANT_BUYER",
            "relationshipRewarmingActive": True,
            "relationshipRewarmingObjective": "BUYER_REWARMING",
            "memoryPriority": "ELEVATED",
        },
    })

    assert "use at most one relevant retrieved memory" in instruction
    assert "Never force a callback" in instruction
    assert "stacked questions" in instruction
    assert "not buying intent" in instruction
    assert "never delays a genuinely current actionable commercial request" in instruction


def test_discovery_answer_projection_uses_written_preference_category():
    discovery = CustomerValueAttentionService._relationship_discovery(
        behavior={
            "latest_message": "the outdoor shots were my favorite",
            "previous_ava_message": "what part stood out the most? favorite style?",
            "memory_written_this_turn": [
                {"category": "preference", "key": "content_style_preference"},
            ],
        },
        buyer_status="VERIFIED_BUYER", buyer_stage="FIRST_TIME_BUYER",
        attention_tier="MEDIUM", effort_mode="BALANCED",
        relationship_investment="WARM", memory_priority="ELEVATED",
        time_waster_risk="NONE", conversational_low_return=False,
        repeated_hostility=False, explicit_disengagement=False,
        active_intent=False, active_session=False, backoff=False, direct=False,
    )
    assert discovery["customerAnsweredDiscovery"] is True
    assert discovery["memoryLearnedFromAnswer"] is True
