import inspect
from types import SimpleNamespace

from app.api import photoshoot as api
from app.services.background_operation_worker_service import BackgroundOperationWorkerService
from app.services.photoshoot_background_executor import PhotoshootBackgroundExecutor
from app.models.generation_engine import GenerationStatus


def test_operator_generation_endpoint_has_no_fastapi_background_task_parameter():
    parameters = inspect.signature(api.generate_manual_photoshoot).parameters
    assert set(parameters) == {"request"}
    assert set(inspect.signature(api.regenerate_manual_candidate).parameters) == {"request"}


def test_photoshoot_executor_is_registered_with_shared_worker():
    worker = BackgroundOperationWorkerService(
        worker_instance_id="test", operations=SimpleNamespace())
    assert isinstance(worker.executors["photoshoot_generation"], PhotoshootBackgroundExecutor)


def test_create_operation_persists_open_ended_request_snapshot(monkeypatch):
    captured = {}
    operation = SimpleNamespace(operation_id="operation-1")

    class Operations:
        def create(self, **values):
            captured.update(values)
            return operation, True

        def progress(self, *args, **kwargs):
            captured["progress"] = kwargs

    monkeypatch.setattr(api, "BackgroundOperationService", lambda: Operations())
    monkeypatch.setattr(api, "_current_account_id", lambda: 7)
    monkeypatch.setattr(api, "PhotoshootQueueService", lambda: SimpleNamespace(
        requests_for_session=lambda _session_id: [SimpleNamespace(status="approved")]))
    session = SimpleNamespace(
        session_id="session-1", target_shot_count=0, provider_id="seedream-5.0",
        creative_continuity={"planning_mode": "frame_by_frame", "seed_image_id": "seed-1"},
    )
    shot = SimpleNamespace(request_id="request-2", sequence_index=2, metadata={})
    job = SimpleNamespace(job_id="job-2")

    result = api._create_photoshoot_operation(
        creator_profile_id=11, session=session, shot=shot, job=job,
        request_payload={"prompt": "next shot", "session_direction": "continue naturally"},
    )

    assert result is operation
    assert captured["executor_key"] == "photoshoot_generation"
    assert captured["idempotency_key"] == "photoshoot-generation:11:session-1:request-2"
    assert captured["metadata"]["targetShotCount"] == 0
    assert captured["metadata"]["openEnded"] is True
    assert captured["metadata"]["request"]["prompt"] == "next shot"
    assert captured["progress"]["result_reference"] == "job-2"


def test_manual_generation_conflicts_with_nonterminal_auto_run(monkeypatch):
    monkeypatch.setattr(api, "PhotoshootAutoRunRepository", lambda: SimpleNamespace(
        get=lambda _session_id: SimpleNamespace(state="GENERATING")))
    try:
        api._ensure_manual_generation_available(1, "session-1")
    except ValueError as error:
        assert "Auto Run" in str(error)
    else:
        raise AssertionError("Expected Auto Run ownership conflict")


