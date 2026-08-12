from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock
import pytest

from app.api import photoshoot as api
from app.models.generation_library import GeneratedImageRecord
from app.models.creative_director import PhotoshootCreativeDirection
from app.models.photoshoot_queue import PhotoshootRequest, PhotoshootSession
from app.services.photoshoot_queue_service import PhotoshootQueueService
from app.services.photoshoot_context_service import PhotoshootContextService
from app.services.photoshoot_manual_service import PhotoshootManualService
from app.services.photoshoot_creative_director_service import PhotoshootCreativeDirectorWorkflowService


def _record(image_id: str, *, status: str = "pending_photoshoot"):
    return GeneratedImageRecord(
        image_id=image_id,
        output_reference=f"D:/Ava_CMS/Content/Pending_Photoshoot/{image_id}.png",
        creator_profile_id=7,
        provider_id="flux",
        prompt_text="Continue the seed shot",
        creative_mode="premium",
        generation_date="2026-07-18T12:00:00Z",
        status=status,
        generation_job_id="job-1",
        generation_request_id="generation-request-1",
        generation_result_id="result-1",
        prompt_plan_id="plan-1",
        reference_asset_id=None,
        imported_asset_id=None,
        provider_metadata={},
        prompt_metadata={},
        generation_metadata={},
        photoshoot_session_id="session-1", photoshoot_request_id="request-1",
        review_state="approved", selected=False, created_at="2026-07-18T12:00:00Z", updated_at=None,
    )


def _session():
    return PhotoshootSession(
        session_id="session-1",
        creator_profile_id=7,
        title="Photoshoot Studio",
        reference_asset_id=None,
        creative_mode="premium",
        status="running",
        provider_id="flux",
        creator_notes=None,
        creative_continuity={
            "seed_image_id": "seed-1", "original_photoshoot_direction": "Seed prompt",
            "continuity_locks": {"wardrobe": False, "camera_style": False},
        },
        request_ids=("request-1", "request-2"),
        current_request_id=None,
        created_at="2026-07-18T12:00:00Z",
        updated_at=None,
        metadata={},
    )


def test_context_aggregates_pending_session_registry_continuity_and_approved_timeline():
    seed = _record("seed-1")
    approved = SimpleNamespace(request_id="request-1", sequence_index=1, status="approved", metadata={"generated_image_ids": ("seed-1",), "is_seed_image": True})
    queued = SimpleNamespace(request_id="request-2", sequence_index=2, status="queued", metadata={"generated_image_ids": ("queued-1",)})
    library = Mock()
    library.list_records.return_value = (seed,)
    library.get.return_value = seed
    queue = Mock()
    queue.current_session.return_value = _session()
    queue.requests_for_session.return_value = (approved, queued)
    capability = SimpleNamespace(supports_images=True, supported_generation_types=("image_to_image",))
    engine = SimpleNamespace(provider_registry=SimpleNamespace(metadata=lambda: (
        SimpleNamespace(provider_id="flux", display_name="Flux", enabled=True, capabilities=capability),
    )))
    service = PhotoshootContextService(generation_library=library, generation_engine=engine, photoshoot_queue=queue)

    result = service.read(creator_profile={"id": 7})

    assert result["creator_profile_exists"] is True
    assert result["pending_photoshoot"]["image_id"] == "seed-1"
    assert result["active_session"]["session_id"] == "session-1"
    assert result["provider_list"] == [{"value": "flux", "label": "Flux"}]
    assert result["creative_mode"] == "premium"
    assert result["continuity_settings"]["wardrobe"] is False
    assert result["continuity_settings"]["camera_style"] is False
    assert [item["request_id"] for item in result["timeline_summary"]] == ["request-1"]
    assert result["timeline_summary"][0]["is_seed"] is True


def test_timeline_numbers_only_approved_positions_not_generation_attempts():
    seed = _record("seed-1", status="photoshoot_session")
    second = _record("approved-2", status="photoshoot_session")
    requests = (
        SimpleNamespace(request_id="seed-request", sequence_index=1, status="approved", metadata={"generated_image_ids": ("seed-1",), "is_seed_image": True}),
        SimpleNamespace(request_id="rejected-attempt", sequence_index=2, status="rejected", metadata={"generated_image_ids": ("rejected",)}),
        SimpleNamespace(request_id="regenerated-attempt", sequence_index=3, status="rejected", metadata={"generated_image_ids": ("regenerated",)}),
        SimpleNamespace(request_id="approved-request", sequence_index=4, status="approved", metadata={"generated_image_ids": ("approved-2",)}),
    )
    library = Mock()
    library.get.side_effect = lambda image_id: {"seed-1": seed, "approved-2": second}[image_id]
    queue = Mock()
    queue.requests_for_session.return_value = requests
    service = PhotoshootContextService(
        generation_library=library,
        generation_engine=SimpleNamespace(provider_registry=SimpleNamespace(metadata=lambda: ())),
        photoshoot_queue=queue,
    )

    timeline = service._timeline_summary(_session())

    assert [(item["sequence_index"], item["shot_number"], item["label"]) for item in timeline] == [
        (1, 1, "Shot 1 (Seed)"),
        (4, 2, "Shot 2"),
    ]


def test_context_returns_empty_gates_without_creator_profile():
    service = PhotoshootContextService(
        generation_library=Mock(), generation_engine=SimpleNamespace(provider_registry=SimpleNamespace(metadata=lambda: ())), photoshoot_queue=Mock(),
    )
    result = service.read(creator_profile={})
    assert result["creator_profile_exists"] is False
    assert result["pending_photoshoot"] is None
    assert result["active_session"] is None
    assert result["timeline_summary"] == []


