from dataclasses import FrozenInstanceError

import pytest

from app.models.creator_intelligence import CreatorIntelligence
from app.services.creator_intelligence_service import CreatorIntelligenceService


class DocumentRepository:
    def __init__(self, documents):
        self.documents = documents
        self.calls = []

    def get(self, *, creator_profile_id, fanvue_account_id):
        key = (creator_profile_id, fanvue_account_id)
        self.calls.append(key)
        return self.documents.get(key)


def profile_loader(profiles):
    return lambda account_id: profiles.get(account_id, {})


def make_service(profiles, lifestyles, social_directions):
    return CreatorIntelligenceService(
        creator_profile_loader=profile_loader(profiles),
        lifestyle_repository=DocumentRepository(lifestyles),
        social_creative_direction_repository=DocumentRepository(
            social_directions
        ),
    )


def test_assembles_only_normalized_creator_documents():
    service = make_service(
        {"2": {"id": 20, "fanvue_account_id": "2", "persona_name": "Ava",
               "created_at": "ignored"}},
        {(20, "2"): {"id": 4, "career": "Marketing", "created_at": "ignored"}},
        {(20, "2"): {"id": 5, "purpose": "Public content",
                     "updated_at": "ignored"}},
    )

    result = service.get_for_account(fanvue_account_id=2)

    assert isinstance(result, CreatorIntelligence)
    assert result.personality["persona_name"] == "Ava"
    assert result.lifestyle["career"] == "Marketing"
    assert result.social_creative_direction["purpose"] == "Public content"
    assert "id" not in result.personality
    assert "created_at" not in result.lifestyle
    assert "updated_at" not in result.social_creative_direction


def test_creator_intelligence_and_nested_documents_are_immutable():
    service = make_service(
        {"2": {"id": 20, "persona_name": "Ava"}},
        {(20, "2"): {"career": "Marketing"}},
        {(20, "2"): {"purpose": "Public content"}},
    )
    result = service.get_for_account(fanvue_account_id="2")

    with pytest.raises(FrozenInstanceError):
        result.personality = {}  # type: ignore[misc]
    with pytest.raises(TypeError):
        result.personality["persona_name"] = "Changed"  # type: ignore[index]


def test_account_scoping_keeps_ava_and_amanda_isolated():
    lifestyles = DocumentRepository({
        (10, "1"): {"career": "Amanda career"},
        (20, "2"): {"career": "Ava career"},
    })
    directions = DocumentRepository({
        (10, "1"): {"purpose": "Amanda direction"},
        (20, "2"): {"purpose": "Ava direction"},
    })
    service = CreatorIntelligenceService(
        creator_profile_loader=profile_loader({
            "1": {"id": 10, "persona_name": "Amanda"},
            "2": {"id": 20, "persona_name": "Ava"},
        }),
        lifestyle_repository=lifestyles,
        social_creative_direction_repository=directions,
    )

    ava = service.get_for_account(fanvue_account_id=2)
    amanda = service.get_for_account(fanvue_account_id=1)

    assert ava.personality["persona_name"] == "Ava"
    assert ava.lifestyle["career"] == "Ava career"
    assert amanda.personality["persona_name"] == "Amanda"
    assert amanda.social_creative_direction["purpose"] == "Amanda direction"
    assert lifestyles.calls == [(20, "2"), (10, "1")]
    assert directions.calls == [(20, "2"), (10, "1")]


@pytest.mark.parametrize("missing", ["profile", "lifestyle", "social"])
def test_missing_canonical_document_fails_instead_of_mixing_or_inventing_data(
    missing,
):
    profiles = {} if missing == "profile" else {
        "2": {"id": 20, "persona_name": "Ava"}
    }
    lifestyles = {} if missing == "lifestyle" else {
        (20, "2"): {"career": "Marketing"}
    }
    social = {} if missing == "social" else {
        (20, "2"): {"purpose": "Public content"}
    }

    with pytest.raises(LookupError):
        make_service(profiles, lifestyles, social).get_for_account(
            fanvue_account_id=2
        )
