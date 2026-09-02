from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.generation_engine import GenerationStatus
from app.api import photoshoot as photoshoot_api
from app.services.photoshoot_manual_service import PhotoshootManualService
from app.services.photoshoot_queue_service import PhotoshootPreparationRequired, PhotoshootQueueService


def test_atomic_queue_replace_retries_transient_windows_collision(tmp_path, monkeypatch):
    path = tmp_path / "photoshoot_requests.json"
    real_replace = __import__("os").replace
    attempts = []

    def replace_with_collision(source, destination):
        attempts.append((source, destination))
        if len(attempts) == 1:
            error = PermissionError("sharing violation")
            error.winerror = 5
            raise error
        return real_replace(source, destination)

    monkeypatch.setattr("app.services.photoshoot_queue_service.os.replace", replace_with_collision)
    monkeypatch.setattr("app.services.photoshoot_queue_service.time.sleep", lambda _delay: None)

    PhotoshootQueueService._write_json(path, [{"request_id": "request-1"}])

    assert len(attempts) == 2
    assert PhotoshootQueueService._read_json(path, []) == [{"request_id": "request-1"}]


def test_replace_retry_window_recovers_after_more_than_200ms_of_collisions(tmp_path, monkeypatch):
    path = tmp_path / "photoshoot_requests.json"
    real_replace = __import__("os").replace
    attempts = 0
    delays = []

    def replace_after_three_collisions(source, destination):
        nonlocal attempts
        attempts += 1
        if attempts <= 3:
            error = PermissionError("sharing violation")
            error.winerror = 32
            raise error
        return real_replace(source, destination)

    monkeypatch.setattr("app.services.photoshoot_queue_service.os.replace", replace_after_three_collisions)
    monkeypatch.setattr("app.services.photoshoot_queue_service.time.sleep", delays.append)
    monkeypatch.setattr("app.services.photoshoot_queue_service.random.uniform", lambda *_args: 0)

    PhotoshootQueueService._write_json(path, [{"request_id": "request-1"}])

    assert attempts == 4
    assert delays == [0.05, 0.1, 0.2]
    assert sum(delays) > 0.2


def test_genuine_nonwritable_access_failure_is_not_retried(tmp_path, monkeypatch):
    path = tmp_path / "photoshoot_requests.json"
    attempts = 0

    def permission_failure(_source, _destination):
        nonlocal attempts
        attempts += 1
        error = PermissionError("access denied")
        error.winerror = 5
        raise error

    monkeypatch.setattr("app.services.photoshoot_queue_service.os.replace", permission_failure)
    monkeypatch.setattr("app.services.photoshoot_queue_service.os.access", lambda *_args: False)

    with pytest.raises(PermissionError):
        PhotoshootQueueService._write_json(path, [])

    assert attempts == 2  # canonical replace plus recovery-file preservation attempt


def test_exhausted_replace_preserves_valid_recovery_copy(tmp_path, monkeypatch):
    path = tmp_path / "photoshoot_requests.json"
    path.write_text("[]", encoding="utf-8")

    real_replace = __import__("os").replace
    def always_fail(source, destination):
        if Path(destination) == path:
            error = PermissionError("sharing violation")
            error.winerror = 5
            raise error
        return real_replace(source, destination)

    monkeypatch.setattr("app.services.photoshoot_queue_service.os.replace", always_fail)
    monkeypatch.setattr("app.services.photoshoot_queue_service.time.sleep", lambda _delay: None)

    with pytest.raises(PermissionError):
        PhotoshootQueueService._write_json(path, [{"request_id": "request-new"}])

    recovery_files = list(tmp_path.glob(".photoshoot_requests.json.*.recovery"))
    assert len(recovery_files) == 1
    assert "request-new" in recovery_files[0].read_text(encoding="utf-8")
    assert path.read_text(encoding="utf-8") == "[]"
    assert PhotoshootQueueService._read_json(path, []) == [{"request_id": "request-new"}]


