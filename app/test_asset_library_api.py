from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api import asset_library as asset_api
from app.api import generation_library as generation_api
from app.models.asset_library import (
    AssetLibraryDetails,
    AssetLibraryFilter,
    AssetLibraryItem,
    AssetLibraryResult,
    AssetPublishingSummary,
    AssetRelationshipSummary,
    AssetStorageSummary,
)
from app.models.generation_library import GeneratedImageRecord
from app.services.generation_library_service import GenerationLibraryService
from app.services.staged_asset_registration_service import (
    StagedAssetRegistrationResult,
)
from app.repositories.photoshoot_commerce_repository import PhotoshootCommerceRepository


def test_session_strategy_endpoint_uses_canonical_generator_and_returns_readiness(monkeypatch):
    calls = []
    monkeypatch.setattr(asset_api, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(asset_api, "PhotoshootCommerceRepository", lambda: SimpleNamespace(
        get=lambda _deliverable_id: {
            "creator_profile_id": 7,
            "registration_state": "IN_ASSET_LIBRARY",
        }
    ))
    monkeypatch.setattr(asset_api, "PhotoshootCommerceDeliverableService", lambda: SimpleNamespace(
        generate_session_sales_strategy=lambda deliverable_id, creator_profile_id, strategy_version: calls.append(
            (deliverable_id, creator_profile_id, strategy_version))))
    monkeypatch.setattr(asset_api, "PhotoshootSalePreparationService", lambda: SimpleNamespace(
        inspect=lambda deliverable_id, creator_profile_id: {
            "deliverableId": deliverable_id, "sellingMode": "SESSION",
            "status": "NOT_PREPARED", "steps": [],
        }))
    result = asset_api.generate_photoshoot_session_sales_strategy("set-1")
    assert result["status"] == "NOT_PREPARED"
    assert calls == [("set-1", 7, "photoshoot_session_sales_v1")]


def test_canonical_asset_id_uses_direct_lookup_without_reference_enrichment(monkeypatch):
    class ReferenceService:
        def get_active_canonical_asset_id(self, *, creator_profile_id):
            assert creator_profile_id == 7
            return 84

        def get_active_reference(self, **_kwargs):
            raise AssertionError("full Reference Library enrichment must not run")

    monkeypatch.setattr(asset_api, "ReferenceLibraryService", ReferenceService)

    assert asset_api._canonical_asset_id(7) == 84


def test_registered_asset_archive_and_restore_preserve_identity_and_creator_scope(monkeypatch):
    calls = []
    class Repository:
        def get_by_id(self, asset_id):
            return None
        def archive_asset_library_item(self, asset_id, creator_profile_id):
            calls.append(("archive", asset_id, creator_profile_id)); return {"id": asset_id}
        def restore_asset_library_item(self, asset_id, creator_profile_id):
            calls.append(("restore", asset_id, creator_profile_id)); return {"id": asset_id}
    monkeypatch.setattr(asset_api, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(
        asset_api,
        "AssetLibraryService",
        lambda: SimpleNamespace(get_asset_details=lambda _asset_id: details),
    )
    monkeypatch.setattr(asset_api, "AssetRepository", Repository)

    assert asset_api.archive_registered_asset(42)["assetId"] == 42
    assert asset_api.restore_registered_asset(42)["assetId"] == 42
    assert calls == [("archive", 42, 7), ("restore", 42, 7)]


def test_photoshoot_archive_and_restore_preserve_deliverable_identity(monkeypatch):
    calls = []
    class Repository:
        def get(self, deliverable_id):
            return None
        def archive_asset_library(self, deliverable_id, creator_profile_id):
            calls.append(("archive", deliverable_id, creator_profile_id)); return {"deliverable_id": deliverable_id}
        def restore_asset_library(self, deliverable_id, creator_profile_id):
            calls.append(("restore", deliverable_id, creator_profile_id)); return {"deliverable_id": deliverable_id}
    monkeypatch.setattr(asset_api, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(asset_api, "PhotoshootCommerceRepository", Repository)

    assert asset_api.archive_photoshoot_asset("set-1")["deliverableId"] == "set-1"
    assert asset_api.restore_photoshoot_asset("set-1")["deliverableId"] == "set-1"
    assert calls == [("archive", "set-1", 7), ("restore", "set-1", 7)]


def _record(**changes):
    values = {
        "image_id": "generated-1",
        "creator_profile_id": 7,
        "status": "active",
        "imported_asset_id": None,
    }
    values.update(changes)
    return SimpleNamespace(**values)


def _item(asset_id=42, original_path="C:/vault/portrait.png"):
    return AssetLibraryItem(
        asset_id=asset_id,
        file_name="portrait.png",
        media_type="image",
        classification="premium",
        status="approved",
        is_active=True,
        created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        preview_path=None,
        original_path=original_path,
        tags=("portrait",),
        themes=("studio",),
        ready_for_rotation=True,
        relationship=AssetRelationshipSummary(),
        publishing=AssetPublishingSummary(status="unpublished"),
    )


def _paged_service(items, captured=None):
    by_id = {item.asset_id: item for item in items}

    def summary(filters, *, candidate_limit):
        if captured is not None:
            captured["filters"] = filters
            captured["candidate_limit"] = candidate_limit
        candidates = tuple(
            {"id": item.asset_id, "created_at": item.created_at}
            for item in items[:candidate_limit]
            if not item.is_reference_image
        )
        classifications = tuple(sorted({
            str(item.classification) for item in items if item.classification
        }))
        return candidates, sum(not item.is_reference_image for item in items), classifications

    def build(ids):
        if captured is not None:
            captured["built_ids"] = ids
        return tuple(by_id[value] for value in ids)

    return SimpleNamespace(
        asset_library_grid_summary=summary,
        build_items_by_ids=build,
    )


def _empty_photoshoots():
    return SimpleNamespace(
        count_asset_library=lambda *_args, **_kwargs: 0,
        list_asset_library=lambda *_args, **_kwargs: (),
    )


def test_photoshoot_sales_classification_filters_use_persisted_configuration():
    build = PhotoshootCommerceRepository._asset_library_sales_classification_filter
    assert build("SESSION") == "COALESCE(d.selling_mode, 'SESSION')='SESSION'"
    assert build("CHAT") == "d.selling_mode='BUNDLE' AND COALESCE(d.bundle_sales_channel, 'CHAT')='CHAT'"
    assert build("WALL") == "d.selling_mode='BUNDLE' AND d.bundle_sales_channel='CONTENT_WALL'"
    assert build(None) is None


def test_all_media_merge_is_complete_union_across_sources():
    staged = [
        {"libraryItemId": f"generation:{index}"}
        for index in range(8)
    ]
    photoshoots = [
        {
            "libraryItemId": "photoshoot:e8f7b86f-b644-5005-9aa5-03fae885d64f",
            "fileName": "Sunlit Serenity",
            "shotCount": 4,
        },
        {
            "libraryItemId": "photoshoot:5948af36-9614-5dd0-9bee-d53527c43954",
            "fileName": "Golden Meadow",
            "shotCount": 8,
        },
        {
            "libraryItemId": "photoshoot:974d27ad-4d41-53b7-a44e-f73c1e00142d",
            "fileName": "Sunlit Serenity",
            "shotCount": 2,
        },
    ]

    merged = asset_api._merge_all_media_candidates(staged, [], photoshoots)

    assert len(merged) == 11
    assert merged[:8] == staged
    assert merged[8:] == photoshoots
    assert {item["libraryItemId"] for item in merged} == {
        *(item["libraryItemId"] for item in staged),
        *(item["libraryItemId"] for item in photoshoots),
    }


def _move_setup(monkeypatch, record, *, already_moved=False):
    library = SimpleNamespace(get=lambda _image_id: record)
    library.move_to_asset_library = lambda _image_id: (SimpleNamespace(image_id=record.image_id, status="staged_asset_library"), already_moved)
    monkeypatch.setattr(generation_api, "_creator_profile_id", lambda: 7)
    monkeypatch.setattr(generation_api, "GenerationLibraryService", lambda: library)


def test_move_generation_stages_without_asset_registration(monkeypatch):
    _move_setup(monkeypatch, _record())
    result = generation_api.move_generation_to_asset_library("generated-1")
    assert result == {
        "success": True,
        "generation_id": "generated-1",
        "already_moved": False,
        "status": "staged_asset_library",
        "message": "Image moved to Asset Library.",
    }


def test_move_generation_is_idempotent(monkeypatch):
    _move_setup(monkeypatch, _record(status="staged_asset_library"), already_moved=True)
    assert generation_api.move_generation_to_asset_library("generated-1")["already_moved"] is True


def test_move_back_endpoint_restores_only_staged_generation(monkeypatch):
    record = _record(status="staged_asset_library")
    library = SimpleNamespace(
        get=lambda _image_id: record,
        move_back_to_generation_library=lambda _image_id: (SimpleNamespace(image_id="generated-1", status="active"), False),
    )
    monkeypatch.setattr(generation_api, "_creator_profile_id", lambda: 7)
    monkeypatch.setattr(generation_api, "GenerationLibraryService", lambda: library)

    result = generation_api.move_generation_back_to_generation_library("generated-1")

    assert result["status"] == "active"
    assert result["message"] == "Image moved back to Generation Library."


def test_protected_reference_generation_cannot_be_staged_or_moved_back(tmp_path):
    protected_metadata = {"reference_library": {"is_reference": True, "protected": True, "role": "creator_identity"}}
    service = GenerationLibraryService(storage_dir=tmp_path / "library", asset_repository=SimpleNamespace(get_by_id=lambda _id: None))
    record = GeneratedImageRecord(
        image_id="protected-reference", generation_job_id="job-1", generation_request_id="request-1",
        generation_result_id="result-1", output_reference=str(tmp_path / "reference.png"), creator_profile_id=7,
        provider_id="local", prompt_plan_id="plan-1", prompt_text="identity",
        creative_mode=None, reference_asset_id=None, generation_metadata=protected_metadata,
    )
    service._write_records([record])
    with pytest.raises(ValueError, match="Protected Reference"):
        service.move_to_asset_library(record.image_id)
    service._write_records([GeneratedImageRecord(**{**record.__dict__, "status": "staged_asset_library"})])
    with pytest.raises(ValueError, match="Protected Reference"):
        service.move_back_to_generation_library(record.image_id)


def test_move_persists_excludes_from_generation_browse_and_preserves_record(tmp_path):
    media = tmp_path / "generated.png"
    media.write_bytes(b"png")
    service = GenerationLibraryService(storage_dir=tmp_path / "library")
    original = GeneratedImageRecord(
        image_id="generated-1", generation_job_id="job-1", generation_request_id="request-1",
        generation_result_id="result-1", output_reference=str(media), creator_profile_id=7,
        provider_id="provider-1", prompt_plan_id="plan-1", prompt_text="portrait prompt",
        creative_mode="portrait", reference_asset_id=93,
        provider_metadata={"source": "provider"}, generation_metadata={"reference_source_role": "canonical"},
    )
    service._write_records([original])

    moved, duplicate = service.move_to_asset_library("generated-1")
    reloaded = GenerationLibraryService(storage_dir=tmp_path / "library")
    moved_again, retried = reloaded.move_to_asset_library("generated-1")

    assert duplicate is False and retried is True
    assert moved_again == moved
    assert reloaded.browse().records == ()
    assert moved.output_reference == original.output_reference
    assert moved.reference_asset_id == 93
    assert moved.provider_metadata == original.provider_metadata
    assert moved.generation_metadata["reference_source_role"] == "canonical"

    restored, duplicate_return = reloaded.move_back_to_generation_library("generated-1")
    restored_again, retried_return = reloaded.move_back_to_generation_library("generated-1")
    assert duplicate_return is False and retried_return is True
    assert restored_again == restored
    assert len(reloaded.list_records()) == 1
    assert reloaded.browse().records == (restored,)
    after_return_reload = GenerationLibraryService(storage_dir=tmp_path / "library", asset_repository=SimpleNamespace(get_by_id=lambda _id: None))
    assert after_return_reload.list_records() == (restored,)


def test_move_generation_returns_missing(monkeypatch):
    monkeypatch.setattr(generation_api, "_creator_profile_id", lambda: 7)
    monkeypatch.setattr(
        generation_api,
        "GenerationLibraryService",
        lambda: SimpleNamespace(get=lambda _image_id: (_ for _ in ()).throw(KeyError("missing"))),
    )
    with pytest.raises(HTTPException) as missing:
        generation_api.move_generation_to_asset_library("missing")
    assert missing.value.status_code == 404


def test_register_staged_asset_uses_pending_business_registration(monkeypatch):
    record = _record(status="staged_asset_library")
    library = SimpleNamespace(get=lambda _image_id: record)
    captured = {}

    class Registration:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def register(self, selected, *, creator_profile_id):
            captured["record"] = selected
            captured["creator_profile_id"] = creator_profile_id
            return StagedAssetRegistrationResult(
                success=True,
                asset_id=91,
                registration_id="registration-91",
                analysis_status="PENDING",
                business_lifecycle_state="INTELLIGENCE_PENDING",
                message="Asset registered. Analysis is pending.",
            )

    monkeypatch.setattr(asset_api, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(asset_api, "GenerationLibraryService", lambda: library)
    monkeypatch.setattr(asset_api, "StagedAssetRegistrationService", Registration)

    result = asset_api.register_staged_asset("generated-1")

    assert result["assetId"] == 91
    assert result["analysisStatus"] == "PENDING"
    assert result["businessLifecycleState"] == "INTELLIGENCE_PENDING"
    assert captured["generation_library_service"] is library
    assert captured["record"] is record
    assert captured["creator_profile_id"] == 7


def _registration_client(monkeypatch, *, library, registration):
    monkeypatch.setattr(asset_api, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(asset_api, "GenerationLibraryService", lambda: library)
    monkeypatch.setattr(asset_api, "StagedAssetRegistrationService", registration)
    app = FastAPI()
    app.include_router(asset_api.router)
    return TestClient(app)


def test_registration_success_and_duplicate_are_json(monkeypatch):
    record = _record(status="staged_asset_library")

    class Registration:
        def __init__(self, **_kwargs):
            pass

        def register(self, _record, *, creator_profile_id):
            assert creator_profile_id == 7
            return StagedAssetRegistrationResult(
                success=True,
                asset_id=91,
                registration_id="registration-91",
                already_registered=True,
                analysis_status="PENDING",
                business_lifecycle_state="INTELLIGENCE_PENDING",
                message="Asset is already registered.",
            )

    client = _registration_client(
        monkeypatch,
        library=SimpleNamespace(get=lambda _generation_id: record),
        registration=Registration,
    )
    response = client.post("/api/v1/assets/staged/generated-1/register")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["alreadyRegistered"] is True


def test_registration_validation_failure_is_json(monkeypatch):
    record = _record(status="staged_asset_library")

    class Registration:
        def __init__(self, **_kwargs):
            pass

        def register(self, _record, *, creator_profile_id):
            return StagedAssetRegistrationResult(
                success=False,
                message="Only staged Asset Library items can be registered.",
            )

    client = _registration_client(
        monkeypatch,
        library=SimpleNamespace(get=lambda _generation_id: record),
        registration=Registration,
    )
    response = client.post("/api/v1/assets/staged/generated-1/register")

    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["detail"] == "Only staged Asset Library items can be registered."


def test_missing_registration_asset_is_json(monkeypatch):
    client = _registration_client(
        monkeypatch,
        library=SimpleNamespace(
            get=lambda _generation_id: (_ for _ in ()).throw(KeyError("missing"))
        ),
        registration=lambda **_kwargs: None,
    )
    response = client.post("/api/v1/assets/staged/missing/register")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": "Staged Asset was not found."}


def test_unexpected_registration_exception_is_structured_json(monkeypatch):
    record = _record(status="staged_asset_library")

    class Registration:
        def __init__(self, **_kwargs):
            pass

        def register(self, _record, *, creator_profile_id):
            raise RuntimeError("database exploded")

    client = _registration_client(
        monkeypatch,
        library=SimpleNamespace(get=lambda _generation_id: record),
        registration=Registration,
    )
    response = client.post("/api/v1/assets/staged/generated-1/register")

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {
        "success": False,
        "error": "registration_failed",
        "detail": "Unable to register Business Asset due to an internal server error.",
    }


def test_list_assets_applies_filters_and_pagination(monkeypatch):
    items = tuple(_item(asset_id=index) for index in range(1, 22))
    captured = {}
    service = _paged_service(items, captured)
    monkeypatch.setattr(asset_api, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(asset_api, "_canonical_asset_id", lambda _profile_id: 2)
    monkeypatch.setattr(asset_api, "AssetLibraryService", lambda: service)
    monkeypatch.setattr(asset_api, "GenerationLibraryService", lambda: SimpleNamespace(list_records=lambda: ()))

    result = asset_api.list_assets(search="face", media_type="image", classification="premium", page=2, page_size=10)
    assert [item["assetId"] for item in result["assets"]] == list(range(11, 21))
    assert result["totalPages"] == 3
    assert result["assets"][0]["isCanonicalReference"] is False
    assert result["assets"][0]["itemKind"] == "registered_asset"
    filters = captured["filters"]
    assert (filters.search, filters.media_type, filters.classification, filters.creator_profile_id) == ("face", "image", "premium", 7)
    assert filters.is_reference_image is False
    assert captured["candidate_limit"] == 20
    assert captured["built_ids"] == tuple(range(11, 21))


@pytest.mark.parametrize("classification", ("CHAT", "SESSION", "WALL"))
def test_list_assets_filters_photoshoots_by_commercial_classification(monkeypatch, classification):
    captured = {}
    photoshoot = {
        "deliverable_id": f"set-{classification.lower()}", "display_title": classification,
        "display_name": "Photoshoot", "registration_state": "IN_ASSET_LIBRARY",
        "completed_at": "2026-08-07T10:00:00Z", "updated_at": "2026-08-07T10:00:00Z",
        "hero_asset_id": 42, "shot_count": 3,
        "selling_mode": "SESSION" if classification == "SESSION" else "BUNDLE",
        "bundle_sales_channel": "CONTENT_WALL" if classification == "WALL" else "CHAT",
    }

    class Repository:
        def count_asset_library(self, _creator_profile_id, **kwargs):
            captured["count"] = kwargs
            return 1

        def list_asset_library(self, _creator_profile_id, **kwargs):
            captured["list"] = kwargs
            return (photoshoot,)

    monkeypatch.setattr(asset_api, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(asset_api, "_canonical_asset_id", lambda _profile_id: None)
    monkeypatch.setattr(asset_api, "AssetLibraryService", lambda: _paged_service(()))
    monkeypatch.setattr(asset_api, "GenerationLibraryService", lambda: SimpleNamespace(list_records=lambda: ()))
    monkeypatch.setattr(asset_api, "PhotoshootCommerceRepository", Repository)

    result = asset_api.list_assets(
        search="photo", media_type="photoshoot", classification=classification,
        page=1, page_size=18,
    )

    assert result["total"] == 1
    assert result["assets"][0]["sellingMode"] == photoshoot["selling_mode"]
    assert result["assets"][0]["bundleSalesChannel"] == (None if classification == "SESSION" else photoshoot["bundle_sales_channel"])
    assert captured["count"] == {"search": "photo", "classification": classification}
    assert captured["list"]["search"] == "photo"
    assert captured["list"]["classification"] == classification


def test_asset_library_defensively_excludes_reference_items(monkeypatch):
    reference = _item(asset_id=84)
    reference = AssetLibraryItem(**{**reference.__dict__, "is_reference_image": True})
    monkeypatch.setattr(asset_api, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(asset_api, "_canonical_asset_id", lambda _profile_id: 84)
    monkeypatch.setattr(asset_api, "AssetLibraryService", lambda: _paged_service((reference, _item(asset_id=42))))
    monkeypatch.setattr(asset_api, "GenerationLibraryService", lambda: SimpleNamespace(list_records=lambda: ()))
    monkeypatch.setattr(asset_api, "PhotoshootCommerceRepository", _empty_photoshoots)

    payload = asset_api.list_assets(page=1, page_size=18)

    assert [item["assetId"] for item in payload["assets"]] == [42]


def test_list_assets_merges_staged_generation_with_registered_assets(monkeypatch, tmp_path):
    media = tmp_path / "staged.png"
    media.write_bytes(b"png")
    staged = GeneratedImageRecord(
        image_id="generated-1", generation_job_id="job-1", generation_request_id="request-1",
        generation_result_id="result-1", output_reference=str(media), creator_profile_id=7,
        provider_id="provider-1", prompt_plan_id="plan-1", prompt_text="portrait prompt",
        creative_mode="portrait", reference_asset_id=None, status="staged_asset_library",
    )
    monkeypatch.setattr(asset_api, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(asset_api, "_canonical_asset_id", lambda _profile_id: 42)
    monkeypatch.setattr(asset_api, "AssetLibraryService", lambda: _paged_service((_item(asset_id=42),)))
    monkeypatch.setattr(asset_api, "GenerationLibraryService", lambda: SimpleNamespace(list_records=lambda: (staged, staged)))
    monkeypatch.setattr(asset_api, "PhotoshootCommerceRepository", _empty_photoshoots)

    result = asset_api.list_assets(page=1, page_size=18)

    assert {item["itemKind"] for item in result["assets"]} == {"staged_generation", "registered_asset"}
    assert sum(item["libraryItemId"] == "generation:generated-1" for item in result["assets"]) == 1
    canonical = next(item for item in result["assets"] if item["itemKind"] == "registered_asset")
    assert canonical["isCanonicalReference"] is True


def test_new_photoshoot_sorts_by_asset_library_entry_time_ahead_of_older_staged_images(monkeypatch, tmp_path):
    media = tmp_path / "older.png"
    media.write_bytes(b"png")
    staged = GeneratedImageRecord(
        image_id="generated-older", generation_job_id="job-1", generation_request_id="request-1",
        generation_result_id="result-1", output_reference=str(media), creator_profile_id=7,
        provider_id="provider-1", prompt_plan_id="plan-1", prompt_text="older portrait",
        creative_mode="portrait", reference_asset_id=None, status="staged_asset_library",
        generation_date="2026-07-21T19:19:29.794963", created_at="2026-07-21T19:19:29.794963",
    )
    photoshoot = {
        "deliverable_id": "set-new", "display_title": "New Photoshoot", "display_name": "Photoshoot Studio",
        "display_description": "Four-image collection", "registration_state": "IN_ASSET_LIBRARY",
        "completed_at": "2026-07-21T16:37:55.178517-05:00", "updated_at": "2026-07-21T16:37:56.502458-05:00",
        "hero_asset_id": 93, "shot_count": 4,
    }
    monkeypatch.setattr(asset_api, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(asset_api, "_canonical_asset_id", lambda _profile_id: None)
    monkeypatch.setattr(asset_api, "AssetLibraryService", lambda: _paged_service(()))
    monkeypatch.setattr(asset_api, "GenerationLibraryService", lambda: SimpleNamespace(list_records=lambda: (staged,)))
    monkeypatch.setattr(asset_api, "PhotoshootCommerceRepository", lambda: SimpleNamespace(
        count_asset_library=lambda *_args, **_kwargs: 1,
        list_asset_library=lambda *_args, **_kwargs: (photoshoot,),
    ))

    result = asset_api.list_assets(page=1, page_size=18)

    assert result["assets"][0]["libraryItemId"] == "photoshoot:set-new"
    assert result["assets"][0]["imageUrl"] == "/api/v1/assets/93/thumbnail"
    assert result["assets"][0]["fileName"] == "New Photoshoot"
    assert result["assets"][0]["shotCount"] == 4


def test_asset_details_and_media_are_creator_scoped(monkeypatch, tmp_path: Path):
    media = tmp_path / "portrait.png"
    media.write_bytes(b"png")
    details = AssetLibraryDetails(
        item=_item(original_path=str(media)),
        creator_profile_id=7,
        storage=AssetStorageSummary(original_path=str(media), original_exists=True),
        media_metadata={"asset_registration": {"source": "generation_library"}},
    )
    monkeypatch.setattr(asset_api, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(asset_api, "_canonical_asset_id", lambda _profile_id: None)
    monkeypatch.setattr(asset_api, "AssetLibraryService", lambda: SimpleNamespace(get_asset_details=lambda _asset_id: details))

    payload = asset_api.asset_details(42)
    assert payload["registrationSource"] == "generation_library"
    assert payload["mediaAvailable"] is True
    assert Path(asset_api.asset_media(42).path) == media


def test_asset_thumbnail_uses_cache_and_preserves_original_route(monkeypatch, tmp_path: Path):
    source = tmp_path / "portrait.png"
    source.write_bytes(b"original")
    thumbnail = tmp_path / "portrait.webp"
    thumbnail.write_bytes(b"thumbnail")
    details = AssetLibraryDetails(
        item=_item(original_path=str(source)),
        creator_profile_id=7,
        storage=AssetStorageSummary(original_path=str(source), original_exists=True),
    )
    monkeypatch.setattr(asset_api, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(asset_api, "AssetLibraryService", lambda: SimpleNamespace(get_asset_details=lambda _asset_id: details))
    media_projection = {
        "id": 42, "creator_profile_id": 7, "file_path": str(source),
        "file_name": source.name, "blurred_preview_path": None,
        "local_vault_path": None, "media_metadata": {}, "updated_at": None,
    }
    monkeypatch.setattr(
        asset_api,
        "_asset_repository",
        lambda: SimpleNamespace(get_media_projection=lambda _asset_id: media_projection),
    )
    monkeypatch.setattr(
        asset_api,
        "GridThumbnailService",
        lambda: SimpleNamespace(
            get_or_create=lambda path, *, identity: thumbnail
        ),
    )

    response = asset_api.asset_thumbnail(42)

    assert Path(response.path) == thumbnail
    assert response.media_type == "image/webp"
    assert Path(asset_api.asset_media(42).path) == source


def test_asset_thumbnail_authorizes_with_narrow_media_projection(monkeypatch, tmp_path: Path):
    source = tmp_path / "source.png"
    source.write_bytes(b"image")
    monkeypatch.setattr(asset_api, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(asset_api, "AssetLibraryService", lambda: (_ for _ in ()).throw(AssertionError("full details must not be built")))
    monkeypatch.setattr(asset_api, "_asset_repository", lambda: SimpleNamespace(get_media_projection=lambda _asset_id: {
        "id": 42, "creator_profile_id": 7, "file_path": str(source),
        "file_name": source.name, "blurred_preview_path": None,
        "local_vault_path": None, "media_metadata": {}, "updated_at": None,
    }))
    monkeypatch.setattr(asset_api, "GridThumbnailService", lambda: SimpleNamespace(get_or_create=lambda path, *, identity: source))

    response = asset_api.asset_thumbnail(42)

    assert Path(response.path) == source


def test_asset_media_reports_missing_file(monkeypatch):
    details = AssetLibraryDetails(
        item=_item(original_path=None),
        creator_profile_id=7,
        storage=AssetStorageSummary(original_path=None, original_exists=False),
    )
    monkeypatch.setattr(asset_api, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(asset_api, "AssetLibraryService", lambda: SimpleNamespace(get_asset_details=lambda _asset_id: details))
    with pytest.raises(HTTPException) as error:
        asset_api.asset_media(42)
    assert error.value.status_code == 404
