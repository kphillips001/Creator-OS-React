"""Workflow-only AI Training Queue with grounded canonical-authority links."""
import re
from datetime import datetime, timezone
from uuid import UUID
from app.repositories.ai_training_work_item_repository import AiTrainingWorkItemRepository
from app.services.ai_training_control_service import AiTrainingControlError, AiTrainingControlService
from app.services.developer_agent_execution_service import DeveloperAgentExecutionService
from app.repositories.developer_agent_execution_repository import DeveloperAgentExecutionRepository
from app.repositories.ai_training_implementation_attempt_repository import AiTrainingImplementationAttemptRepository


class AiTrainingWorkQueueService:
    OPEN={"TODO","READY_TO_APPLY","REQUIRES_IMPLEMENTATION","READY_FOR_IMPLEMENTATION"}
    PROTECTED=["Safety","Ownership","Pricing","Inventory truth","Settlement","Fulfillment","PurchaseIntent","Sales Session"]
    def __init__(self, repository=None, training=None, developer=None, developer_repository=None,
                 attempt_repository=None):
        self.repository=repository or AiTrainingWorkItemRepository();self.training=training or AiTrainingControlService()
        self.developer=developer or DeveloperAgentExecutionService();self.developer_repository=developer_repository or DeveloperAgentExecutionRepository()
        self.attempt_repository=attempt_repository or AiTrainingImplementationAttemptRepository()

    @staticmethod
    def implementation_status(item):
        status=item.status.value if hasattr(item.status,"value") else str(item.status)
        kind=item.instruction_type.value if hasattr(item.instruction_type,"value") else str(item.instruction_type)
        supported=(kind=="CONVERSATION_RULE" and item.enforcement_mode=="PROMPT") or (
            kind=="CUSTOMER_TREATMENT_POLICY" and item.enforcement_mode=="BACKEND") or (
            kind=="SAFETY_HARD_STOP" and item.policy_key=="UNDERAGE_CUSTOMER" and item.enforcement_mode=="BACKEND") or (
            kind=="ENGAGEMENT_RULE" and item.policy_key=="INTELLIGENT_FREE_ENGAGEMENT_TEASERS" and item.enforcement_mode=="BACKEND") or (
            kind=="SALES_RULE" and item.policy_key=="ADAPTIVE_SALES_READINESS" and item.enforcement_mode=="BACKEND")
        if not supported or status=="REQUIRES_IMPLEMENTATION":return {"implemented":False,"label":"REQUIRES IMPLEMENTATION"}
        suffix={"ENABLED":"ACTIVE","DISABLED":"DISABLED","ARCHIVED":"ARCHIVED"}.get(status)
        return {"implemented":True,"label":f"IMPLEMENTED · {suffix}" if suffix else "IMPLEMENTED"}

    def list(self, **scope):return [self._project(row) for row in self.repository.list(**scope)]
    def add(self, *, text, scope="GLOBAL", customer_fanvue_user_id=None, customer_projection_key=None, **identity):
        text=str(text).strip()
        if not text:raise AiTrainingControlError("A training request is required.")
        if scope not in {"GLOBAL","CUSTOMER"} or (scope=="CUSTOMER") != (customer_fanvue_user_id is not None):
            raise AiTrainingControlError("Customer Queue items require one canonical customer identity.")
        analysis={"customerProjectionKey":customer_projection_key} if customer_projection_key else {}
        return self._project(self.repository.create(scope=scope,customer_fanvue_user_id=customer_fanvue_user_id,text=text,analysis=analysis,**identity))

    def edit(self, work_item_id, *, text, **identity):
        current=self._required(work_item_id,**identity)
        if current["status"] not in self.OPEN|{"IMPLEMENTATION_FAILED"}:raise AiTrainingControlError("Only open or failed Queue items can be edited.")
        attempt_id=dict(current.get("analysis") or {}).get("implementationAttemptId")
        if attempt_id:self.attempt_repository.supersede_prepared(UUID(str(attempt_id)))
        return self._project(self.repository.update(work_item_id,original_request_text=str(text).strip(),status="TODO",
            classification=None,classification_rationale=None,analysis=self._orchestration_metadata(current),
            linked_instruction_id=None,linked_future_task_id=None,**identity))

    def analyze(self, work_item_id, **identity):
        row=self._required(work_item_id,**identity); text=row["original_request_text"]
        existing=self.training.list(creator_profile_id=identity["creator_profile_id"],fanvue_account_id=identity["fanvue_account_id"])
        if row["scope"]=="CUSTOMER":
            existing=self.training.list_customer(creator_profile_id=identity["creator_profile_id"],fanvue_account_id=identity["fanvue_account_id"],customer_fanvue_user_id=row["customer_fanvue_user_id"])
        match=next((item for item in existing if self._equivalent(text,item.normalized_instruction)),None)
        if match:
            evidence=self.implementation_status(match); status="IMPLEMENTED" if evidence["implemented"] else "REQUIRES_IMPLEMENTATION"
            return self._project(self.repository.update(work_item_id,status=status,classification="ALREADY_IMPLEMENTED",
                classification_rationale=f"Covered by {match.normalized_instruction}",analysis={"coverage":"FULL","implementation":evidence},linked_instruction_id=match.instruction_id,**identity))
        if row["scope"]=="CUSTOMER":
            plan=self.training.analyze_customer_training(text)
            covered=[]
            treatment_reader=getattr(self.training,"get_customer_treatment",None)
            current=(treatment_reader(creator_profile_id=identity["creator_profile_id"],
                fanvue_account_id=identity["fanvue_account_id"],customer_fanvue_user_id=row["customer_fanvue_user_id"])
                if treatment_reader else {"configuration":{}})
            current_values=dict(current.get("configuration") or {})
            for key,value in dict(plan.get("treatment") or {}).items():
                if value!="NORMAL" and current_values.get(key)==value:covered.append(key)
            remaining_guidance=[]
            for guidance in plan.get("conversationGuidance") or []:
                if any(self._equivalent(guidance,item.normalized_instruction) for item in existing):covered.append("conversation_guidance")
                else:remaining_guidance.append(guidance)
            plan={**plan,"conversationGuidance":remaining_guidance,"alreadyCovered":covered}
            status="READY_TO_APPLY" if plan["supported"] else ("REJECTED" if plan["classification"] in {"UNSAFE_CUSTOMER_POLICY","REJECTED_PROTECTED_AUTHORITY"} else "REQUIRES_IMPLEMENTATION")
            missing=bool(remaining_guidance or any(value!="NORMAL" and key not in covered for key,value in dict(plan.get("treatment") or {}).items()))
            classification=("PARTIALLY_IMPLEMENTED" if covered and missing else "CUSTOMER_TRAINING" if plan["supported"] else plan["classification"])
            if covered and not missing:
                status="IMPLEMENTED";classification="ALREADY_IMPLEMENTED"
            analysis={**plan,**self._orchestration_metadata(row)}
        else:
            plan=self.training.classify(text); eligible=plan["runtimeEligible"]
            unsafe=bool(re.search(r"\b(?:ignore|bypass|fabricate|fake|give)\b.*\b(?:underage|safety|ownership|purchase|settlement|inventory|paid content|previous instructions|system)\b",text.lower()))
            status="READY_TO_APPLY" if eligible else ("REJECTED" if unsafe else "REQUIRES_IMPLEMENTATION")
            classification="GLOBAL_PROMPT_GUIDANCE" if eligible else plan["classification"];analysis=plan
        return self._project(self.repository.update(work_item_id,status=status,classification=classification,
            classification_rationale=plan.get("explanation") or plan.get("classificationReason"),analysis=analysis,**identity))

    def apply(self, work_item_id, **identity):
        row=self._required(work_item_id,**identity)
        if row["status"]!="READY_TO_APPLY":raise AiTrainingControlError("Queue item is not ready to apply.")
        analysis=dict(row.get("analysis") or {})
        if row["scope"]=="GLOBAL":
            item=self.training.create(operator_text=row["original_request_text"],activate=True,**identity)
        else:
            result=self.training.apply_customer_training_plan(customer_fanvue_user_id=row["customer_fanvue_user_id"],
                operator_text=row["original_request_text"],conversation_guidance=analysis.get("conversationGuidance") or [],
                configuration=analysis.get("treatment") or self.training.TREATMENT_DEFAULTS,**identity)
            item=(result["guidance"] or [result["treatment"]])[0]
        evidence=self.implementation_status(item)
        status="IMPLEMENTED" if evidence["implemented"] else "REQUIRES_IMPLEMENTATION"
        return self._project(self.repository.update(work_item_id,status=status,linked_instruction_id=item.instruction_id,
            classification_rationale=("Canonical training applied and runtime support verified." if evidence["implemented"] else "Training persisted but runtime support could not be verified."),analysis={**analysis,"implementation":evidence},**identity))

    def close(self,work_item_id,**identity):
        self._required(work_item_id,**identity)
        return self._project(self.repository.update(work_item_id,status="CLOSED",**identity))

    def prepare_implementation(self, work_item_id, **identity):
        row=self._required(work_item_id,**identity)
        if row["status"] not in {"REQUIRES_IMPLEMENTATION","IMPLEMENTATION_FAILED"}:
            raise AiTrainingControlError("Only implementation-required or failed Queue items can be prepared.")
        analysis=dict(row.get("analysis") or {})
        prior_versions=[int(item["implementation_brief_version"]) for item in self.attempt_repository.list(work_item_id)]
        version=max([int(analysis.get("implementationBriefVersion") or 0),*prior_versions])+1
        scope=(f"CUSTOMER — canonical customer ID {row['customer_fanvue_user_id']}" if row["scope"]=="CUSTOMER" else "GLOBAL")
        rationale=row.get("classification_rationale") or "The existing AI Training runtime cannot safely apply this request."
        acceptance=[row["original_request_text"],"Use authoritative runtime data rather than static prompt claims.","Preserve existing protected business authorities."]
        tests=["Add focused isolated regression coverage for the requested behavior.","Run affected backend/frontend tests and git diff --check.","Do not call external providers or mutate production business state."]
        brief={"version":version,"request":row["original_request_text"],"scope":scope,
            "whyImplementationIsRequired":rationale,"desiredBehavior":row["original_request_text"],
            "protectedAuthorities":self.PROTECTED,"acceptanceCriteria":acceptance,
            "regressionBoundaries":["Do not weaken safety, commerce, ownership, pricing, inventory, settlement, fulfillment, PurchaseIntent, or Sales Session authority.","Do not alter launch gates or real customer/business state."],
            "proposedVerification":tests,"repository":"C:\\Creator-OS-React","branch":"react-migration"}
        payload=self._execution_payload(brief)
        analysis.update({"implementationBrief":brief,"implementationBriefVersion":version})
        def create_task(_attempt_number):
            return self.developer.create_task(issue_identifier=f"AI Training Queue {row['work_item_id']} v{version}",
                investigation_package=self._brief_text(brief),implementation_task=payload)
        try:
            updated,attempt,_task=self.attempt_repository.prepare(work_item_id,brief_version=version,
                analysis=analysis,task_factory=create_task,**identity)
        except ValueError as error:
            raise AiTrainingControlError(str(error)) from error
        projected=self._project(updated)
        projected["implementation"]={"brief":brief,"execution":None,"currentAttempt":self._project_attempt(attempt,None),
            "attempts":self._attempt_history(work_item_id)}
        return projected

    def start_implementation(self, work_item_id, **identity):
        row=self._required(work_item_id,**identity)
        if not row.get("linked_future_task_id"):
            raise AiTrainingControlError("A current reviewed implementation brief is required before approval.")
        analysis=dict(row.get("analysis") or {}); version=analysis.get("implementationBriefVersion")
        task_id=UUID(str(row["linked_future_task_id"])); task=self.developer_repository.get_task(task_id)
        attempt_id=analysis.get("implementationAttemptId")
        attempt=self.attempt_repository.get(UUID(str(attempt_id))) if attempt_id else None
        if (not task or not version or
                task["issue_identifier"]!=f"AI Training Queue {row['work_item_id']} v{version}" or
                str(analysis.get("implementationTaskId"))!=str(task_id) or
                (attempt is not None and (str(attempt["developer_agent_task_id"])!=str(task_id)
                    or int(attempt["implementation_brief_version"])!=int(version)))):
            raise AiTrainingControlError("The implementation approval snapshot does not match this Queue item.")
        replay_states={"IMPLEMENTING","NEEDS_VERIFICATION","IMPLEMENTATION_FAILED","IMPLEMENTED"}
        existing=self.developer_repository.latest_execution_for_task(task_id)
        if row["status"] in replay_states:
            if existing is None or str(existing["task_id"])!=str(task_id):
                raise AiTrainingControlError("The linked implementation execution could not be verified.")
            recorded=analysis.get("implementationExecutionId")
            if recorded and str(recorded)!=str(existing["execution_id"]):
                raise AiTrainingControlError("The implementation execution does not match the approved snapshot.")
            return self._with_attempts(self._with_execution(self._project(row),existing,reused=True),row["work_item_id"])
        if row["status"]!="READY_FOR_IMPLEMENTATION":
            raise AiTrainingControlError("A current reviewed implementation brief is required before approval.")
        if task["status"]=="AWAITING_APPROVAL": self.developer.approve_task(task_id)
        execution=self.developer.submit(task_id)
        if attempt is not None:
            try:self.attempt_repository.attach_execution(attempt["attempt_id"],task_id=task_id,execution=execution)
            except ValueError as error:raise AiTrainingControlError(str(error)) from error
        analysis={**analysis,"implementationExecutionId":str(execution["execution_id"]),"implementationAuthority":"Developer Agent / Codex"}
        updated=self.repository.update(work_item_id,status="IMPLEMENTING",analysis=analysis,**identity)
        return self._with_attempts(self._with_execution(self._project(updated),execution,reused=bool(existing)),work_item_id)

    def implementation_detail(self, work_item_id, **identity):
        row=self._required(work_item_id,**identity); analysis=dict(row.get("analysis") or {})
        execution=None
        if analysis.get("implementationExecutionId"):
            execution=self.developer_repository.get_execution(UUID(analysis["implementationExecutionId"]))
            if execution:
                if str(execution.get("task_id"))!=str(row.get("linked_future_task_id")):
                    raise AiTrainingControlError("The current execution does not belong to the current implementation attempt.")
                mapped={"COMPLETED":"NEEDS_VERIFICATION","FAILED":"IMPLEMENTATION_FAILED","CANCELLED":"IMPLEMENTATION_FAILED","INTERRUPTED":"IMPLEMENTATION_FAILED"}.get(execution["status"])
                if mapped and row["status"]=="IMPLEMENTING":
                    if analysis.get("implementationAttemptId"):
                        try:self.attempt_repository.update_from_execution(UUID(analysis["implementationAttemptId"]),execution)
                        except ValueError as error:raise AiTrainingControlError(str(error)) from error
                    row=self.repository.update(work_item_id,status=mapped,analysis=analysis,**identity)
        projected=self._project(row);projected["implementation"]={"brief":analysis.get("implementationBrief"),"execution":self._safe_execution(execution),
            "attempts":self._attempt_history(work_item_id)}
        projected["implementation"]["currentAttempt"]=next((item for item in projected["implementation"]["attempts"] if item["isCurrent"]),None)
        return projected

    def verify_implementation(self, work_item_id, **identity):
        detail=self.implementation_detail(work_item_id,**identity)
        if detail["status"]!="NEEDS_VERIFICATION":raise AiTrainingControlError("Only completed implementations awaiting verification can be accepted.")
        execution_id=detail["analysis"].get("implementationExecutionId")
        if execution_id:self.developer_repository.update_review(UUID(execution_id),"ACKNOWLEDGED")
        analysis={**detail["analysis"],"verifiedAt":datetime.now(timezone.utc).isoformat(),"verificationOutcome":"ACCEPTED"}
        if analysis.get("implementationAttemptId") and execution_id:
            try:self.attempt_repository.verify(UUID(analysis["implementationAttemptId"]),UUID(execution_id))
            except ValueError as error:raise AiTrainingControlError(str(error)) from error
        return self._project(self.repository.update(work_item_id,status="IMPLEMENTED",analysis=analysis,**identity))

    def _attempt_history(self,work_item_id):
        attempts=[]
        for index,attempt in enumerate(self.attempt_repository.list(work_item_id)):
            execution=None
            if attempt.get("developer_agent_execution_id"):
                execution=self.developer_repository.get_execution(UUID(str(attempt["developer_agent_execution_id"])))
                if execution and str(execution.get("task_id"))!=str(attempt["developer_agent_task_id"]):
                    raise AiTrainingControlError("An implementation attempt references an execution from another task.")
            projected=self._project_attempt(attempt,execution);projected["isCurrent"]=index==0;attempts.append(projected)
        return attempts

    def _with_attempts(self,projected,work_item_id):
        attempts=self._attempt_history(work_item_id)
        projected.setdefault("implementation",{})["attempts"]=attempts
        projected["implementation"]["currentAttempt"]=next((item for item in attempts if item["isCurrent"]),None)
        return projected

    @classmethod
    def _project_attempt(cls,attempt,execution):
        return {"attemptId":str(attempt["attempt_id"]),"attemptNumber":attempt["attempt_number"],
            "briefVersion":attempt["implementation_brief_version"],"taskId":str(attempt["developer_agent_task_id"]),
            "executionId":str(attempt["developer_agent_execution_id"]) if attempt.get("developer_agent_execution_id") else None,
            "status":attempt["status"],"approvedAt":cls._iso(attempt.get("approved_at")),
            "startedAt":cls._iso(attempt.get("started_at")),"completedAt":cls._iso(attempt.get("completed_at")),
            "verifiedAt":cls._iso(attempt.get("verified_at")),"createdAt":cls._iso(attempt.get("created_at")),
            "updatedAt":cls._iso(attempt.get("updated_at")),"isCurrent":False,
            "execution":cls._safe_execution(execution)}

    @staticmethod
    def _iso(value):return value.isoformat() if hasattr(value,"isoformat") else value

    @staticmethod
    def _safe_execution(value):
        if not value:return None
        return {key:value.get(key) for key in ("execution_id","task_id","status","started_at","completed_at","failure_reason","final_report","review_status")}
    @classmethod
    def _with_execution(cls, projected, execution, *, reused):
        projected["implementation"]={"brief":projected["analysis"].get("implementationBrief"),
            "execution":cls._safe_execution(execution),"reusedExistingExecution":reused}
        return projected
    @classmethod
    def _brief_text(cls,brief):
        return "\n\n".join(f"{key.replace('_',' ').upper()}\n{value if isinstance(value,str) else chr(10).join('- '+str(item) for item in value)}" for key,value in brief.items() if key not in {"version"})
    @classmethod
    def _execution_payload(cls,brief):
        return f"""Implement this approved bounded Creator-OS task in C:\\Creator-OS-React on react-migration.\n\n{cls._brief_text(brief)}\n\nSTOP CONDITIONS\nStop rather than broaden scope or weaken a protected authority. Do not send Telegram, mutate Fanvue, publish content, create real PurchaseIntent, alter real customer training/business state, launch gates, or runtime switches. Use isolated fixtures/mocks.\n\nFINAL REPORT\nReport files changed, tests/checks, migration required/applied, warnings, and any unmet acceptance criteria. Do not expose secrets or chain-of-thought."""
    def _required(self,work_item_id,**identity):
        row=self.repository.get(work_item_id,**identity)
        if not row:raise AiTrainingControlError("AI Training Queue item was not found.")
        return row
    @staticmethod
    def _orchestration_metadata(row):
        """Keep stable Queue routing identity separate from replaceable analysis results."""
        analysis=dict(row.get("analysis") or {})
        return ({"customerProjectionKey":analysis["customerProjectionKey"]}
                if row.get("scope")=="CUSTOMER" and analysis.get("customerProjectionKey") else {})
    @staticmethod
    def _equivalent(left,right):
        clean=lambda value: re.sub(r"[^a-z0-9]+"," ",str(value).lower()).strip()
        a,b=clean(left),clean(right)
        if a==b:return True
        solo=lambda value:"solo" in value and "content" in value and any(word in value for word in ("only","offer"))
        underage=lambda value:"underage" in value and any(word in value for word in ("stop","block","contact"))
        return (solo(a) and solo(b)) or (underage(a) and underage(b))
    @staticmethod
    def _project(row):
        return {"workItemId":str(row["work_item_id"]),"creatorProfileId":row["creator_profile_id"],
            "fanvueAccountId":row["fanvue_account_id"],"scope":row["scope"],"customerFanvueUserId":row.get("customer_fanvue_user_id"),
            "originalRequestText":row["original_request_text"],"status":row["status"],"classification":row.get("classification"),
            "classificationRationale":row.get("classification_rationale"),"analysis":dict(row.get("analysis") or {}),
            "linkedInstructionId":str(row["linked_instruction_id"]) if row.get("linked_instruction_id") else None,
            "linkedFutureTaskId":str(row["linked_future_task_id"]) if row.get("linked_future_task_id") else None,
            "createdAt":row["created_at"].isoformat(),"updatedAt":row["updated_at"].isoformat(),
            "completedAt":row["completed_at"].isoformat() if row.get("completed_at") else None}