def test_local_first_reconciliation_reuses_matching_record_without_provider_work():
    request = SimpleNamespace(
        request_id="request-1", session_id="session-1", generation_job_id="job-1",
        status="finalization_required", metadata={"finalization_required": True},
    )
    session = SimpleNamespace(session_id="session-1")
    job = SimpleNamespace(job_id="job-1", status=GenerationStatus.SUCCEEDED.value, result=object())
    record = SimpleNamespace(
        image_id="image-1", generation_job_id="job-1",
        output_reference="https://cdn.test/image-1.png",
        photoshoot_session_id="session-1", photoshoot_request_id="request-1",
        prompt_metadata={}, generation_metadata={},
    )
    completed = SimpleNamespace(request_id="request-1")
    calls = []
    queue = SimpleNamespace(
        get_session=lambda _session_id: session,
        requests_for_session=lambda _session_id: (request,),
    )
    engine = SimpleNamespace(get_job=lambda _job_id: job)
    library = SimpleNamespace(list_records=lambda: (record,))
    service = PhotoshootManualService(queue=queue, engine=engine, library=library)
    service.synchronize_completed = lambda **values: calls.append(values) or completed

    first = service.reconcile_local_completion(session_id="session-1", request_id="request-1")
    second = service.reconcile_local_completion(session_id="session-1", request_id="request-1")

    assert first["image_ids"] == ["image-1"]
    assert second["image_ids"] == ["image-1"]
    assert len(calls) == 2
    assert all(call["records"] == (record,) for call in calls)


def test_local_first_reconciliation_rejects_mismatched_photoshoot_lineage():
    request = SimpleNamespace(
        request_id="request-1", session_id="session-1", generation_job_id="job-1",
        status="finalization_required", metadata={"finalization_required": True},
    )
    record = SimpleNamespace(
        image_id="image-1", generation_job_id="job-1",
        output_reference="https://cdn.test/image-1.png",
        photoshoot_session_id="other-session", photoshoot_request_id="request-1",
        prompt_metadata={}, generation_metadata={},
    )
    service = PhotoshootManualService(
        queue=SimpleNamespace(
            get_session=lambda _session_id: SimpleNamespace(session_id="session-1"),
            requests_for_session=lambda _session_id: (request,),
        ),
        engine=SimpleNamespace(get_job=lambda _job_id: SimpleNamespace(
            job_id="job-1", status=GenerationStatus.SUCCEEDED.value, result=object())),
        library=SimpleNamespace(list_records=lambda: (record,)),
    )

    with pytest.raises(RuntimeError, match="lineage"):
        service.reconcile_local_completion(session_id="session-1", request_id="request-1")


def test_retry_finalization_endpoint_uses_only_local_reconciliation(monkeypatch):
    calls = []

    class Manual:
        def session_for_creator(self, session_id, creator_profile_id):
            calls.append(("session", session_id, creator_profile_id))

        def reconcile_local_completion(self, **values):
            calls.append(("local", values))
            return {"status": "succeeded", "job_id": "job-1", "request_id": "request-1",
                    "image_ids": ["image-1"]}

        def reconcile_provider_task(self, **_values):
            raise AssertionError("targeted finalization must not poll the provider")

    class Operations:
        def list(self, **_values):
            return ()

    monkeypatch.setattr(photoshoot_api, "PhotoshootManualService", Manual)
    monkeypatch.setattr(photoshoot_api, "BackgroundOperationService", Operations)
    monkeypatch.setattr(photoshoot_api, "_creator_profile_id_required", lambda: 7)

    result = photoshoot_api.retry_candidate_finalization(
        photoshoot_api.FinalizeCandidateRequest(session_id="session-1", request_id="request-1"))

    assert result["status"] == "succeeded"
    assert result["image_ids"] == ["image-1"]
    assert calls == [
        ("session", "session-1", 7),
        ("local", {"session_id": "session-1", "request_id": "request-1"}),
    ]


def test_pre_provider_queue_persistence_failure_creates_recovery_state_without_submission(tmp_path, monkeypatch):
    service = PhotoshootQueueService(storage_dir=tmp_path)
    session = service.create_session(creator_profile_id=7, prompt_plans=[SimpleNamespace(
        plan_id="plan-1", prompt_text="shot", creative_mode="safe", reference_asset_id=1,
        creative_tags=(), prompt_metadata={},
    )])
    queued_jobs = []

    class Engine:
        def queue_prompt_plan(self, **_values):
            job = SimpleNamespace(job_id="job-prepared")
            queued_jobs.append(job)
            return job

    original_replace = service._replace_request
    calls = 0

    def fail_once(updated):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise PermissionError("queue persistence unavailable")
        return original_replace(updated)

    monkeypatch.setattr(service, "_replace_request", fail_once)

    with pytest.raises(PhotoshootPreparationRequired):
        service.queue_next_prompt(session_id=session.session_id, generation_engine=Engine())

    request = service.requests_for_session(session.session_id)[0]
    assert len(queued_jobs) == 1
    assert request.status == "preparation_recovery_required"
    assert request.generation_job_id == "job-prepared"
    assert request.metadata["preparation_recovery_required"] is True
