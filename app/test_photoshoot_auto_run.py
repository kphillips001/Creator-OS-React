from types import SimpleNamespace

from app.models.photoshoot_auto_run import PhotoshootAutoRun
from app.services.photoshoot_auto_run_service import PhotoshootAutoRunService
from app.services.photoshoot_auto_run_worker_service import PhotoshootAutoRunWorkerService


class FakeRepository:
    def __init__(self, run):
        self.run = run
        self.transitions = []

    def get(self, _session_id): return self.run
    def claim_next(self, _worker_id): return self.run
    def transition(self, session_id, state, **fields):
        self.transitions.append((session_id, state, fields))
        return self.run


class FakeQueue:
    def __init__(self, session, requests):
        self.session = session
        self.requests = requests

    def get_session(self, _): return self.session
    def requests_for_session(self, _): return tuple(self.requests)
    def get_request(self, request_id): return next(item for item in self.requests if item.request_id == request_id)


def session(index=4):
    plan = tuple({"shot_number": number + 1, "title": f"Frame {number + 1}",
                  "status": "completed" if number < index else "current" if number == index else "pending"}
                 for number in range(8))
    return SimpleNamespace(session_id="session-1", creator_profile_id=2, status="running", provider_id="provider",
                           creative_mode="premium", updated_at="now",
                           creative_continuity={"session_plan": plan, "session_plan_index": index,
                                                "session_plan_approved": True})


def test_runtime_projection_counts_plan_frames_not_seed_requests():
    request = SimpleNamespace(request_id="request-5", status="awaiting_review", generation_job_id="job-5")
    run = PhotoshootAutoRun("session-1", "WAITING_FOR_REVIEW", 4, 8, current_request_id="request-5",
                            auto_approve_enabled=False, review_mode="MANUAL_REVIEW")
    repository = FakeRepository(run)
    queue = FakeQueue(session(), [SimpleNamespace(request_id="seed", status="approved"), request])
    manual = SimpleNamespace(session_for_creator=lambda *_: queue.session, _candidate_record=lambda _: None)
    runtime = PhotoshootAutoRunService(repository=repository, queue=queue, manual=manual).runtime(
        creator_profile_id=2, session_id="session-1")
    assert runtime["completed_frames"] == 4
    assert runtime["total_frames"] == 8
    assert runtime["progress_percent"] == 50
    assert runtime["current_frame_number"] == 5
    assert runtime["current_frame_title"] == "Frame 5"
    assert runtime["waiting_for_review"] is True
    assert runtime["spinner_active"] is False


def test_worker_adopts_awaiting_review_candidate_without_generating_duplicate():
    request = SimpleNamespace(request_id="request-5", status="awaiting_review", generation_job_id="job-5")
    run = PhotoshootAutoRun("session-1", "READY", 4, 8, current_request_id=None, auto_approve_enabled=True)
    repository = FakeRepository(run)
    queue = FakeQueue(session(), [request])
    manual = SimpleNamespace()
    runtime = SimpleNamespace(queue=queue, manual=manual, _active_request=lambda _: request)
    result = PhotoshootAutoRunWorkerService(worker_instance_id="worker-1", repository=repository, runtime=runtime).process_one()
    assert result["status"] == "WAITING_FOR_REVIEW"
    assert repository.transitions[-1][2]["current_request_id"] == "request-5"


def test_advancing_checkpoint_does_not_advance_session_twice():
    request = SimpleNamespace(request_id="request-5", status="approved", generation_job_id="job-5")
    run = PhotoshootAutoRun("session-1", "ADVANCING", 4, 8, current_request_id="request-5")
    repository = FakeRepository(run)
    queue = FakeQueue(session(index=5), [request])
    director = SimpleNamespace(advance_session_plan=lambda **_: (_ for _ in ()).throw(AssertionError("double advance")))
    runtime = SimpleNamespace(queue=queue, manual=SimpleNamespace(), director=director, _active_request=lambda _: None)
    result = PhotoshootAutoRunWorkerService(worker_instance_id="worker-1", repository=repository, runtime=runtime).process_one()
    assert result["status"] == "PREPARING"
    assert repository.transitions[-1][2]["current_plan_index"] == 5


def test_resumed_run_adopts_already_approved_checkpoint_before_preparing():
    request = SimpleNamespace(request_id="request-5", status="approved", generation_job_id="job-5")
    run = PhotoshootAutoRun("session-1", "READY", 4, 8, current_request_id="request-5")
    repository = FakeRepository(run)
    queue = FakeQueue(session(index=4), [request])
    runtime = SimpleNamespace(queue=queue, manual=SimpleNamespace(), director=SimpleNamespace(),
                              _active_request=lambda _: None)
    result = PhotoshootAutoRunWorkerService(worker_instance_id="worker-1", repository=repository, runtime=runtime).process_one()
    assert result["status"] == "ADVANCING"
    assert repository.transitions[-1][2]["current_request_id"] == "request-5"
