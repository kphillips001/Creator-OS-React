from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.services.ai_training_control_service import AiTrainingControlError
from app.services.ai_training_work_queue_service import AiTrainingWorkQueueService


NOW = datetime.now(timezone.utc)


class QueueRepository:
    def __init__(self, status="REQUIRES_IMPLEMENTATION"):
        self.row = {"work_item_id": uuid4(), "creator_profile_id": 7, "fanvue_account_id": 8,
                    "scope": "GLOBAL", "customer_fanvue_user_id": None,
                    "original_request_text": "Before answering whether Ava has a content type, check actual current inventory.",
                    "status": status, "classification": "DYNAMIC_AUTHORITY_REQUIRED",
                    "classification_rationale": "Dynamic inventory truth requires code-backed integration.",
                    "analysis": {}, "linked_instruction_id": None, "linked_future_task_id": None,
                    "created_at": NOW, "updated_at": NOW, "completed_at": None}
    def get(self, *_args, **_kwargs): return self.row
    def update(self, _id, **values):
        values.pop("creator_profile_id"); values.pop("fanvue_account_id")
        self.row.update(values); return self.row


class DeveloperRepository:
    def __init__(self): self.task = None; self.execution = None; self.review = None;self.tasks={};self.executions={}
    def get_task(self, task_id): return self.tasks.get(task_id)
    def get_execution(self, execution_id): return self.executions.get(execution_id)
    def latest_execution_for_task(self, task_id):
        return next((value for value in reversed(list(self.executions.values())) if value["task_id"]==task_id),None)
    def update_review(self, _id, status): self.review = status


class Developer:
    def __init__(self, repository): self.repository=repository; self.created=0; self.submitted=0
    def create_task(self, **values):
        self.created += 1; task_id=uuid4()
        self.repository.task={"task_id":task_id,"status":"AWAITING_APPROVAL",**values}
        self.repository.tasks[task_id]=self.repository.task
        return self.repository.task
    def approve_task(self, _id): self.repository.task["status"]="APPROVED"; return self.repository.task
    def submit(self, task_id):
        self.submitted += 1; execution_id=uuid4()
        self.repository.execution={"execution_id":execution_id,"task_id":task_id,"status":"QUEUED",
            "started_at":None,"completed_at":None,"failure_reason":None,"final_report":None,"review_status":"PENDING"}
        self.repository.executions[execution_id]=self.repository.execution
        return self.repository.execution


class AttemptRepository:
    def __init__(self, queue): self.queue=queue;self.rows=[]
    def prepare(self, work_item_id, *, brief_version, analysis, task_factory, **identity):
        if self.queue.row["status"] not in {"REQUIRES_IMPLEMENTATION","IMPLEMENTATION_FAILED"}:
            raise ValueError("Only implementation-required or failed Queue items can be prepared.")
        task=task_factory(len(self.rows)+1);attempt={"attempt_id":uuid4(),"work_item_id":work_item_id,
            "attempt_number":len(self.rows)+1,"implementation_brief_version":brief_version,
            "developer_agent_task_id":task["task_id"],"developer_agent_execution_id":None,
            "status":"READY_FOR_IMPLEMENTATION","approved_at":None,"started_at":None,
            "completed_at":None,"verified_at":None,"created_at":NOW,"updated_at":NOW}
        self.rows.append(attempt);analysis={**analysis,"implementationAttemptId":str(attempt["attempt_id"]),
            "implementationAttemptNumber":attempt["attempt_number"],"implementationTaskId":str(task["task_id"])}
        analysis.pop("implementationExecutionId",None)
        self.queue.row.update(status="READY_FOR_IMPLEMENTATION",analysis=analysis,linked_future_task_id=task["task_id"])
        return self.queue.row,attempt,task
    def list(self, work_item_id): return list(reversed(self.rows))
    def get(self, attempt_id): return next((row for row in self.rows if row["attempt_id"]==attempt_id),None)
    def attach_execution(self, attempt_id, *, task_id, execution):
        row=self.get(attempt_id)
        if str(execution["task_id"])!=str(task_id) or str(row["developer_agent_task_id"])!=str(task_id):raise ValueError("mismatch")
        row.update(developer_agent_execution_id=execution["execution_id"],status="IMPLEMENTING",approved_at=NOW,started_at=NOW);return row
    def update_from_execution(self, attempt_id, execution):
        row=self.get(attempt_id);row.update(status="NEEDS_VERIFICATION" if execution["status"]=="COMPLETED" else "FAILED",completed_at=execution.get("completed_at") or NOW);return row
    def verify(self, attempt_id, execution_id):
        row=self.get(attempt_id);row.update(status="VERIFIED",verified_at=NOW);return row
    def supersede_prepared(self, attempt_id):
        row=self.get(attempt_id)
        if row and row["status"]=="READY_FOR_IMPLEMENTATION":row["status"]="SUPERSEDED"
        return row