def test_executor_accepts_generation_progress_keywords_and_completes(monkeypatch):
    progress = []
    succeeded = []
    job = SimpleNamespace(job_id="job-2")
    request = SimpleNamespace(
        request_id="request-2", session_id="session-1", generation_job_id="job-2")

    class Manual:
        queue = SimpleNamespace(get_request=lambda _request_id: request)

        def session_for_creator(self, session_id, creator_profile_id):
            assert (session_id, creator_profile_id) == ("session-1", 11)

        def execute(self, *, session_id, job, progress_callback):
            progress_callback(
                current=0, total=1, percent=42, status="running",
                message="Provider generation is active", jobId=job.job_id,
            )
            return {
                "status": "succeeded", "job_id": job.job_id,
                "request_id": "request-2", "image_ids": ["image-2"],
            }

    monkeypatch.setattr(
        "app.services.photoshoot_manual_service.PhotoshootManualService", Manual)
    monkeypatch.setattr(
        "app.services.generation_engine_service.GenerationEngineService",
        lambda: SimpleNamespace(get_job=lambda _job_id: job),
    )
    operations = SimpleNamespace(
        repository=SimpleNamespace(renew_lease=lambda *_args, **_kwargs: True),
        progress=lambda _operation_id, **values: progress.append(values),
        succeed=lambda _operation_id, **values: succeeded.append(values),
        fail=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Executor unexpectedly failed")),
    )
    operation = SimpleNamespace(
        operation_id="operation-2", subject_id="session-1", creator_profile_id=11,
        result_reference="job-2", attempt_count=1,
        metadata={"photoshootSessionId": "session-1", "requestId": "request-2",
                  "generationJobId": "job-2"},
    )

    PhotoshootBackgroundExecutor().execute(
        operation, operations, worker_id="worker-1")

    assert any(item["percent"] == 42 and item["stage"] == "GENERATING"
               for item in progress)
    assert progress[-1]["stage"] == "READY_FOR_REVIEW"
    assert succeeded == [{
        "result_reference": "job-2",
        "metadata": {"requestId": "request-2", "imageIds": ["image-2"]},
        "message": "Photoshoot image is ready for review",
    }]


def test_executor_preserves_accepted_provider_task_as_waiting_external(monkeypatch):
    transitions = []
    job = SimpleNamespace(job_id="job-2", status=GenerationStatus.QUEUED.value)
    request = SimpleNamespace(request_id="request-2", session_id="session-1", generation_job_id="job-2")

    class Manual:
        queue = SimpleNamespace(get_request=lambda _request_id: request)
        def session_for_creator(self, session_id, creator_profile_id):
            return None
        def execute(self, **_kwargs):
            return {"status": "provider_pending", "job_id": "job-2",
                    "provider_request_id": "provider-task-2"}

    monkeypatch.setattr("app.services.photoshoot_manual_service.PhotoshootManualService", Manual)
    monkeypatch.setattr("app.services.generation_engine_service.GenerationEngineService",
                        lambda: SimpleNamespace(get_job=lambda _job_id: job))
    operations = SimpleNamespace(
        repository=SimpleNamespace(
            renew_lease=lambda *_args, **_kwargs: True,
            transition=lambda *args, **kwargs: transitions.append((args, kwargs)),
        ),
        progress=lambda *_args, **_kwargs: None,
        fail=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must remain recoverable")),
    )
    operation = SimpleNamespace(
        operation_id="operation-2", subject_id="session-1", creator_profile_id=11,
        result_reference="job-2", attempt_count=1,
        metadata={"photoshootSessionId": "session-1", "requestId": "request-2",
                  "generationJobId": "job-2"},
    )

    PhotoshootBackgroundExecutor().execute(operation, operations, worker_id="worker-1")

    assert transitions[0][0][1] == "WAITING_EXTERNAL"
    assert transitions[0][1]["stage"] == "WAITING_PROVIDER"
    assert transitions[0][1]["metadata"]["providerRequestId"] == "provider-task-2"


def test_reclaimed_waiting_operation_reconciles_without_generation_submission(monkeypatch):
    succeeded = []
    job = SimpleNamespace(job_id="job-2", status=GenerationStatus.RUNNING.value)
    request = SimpleNamespace(request_id="request-2", session_id="session-1", generation_job_id="job-2")

    class Manual:
        queue = SimpleNamespace(get_request=lambda _request_id: request)
        def session_for_creator(self, session_id, creator_profile_id):
            return None
        def execute(self, **_kwargs):
            raise AssertionError("recovery must not submit generation")
        def reconcile_provider_task(self, **_kwargs):
            return {"status": "succeeded", "job_id": "job-2", "request_id": "request-2",
                    "image_ids": ["image-2"], "provider_request_id": "provider-task-2"}

    monkeypatch.setattr("app.services.photoshoot_manual_service.PhotoshootManualService", Manual)
    monkeypatch.setattr("app.services.generation_engine_service.GenerationEngineService",
                        lambda: SimpleNamespace(get_job=lambda _job_id: job))
    operations = SimpleNamespace(
        repository=SimpleNamespace(renew_lease=lambda *_args, **_kwargs: True),
        progress=lambda *_args, **_kwargs: None,
        succeed=lambda _operation_id, **kwargs: succeeded.append(kwargs),
        fail=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must reconcile")),
    )
    operation = SimpleNamespace(
        operation_id="operation-2", subject_id="session-1", creator_profile_id=11,
        result_reference="job-2", attempt_count=2,
        metadata={"photoshootSessionId": "session-1", "requestId": "request-2",
                  "generationJobId": "job-2"},
    )

    PhotoshootBackgroundExecutor().execute(operation, operations, worker_id="worker-1")

    assert succeeded[0]["result_reference"] == "job-2"
    assert succeeded[0]["metadata"]["imageIds"] == ["image-2"]


