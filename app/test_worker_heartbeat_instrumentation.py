from app.outreach_worker import run_outreach_worker
from app.services.delayed_message_worker_loop_service import DelayedMessageWorkerLoopService
from app.services.mass_ppv_worker_loop_service import MassPPVWorkerLoopService
from app.services.wall_worker_loop_service import WallWorkerLoopService


class Recorder:
    def __init__(self): self.calls = []
    def register_startup(self): self.calls.append("startup")
    def record_poll(self): self.calls.append("poll")
    def record_success(self, *, idle=False): self.calls.append(("success", idle))
    def record_failure(self, error): self.calls.append(("failure", str(error)))
    def record_stopping(self): self.calls.append("stopping")
    def record_shutdown(self): self.calls.append("shutdown")
    def heartbeat(self, *, idle=False): self.calls.append(("heartbeat", idle))


class DelayedWorker:
    def process_due_messages(self): return []
class MassWorker:
    def process_all_available_queue(self, **kwargs): return []
class WallWorker:
    def process_wall_queue(self, **kwargs): return {"processed_count": 0}
class OutreachRunner:
    def run_outreach_cycle(self, **kwargs): return {"candidate_count": 0, "eligible_count": 0, "processed_count": 0}


def assert_cycle(recorder):
    assert recorder.calls == ["startup", "poll", ("success", True), "stopping", "shutdown"]


def test_isolated_worker_loops_record_cycles_without_external_execution():
    delayed = Recorder(); DelayedMessageWorkerLoopService(heartbeat_service=delayed, worker_service=DelayedWorker()).start_loop(max_cycles=1); assert_cycle(delayed)
    mass = Recorder(); MassPPVWorkerLoopService(heartbeat_service=mass, worker_service=MassWorker()).run_loop(max_cycles=1); assert_cycle(mass)
    wall = Recorder(); WallWorkerLoopService(heartbeat_service=wall, worker_service=WallWorker()).run_forever(max_cycles=1); assert_cycle(wall)
    outreach = Recorder(); run_outreach_worker(heartbeat_service=outreach, runner=OutreachRunner(), max_cycles=1); assert_cycle(outreach)


def test_fastapi_lifespan_registers_periodic_heartbeat_and_shutdown(monkeypatch):
    from fastapi.testclient import TestClient
    from app import fanvue_callback_server as server
    recorder = Recorder()
    monkeypatch.setattr(server, "WorkerHeartbeatService", lambda **kwargs: recorder)
    with TestClient(server.app) as client:
        assert client.get("/callback").status_code == 200
    assert recorder.calls[0] == "startup"
    assert ("heartbeat", False) in recorder.calls
    assert recorder.calls[-2:] == ["stopping", "shutdown"]
