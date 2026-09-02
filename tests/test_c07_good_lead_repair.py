from types import SimpleNamespace

import pytest

from app.services.conversational_memory_service import ConversationalMemoryService
from app.services.conversational_sales_progression_service import (
    ConversationalSalesProgressionService,
)
from app.services.customer_sales_brain_service import CustomerSalesBrainService
from app.testing.session5_scenario_harness import CustomerScenarioHarness
from app.testing.session5_scenario_runner import Session5ScenarioRunner


GOOD_LEAD_MESSAGES = (
    "hey, how's your day going?",
    "mine was long but pretty good honestly",
    "I took my dog Milo for a walk after work",
    "he's a little menace but he's my favorite",
    "weekends are usually hiking or trying a new coffee place",
    "you actually remembered my dog, that's cute... he was being such a menace again today",
    "I like talking to you, this feels easy",
    "so what have you been getting into lately?",
)


def test_generic_good_lead_evidence_reaches_tease_without_scenario_identity():
    warming = ConversationalSalesProgressionService.relationship_warming_evidence(
        GOOD_LEAD_MESSAGES
    )
    readiness = CustomerSalesBrainService._deterministic_proactive_tease_readiness({
        "inbound_message_count": 8,
        "meaningful_engagement_count": 5,
        "recent_history_turn_count": 8,
        "durable_conversational_fact_count": 3,
        "relationship_warming_evidence": warming,
        "offer_exposure_count": 0,
    })
    assert warming["relationalWarmthTurnCount"] == 2
    assert warming["reciprocalWarmingObserved"] is True
    assert readiness["authorized"] is True
    assert set(readiness["evidence"]) == {
        "SUSTAINED_VOLUNTARY_CONVERSATION",
        "MEANINGFUL_ENGAGEMENT",
        "VOLUNTARY_SELF_DISCLOSURE",
        "RECIPROCAL_RELATIONAL_WARMING",
        "NO_OFFER_EXPOSURE",
    }


def test_friendly_volume_without_relational_warming_still_cannot_tease():
    readiness = CustomerSalesBrainService._deterministic_proactive_tease_readiness({
        "inbound_message_count": 12,
        "meaningful_engagement_count": 12,
        "recent_history_turn_count": 12,
        "durable_conversational_fact_count": 4,
        "relationship_warming_evidence": {"reciprocalWarmingObserved": False},
        "offer_exposure_count": 0,
    })
    assert readiness["authorized"] is False
    assert "RECIPROCAL_RELATIONAL_WARMING" not in readiness["evidence"]


def test_recurring_compound_weekend_preferences_are_truthfully_extracted():
    records = ConversationalMemoryService.extract_records(
        "weekends are usually hiking or trying a new coffee place"
    )
    values = {record["value"] for record in records}
    assert "hiking" in values
    assert "trying new coffee places" in values
    assert all(record["source"] == "customer_self_disclosure" for record in records)


def test_memory_use_requires_a_durable_anchor_not_repeated_in_current_inbound():
    guidance = {
        "strongestMemory": {
            "key": "milo",
            "value": {"name": "Milo", "type": "dog"},
        },
    }
    genuine = __import__("app.services.gpt_service", fromlist=["GPTService"]).GPTService \
        ._final_memory_callback_evidence(
            "Milo sounds impossible not to love",
            "you actually remembered my dog, that's cute",
            guidance,
        )
    foreground_only = __import__("app.services.gpt_service", fromlist=["GPTService"]).GPTService \
        ._final_memory_callback_evidence(
            "Milo sounds impossible not to love",
            "you remembered Milo, that's cute",
            guidance,
        )
    assert genuine["used"] is True
    assert genuine["memoriesUsed"] == ["milo"]
    assert foreground_only["used"] is False
    assert foreground_only["classification"] == "CURRENT_TURN_TOPIC_ONLY"


def test_c07_fixture_creates_a_real_later_memory_callback_opportunity():
    messages = CustomerScenarioHarness.definition("C07").canonical_customer_turns
    assert "Milo" in messages[2]
    assert "Milo" not in messages[5]
    assert "menace again" in messages[5]


def test_milo_is_retrieved_for_pronoun_only_pet_callback_without_false_use():
    state = ConversationalMemoryService._normalize_state({})
    ConversationalMemoryService._merge_records(
        state,
        ConversationalMemoryService.extract_records(
            "I took my dog Milo for a walk after work"
        ),
    )

    projection = ConversationalMemoryService.retrieve(
        state, "you actually remembered my dog, that's cute... he was being such a menace again today"
    )
    diagnostics = projection["memoryDiagnostics"]
    guidance = diagnostics["continuityGuidance"]

    assert diagnostics["retrievedKeys"] == ["milo"]
    assert guidance["strongestMemory"]["key"] == "milo"
    assert guidance["priority"] == "HIGH"
    genuine = __import__(
        "app.services.gpt_service", fromlist=["GPTService"]
    ).GPTService._final_memory_callback_evidence(
        "Milo really does keep you entertained 😂",
        "you actually remembered my dog, that's cute... he was being such a menace again today",
        guidance,
    )
    omitted = __import__(
        "app.services.gpt_service", fromlist=["GPTService"]
    ).GPTService._final_memory_callback_evidence(
        "sounds like he kept you entertained again 😂",
        "you actually remembered my dog, that's cute... he was being such a menace again today",
        guidance,
    )
    assert genuine["memoriesUsed"] == ["milo"]
    assert omitted["memoriesUsed"] == []


def _ownership_runner(*, operation_fails=False):
    calls = []
    runner = object.__new__(Session5ScenarioRunner)
    runner.harness = SimpleNamespace(
        definition=lambda _scenario: SimpleNamespace(maximum_turn_count=14),
    )
    runner._active = lambda **_: {"scenario_id": "C99"}
    runner._turn_owned = lambda message, **kwargs: (
        calls.append(("turn", message, kwargs["owner_id"])),
        {"customer": message},
    )[1]

    class Recovery:
        def scenario_attempt(self, _scenario): return 3
        def next_logical_turn(self, _scenario, _attempt): return 1
        def claim_execution(self, scenario, attempt, **kwargs):
            calls.append(("claim", scenario, attempt, kwargs))
            return "owner-one"
        def release_execution(self, scenario, attempt, owner, **kwargs):
            calls.append(("release", scenario, attempt, owner, kwargs))

    runner.recovery = Recovery()

    def operation():
        runner.turn("first")
        runner.turn("second")
        if operation_fails:
            raise RuntimeError("preserved failure")
        return "done"

    return runner, calls, operation


def test_attempt_wide_execution_reuses_one_owner_for_internal_turns():
    runner, calls, operation = _ownership_runner()
    assert runner._execute_with_attempt_owner("C99", 14, operation) == "done"
    assert [call for call in calls if call[0] == "claim"] == [
        ("claim", "C99", 3, {"requested_start_turn": 1, "requested_end_turn": 14})
    ]
    assert [call[2] for call in calls if call[0] == "turn"] == [
        "owner-one", "owner-one",
    ]
    assert [call for call in calls if call[0] == "release"] == [
        ("release", "C99", 3, "owner-one", {})
    ]


def test_attempt_wide_execution_preserves_failed_owner_evidence():
    runner, calls, operation = _ownership_runner(operation_fails=True)
    with pytest.raises(RuntimeError, match="preserved failure"):
        runner._execute_with_attempt_owner("C99", 14, operation)
    release = [call for call in calls if call[0] == "release"]
    assert len(release) == 1
    assert release[0][4]["failed"] is True
    assert release[0][4]["reason"] == "RuntimeError: preserved failure"