def service(status="REQUIRES_IMPLEMENTATION"):
    queue=QueueRepository(status); developer_repository=DeveloperRepository(); developer=Developer(developer_repository)
    attempts=AttemptRepository(queue)
    return AiTrainingWorkQueueService(repository=queue,training=object(),developer=developer,
        developer_repository=developer_repository,attempt_repository=attempts),queue,developer,developer_repository,attempts


def identity(): return {"creator_profile_id":7,"fanvue_account_id":8}


def test_prepare_is_non_executing_and_builds_bounded_inventory_truth_brief():
    subject,queue,developer,_,_=service()
    result=subject.prepare_implementation(queue.row["work_item_id"],**identity())
    assert result["status"] == "READY_FOR_IMPLEMENTATION"
    assert developer.created == 1 and developer.submitted == 0
    brief=result["analysis"]["implementationBrief"]
    assert "inventory" in brief["whyImplementationIsRequired"].lower()
    assert "Inventory truth" in brief["protectedAuthorities"]
    assert brief["repository"] == r"C:\Creator-OS-React"


@pytest.mark.parametrize("status", ["REJECTED", "READY_TO_APPLY", "IMPLEMENTED"])
def test_non_implementation_classifications_cannot_prepare(status):
    subject,queue,developer,_,_=service(status)
    with pytest.raises(AiTrainingControlError):
        subject.prepare_implementation(queue.row["work_item_id"],**identity())
    assert developer.created == 0


def test_success_stops_at_needs_verification_until_operator_accepts():
    subject,queue,_,developer_repository,_=service()
    subject.prepare_implementation(queue.row["work_item_id"],**identity())
    started=subject.start_implementation(queue.row["work_item_id"],**identity())
    assert started["status"] == "IMPLEMENTING"
    developer_repository.execution.update({"status":"COMPLETED","completed_at":NOW,
        "final_report":{"summary":"Implemented","tests":["focused: passed"]}})
    detail=subject.implementation_detail(queue.row["work_item_id"],**identity())
    assert detail["status"] == "NEEDS_VERIFICATION"
    accepted=subject.verify_implementation(queue.row["work_item_id"],**identity())
    assert accepted["status"] == "IMPLEMENTED"
    assert developer_repository.review == "ACKNOWLEDGED"


@pytest.mark.parametrize("replay_status", [
    "IMPLEMENTING", "NEEDS_VERIFICATION", "IMPLEMENTATION_FAILED", "IMPLEMENTED",
])
def test_start_replay_returns_same_execution_without_dispatch(replay_status):
    subject,queue,developer,developer_repository,_=service()
    subject.prepare_implementation(queue.row["work_item_id"],**identity())
    first=subject.start_implementation(queue.row["work_item_id"],**identity())
    queue.row["status"]=replay_status
    replay=subject.start_implementation(queue.row["work_item_id"],**identity())
    assert replay["implementation"]["execution"]["execution_id"] == developer_repository.execution["execution_id"]
    assert replay["implementation"]["reusedExistingExecution"] is True
    assert developer.submitted == 1
    assert first["analysis"]["implementationExecutionId"] == str(developer_repository.execution["execution_id"])


def test_edited_or_stale_snapshot_cannot_reuse_execution():
    subject,queue,developer,_,_=service()
    subject.prepare_implementation(queue.row["work_item_id"],**identity())
    subject.start_implementation(queue.row["work_item_id"],**identity())
    queue.row["status"]="TODO"
    with pytest.raises(AiTrainingControlError):
        subject.start_implementation(queue.row["work_item_id"],**identity())
    queue.row["status"]="IMPLEMENTING"
    queue.row["analysis"]["implementationBriefVersion"]=999
    with pytest.raises(AiTrainingControlError,match="snapshot"):
        subject.start_implementation(queue.row["work_item_id"],**identity())
    assert developer.submitted == 1


def test_wrong_scope_cannot_resolve_existing_execution():
    subject,queue,developer,_,_=service()
    subject.prepare_implementation(queue.row["work_item_id"],**identity())
    subject.start_implementation(queue.row["work_item_id"],**identity())
    queue.get=lambda *_args,**_kwargs: None
    with pytest.raises(AiTrainingControlError,match="not found"):
        subject.start_implementation(queue.row["work_item_id"],creator_profile_id=99,fanvue_account_id=8)
    assert developer.submitted == 1


