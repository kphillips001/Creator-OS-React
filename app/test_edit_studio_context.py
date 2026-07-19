from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from app.models.generation_engine import GenerationType
from app.models.generation_library import GeneratedImageRecord
from app.api.edit_studio import EditStudioReferenceInput
from app.services.edit_studio_context_service import EditStudioContextService
from app.services.edit_studio_service import EditStudioService


def _provider(provider_id, label, *, enabled=True, supports_images=True, edit=True):
    return SimpleNamespace(
        provider_id=provider_id,
        display_name=label,
        enabled=enabled,
        capabilities=SimpleNamespace(
            supports_images=supports_images,
            supported_generation_types=(GenerationType.IMAGE_TO_IMAGE.value,) if edit else (),
        ),
    )


def _service(*, pending=None):
    library = Mock()
    library.pending_edit_record.return_value = pending
    registry = SimpleNamespace(metadata=lambda: (
        _provider("nano_banana", "Google Nano Banana 2 Edit"),
        _provider("seedream_4_5", "ByteDance Seedream 4.5 Edit"),
        _provider("wan_2_7_image_edit", "WAN 2.7 Image Edit"),
        _provider("disabled", "Disabled", enabled=False),
        _provider("video", "Video", supports_images=False),
        _provider("text_only", "Text only", edit=False),
        _provider("nano_banana_pro", "Google Nano Banana Pro Edit"),
        _provider("seedream_5_0_pro", "ByteDance Seedream 5.0 Pro Edit"),
    ))
    engine = SimpleNamespace(provider_registry=registry)
    return EditStudioContextService(
        generation_library=library,
        generation_engine=engine,
    ), library


def test_missing_profile_skips_pending_lookup_and_returns_registry_providers():
    service, library = _service()

    context = service.read(creator_profile={})

    assert context == {
        "creator_profile_exists": False,
        "pending_source": None,
        "providers": (
            {"value": "seedream_5_0_pro", "label": "ByteDance Seedream 5.0 Pro Edit"},
            {"value": "nano_banana_pro", "label": "Google Nano Banana Pro Edit"},
            {"value": "wan_2_7_image_edit", "label": "WAN 2.7 Image Edit"},
            {"value": "nano_banana", "label": "Google Nano Banana 2 Edit"},
        ),
    }
    library.pending_edit_record.assert_not_called()


def test_context_returns_existing_pending_edit_for_creator(tmp_path):
    source = tmp_path / "pending.png"
    source.write_bytes(b"image")
    pending = GeneratedImageRecord(
        image_id="image-1",
        generation_job_id="job-1",
        generation_request_id="request-1",
        generation_result_id="result-1",
        output_reference=str(source),
        creator_profile_id=7,
        provider_id="first",
        prompt_plan_id="plan-1",
        prompt_text="Portrait",
        creative_mode="premium_teaser",
        reference_asset_id=None,
        status="pending_edit",
    )
    service, library = _service(pending=pending)

    context = service.read(creator_profile={"id": 7})

    library.pending_edit_record.assert_called_once_with(creator_profile_id=7)
    assert context["creator_profile_exists"] is True
    assert context["pending_source"]["image_id"] == "image-1"
    assert context["pending_source"]["image_url"].startswith(
        "/api/v1/edit-studio/pending-source/image?image_id=image-1&v="
    )
    assert service.pending_source_path(creator_profile={"id": 7}) == Path(source)


def test_edit_studio_context_route_is_registered_for_get():
    from app.fanvue_callback_server import app

    route = next(
        route
        for route in app.routes
        if getattr(route, "path", None) == "/api/v1/edit-studio/context"
    )

    assert route.methods == {"GET"}
    assert route.response_model.__name__ == "EditStudioContextResponse"


