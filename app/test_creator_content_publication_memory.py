from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.models.creator_content_publication import CreatorContentPublication
from app.services.creator_content_publication_memory_service import CreatorContentPublicationMemoryService


class MemoryRepository:
    def __init__(self):
        self.values = {}

    def save_successful(self, value):
        key = (value.platform, value.destination, value.telegram_channel_id, value.telegram_message_id)
        self.values.setdefault(key, value)
        return self.values[key]


def record(**overrides):
    values = dict(image_id="img-1", generation_job_id="job-1",
        generation_request_id="request-1", generation_result_id="result-1",
        output_reference="C:/generated/output.jpg", creator_profile_id=7,
        provider_id="provider-1", prompt_plan_id="plan-1",
        prompt_text="Ava in a red dress on a balcony", creative_mode="portrait",
        reference_asset_id=999, imported_asset_id=None, generation_recipe_id="recipe-1",
        photoshoot_session_id="shoot-1", photoshoot_request_id="shot-request-1",
        prompt_metadata={}, generation_metadata={})
    values.update(overrides)
    return SimpleNamespace(**values)


def request(*, status="posted", message_id=81, channel_id=-10055):
    return SimpleNamespace(publish_request_id="publish-1", platform="telegram",
        status=status, created_at="2026-01-02T03:04:05+00:00", metadata={
            "telegram_post_to": "main", "provider_post_id": str(message_id),
            "selected_ctas": ["CHAT"], "provider_metadata": {"response": {"result": {
                "message_id": message_id, "date": 1767323045,
                "chat": {"id": channel_id},
                "photo": [{"file_unique_id": "file-unique-1"}],
            }}},
        })


def service(**kwargs):
    repository = kwargs.pop("repository", MemoryRepository())
    return CreatorContentPublicationMemoryService(repository=repository, **kwargs), repository


def test_confirmed_broadcast_creates_exactly_one_durable_memory_and_retry_is_idempotent():
    subject, repository = service()
    first = subject.record_confirmed_telegram_broadcast(record=record(), publish_item=request(), caption="Hello")
    second = subject.record_confirmed_telegram_broadcast(record=record(), publish_item=request(), caption="Changed")
    assert first == second
    assert len(repository.values) == 1
    assert first.telegram_message_id == 81 and first.telegram_channel_id == -10055
    assert first.published_caption == "Hello"


def test_failed_or_non_broadcast_publication_creates_no_memory():
    subject, repository = service()
    with pytest.raises(ValueError):
        subject.record_confirmed_telegram_broadcast(record=record(), publish_item=request(status="failed"), caption="x")
    vault = request(); vault.metadata["telegram_post_to"] = "vault"
    with pytest.raises(ValueError):
        subject.record_confirmed_telegram_broadcast(record=record(), publish_item=vault, caption="x")
    assert not repository.values


def test_caption_studio_actual_output_analysis_is_preferred():
    captions = SimpleNamespace(get_result=lambda _id: SimpleNamespace(formatter_metadata={
        "formatter": "CaptionStudioService", "vision": {"summary": "Ava by a lake",
        "setting": "lake", "outfit": "blue dress", "objects": ["boat"], "mood": "calm"}}))
    subject, _ = service(caption_studio=captions)
    value = subject.record_confirmed_telegram_broadcast(record=record(), publish_item=request(), caption="Lake", caption_result_id="cap-1")
    assert value.intelligence_source == "CAPTION_STUDIO_GROK_VISION"
    assert value.setting == "lake" and value.clothing == "blue dress"


def test_actual_asset_content_intelligence_fallback_never_uses_reference_asset():
    calls = []
    content = SimpleNamespace(get_asset_intelligence=lambda asset_id: calls.append(asset_id) or SimpleNamespace(
        summary="actual output", setting="studio", environment=None, outfit="black dress",
        clothing=None, pose="standing", activity="posing", objects=("chair",), mood="bold",
        themes=("fashion",), ai_metadata={"safety": {"explicit": False}}, provenance={"version": "v1"}))
    subject, _ = service(content_intelligence=content)
    value = subject.record_confirmed_telegram_broadcast(record=record(imported_asset_id=42), publish_item=request(), caption="Studio")
    assert calls == [42]
    assert value.published_asset_id == 42 and value.intelligence_source == "CONTENT_INTELLIGENCE"
    assert value.published_asset_id != 999


def test_asset_intelligence_fallback_bounds_nudenet_to_safety():
    content = SimpleNamespace(get_asset_intelligence=lambda _asset_id: None)
    profile = SimpleNamespace(content_summary="portrait", detailed_description=None,
        short_description=None, setting="bedroom", environment=None, clothing=("robe",),
        pose="seated", activity="reading", expression="smile", objects=("book",),
        mood="warm", themes=("home",), nudity_level="none", explicit_content=False,
        visible_body_regions=(), sexual_intensity="none", safety_classification="safe",
        risk_flags=(), schema_version="asset-v1")
    assets = SimpleNamespace(get_profile=lambda _asset_id: profile)
    subject, _ = service(content_intelligence=content, asset_intelligence=assets)
    value = subject.record_confirmed_telegram_broadcast(record=record(imported_asset_id=42), publish_item=request(), caption="Reading")
    assert value.intelligence_source == "ASSET_INTELLIGENCE"
    assert value.safety_snapshot["nudityLevel"] == "none"
    assert "nudity" not in value.factual_visual_summary.lower()


def test_generation_metadata_fallback_is_bounded_and_provenanced():
    subject, _ = service()
    value = subject.record_confirmed_telegram_broadcast(record=record(
        prompt_metadata={"setting": "rooftop", "tags": ["night"]}), publish_item=request(), caption="City")
    assert value.intelligence_source == "GENERATION_METADATA"
    assert value.intelligence_provenance["factuality"] == "UNVERIFIED_FALLBACK"
    assert value.setting == "rooftop"


def test_snapshot_survives_source_mutation():
    vision = {"summary": "original", "objects": ["lamp"]}
    captions = SimpleNamespace(get_result=lambda _id: SimpleNamespace(formatter_metadata={"vision": vision}))
    subject, _ = service(caption_studio=captions)
    value = subject.record_confirmed_telegram_broadcast(record=record(), publish_item=request(), caption="x", caption_result_id="cap")
    vision["summary"] = "moved or archived"
    assert value.factual_visual_summary == "original" and value.useful_objects == ("lamp",)


@pytest.mark.parametrize("age", [timedelta(hours=13), timedelta(weeks=2), timedelta(days=180)])
def test_publication_age_has_no_eligibility_expiration(age):
    value = CreatorContentPublication(publication_id="p", creator_profile_id=1,
        platform="telegram", destination="main", telegram_channel_id=1,
        telegram_message_id=2, published_at=datetime.now(UTC) - age,
        generated_image_id="g", search_document="red dress")
    assert value.publication_status == "PUBLISHED"


def test_search_is_local_snapshot_only_and_has_no_provider_dependency():
    subject, _ = service()
    value = subject.record_confirmed_telegram_broadcast(record=record(), publish_item=request(), caption="Red dress")
    assert "Red dress" in value.search_document and "September" not in value.search_document