def test_reclaimed_succeeded_job_resolves_existing_candidate_without_resubmission(monkeypatch):
    succeeded = []
    candidate = SimpleNamespace(image_id="existing-image")
    job = SimpleNamespace(job_id="job-2", status=GenerationStatus.SUCCEEDED.value, result=object())
    request = SimpleNamespace(request_id="request-2", session_id="session-1", generation_job_id="job-2")

    class Manual:
        queue = SimpleNamespace(get_request=lambda _request_id: request)
        def session_for_creator(self, *_args): return None
        def execute(self, **_kwargs): raise AssertionError("provider must not be submitted")
        def reconcile_local_completion(self, *, session_id, request_id):
            assert (session_id, request_id) == ("session-1", "request-2")
            return {"status": "succeeded", "job_id": "job-2", "request_id": "request-2",
                    "image_ids": [candidate.image_id]}

    monkeypatch.setattr("app.services.photoshoot_manual_service.PhotoshootManualService", Manual)
    monkeypatch.setattr("app.services.generation_engine_service.GenerationEngineService",
                        lambda: SimpleNamespace(get_job=lambda _job_id: job))
    operations = SimpleNamespace(
        progress=lambda *_args, **_kwargs: None,
        succeed=lambda _operation_id, **kwargs: succeeded.append(kwargs),
        fail=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must recover")),
    )
    operation = SimpleNamespace(operation_id="operation-2", subject_id="session-1",
        creator_profile_id=11, result_reference="job-2", attempt_count=2,
        metadata={"photoshootSessionId":"session-1","requestId":"request-2","generationJobId":"job-2"})
    PhotoshootBackgroundExecutor().execute(operation, operations, worker_id="worker-1")
    assert succeeded[0]["metadata"]["imageIds"] == ["existing-image"]


def test_generate_reconnects_to_existing_operation_without_creating_provider_work(monkeypatch):
    existing = SimpleNamespace(
        operation_id="operation-existing", status="RUNNING",
        result_reference="job-existing",
        metadata={"requestId": "request-existing", "generationJobId": "job-existing"},
    )
    monkeypatch.setattr(api, "_creator_profile_id_required", lambda: 11)
    monkeypatch.setattr(api, "_active_manual_operation", lambda *_args: existing)

    class Manual:
        def create_manual_request(self, **_values):
            raise AssertionError("Duplicate request reached Photoshoot services")

    monkeypatch.setattr(api, "PhotoshootManualService", Manual)
    request = api.ManualGenerateRequest(
        session_id="session-1", provider_id="seedream-5.0", creative_mode="safe",
        prompt="next shot", continuity_settings=api.ContinuitySettingsResponse(
            location=True, wardrobe=True, lighting=True, hairstyle=True,
            makeup=True, camera_style=True,
        ),
    )

    result = api.generate_manual_photoshoot(request)

    assert result == {
        "success": True, "session_id": "session-1",
        "request_id": "request-existing", "generation_job_id": "job-existing",
        "operation_id": "operation-existing", "status": "running",
    }