def test_edit_service_preserves_reference_collection_and_uses_first_asset(tmp_path):
    source = GeneratedImageRecord(
        image_id="source-1",
        generation_job_id="job-source",
        generation_request_id="request-source",
        generation_result_id="result-source",
        output_reference=str(tmp_path / "source.png"),
        creator_profile_id=7,
        provider_id="provider",
        prompt_plan_id="source-plan",
        prompt_text="Source",
        creative_mode="premium_teaser",
        reference_asset_id=None,
        status="pending_edit",
    )
    library = Mock()
    library.get.return_value = source
    engine = Mock()
    engine.queue_prompt_plan.return_value = SimpleNamespace(job_id="edit-job")
    references = (
        {"role": "Wardrobe", "source": "reference_library", "asset_id": 12},
        {"role": "Pose", "source": "upload", "asset_id": 13},
    )

    edit_item, _ = EditStudioService(storage_dir=tmp_path / "edit").create_edit_request(
        creator_profile={"id": 7},
        source_image_ids=(source.image_id,),
        edit_mode="multi_image",
        edit_prompt="Use both references.",
        provider_id="provider",
        generation_library=library,
        generation_engine=engine,
        reference_asset_id=12,
        references=references,
    )

    assert tuple(edit_item.metadata["references"]) == references
    queued = engine.queue_prompt_plan.call_args.kwargs
    assert queued["prompt_plan"].reference_asset_id == 12
    assert tuple(queued["prompt_plan"].prompt_metadata["references"]) == references
    assert "Reference roles supplied" not in queued["prompt_plan"].prompt_text
    assert tuple(queued["metadata"]["references"]) == references


def test_reference_request_defaults_role_for_backend_compatibility():
    reference = EditStudioReferenceInput(
        source="reference_library",
        asset_id=12,
    )

    assert reference.role == "Other"


def _reference(asset_id, filename, *, active=False, metadata=None, tags=()):
    return SimpleNamespace(
        asset_id=asset_id,
        is_active=active,
        metadata=metadata or {},
        asset=SimpleNamespace(file_name=filename, tags=tags),
    )


def test_creative_reference_catalog_excludes_identity_assets_and_prefers_friendly_labels():
    active = _reference(1, "active.png", active=True)
    canonical = _reference(2, "canonical.png", metadata={"canonical": True})
    locked = _reference(3, "locked.png", tags=("identity-lock",))
    titled = _reference(4, "uuid-title.png")
    named = _reference(5, "uuid-name.png", metadata={"user_defined_name": "Pool Wardrobe"})
    summarized = _reference(6, "uuid-prompt.png", metadata={"prompt_summary": "Golden-hour pool lighting"})
    described = _reference(7, "uuid-vision.png")
    fallback = _reference(8, "creative-fallback.png")
    reference_library = Mock()
    reference_library.list_references.return_value = SimpleNamespace(
        references=(active, canonical, locked, titled, named, summarized, described, fallback),
    )
    details = {
        1: SimpleNamespace(media_metadata={}, intelligence_profile=None, gpt_vision_result=None, summary=None),
        2: SimpleNamespace(media_metadata={}, intelligence_profile=None, gpt_vision_result=None, summary=None),
        3: SimpleNamespace(media_metadata={}, intelligence_profile=None, gpt_vision_result=None, summary=None),
        4: SimpleNamespace(media_metadata={}, intelligence_profile=SimpleNamespace(title="Silk Evening Look", short_description=None, detailed_description=None, content_summary=None), gpt_vision_result=None, summary=None),
        5: SimpleNamespace(media_metadata={}, intelligence_profile=None, gpt_vision_result=None, summary=None),
        6: SimpleNamespace(media_metadata={}, intelligence_profile=None, gpt_vision_result=None, summary=None),
        7: SimpleNamespace(media_metadata={}, intelligence_profile=None, gpt_vision_result={"description": "Neon city background"}, summary=None),
        8: SimpleNamespace(media_metadata={}, intelligence_profile=None, gpt_vision_result=None, summary=None),
    }
    reference_library.asset_library.get_asset_details.side_effect = details.get
    service, _ = _service()
    service.reference_library = reference_library

    result = service.creative_references(creator_profile_id=7)

    assert [item["asset_id"] for item in result] == [4, 5, 6, 7, 8]
    assert [item["label"] for item in result] == [
        "Silk Evening Look",
        "Pool Wardrobe",
        "Golden-hour pool lighting",
        "Neon city background",
        "creative-fallback.png",
    ]


def test_edit_studio_workflow_routes_are_registered():
    from app.fanvue_callback_server import app

    methods_by_path = {
        route.path: route.methods
        for route in app.routes
        if route.path.startswith("/api/v1/edit-studio")
    }

    assert methods_by_path["/api/v1/edit-studio/references"] == {"GET"}
    assert methods_by_path["/api/v1/edit-studio/references/upload"] == {"POST"}
    assert methods_by_path["/api/v1/edit-studio/return-to-library"] == {"POST"}
    assert methods_by_path["/api/v1/edit-studio/generate"] == {"POST"}
    assert methods_by_path["/api/v1/edit-studio/generation/{job_id}"] == {"GET"}
    assert methods_by_path["/api/v1/edit-studio/candidates/{candidate_id}/image"] == {"GET"}
    assert methods_by_path["/api/v1/edit-studio/approve"] == {"POST"}
    assert methods_by_path["/api/v1/edit-studio/edit-again"] == {"POST"}
    assert methods_by_path["/api/v1/edit-studio/discard"] == {"POST"}


