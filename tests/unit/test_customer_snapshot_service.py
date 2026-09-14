from dataclasses import asdict
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.customer_snapshot_policy import CustomerSnapshotPolicy
from app.services.customer_snapshot_service import CustomerSnapshotService
from app.repositories.customer_snapshot_repository import CustomerSnapshotRepository


NOW = datetime(2026, 9, 12, tzinfo=timezone.utc)


def record(category, key, value, **overrides):
    item = {
        "category": category, "key": key, "value": value, "status": "current",
        "confidence": .95, "source": "customer_volunteered_telegram",
        "evidence": "customer disclosure", "observedAt": NOW.isoformat(),
        "metadata": {},
    }
    item.update(overrides)
    return item


def fact(*, subject="CUSTOMER", category="RELATIONSHIP", relation="owns_pet",
         value="Bully", usage="NORMAL_CONTEXT", attributes=None, aliases=()):
    return {
        "fact_id": uuid4(), "subject_type": subject,
        "subject_id": 2 if subject == "CREATOR" else 7245,
        "relation": relation, "object_type": "ENTITY", "object_value": value,
        "object_data": {"aliases": list(aliases)}, "attributes": attributes or {}, "category": category,
        "source_platform": "CREATOR_OS", "source_type": "OPERATOR_VERIFIED",
        "verification_method": "OPERATOR_VERIFIED", "confidence": 1,
        "usage_policy": usage, "state": "CURRENT", "observed_at": NOW,
        "verified_at": NOW, "updated_at": NOW,
    }


class Repository:
    def __init__(self, *, prospect=None, facts=(), mapped=True):
        self.prospect, self.facts, self.mapped = prospect, list(facts), mapped
        self.calls = []

    def canonical_sources(self, **kwargs):
        self.calls.append(("canonical", kwargs))
        mapping = SimpleNamespace(telegram_user_id=99) if self.mapped else None
        return mapping, self.prospect if self.mapped else None, self.facts

    def prospect_sources(self, **kwargs):
        self.calls.append(("prospect", kwargs))
        return self.prospect, [item for item in self.facts
                               if item["subject_type"] == "CREATOR"]


def prospect(records, *, graduated_mapping_id=None):
    return SimpleNamespace(
        preference_state={"schemaVersion": 2, "records": records},
        graduated_mapping_id=graduated_mapping_id,
    )


@pytest.mark.parametrize("item", (
    record("fact", "location", "Chicago"),
    record("fact", "timezone", "America/Chicago",
           source="deterministic_location_inference"),
    record("hobby", "hiking", "hiking"),
    record("interest", "camping", "camping"),
    record("preference", "music_artist_foo_fighters", "Foo Fighters",
           metadata={"domain": "music", "kind": "artist"}),
    record("routine", "walk_charlie", "walks Charlie"),
))
def test_policy_allows_bounded_low_risk_memory(item):
    assert CustomerSnapshotPolicy.telegram_eligibility(item) is None


@pytest.mark.parametrize("item, reason", (
    (record("trait", "social_style", "anxious"), "Not snapshot eligible"),
    (record("preference", "medical", "customer has a medical diagnosis"),
     "Sensitive category"),
    (record("preference", "music_artist_bad", "them way too much",
            metadata={"domain": "music", "kind": "artist"}), "Malformed value"),
    (record("hobby", "hiking", "hiking", status="superseded"), "Superseded"),
    (record("event", "trip", {"subject": "customer", "event": "trip",
            "status": "past", "scheduledFor": NOW.isoformat()}), "Past event"),
    (record("entity", "charlie", {"name": "Charlie", "type": "dog"}),
     "Low/ambiguous ownership confidence"),
    (record("fact", "location", "123 Main Street"), "Sensitive category"),
    (record("hobby", "hiking", "hiking", confidence=.4),
     "Low/ambiguous ownership confidence"),
))
def test_policy_excludes_unsafe_or_inactive_memory(item, reason):
    assert CustomerSnapshotPolicy.telegram_eligibility(item) == reason


def test_upcoming_and_tentative_event_is_included_with_lifecycle_metadata():
    event = record("event", "charlie_vet", {
        "subject": "Charlie", "event": "vet appointment", "status": "upcoming",
        "scheduledFor": "2026-09-18T12:00:00-05:00",
        "originalTemporalText": "Friday", "temporalCertainty": "TENTATIVE",
        "completionVerified": False,
    })
    service = CustomerSnapshotService(repository=Repository(
        prospect=prospect([event]), facts=()))
    snapshot = service.for_customer(
        creator_profile_id=2, fanvue_account_id=2, customer_id=7245)
    item = snapshot.sections["THINGS_TO_REMEMBER"][0]
    assert item.lifecycle_status == "UPCOMING"
    assert item.attributes["temporalCertainty"] == "TENTATIVE"
    assert item.attributes["completionVerified"] is False


