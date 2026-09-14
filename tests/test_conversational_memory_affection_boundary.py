from datetime import datetime, timezone

from app.services.conversational_memory_service import ConversationalMemoryService


def values(text):
    return {(row["category"], str(row["value"]).lower())
            for row in ConversationalMemoryService.extract_records(text)}


def test_relationship_directed_affection_never_becomes_interest_memory():
    examples = (
        "I love you", "I love u", "I love you so much", "I adore you",
        "I love everything about you", "Everything about you", "So much",
        "You babe", "Love you babe", "I really like you",
        "I'm crazy about you", "Love you babe 😘",
    )
    for example in examples:
        assert not {row for row in values(example)
                    if row[0] in {"interest", "hobby"}}


def test_legitimate_love_interests_are_preserved():
    expected = {
        "I love hiking.": "hiking",
        "I love camping.": "camping",
        "I love Foo Fighters.": "foo fighters",
        "I love old cars.": "old cars",
        "I really love photography.": "photography",
    }
    for message, interest in expected.items():
        assert any(value.replace("_", " ") == interest
                   for _, value in values(message))


def test_mixed_affection_does_not_suppress_external_interest():
    first = values("I love you babe, and I love hiking.")
    assert any(value == "hiking" for _, value in first)
    assert not any("you" in value for category, value in first
                   if category in {"interest", "hobby"})
    second = values("I love you, but Foo Fighters are still my favorite band.")
    assert any("foo fighters" in value for _, value in second)
    assert not any("you" in value for category, value in second
                   if category in {"interest", "hobby"})


def test_persisted_affection_fragments_fail_closed_and_are_not_retrieved():
    invalid = {"category": "interest", "key": "you_so_much",
               "value": "you so much", "status": "current",
               "evidence": "I love you so much"}
    assert ConversationalMemoryService.validate_persisted_record(invalid) == (
        "RELATIONSHIP_DIRECTED_AFFECTION"
    )
    result = ConversationalMemoryService.retrieve(
        {"schemaVersion": 2, "records": [invalid]},
        "What interests have I told you about?",
    )
    assert result.get("interests") in (None, [])
    assert result["durableRecordCount"] == 0


def test_validation_diagnostics_report_bounded_affection_reason():
    record = ConversationalMemoryService._record(
        "interest", "everything_about_you", "everything about you",
        "I love everything about you", datetime.now(timezone.utc),
    )
    valid, rejected = ConversationalMemoryService._validate_extracted_records([record])
    assert valid == []
    assert rejected == [{"category": "interest", "key": "everything_about_you",
                         "reason": "RELATIONSHIP_DIRECTED_AFFECTION"}]