def test_retry_preserves_failed_attempt_and_never_projects_old_execution_onto_new_brief():
    subject,queue,developer,developer_repository,attempts=service()
    subject.prepare_implementation(queue.row["work_item_id"],**identity())
    first=subject.start_implementation(queue.row["work_item_id"],**identity())
    first_id=str(first["implementation"]["execution"]["execution_id"])
    developer_repository.execution.update(status="FAILED",completed_at=NOW,failure_reason="Production build failed.")
    failed=subject.implementation_detail(queue.row["work_item_id"],**identity())
    assert failed["status"]=="IMPLEMENTATION_FAILED"
    retry=subject.prepare_implementation(queue.row["work_item_id"],**identity())
    assert retry["implementation"]["execution"] is None
    assert retry["implementation"]["currentAttempt"]["attemptNumber"]==2
    assert retry["implementation"]["currentAttempt"]["executionId"] is None
    assert retry["implementation"]["attempts"][1]["executionId"]==first_id
    second=subject.start_implementation(queue.row["work_item_id"],**identity())
    second_id=str(second["implementation"]["execution"]["execution_id"])
    assert second_id!=first_id and developer.submitted==2
    assert [(value["attemptNumber"],value["executionId"]) for value in second["implementation"]["attempts"]]==[(2,second_id),(1,first_id)]
    assert attempts.rows[0]["status"]=="FAILED"


def test_successful_retry_requires_verification_and_retains_failed_attempt():
    subject,queue,_,developer_repository,attempts=service()
    subject.prepare_implementation(queue.row["work_item_id"],**identity());subject.start_implementation(queue.row["work_item_id"],**identity())
    developer_repository.execution.update(status="FAILED",completed_at=NOW,failure_reason="Failed")
    subject.implementation_detail(queue.row["work_item_id"],**identity());subject.prepare_implementation(queue.row["work_item_id"],**identity());subject.start_implementation(queue.row["work_item_id"],**identity())
    developer_repository.execution.update(status="COMPLETED",completed_at=NOW,final_report={"summary":"Implemented"})
    detail=subject.implementation_detail(queue.row["work_item_id"],**identity())
    assert detail["status"]=="NEEDS_VERIFICATION"
    assert [item["status"] for item in detail["implementation"]["attempts"]]==["NEEDS_VERIFICATION","FAILED"]
    verified=subject.verify_implementation(queue.row["work_item_id"],**identity())
    assert verified["status"]=="IMPLEMENTED"
    assert attempts.rows[0]["status"]=="FAILED" and attempts.rows[1]["status"]=="VERIFIED"


def test_edit_after_failure_preserves_attempt_and_requires_fresh_monotonic_brief():
    subject,queue,_,developer_repository,attempts=service()
    subject.prepare_implementation(queue.row["work_item_id"],**identity());subject.start_implementation(queue.row["work_item_id"],**identity())
    developer_repository.execution.update(status="FAILED",completed_at=NOW,failure_reason="Failed")
    subject.implementation_detail(queue.row["work_item_id"],**identity())
    first=dict(attempts.rows[0]);subject.edit(queue.row["work_item_id"],text="Check current owned inventory",**identity())
    assert attempts.rows[0]==first and queue.row["linked_future_task_id"] is None
    queue.row.update(status="REQUIRES_IMPLEMENTATION",classification="DYNAMIC_AUTHORITY_REQUIRED",
        classification_rationale="Needs code")
    prepared=subject.prepare_implementation(queue.row["work_item_id"],**identity())
    assert prepared["analysis"]["implementationBriefVersion"]==2
    assert [item["attemptNumber"] for item in prepared["implementation"]["attempts"]]==[2,1]


def test_edit_before_execution_supersedes_prepared_attempt_and_blocks_old_approval():
    subject,queue,developer,_,attempts=service()
    prepared=subject.prepare_implementation(queue.row["work_item_id"],**identity());old_task=prepared["linkedFutureTaskId"]
    subject.edit(queue.row["work_item_id"],text="Changed request",**identity())
    assert attempts.rows[0]["status"]=="SUPERSEDED" and queue.row["linked_future_task_id"] is None
    with pytest.raises(AiTrainingControlError):subject.start_implementation(queue.row["work_item_id"],**identity())
    assert developer.submitted==0 and old_task!=queue.row["linked_future_task_id"]


def test_three_attempts_remain_distinct_and_latest_start_replay_is_idempotent():
    subject,queue,developer,developer_repository,attempts=service()
    execution_ids=[]
    for _ in range(2):
        subject.prepare_implementation(queue.row["work_item_id"],**identity())
        started=subject.start_implementation(queue.row["work_item_id"],**identity())
        execution_ids.append(str(started["implementation"]["execution"]["execution_id"]))
        developer_repository.execution.update(status="FAILED",completed_at=NOW,failure_reason="Failed")
        subject.implementation_detail(queue.row["work_item_id"],**identity())
    subject.prepare_implementation(queue.row["work_item_id"],**identity())
    third=subject.start_implementation(queue.row["work_item_id"],**identity())
    third_id=str(third["implementation"]["execution"]["execution_id"]);execution_ids.append(third_id)
    replay=subject.start_implementation(queue.row["work_item_id"],**identity())
    assert str(replay["implementation"]["execution"]["execution_id"])==third_id
    assert developer.submitted==3 and len(attempts.rows)==3 and len(set(execution_ids))==3
    assert [(item["attemptNumber"],item["executionId"]) for item in replay["implementation"]["attempts"]]==[(3,execution_ids[2]),(2,execution_ids[1]),(1,execution_ids[0])]