def test_background_generation_reuses_engine_sync_and_candidate_services(monkeypatch):
    from app.api import edit_studio as api

    executed = SimpleNamespace(status="succeeded")
    record = SimpleNamespace(image_id="candidate-1")
    engine = Mock()
    engine.dispatch_job.return_value = executed
    library = Mock()
    library.sync_job.return_value = (record,)
    monkeypatch.setattr(api, "GenerationEngineService", lambda: engine)
    monkeypatch.setattr(api, "GenerationLibraryService", lambda: library)

    api._execute_edit_generation(job_id="job-1", pending_source_image_id="source-1")

    engine.dispatch_job.assert_called_once_with("job-1")
    library.sync_job.assert_called_once_with(executed)
    library.mark_edit_candidate.assert_called_once_with(
        "candidate-1",
        pending_source_image_id="source-1",
    )


def test_return_to_library_discards_all_linked_candidates_and_clears_pending(monkeypatch):
    from app.api import edit_studio as api

    source = SimpleNamespace(image_id="source-1")
    candidates = (
        SimpleNamespace(image_id="candidate-1", status="edit_candidate", generation_metadata={"edit_pending_source_image_id": "source-1"}),
        SimpleNamespace(image_id="candidate-2", status="edit_candidate", generation_metadata={"edit_pending_source_image_id": "source-1"}),
    )
    success = SimpleNamespace(success=True, errors=(), message="Returned.")
    library = Mock()
    library.pending_edit_record.side_effect = (source, None)
    library.list_records.return_value = candidates
    library.discard_edit_candidate.return_value = success
    library.return_pending_edit_to_library.return_value = success
    monkeypatch.setattr(api, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(api, "GenerationLibraryService", lambda: library)

    result = api.edit_studio_return_to_library()

    assert result == {"success": True, "message": "Returned."}
    assert [call.args[0] for call in library.discard_edit_candidate.call_args_list] == ["candidate-1", "candidate-2"]
    library.return_pending_edit_to_library.assert_called_once_with("source-1")
    assert library.pending_edit_record(creator_profile_id=7) is None


def test_approve_endpoint_returns_promoted_current_generation_record(monkeypatch, tmp_path):
    from app.api import edit_studio as api

    source = GeneratedImageRecord(
        image_id="source-1", generation_job_id="old-job", generation_request_id="old-request",
        generation_result_id="old-result", output_reference=str(tmp_path / "pending.png"),
        creator_profile_id=7, provider_id="old-provider", prompt_plan_id="old-plan",
        prompt_text="Old prompt", creative_mode="premium_teaser", reference_asset_id=None,
        status="pending_edit",
    )
    candidate = GeneratedImageRecord(
        image_id="candidate-1", generation_job_id="new-job", generation_request_id="new-request",
        generation_result_id="new-result", output_reference=str(tmp_path / "candidate.png"),
        creator_profile_id=7, provider_id="new-provider", prompt_plan_id="new-plan",
        prompt_text="New prompt", creative_mode="edit_single_image", reference_asset_id=None,
        status="edit_candidate", generation_metadata={"edit_pending_source_image_id": "source-1"},
    )
    updated = GeneratedImageRecord(
        **{
            **source.__dict__,
            "output_reference": str(tmp_path / "active-v2.png"),
            "provider_id": "new-provider",
            "prompt_text": "New prompt",
            "status": "active",
            "review_state": "approved_edit",
            "generation_metadata": {"asset_version": 2},
        }
    )
    library = Mock()
    library.pending_edit_record.return_value = source
    library.get.side_effect = lambda image_id: {"candidate-1": candidate, "source-1": updated}[image_id]
    library.approve_edit_candidate.return_value = SimpleNamespace(success=True, errors=(), message="Approved.")
    library.list_records.return_value = (updated,)
    monkeypatch.setattr(api, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(api, "GenerationLibraryService", lambda: library)

    result = api.edit_studio_approve(api.EditCandidateActionRequest(candidate_image_id="candidate-1"))

    assert result["updated_record"]["image_id"] == "source-1"
    assert result["updated_record"]["status"] == "active"
    assert result["updated_record"]["image_url"] == "/api/generation-library/media/source-1?v=2"