def test_photoshoot_context_endpoint_uses_active_creator(monkeypatch):
    context = Mock()
    context.read.return_value = {
        "creator_profile_exists": False, "pending_photoshoot": None, "active_session": None,
        "provider_list": [], "creative_mode": None, "continuity_settings": None, "timeline_summary": [],
    }
    monkeypatch.setattr(api, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(api, "PhotoshootContextService", lambda: context)
    assert api.photoshoot_context()["creator_profile_exists"] is False
    context.read.assert_called_once_with(creator_profile={"id": 7})


def test_photoshoot_context_route_is_registered():
    from app.fanvue_callback_server import app

    route = next(route for route in app.routes if getattr(route, "path", None) == "/api/v1/photoshoot/context")
    assert route.methods == {"GET"}
    assert route.response_model.__name__ == "PhotoshootContextResponse"


def test_context_uses_session_seed_instead_of_newest_stale_pending():
    seed = _record("seed-1")
    stale = _record("stale-newer")
    library = Mock()
    library.list_records.return_value = (stale, seed)
    library.get.return_value = seed
    queue = Mock()
    queue.current_session.return_value = _session()
    queue.requests_for_session.return_value = (SimpleNamespace(request_id="request-1", sequence_index=1, status="approved", metadata={"generated_image_ids": ("seed-1",), "is_seed_image": True}),)
    engine = SimpleNamespace(provider_registry=SimpleNamespace(metadata=lambda: ()))
    result = PhotoshootContextService(generation_library=library, generation_engine=engine, photoshoot_queue=queue).read(creator_profile={"id": 7})
    assert result["pending_photoshoot"]["image_id"] == "seed-1"
    assert result["timeline_summary"][0]["image"]["image_id"] == "seed-1"


def test_return_to_library_resolves_queue_and_pending_seed(monkeypatch):
    session = _session()
    request = SimpleNamespace(request_id="request-1", status="approved", metadata={"is_seed_image": True})
    queue = Mock()
    queue.current_session.return_value = session
    queue.requests_for_session.return_value = (request,)
    queue.get_session.return_value = SimpleNamespace(status="cancelled")
    library = Mock()
    library.return_photoshoot_seed_to_library.return_value = SimpleNamespace(success=True, message="Returned", errors=())
    monkeypatch.setattr(api, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(api, "PhotoshootQueueService", lambda: queue)
    monkeypatch.setattr(api, "GenerationLibraryService", lambda: library)
    result = api.return_photoshoot_to_library()
    queue.return_seed_request_to_library.assert_called_once_with("request-1", notes="Returned from Photoshoot Studio.")
    library.return_photoshoot_seed_to_library.assert_called_once_with("seed-1")
    assert result["redirect"] == "/library/generations"


def test_stop_returns_original_seed_once_and_never_uses_latest_approved_shot():
    session = replace(_session(), creative_continuity={
        "seed_image_id": "seed-1", "current_shot_image_id": "approved-latest",
        "inspiration_ideas": ("idea",), "current_prompt": "prompt", "creator_guidance": "guidance",
    })
    cancelled = replace(session, status="cancelled", creative_continuity={
        "seed_image_id": "seed-1", "seed_returned_to_library": True,
    })
    seed_request = SimpleNamespace(request_id="request-1", status="approved", metadata={"is_seed_image": True})
    queue = Mock()
    queue.current_session.side_effect = [session, None]
    queue.list_sessions.return_value = (cancelled,)
    queue.requests_for_session.return_value = (seed_request,)
    queue.cancel_session_for_seed_return.return_value = cancelled
    library = Mock()
    library.return_photoshoot_seed_to_library.return_value = SimpleNamespace(success=True, errors=(), message="Returned")
    service = PhotoshootManualService(queue=queue, engine=Mock(), library=library, ingestion=Mock())

    first_session, first_seed = service.stop_and_return_seed(creator_profile_id=7)
    second_session, second_seed = service.stop_and_return_seed(creator_profile_id=7)

    assert first_session.status == second_session.status == "cancelled"
    assert first_seed == second_seed == "seed-1"
    assert library.return_photoshoot_seed_to_library.call_args_list[0].args == ("seed-1",)
    assert all(call.args != ("approved-latest",) for call in library.return_photoshoot_seed_to_library.call_args_list)
    queue.return_seed_request_to_library.assert_called_once()
    queue.cancel_session_for_seed_return.assert_called_once_with("session-1", seed_image_id="seed-1")


def test_cancel_for_seed_return_clears_candidate_and_ai_state_without_touching_other_sessions():
    session = replace(_session(), current_request_id="request-2", creative_continuity={
        "seed_image_id": "seed-1", "current_shot_image_id": "approved-latest",
        "inspiration_ideas": ("idea",), "selected_inspiration": "idea",
        "current_direction": {"title": "Direction"}, "current_prompt": "prompt",
        "creator_guidance": "guidance", "grok_guidance": "guidance", "direction_approved": True,
        "continuity_locks": {"wardrobe": True},
    })
    candidate = PhotoshootRequest(
        request_id="request-2", session_id="session-1", prompt_plan_id="plan-2",
        prompt_text="candidate", sequence_index=2, creative_mode="premium",
        reference_asset_id=None, status="awaiting_review", metadata={"generated_image_ids": ("candidate-2",)},
    )
    queue = Mock()
    queue.get_session.return_value = session
    queue.requests_for_session.return_value = (candidate,)

    updated = PhotoshootQueueService.cancel_session_for_seed_return(queue, "session-1", seed_image_id="seed-1")

    assert updated.status == "cancelled"
    assert updated.current_request_id is None
    assert updated.creative_continuity["seed_image_id"] == "seed-1"
    assert updated.creative_continuity["seed_returned_to_library"] is True
    assert updated.creative_continuity["continuity_locks"] == {"wardrobe": True}
    for key in ("inspiration_ideas", "selected_inspiration", "current_direction", "current_prompt", "creator_guidance", "grok_guidance", "direction_approved"):
        assert key not in updated.creative_continuity
    assert queue._replace_request.call_args.args[0].status == "cancelled"
    queue.get_session.assert_called_once_with("session-1")


def test_stop_does_not_modify_completed_photoshoots():
    completed = replace(_session(), status="completed")
    queue = Mock()
    queue.current_session.return_value = None
    queue.list_sessions.return_value = (completed,)
    service = PhotoshootManualService(queue=queue, engine=Mock(), library=Mock(), ingestion=Mock())

    try:
        service.stop_and_return_seed(creator_profile_id=7)
        assert False, "Expected no active Photoshoot"
    except KeyError:
        pass

    queue.cancel_session_for_seed_return.assert_not_called()


def test_manual_request_persists_settings_uses_latest_approved_reference_and_dispatches():
    session = _session()
    session = SimpleNamespace(**{**session.__dict__, "creative_continuity": {
        **dict(session.creative_continuity), "current_shot_image_id": "approved-1",
    }})
    approved_request = SimpleNamespace(status="approved", metadata={"generated_image_ids": ("approved-1",)})
    created = SimpleNamespace(request_id="manual-1")
    job = SimpleNamespace(job_id="job-2")
    latest = _record("approved-1", status="photoshoot_session")
    queue = Mock()
    queue.get_session.return_value = session
    queue.requests_for_session.return_value = (approved_request,)
    queue.update_session_settings.return_value = session
    queue.add_studio_shot_request.return_value = created
    queue.queue_next_prompt.return_value = job
    library = Mock()
    library.get.return_value = latest
    service = PhotoshootManualService(queue=queue, engine=Mock(), library=library, ingestion=Mock())
    request, dispatched = service.create_manual_request(
        creator_profile_id=7, session_id="session-1", provider_id="flux", creative_mode="premium",
        prompt="Next pose", continuity_locks={"wardrobe": True}, session_direction="Balcony",
        creative_hint="Look back",
    )
    assert request is created and dispatched is job
    queue.update_session_settings.assert_called_once_with(
        "session-1", provider_id="flux", creative_mode="premium", continuity_locks={"wardrobe": True},
        session_direction="Balcony", creative_hint="Look back", workflow_stage="ready_to_generate",
    )
    queue.add_studio_shot_request.assert_called_once_with(
        session_id="session-1", prompt_text="Next pose", shot_direction="Balcony\nLook back",
        provider_id="flux", active_reference_image_id="approved-1",
        active_reference_output_reference=latest.output_reference, creative_direction={},
    )


def test_manual_request_reuses_provider_url_for_approved_shot_continuity():
    session = SimpleNamespace(**{**_session().__dict__, "creative_continuity": {
        "current_shot_image_id": "approved-1",
    }})
    latest = _record("approved-1", status="photoshoot_session")
    queue = Mock()
    queue.get_session.return_value = session
    queue.requests_for_session.return_value = ()
    queue.update_session_settings.return_value = session
    queue.add_studio_shot_request.return_value = SimpleNamespace(request_id="manual-remote")
    queue.queue_next_prompt.return_value = SimpleNamespace(job_id="job-next")
    library = Mock()
    library.get.return_value = latest
    engine = Mock()
    engine.get_job.return_value = SimpleNamespace(result=SimpleNamespace(
        output_references=("https://provider.test/approved-1.png",),
    ))

    PhotoshootManualService(queue=queue, engine=engine, library=library, ingestion=Mock()).create_manual_request(
        creator_profile_id=7, session_id="session-1", provider_id="flux", creative_mode="premium",
        prompt="Next shot", continuity_locks={}, session_direction="", creative_hint="",
    )

    engine.get_job.assert_called_once_with(latest.generation_job_id)
    assert queue.add_studio_shot_request.call_args.kwargs["active_reference_output_reference"] == (
        "https://provider.test/approved-1.png"
    )


def test_manual_candidate_actions_reuse_junk_and_queue_lifecycle():
    session = _session()
    request = SimpleNamespace(request_id="request-2", session_id="session-1", status="awaiting_review",
                              prompt_text="Try this", metadata={"generated_image_ids": ("candidate-1",)})
    job = SimpleNamespace(job_id="job-3")
    queue = Mock()
    queue.get_session.return_value = session
    queue.get_request.return_value = request
    queue.regenerate_request.return_value = request
    queue.queue_next_prompt.return_value = job
    library = Mock()
    library.move_photoshoot_records_to_junk.return_value = SimpleNamespace(success=True, errors=(), message="Junked")
    service = PhotoshootManualService(queue=queue, engine=Mock(), library=library, ingestion=Mock())
    regenerated, dispatched = service.regenerate(creator_profile_id=7, session_id="session-1", request_id="request-2")
    assert regenerated is request and dispatched is job
    library.move_photoshoot_records_to_junk.assert_called_once_with(
        ("candidate-1",), session_id="session-1", session_title="Photoshoot Studio", reason="photoshoot_regenerate",
    )
    queue.regenerate_request.assert_called_once_with("request-2")


def test_manual_reject_can_save_candidate_without_approving_or_advancing():
    session = _session()
    request = SimpleNamespace(
        request_id="request-2", session_id="session-1", status="awaiting_review",
        prompt_text="Try this", metadata={"generated_image_ids": ("candidate-1",)},
    )
    queue = Mock()
    queue.get_session.return_value = session
    queue.get_request.return_value = request
    library = Mock()
    library.save_rejected_photoshoot_candidate_to_library.return_value = SimpleNamespace(
        success=True, errors=(), message="Saved",
    )
    service = PhotoshootManualService(queue=queue, engine=Mock(), library=library, ingestion=Mock())

    service.reject(
        creator_profile_id=7, session_id="session-1", request_id="request-2",
        save_to_generation_library=True,
    )

    library.save_rejected_photoshoot_candidate_to_library.assert_called_once_with("candidate-1")
    library.move_photoshoot_records_to_junk.assert_not_called()
    queue.reject_request.assert_called_once_with("request-2")
    queue.approve_request.assert_not_called()
    queue.update_session_settings.assert_not_called()


def test_manual_reference_uses_backend_current_shot_and_never_stale_seed():
    session = _session()
    session = SimpleNamespace(**{**session.__dict__, "creative_continuity": {
        "seed_image_id": "seed-1", "current_shot_image_id": "shot-2",
        "continuity_locks": {"location": True, "wardrobe": True},
    }})
    current = _record("shot-2", status="photoshoot_session")
    queue = Mock()
    queue.get_session.return_value = session
    queue.requests_for_session.return_value = ()
    queue.update_session_settings.return_value = session
    queue.add_studio_shot_request.return_value = SimpleNamespace(request_id="request-3")
    queue.queue_next_prompt.return_value = SimpleNamespace(job_id="job-4")
    library = Mock()
    library.get.return_value = current
    service = PhotoshootManualService(queue=queue, engine=Mock(), library=library, ingestion=Mock())

    service.create_manual_request(
        creator_profile_id=7, session_id="session-1", provider_id="flux", creative_mode="premium",
        prompt="Third shot", continuity_locks={"location": True, "wardrobe": True},
        session_direction="", creative_hint="",
    )

    library.get.assert_called_once_with("shot-2")
    assert queue.add_studio_shot_request.call_args.kwargs["active_reference_image_id"] == "shot-2"
    assert queue.add_studio_shot_request.call_args.kwargs["active_reference_image_id"] != "seed-1"


def test_manual_photoshoot_routes_are_registered():
    from app.fanvue_callback_server import app
    paths = {getattr(route, "path", None): route.methods for route in app.routes}
    assert paths["/api/v1/photoshoot/generate"] == {"POST"}
    assert paths["/api/v1/photoshoot/status"] == {"GET"}
    for action in ("approve", "regenerate", "edit-prompt", "reject"):
        assert paths[f"/api/v1/photoshoot/candidate/{action}"] == {"POST"}
    assert paths["/api/v1/photoshoot/finish"] == {"POST"}
    assert paths["/api/v1/photoshoot/stop-and-return-seed"] == {"POST"}


def test_approve_endpoint_returns_the_persisted_request_and_session(monkeypatch):
    approved = PhotoshootRequest(
        request_id="request-2", session_id="session-1", prompt_plan_id="plan-2",
        prompt_text="Approved shot", sequence_index=2, creative_mode="premium",
        reference_asset_id=None, status="approved", imported_asset_ids=(94,),
    )
    session = replace(
        _session(),
        current_request_id=None,
        creative_continuity={
            **dict(_session().creative_continuity),
            "current_shot_image_id": "shot-2",
            "workflow_stage": "ready_for_next_shot",
        },
    )
    service = Mock()
    service.approve.return_value = approved
    service.queue.get_session.return_value = session
    monkeypatch.setattr(api, "PhotoshootManualService", lambda: service)
    monkeypatch.setattr(api, "_creator_profile_id_required", lambda: 7)

    result = api.approve_manual_candidate(
        api.CandidateActionRequest(session_id="session-1", request_id="request-2")
    )

    assert result["request"] == {
        "request_id": "request-2", "status": "approved", "imported_asset_ids": [94],
    }
    assert result["session"]["current_request_id"] is None
    assert result["session"]["creative_continuity"]["current_shot_image_id"] == "shot-2"
    assert result["session"]["creative_continuity"]["workflow_stage"] == "ready_for_next_shot"


def test_finish_is_the_only_session_completion_transition():
    session = replace(_session(), creative_continuity={
        **_session().creative_continuity, "workflow_stage": "ready_for_next_shot", "current_shot_image_id": "approved-2",
    })
    completed = replace(session, status="completed", creative_continuity={
        **session.creative_continuity, "completed_at": "2026-07-18T12:05:00Z", "gallery_ready": True,
    })
    queue = Mock()
    queue.get_session.return_value = session
    queue.requests_for_session.return_value = ()
    queue.finish_session.return_value = completed
    commerce = Mock()
    commerce.complete.return_value = (completed, {"deliverable_id": "deliverable-1"})
    service = PhotoshootManualService(queue=queue, engine=Mock(), library=Mock(), ingestion=Mock(), commerce_deliverables=commerce)

    finish_result = service.finish_session(creator_profile_id=7, session_id="session-1")
    assert finish_result.status == "completed"
    assert finish_result.creative_continuity["gallery_ready"] is True
    assert finish_result.creative_continuity["current_shot_image_id"] == "approved-2"
    commerce.complete.assert_called_once_with("session-1", 7)


def test_creative_director_context_restores_persisted_workflow_state():
    session = _session()
    session = replace(session, creative_mode="explicit", creative_continuity={
        "creator_guidance": "Progress naturally", "creative_hint": "Idea two", "grok_guidance": "Progress naturally",
        "workflow_stage": "recommendation_ready", "continuity_locks": {"wardrobe": False},
            "inspiration_ideas": ("Idea one", "Idea two"), "selected_inspiration": "Idea two",
            "inspiration_edits": {"Idea two": "Idea two with stronger eye contact"},
            "inspiration_planning_shot": 2,
        "current_direction": {"title": "Closer framing", "creative_direction": "Move closer"},
        "direction_approved": False,
    })
    queue = Mock()
    queue.get_session.return_value = session
    result = PhotoshootCreativeDirectorWorkflowService(queue=queue, library=Mock(), creative_director=Mock()).context(
        creator_profile_id=7, session_id="session-1",
    )
    assert result["creative_mode"] == "explicit"
    assert result["creator_guidance"] == "Progress naturally"
    assert result["recommendation_state"]["inspiration_ideas"] == ["Idea one", "Idea two"]
    assert result["recommendation_state"]["selected_inspiration"] == "Idea two"
    assert result["recommendation_state"]["inspiration_edits"] == {"Idea two": "Idea two with stronger eye contact"}
    assert result["recommendation_state"]["recommendation"]["title"] == "Closer framing"


def test_creative_director_recommendation_delegates_and_persists(monkeypatch):
    session = _session()
    session = replace(session, creative_continuity={
        **session.creative_continuity, "inspiration_ideas": ("Turn", "Look away"), "selected_inspiration": "Turn", "inspiration_planning_shot": 2,
        "inspiration_edits": {"Turn": "Keep her head turned farther back toward the camera"},
    })
    queue = Mock()
    queue.get_session.return_value = session
    queue.update_session_settings.return_value = session
    queue.requests_for_session.return_value = ()
    library = Mock()
    library.get.return_value = _record("seed-1")
    director = Mock()
    director.recommend_photoshoot_direction.return_value = PhotoshootCreativeDirection(
        title="Next", creative_direction="Turn toward camera", reasoning="Progression", continuity_notes="Keep lighting",
        camera_framing="Medium", lighting="Warm", emotion="Confident", pose_composition="Standing",
        creative_mode="premium", session_direction="Balcony", continuity_locks={"location": True}, raw_response="{}",
    )
    service = PhotoshootCreativeDirectorWorkflowService(queue=queue, library=library, creative_director=director)
    monkeypatch.setattr(service, "_image_bytes", lambda _: (b"image", "image/png"))
    result = service.recommendation(
        creator_profile_id=7, session_id="session-1", creative_mode="premium", creator_guidance="Balcony",
        continuity_locks={"location": True},
    )
    assert result["title"] == "Next"
    director.recommend_photoshoot_direction.assert_called_once()
    assert director.recommend_photoshoot_direction.call_args.kwargs["creative_hint"] == "Keep her head turned farther back toward the camera"
    call = director.recommend_photoshoot_direction.call_args.kwargs
    assert call["session_direction"] == "Seed prompt"
    assert call["session_context"]["original_photoshoot_direction"] == "Seed prompt"
    assert call["session_context"]["optional_user_guidance"] == "Balcony"
    assert call["approved_history"] == ()
    assert call["session_context"]["progression_stage"] == 0
    queue.record_pending_recommendation.assert_called_once_with(session_id="session-1", recommendation=result)


def test_direct_shot_recommendation_bypasses_inspiration_gate_and_reuses_enhancement(monkeypatch):
    session = replace(_session(), creative_continuity={
        **_session().creative_continuity,
        "canonical_seed_summary": {"scene": "Hotel window portrait"},
        "approved_directions": ({"title": "Previous shot"},),
        "progression_stage": 2,
    })
    queue = Mock()
    queue.get_session.return_value = session
    queue.update_session_settings.return_value = session
    queue.requests_for_session.return_value = ()
    library = Mock()
    library.get.return_value = _record("seed-1")
    director = Mock()
    director.recommend_photoshoot_direction.return_value = PhotoshootCreativeDirection(
        title="Directed shot", creative_direction="Lift the shirt naturally", reasoning="Operator direction",
        continuity_notes="Keep the hotel and lighting", camera_framing="Medium", lighting="Warm",
        emotion="Confident", pose_composition="Standing", creative_mode="premium",
        session_direction="Seed prompt", continuity_locks={"location": True}, raw_response="{}",
    )
    service = PhotoshootCreativeDirectorWorkflowService(
        queue=queue, library=library, creative_director=director,
    )
    monkeypatch.setattr(service, "_image_bytes", lambda _: (b"image", "image/png"))

    result = service.direct_recommendation(
        creator_profile_id=7,
        session_id="session-1",
        creative_mode="premium",
        operator_direction="  Have her lift her shirt.  ",
        continuity_locks={"location": True},
    )

    assert result["title"] == "Directed shot"
    call = director.recommend_photoshoot_direction.call_args.kwargs
    assert call["creative_hint"] == "Have her lift her shirt."
    assert call["image_bytes"] == b"image"
    assert call["approved_history"] == ({"title": "Previous shot"},)
    assert call["session_context"]["canonical_seed_summary"].startswith(
        "Original scene: Hotel window portrait"
    )
    assert call["session_context"]["progression_stage"] == 2
    settings = queue.update_session_settings.call_args_list[-1]
    assert settings.kwargs["creative_hint"] == "Have her lift her shirt."
    assert settings.kwargs["selected_inspiration"] == ""
    assert "inspiration_ideas" not in settings.kwargs
    queue.record_pending_recommendation.assert_called_once_with(
        session_id="session-1", recommendation=result,
    )


def test_one_inspiration_selection_is_validated_and_persisted():
    session = replace(_session(), creative_continuity={
        **_session().creative_continuity, "inspiration_ideas": ("First", "Second"), "inspiration_planning_shot": 2,
    })
    queue = Mock()
    queue.get_session.return_value = session
    result = PhotoshootCreativeDirectorWorkflowService(queue=queue, library=Mock(), creative_director=Mock()).select_inspiration(
        creator_profile_id=7, session_id="session-1", idea="Second", edited_direction="Lower the shorts another inch while looking back",
    )
    assert result["selected_inspiration"] == "Second"
    queue.update_session_settings.assert_called_once_with(
        "session-1", creative_hint="Lower the shorts another inch while looking back",
        selected_inspiration="Second", inspiration_edits={"Second": "Lower the shorts another inch while looking back"},
        workflow_stage="inspiration_selected",
    )
    assert result["edited_direction"] == "Lower the shorts another inch while looking back"


def test_ai_ideas_cannot_cross_planning_positions():
    session = replace(_session(), creative_continuity={
        **_session().creative_continuity, "inspiration_ideas": ("First",),
        "selected_inspiration": "First", "inspiration_planning_shot": 2,
    })
    queue = Mock()
    queue.get_session.return_value = session
    queue.requests_for_session.return_value = (
        SimpleNamespace(status="approved", sequence_index=1),
        SimpleNamespace(status="approved", sequence_index=2),
    )
    service = PhotoshootCreativeDirectorWorkflowService(queue=queue, library=Mock(), creative_director=Mock())
    with pytest.raises(ValueError, match="different Photoshoot position"):
        service.select_inspiration(creator_profile_id=7, session_id="session-1", idea="First")


def test_continuity_assessment_warns_only_for_significant_drift(monkeypatch):
    queue, library, director = Mock(), Mock(), Mock()
    queue.get_session.return_value = replace(_session(), creative_continuity={
        **_session().creative_continuity,
        "canonical_identity_reference": {"asset_id": 55, "path": "C:/identity.png"},
        "canonical_identity_reference_frozen": True,
    })
    queue.get_request.return_value = SimpleNamespace(
        session_id="session-1", metadata={"active_reference_image_id": "approved-2"},
    )
    library.get.side_effect = lambda image_id: _record(str(image_id), status="photoshoot_session")
    service = PhotoshootCreativeDirectorWorkflowService(queue=queue, library=library, creative_director=director)
    monkeypatch.setattr(service, "_image_bytes", lambda reference: (str(reference).encode(), "image/png"))
    director.ask_anything.return_value = '{"identity":"strong","wardrobe":"weak","location":"weak","lighting":"acceptable","composition":"acceptable","overall_continuity":"weak","reason":"Setting and clothing changed."}'
    weak = service.assess_continuity(session_id="session-1", request_id="request-2", candidate_image_id="candidate-2")
    assessment_call = director.ask_anything.call_args
    assert [item["label"] for item in assessment_call.kwargs["images"]] == [
        "Frozen canonical identity", "Approved continuity reference", "Candidate",
    ]
    assert "Assess identity only against Image 1" in assessment_call.kwargs["question"]
    assert "Expression may intentionally change" in assessment_call.kwargs["question"]
    director.ask_anything.return_value = '{"identity":"strong","wardrobe":"strong","location":"strong","lighting":"acceptable","composition":"acceptable","overall_continuity":"strong","reason":"Continuity holds."}'
    strong = service.assess_continuity(session_id="session-1", request_id="request-2", candidate_image_id="candidate-3")
    assert weak["warning"] is True
    assert weak["warning_message"] == "This generation may have drifted from the current photoshoot."
    assert strong["warning"] is False
    assert strong["warning_message"] == ""


def test_different_ideas_reuses_session_and_returns_a_fresh_ten(monkeypatch):
    session = replace(_session(), creative_continuity={
        **_session().creative_continuity,
        "inspiration_edits": {"Old direction": "Old edited direction"},
    })
    queue, library, director = Mock(), Mock(), Mock()
    queue.get_session.return_value = session
    queue.update_session_settings.return_value = session
    queue.requests_for_session.return_value = ()
    library.get.return_value = _record("seed-1")
    director.suggest_photoshoot_inspiration.side_effect = (
        tuple(f"First set {index}" for index in range(10)),
        tuple(f"Fresh set {index}" for index in range(10)),
    )
    service = PhotoshootCreativeDirectorWorkflowService(queue=queue, library=library, creative_director=director)
    monkeypatch.setattr(service, "_image_bytes", lambda _: (b"image", "image/png"))
    args = dict(creator_profile_id=7, session_id="session-1", creative_mode="premium", creator_guidance="",
                provider_context="Flux", continuity_locks={"location": True})
    first = service.inspiration(**args)
    refreshed = service.inspiration(**args)
    assert first["ideas"] != refreshed["ideas"]
    assert len(refreshed["ideas"]) == 10
    assert director.suggest_photoshoot_inspiration.call_count == 2
    assert queue.update_session_settings.call_args.kwargs["inspiration_edits"] == {}


def test_freeflow_ask_ai_appends_durable_idea_sets_without_overwriting(monkeypatch, tmp_path):
    queue = PhotoshootQueueService(storage_dir=tmp_path / "queue")
    session = replace(_session(), target_shot_count=0, creative_continuity={
        **_session().creative_continuity, "planning_mode": "frame_by_frame", "target_shot_count": 0,
    })
    queue._write_sessions((session,))
    library, director, summary = Mock(), Mock(), Mock()
    library.get.return_value = _record("seed-1")
    summary.refresh.return_value = {}
    director.suggest_photoshoot_inspiration.side_effect = (
        tuple(f"Original idea {index}" for index in range(1, 11)),
        tuple(f"Different idea {index}" for index in range(1, 11)),
    )
    service = PhotoshootCreativeDirectorWorkflowService(
        queue=queue, library=library, creative_director=director, summary_service=summary,
    )
    monkeypatch.setattr(service, "_image_bytes", lambda _: (b"image", "image/png"))
    args = dict(creator_profile_id=7, session_id="session-1", creative_mode="premium",
                creator_guidance="", provider_context="Flux", continuity_locks={"location": True},
                target_shot_count=0)

    first = service.inspiration(**args)
    second = service.inspiration(**args)

    continuity = dict(queue.get_session("session-1").creative_continuity)
    sets = tuple(continuity["freeflow_idea_sets"])
    assert len(sets) == 2
    assert sets[0]["ideas"] == first["ideas"]
    assert sets[1]["ideas"] == second["ideas"]
    assert sets[0]["idea_set_id"] != sets[1]["idea_set_id"]
    assert sets[0]["recommended_idea"] == first["ideas"][0]
    assert director.suggest_photoshoot_inspiration.call_count == 2


def test_existing_freeflow_ideas_reactivate_exact_text_without_provider_call(tmp_path):
    queue = PhotoshootQueueService(storage_dir=tmp_path / "queue")
    session = replace(_session(), target_shot_count=0, creative_continuity={
        **_session().creative_continuity, "planning_mode": "frame_by_frame", "target_shot_count": 0,
    })
    queue._write_sessions((session,))
    queue.record_freeflow_idea_set(
        "session-1", idea_set_id="idea-set-1", ideas=("Exact first idea", "Exact second idea"),
        recommended_idea="Exact second idea", planning_shot=2,
    )
    queue._write_requests((
        PhotoshootRequest("seed-request", "session-1", "seed-plan", "Seed", 1, "premium", None,
                          status="approved", metadata={"is_seed_image": True}),
        PhotoshootRequest("idea-request", "session-1", "idea-plan", "Prompt", 2, "premium", None,
                          status="approved", metadata={"inspiration_idea_set_id": "idea-set-1", "selected_inspiration": "Exact first idea"}),
    ))
    director = Mock()
    service = PhotoshootCreativeDirectorWorkflowService(queue=queue, library=Mock(), creative_director=director)

    result = service.existing_inspiration(creator_profile_id=7, session_id="session-1")

    assert result["ideas"] == ["Exact first idea", "Exact second idea"]
    assert result["freeflow_idea_set"]["recommended_idea"] == "Exact second idea"
    assert result["freeflow_idea_set"]["usage"] == {"Exact first idea": ["Shot 2"]}
    restored = queue.get_session("session-1")
    assert tuple(restored.creative_continuity["inspiration_ideas"]) == ("Exact first idea", "Exact second idea")
    assert restored.creative_continuity["active_freeflow_idea_set_id"] == "idea-set-1"
    director.suggest_photoshoot_inspiration.assert_not_called()
    director.recommend_photoshoot_direction.assert_not_called()


@pytest.mark.parametrize("target", [5, 10, 20, 27])
def test_existing_freeflow_ideas_are_not_exposed_in_progression_modes(target):
    session = replace(_session(), target_shot_count=target, creative_continuity={
        **_session().creative_continuity,
        "planning_mode": "frame_by_frame",
        "freeflow_idea_sets": ({"idea_set_id": "saved", "ideas": ("Keep me",), "recommended_idea": "Keep me"},),
    })
    queue = Mock()
    queue.get_session.return_value = session
    queue.requests_for_session.return_value = ()
    director = Mock()
    service = PhotoshootCreativeDirectorWorkflowService(queue=queue, library=Mock(), creative_director=director)
    assert service.context(creator_profile_id=7, session_id="session-1")["freeflow_idea_set"] is None
    with pytest.raises(ValueError, match="only in Creative Freeflow"):
        service.existing_inspiration(creator_profile_id=7, session_id="session-1")
    director.suggest_photoshoot_inspiration.assert_not_called()


def test_all_modes_request_ten_ideas_with_summary_original_direction_and_guidance(monkeypatch):
    for mode, guidance in (("safe", ""), ("premium", "More eye contact"), ("explicit", "Slow the progression")):
        session = replace(_session(), creative_mode=mode, creative_continuity={
            **_session().creative_continuity, "current_shot_image_id": "shot-2",
            "approved_prompts": ("Seed prompt", "Second prompt"),
            "approved_directions": ({"title": "Second"},), "progression_stage": 2,
        })
        requests = (
            SimpleNamespace(status="approved", prompt_text="Seed prompt", metadata={"generated_image_ids": ("seed-1",), "is_seed_image": True}),
            SimpleNamespace(status="approved", prompt_text="Second prompt", metadata={"generated_image_ids": ("shot-2",)}),
        )
        queue, library, director = Mock(), Mock(), Mock()
        queue.get_session.return_value = session
        queue.update_session_settings.return_value = session
        queue.requests_for_session.return_value = requests
        library.get.side_effect = lambda image_id: _record(str(image_id), status="photoshoot_session")
        director.suggest_photoshoot_inspiration.return_value = tuple(f"{mode} idea {index}" for index in range(1, 11))
        service = PhotoshootCreativeDirectorWorkflowService(queue=queue, library=library, creative_director=director)
        monkeypatch.setattr(service, "_image_bytes", lambda reference: (str(reference).encode(), "image/png"))

        result = service.inspiration(
            creator_profile_id=7, session_id="session-1", creative_mode=mode,
            creator_guidance=guidance, provider_context="Flux", continuity_locks={"location": True},
        )

        assert len(result["ideas"]) == 10
        expected_selected = f"{mode} idea 1" if mode == "explicit" else ""
        assert result["selected_inspiration"] == expected_selected
        call = director.suggest_photoshoot_inspiration.call_args.kwargs
        assert call["creative_mode"] == mode
        assert call["idea_count"] == 10
        assert call["image_bytes"] == _record("shot-2").output_reference.encode()
        timeline = call["timeline_images"]
        assert len(timeline) == 2
        assert timeline[0]["label"] == "Shot 1 (Seed)"
        assert timeline[1]["label"] == "Shot 2 — current"
        assert timeline[0]["bytes"] == b"D:/Ava_CMS/Content/Pending_Photoshoot/seed-1.png"
        assert timeline[1]["bytes"] == b"D:/Ava_CMS/Content/Pending_Photoshoot/shot-2.png"
        assert call["approved_history"] == ({"title": "Second"},)
        assert call["grok_guidance"] == guidance
        assert call["session_direction"] == "Seed prompt"
        assert call["session_context"]["original_photoshoot_direction"] == "Seed prompt"
        assert call["session_context"]["optional_user_guidance"] == guidance
        assert call["session_context"]["current_photoshoot_summary"]["approved_shot_count"] == 2
        assert call["session_context"]["progression_stage"] == 2
        assert call["session_context"]["timeline_image_count"] == 2
        assert call["session_context"]["current_shot"] == 2
        assert call["session_context"]["planning_shot"] == 3
        assert call["session_context"]["remaining_shots"] == 8
        assert call["session_context"]["editorial_stage"] == "Beginning"
        settings_call = queue.update_session_settings.call_args_list[-1]
        assert settings_call.args[0] == "session-1"
        assert settings_call.kwargs["selected_inspiration"] == expected_selected
        assert settings_call.kwargs["creative_hint"] == expected_selected
        assert settings_call.kwargs["workflow_stage"] == (
            "inspiration_selected" if mode == "explicit" else "inspiration_ready"
        )


def test_creative_director_approval_uses_canonical_planner_and_existing_queue_history():
    session = _session()
    recommendation = {
        "title": "Next",
        "creative_direction": "Move closer",
        "camera_framing": "Medium",
        "emotion": "locked salacious eye contact, alert open eyes, parted lips",
    }
    session = SimpleNamespace(**{**session.__dict__, "creative_mode": "explicit", "creative_continuity": {
        **session.creative_continuity, "current_direction": recommendation,
    }})
    queue = Mock()
    queue.get_session.return_value = session
    queue.requests_for_session.return_value = ()
    library = Mock()
    library.get.return_value = _record("seed-1")
    director = Mock()
    director.plan_prompts.return_value = SimpleNamespace(prompts=("Canonical explicit prompt",))
    result = PhotoshootCreativeDirectorWorkflowService(queue=queue, library=library, creative_director=director).approve(
        creator_profile_id=7, session_id="session-1",
    )
    assert result["prompt"] == "Canonical explicit prompt"
    assert director.plan_prompts.call_args.kwargs["mode"] == "photoshoot_explicit"
    metadata = director.plan_prompts.call_args.kwargs["metadata"]
    assert metadata["source"] == "photoshoot_studio"
    assert metadata["operator_expression"] == recommendation["emotion"]
    assert metadata["freeflow_expression"] is False
    assert metadata["concept_tier"] == "hardcore"
    queue.record_creative_direction.assert_called_once_with(
        session_id="session-1", recommendation=recommendation, final_prompt="Canonical explicit prompt",
    )


def test_creative_director_routes_are_registered():
    from app.fanvue_callback_server import app
    paths = {getattr(route, "path", None): route.methods for route in app.routes}
    assert paths["/api/v1/photoshoot/creative-director/context"] == {"GET"}
    for action in ("inspiration", "selection", "guidance", "recommendation", "direct-recommendation", "approve", "choose-another", "planning-mode", "target-shot-count", "session-plan"):
        assert paths[f"/api/v1/photoshoot/creative-director/{action}"] == {"POST"}
    assert paths["/api/v1/photoshoot/creative-director/session-plan/approve"] == {"POST"}
    assert paths["/api/v1/photoshoot/auto-run/runtime"] == {"GET"}
    for action in ("start", "pause", "resume", "stop", "retry"):
        assert paths[f"/api/v1/photoshoot/auto-run/{action}"] == {"POST"}
    assert paths["/api/v1/photoshoot/curation"] == {"GET"}
    assert paths["/api/v1/photoshoot/curation/confirm"] == {"POST"}
    assert paths["/api/v1/photoshoot/creative-director/session-plan/develop"] == {"POST"}
    assert paths["/api/v1/photoshoot/creative-director/session-plan/advance"] == {"POST"}


def test_full_session_plan_generation_approve_develop_and_advance(monkeypatch):
    session = replace(_session(), creative_mode="explicit", target_shot_count=27, creative_continuity={
        **_session().creative_continuity, "current_shot_image_id": "seed-1", "planning_mode": "full_plan", "plan_frame_count": 4,
    })
    plan = tuple(
        {
            "shot_number": index,
            "title": f"Shot {index}",
            "creative_direction": f"Direction {index}",
            "reasoning": "Arc",
            "emotion": "Flirty",
            "camera_framing": "Medium",
            "lighting": "Soft",
            "pose_composition": "Seated",
            "continuity_notes": "Keep bed",
            "status": "current" if index == 1 else "pending",
        }
        for index in range(1, 5)
    )
    queue, library, director = Mock(), Mock(), Mock()
    queue.get_session.return_value = session
    queue.update_session_settings.return_value = session
    queue.requests_for_session.return_value = (
        SimpleNamespace(status="approved", prompt_text="Seed", metadata={"generated_image_ids": ("seed-1",), "is_seed_image": True}),
    )
    library.get.return_value = _record("seed-1")
    director.plan_full_photoshoot_session.return_value = plan
    service = PhotoshootCreativeDirectorWorkflowService(queue=queue, library=library, creative_director=director)
    monkeypatch.setattr(service, "_image_bytes", lambda _: (b"seed", "image/png"))

    generated = service.generate_session_plan(
        creator_profile_id=7, session_id="session-1", creative_mode="explicit",
        creator_guidance="Slow tease", continuity_locks={"location": True}, plan_frame_count=4,
        target_shot_count=27,
    )
    assert generated["plan_frame_count"] == 4
    assert len(generated["session_plan"]) == 4
    assert generated["session_plan_approved"] is False
    director.plan_full_photoshoot_session.assert_called_once()
    assert director.plan_full_photoshoot_session.call_args.kwargs["frame_count"] == 4
    planner_context = director.plan_full_photoshoot_session.call_args.kwargs["session_context"]
    assert planner_context["current_shot"] == 1
    assert planner_context["target_shot_count"] == 27
    assert planner_context["remaining_shots"] == 26

    approved_session = replace(session, creative_continuity={
        **session.creative_continuity, "session_plan": list(plan), "session_plan_index": 0, "session_plan_approved": False, "planning_mode": "full_plan",
    })
    queue.get_session.return_value = approved_session
    approved = service.approve_session_plan(creator_profile_id=7, session_id="session-1")
    assert approved["session_plan_approved"] is True
    assert approved["session_plan"][0]["status"] == "current"

    ready_session = replace(session, creative_continuity={
        **session.creative_continuity,
        "session_plan": list(approved["session_plan"]),
        "session_plan_index": 0,
        "session_plan_approved": True,
        "planning_mode": "full_plan",
    })
    queue.get_session.return_value = ready_session
    recommendation = service.develop_planned_shot(creator_profile_id=7, session_id="session-1")
    assert recommendation["title"] == "Shot 1"
    assert recommendation["creative_direction"] == "Direction 1"
    queue.record_pending_recommendation.assert_called_once()

    advanced_session = replace(session, creative_continuity={
        **session.creative_continuity,
        "session_plan": list(approved["session_plan"]),
        "session_plan_index": 0,
        "session_plan_approved": True,
        "planning_mode": "full_plan",
    })
    queue.get_session.return_value = advanced_session
    advanced = service.advance_session_plan(creator_profile_id=7, session_id="session-1")
    assert advanced["session_plan_index"] == 1
    assert advanced["session_plan_complete"] is False
    assert advanced["next_planned_shot"]["title"] == "Shot 2"


def test_creator_guidance_persists_without_invoking_ai():
    queue, director = Mock(), Mock()
    queue.get_session.return_value = _session()
    result = PhotoshootCreativeDirectorWorkflowService(queue=queue, library=Mock(), creative_director=director).save_guidance(
        creator_profile_id=7, session_id="session-1", creator_guidance="Try more varied camera angles.",
    )
    assert result["creator_guidance"] == "Try more varied camera angles."
    queue.update_session_settings.assert_called_once_with(
        "session-1", creator_guidance="Try more varied camera angles.",
        grok_guidance="Try more varied camera angles.",
    )
    director.assert_not_called()


def test_creative_director_endpoints_delegate_without_ai_logic(monkeypatch):
    workflow = Mock()
    workflow.inspiration.return_value = {"ideas": ["One"], "selected_inspiration": "One", "creative_hint": "One"}
    workflow.recommendation.return_value = {"title": "Next"}
    workflow.approve.return_value = {"prompt": "Canonical", "workflow_stage": "direction_approved"}
    monkeypatch.setattr(api, "_creator_profile_id_required", lambda: 7)
    monkeypatch.setattr(api, "PhotoshootCreativeDirectorWorkflowService", lambda: workflow)
    locks = api.ContinuitySettingsResponse(location=True, wardrobe=True, lighting=True, hairstyle=True, makeup=True, camera_style=True)
    inspiration = api.creative_director_inspiration(api.InspirationRequest(
        session_id="session-1", creative_mode="safe", creator_guidance="Studio",
        provider_context="Flux", continuity_locks=locks,
    ))
    recommendation = api.creative_director_recommendation(api.CreativeDirectorInputRequest(
        session_id="session-1", creative_mode="premium", creator_guidance="Studio",
        continuity_locks=locks,
    ))
    approval = api.creative_director_approve(api.CreativeDirectorSessionRequest(session_id="session-1"))
    assert inspiration["ideas"] == ["One"]
    assert recommendation["title"] == "Next"
    assert approval["prompt"] == "Canonical"
    workflow.inspiration.assert_called_once()
    workflow.recommendation.assert_called_once()
    workflow.approve.assert_called_once_with(creator_profile_id=7, session_id="session-1")


def test_canonical_planner_mode_mapping_preserves_safe_premium_and_explicit():
    for creative_mode, expected_planner_mode in (
        ("safe", "photoshoot_safe"),
        ("premium", "photoshoot_premium"),
        ("explicit", "photoshoot_explicit"),
    ):
        session = _session()
        session = SimpleNamespace(**{**session.__dict__, "creative_mode": creative_mode, "creative_continuity": {
            **session.creative_continuity, "current_direction": {"title": "Next", "creative_direction": "Continue"},
        }})
        queue, library, director = Mock(), Mock(), Mock()
        queue.get_session.return_value = session
        queue.requests_for_session.return_value = ()
        library.get.return_value = _record("seed-1")
        director.plan_prompts.return_value = SimpleNamespace(prompts=("Canonical",))
        PhotoshootCreativeDirectorWorkflowService(queue=queue, library=library, creative_director=director).approve(
            creator_profile_id=7, session_id="session-1",
        )
        assert director.plan_prompts.call_args.kwargs["mode"] == expected_planner_mode