def test_combined_mapped_snapshot_preserves_sources_sections_and_inference():
    records = [
        record("fact", "location", "Chicago"),
        record("fact", "timezone", "America/Chicago",
               source="deterministic_location_inference"),
        record("entity", "charlie", {
            "name": "Charlie", "type": "dog", "breed": "golden retriever",
            "relationship": "customer's dog"}),
    ]
    facts = [
        fact(value="Bully", attributes={"type": "dog", "gender": "female"}),
        fact(category="PREFERENCE", relation="prefers", value="facial expressions"),
        fact(category="SILENT_CONTEXT", relation="understands", value="Ava is AI",
             usage="SILENT_CONTEXT"),
        fact(subject="CREATOR", category="CREATOR_SELF", relation="owns_pet",
             value="JoJo", attributes={"type": "Staffordshire Bull Terrier"}),
    ]
    repository = Repository(prospect=prospect(records), facts=facts)
    snapshot = CustomerSnapshotService(repository=repository).for_customer(
        creator_profile_id=2, fanvue_account_id=2, customer_id=7245)
    assert snapshot.mapping_state == "MAPPED_VERIFIED"
    assert {item.label for item in snapshot.sections["PERSONAL"]} == {
        "Chicago", "America/Chicago", "Charlie"}
    assert next(item for item in snapshot.sections["PERSONAL"]
                if item.label == "America/Chicago").inferred is True
    assert {item.label for item in snapshot.sections["RELATIONSHIP_WITH_AVA"]} == {"Bully"}
    assert {item.label for item in snapshot.sections["PREFERENCES"]} >= {"facial expressions"}
    assert [item.label for item in snapshot.sections["SILENT_CONTEXT"]] == ["Ava is AI"]
    assert "RELEVANT_CREATOR_FACTS" not in snapshot.sections
    assert len(repository.calls) == 1


def test_unmapped_snapshot_has_no_customer_fact_or_unrelated_creator_fact():
    repository = Repository(
        prospect=prospect([record("hobby", "hiking", "hiking")]),
        facts=[fact(value="Must not leak"), fact(subject="CREATOR", value="JoJo")],
    )
    snapshot = CustomerSnapshotService(repository=repository).for_prospect(
        creator_profile_id=2, fanvue_account_id=2, telegram_user_id=99)
    assert snapshot.mapping_state == "TELEGRAM_PROSPECT_NOT_MAPPED"
    assert snapshot.identity_summary["status"] == "TELEGRAM PROSPECT — NOT MAPPED"
    assert [item.label for item in snapshot.sections["INTERESTS"]] == ["Hiking"]
    assert "RELEVANT_CREATOR_FACTS" not in snapshot.sections
    assert all(item.label != "Must not leak" for values in snapshot.sections.values()
               for item in values)


def test_mapped_transition_uses_same_prospect_memory_and_adds_canonical_facts():
    memory = prospect([record("fact", "location", "Chicago")])
    before = CustomerSnapshotService(repository=Repository(
        prospect=memory, facts=[])).for_prospect(
            creator_profile_id=2, fanvue_account_id=2, telegram_user_id=99)
    after = CustomerSnapshotService(repository=Repository(
        prospect=memory, facts=[fact(value="Bully")])).for_customer(
            creator_profile_id=2, fanvue_account_id=2, customer_id=7245)
    assert before.sections["PERSONAL"][0].label == after.sections["PERSONAL"][0].label
    assert after.sections["RELATIONSHIP_WITH_AVA"][0].label == "Bully"


def test_wally_creator_pet_is_relevant_by_explicit_canonical_dependency_and_ownership_stays_distinct():
    bully = fact(value="Bully", attributes={"type":"dog","gender":"female"})
    dog_images = fact(category="RECURRING_BEHAVIOR", relation="frequently_creates",
        value="Dogs sometimes included in Wally and Ava AI images",
        attributes={"possible_participants":["Bully","JoJo","both"]})
    jojo = fact(subject="CREATOR", category="CREATOR_SELF", relation="owns_pet",
        value="JoJo", attributes={"type":"dog","breed":"Staffordshire Bull Terrier","nickname":"Joey"}, aliases=("Joey",))
    snapshot=CustomerSnapshotService(repository=Repository(facts=[bully,dog_images,jojo],prospect=None)).for_customer(
        creator_profile_id=2,fanvue_account_id=2,customer_id=7245)
    personal=snapshot.sections["RELATIONSHIP_WITH_AVA"]
    creator=snapshot.sections["RELEVANT_CREATOR_FACTS"]
    assert next(x for x in personal if x.label=="Bully").subject_type=="CUSTOMER"
    assert creator[0].label=="JoJo" and creator[0].subject_type=="CREATOR"


@pytest.mark.parametrize("reference",("JoJo","Joey"))
def test_explicit_telegram_object_or_alias_reference_selects_creator_fact(reference):
    jojo=fact(subject="CREATOR",category="CREATOR_SELF",value="JoJo",aliases=("Joey",))
    snapshot=CustomerSnapshotService(repository=Repository(
        prospect=prospect([record("routine","creator_pet",f"asked how {reference} is doing")]),facts=[jojo])).for_customer(
            creator_profile_id=2,fanvue_account_id=2,customer_id=7245)
    assert [x.label for x in snapshot.sections["RELEVANT_CREATOR_FACTS"]]==["JoJo"]


