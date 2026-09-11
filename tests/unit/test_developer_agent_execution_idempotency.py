import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.services.developer_agent_execution_service import DeveloperAgentExecutionService


class AtomicRepository:
    def __init__(self):
        self.task_id=uuid4();self.execution=None;self.reservations=0
        self.lock=threading.Lock();self.lookup_barrier=threading.Barrier(2)
    def get_task(self, task_id):
        return {"task_id":task_id,"status":"APPROVED","approved_at":datetime.now(timezone.utc),
            "repository_path":r"C:\Creator-OS-React","expected_branch":"react-migration",
            "issue_identifier":"isolated"}
    def latest_execution_for_task(self, task_id):
        self.lookup_barrier.wait(timeout=2)
        return None
    def create_or_get_execution(self, **values):
        with self.lock:
            if self.execution:return self.execution,True
            self.reservations+=1
            self.execution={"execution_id":uuid4(),"task_id":values["task_id"],"status":"QUEUED"}
            return self.execution,False
    def add_event(self,*_args,**_kwargs): return {}
    def create_notification(self,**_kwargs): return {}


class CapturingExecutor:
    def __init__(self): self.submissions=0
    def submit(self,*_args,**_kwargs): self.submissions+=1;return object()


def test_concurrent_approved_submits_reserve_and_dispatch_exactly_once(monkeypatch):
    repository=AtomicRepository();subject=DeveloperAgentExecutionService(repository=repository,repository_path=Path(r"C:\Creator-OS-React"))
    executor=CapturingExecutor();subject._executor=executor
    monkeypatch.setattr(subject,"_validate_repository",lambda task:None)
    monkeypatch.setattr(subject,"readiness",lambda:{"overallReadiness":"READY","reason":None})
    monkeypatch.setattr(subject,"_git",lambda *_args:"")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:subject.submit(repository.task_id),range(2)))
    assert results[0]["execution_id"] == results[1]["execution_id"]
    assert repository.reservations == 1
    assert executor.submissions == 1