def test_unrelated_dog_and_multiple_creator_facts_do_not_leak_globally():
    facts=[fact(subject="CREATOR",category="CREATOR_SELF",value="JoJo",aliases=("Joey",)),
           fact(subject="CREATOR",category="CREATOR_SELF",relation="prefers",value="Horse riding"),
           fact(subject="CREATOR",category="CREATOR_SELF",relation="knows",value="Austin")]
    snapshot=CustomerSnapshotService(repository=Repository(
        prospect=prospect([record("entity","charlie",{"name":"Charlie","type":"dog","relationship":"customer's dog"})]),facts=facts)).for_customer(
            creator_profile_id=2,fanvue_account_id=2,customer_id=7245)
    assert "RELEVANT_CREATOR_FACTS" not in snapshot.sections


def test_unmapped_prospect_can_select_creator_fact_from_explicit_memory_only():
    jojo=fact(subject="CREATOR",category="CREATOR_SELF",value="JoJo",aliases=("Joey",))
    related=CustomerSnapshotService(repository=Repository(
        prospect=prospect([record("routine","jojo", "asks about Joey")]),facts=[jojo])).for_prospect(
            creator_profile_id=2,fanvue_account_id=2,telegram_user_id=99)
    empty=CustomerSnapshotService(repository=Repository(
        prospect=prospect([]),facts=[jojo])).for_prospect(
            creator_profile_id=2,fanvue_account_id=2,telegram_user_id=99)
    assert [x.label for x in related.sections["RELEVANT_CREATOR_FACTS"]]==["JoJo"]
    assert empty.sections=={}


def test_canonical_owned_pet_wins_over_duplicate_telegram_pet():
    memory = prospect([record("entity", "bully", {
        "name": "Bully", "type": "dog", "relationship": "customer's dog"})])
    snapshot = CustomerSnapshotService(repository=Repository(
        prospect=memory, facts=[fact(value="Bully")])).for_customer(
            creator_profile_id=2, fanvue_account_id=2, customer_id=7245)
    displayed = [item for values in snapshot.sections.values() for item in values
                 if not item.item_id.startswith("recent:")]
    assert sum(item.label == "Bully" for item in displayed) == 1
    assert any(item.exclusion_reason == "Duplicate of higher-authority canonical fact"
               for item in snapshot.excluded_items)


def test_historical_memory_policy_excludes_malformed_artist_and_past_vet():
    records = [
        record("fact", "location", "Chicago"),
        record("fact", "timezone", "America/Chicago",
               source="deterministic_location_inference"),
        record("entity", "charlie", {"name": "Charlie", "type": "dog",
               "breed": "golden retriever", "relationship": "customer's dog"}),
        record("preference", "music_artist_them_way_too_much", "them way too much 😂",
               metadata={"domain": "music", "kind": "artist"}),
        record("event", "charlie_vet", {"subject": "Charlie",
               "event": "vet appointment", "status": "past",
               "scheduledFor": "2026-08-28T12:00:00-05:00"}),
    ]
    snapshot = CustomerSnapshotService(repository=Repository(
        prospect=prospect(records), facts=[])).for_customer(
            creator_profile_id=2, fanvue_account_id=2, customer_id=7245)
    labels = {item.label for values in snapshot.sections.values() for item in values}
    assert {"Chicago", "America/Chicago", "Charlie"} <= labels
    assert "them way too much 😂" not in labels
    assert "THINGS_TO_REMEMBER" not in snapshot.sections
    assert {item.exclusion_reason for item in snapshot.excluded_items} >= {
        "Malformed value", "Past event"}


def test_service_is_read_only_bounded_and_has_no_provider_llm_or_transcript_dependency():
    repository = Repository(prospect=prospect([]), facts=[])
    snapshot = CustomerSnapshotService(repository=repository).for_customer(
        creator_profile_id=2, fanvue_account_id=2, customer_id=7245)
    assert snapshot.sections == {}
    assert repository.calls == [("canonical", {
        "creator_profile_id": 2, "fanvue_account_id": 2, "customer_id": 7245})]
    assert "provider" not in vars(CustomerSnapshotService(repository=repository))
    assert "llm" not in vars(CustomerSnapshotService(repository=repository))
    assert "transcript" not in vars(CustomerSnapshotService(repository=repository))


def test_native_repository_uses_three_bounded_reads_for_mapped_customer():
    calls = []
    mapping = SimpleNamespace(telegram_user_id=99, verification_status="VERIFIED")
    identities = SimpleNamespace(get_by_local_user_id=lambda *args: (
        calls.append(("identity", args)) or mapping))
    prospects = SimpleNamespace(get=lambda **kwargs: (
        calls.append(("prospect", kwargs)) or prospect([])))
    facts = SimpleNamespace(list_current=lambda **kwargs: (
        calls.append(("facts", kwargs)) or []))
    repository = CustomerSnapshotRepository(
        identities=identities, prospects=prospects, facts=facts)
    repository.canonical_sources(
        creator_profile_id=2, fanvue_account_id=2, customer_id=7245)
    assert [name for name, _ in calls] == ["identity", "prospect", "facts"]
