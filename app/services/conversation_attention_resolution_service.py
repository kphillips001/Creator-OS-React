"""Inspection, frozen planning, approval, and closed customer resolution."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from threading import Lock
from uuid import UUID, uuid4

from app.models.conversation_attention_resolution import (
    EXECUTABLE_ACTIONS, InspectionNarrative, InspectionResult, ResolutionAction, RootCauseScope,
    SCHEMA_VERSION,
)

_INSPECTION_LOCKS_GUARD = Lock()
_INSPECTION_LOCKS: dict[str, Lock] = {}
from app.repositories.conversation_attention_resolution_repository import (
    ConversationAttentionResolutionRepository,
)
from app.services.conversation_attention_evidence_service import (
    ConversationAttentionEvidenceService,
)
from app.services.conversation_attention_inspection_provider import (
    ConversationAttentionInspectionProvider,
)
from app.services.relationships_service import RelationshipsService


class ConversationAttentionResolutionService:
    """Codex diagnoses; this service validates and executes closed actions."""
    ACTION_SERVICES = {
        ResolutionAction.ACKNOWLEDGE_ONLY: "RelationshipsService.acknowledge_attention",
        ResolutionAction.RESOLVE_AS_SUPERSEDED: "ConversationAttentionResolutionService.resolve_as_superseded",
        ResolutionAction.REQUEUE_CORRECTIVE_REPLY: "OrdinaryChatReplyRepository.requeue_historical_corrective",
        ResolutionAction.CONFIRM_DELIVERED: "OperatorDeliveryResolutionRepository.resolve",
        ResolutionAction.CONFIRM_NOT_DELIVERED: "OperatorDeliveryResolutionRepository.resolve",
    }

    def __init__(self, *, repository=None, evidence=None, provider=None,
                 relationships=None, ordinary_repository=None, signing_secret=None):
        self.repository = repository or ConversationAttentionResolutionRepository()
        self.evidence = evidence or ConversationAttentionEvidenceService()
        self.provider = provider or ConversationAttentionInspectionProvider()
        self.relationships = relationships or RelationshipsService()
        if ordinary_repository is None:
            from app.repositories.ordinary_chat_reply_repository import OrdinaryChatReplyRepository
            ordinary_repository=OrdinaryChatReplyRepository()
        self.ordinary=ordinary_repository
        configured=(signing_secret or os.getenv("CREATOR_OS_RESOLUTION_PLAN_SECRET")
                    or os.getenv("CREATOR_OS_DEVELOPER_KEY"))
        if not configured:
            # Domain-separated derivation from an existing server-held signing key;
            # no key material is persisted in a plan or sent to the model.
            from app.config import FANVUE_WEBHOOK_SIGNING_SECRET
            if str(FANVUE_WEBHOOK_SIGNING_SECRET) == "test_webhook_secret":
                raise RuntimeError("Resolution plan signing secret is not configured.")
            configured=hmac.new(str(FANVUE_WEBHOOK_SIGNING_SECRET).encode(),
                                b"creator-os-attention-resolution-v1",
                                hashlib.sha256).hexdigest()
        self.secret=str(configured or "").encode()

    def inspect(self, *, creator_profile_id, fanvue_account_id, telegram_user_id,
                relationship_key, occurrence_id, request_id=None):
        evidence=self.evidence.build(creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,telegram_user_id=telegram_user_id,
            relationship_key=relationship_key,occurrence_id=occurrence_id)
        eligibility = dict(evidence.get("recoveryEligibility") or {})
        if eligibility.get("reason") == (
                "HISTORICAL_CORRECTIVE_REJECTED_CANDIDATE_EVIDENCE_REQUIRED"):
            raise RuntimeError(
                "Historical repetition recovery is blocked: authoritative "
                "rejected-candidate evidence is unavailable. No provider call "
                "or recovery plan was created."
            )
        request_id=UUID(str(request_id)) if request_id else uuid4()
        lock_key=f"{creator_profile_id}:{fanvue_account_id}:{request_id}"
        with _INSPECTION_LOCKS_GUARD:
            lock=_INSPECTION_LOCKS.setdefault(lock_key,Lock())
        with lock, self.repository.inspection_singleflight(request_id):
            existing=self.repository.get_inspection_by_request(request_id,
                creator_profile_id=creator_profile_id,fanvue_account_id=fanvue_account_id,
                relationship_key=relationship_key,attention_occurrence_id=occurrence_id,
                state_fingerprint=evidence["stateFingerprint"])
            if existing:
                return {"inspection":existing,"result":existing["validated_result"],
                        "plan":self.repository.get_plan_for_inspection(existing["inspection_id"])}
            inspection_id=uuid4(); now=datetime.now(timezone.utc).isoformat()
            if (evidence["failureSignature"] == "SEND_UNCERTAIN"
                    and not (evidence.get("recoveryEligibility") or {}).get("eligible")):
                result=self._delivery_uncertain_result(evidence,inspection_id,now)
                stored=self.repository.create_inspection(
                    inspection_id=inspection_id,creator_profile_id=creator_profile_id,
                    fanvue_account_id=fanvue_account_id,relationship_key=relationship_key,
                    telegram_user_id=telegram_user_id,attention_occurrence_id=occurrence_id,
                    evidence_digest=evidence["evidenceDigest"],
                    state_fingerprint=evidence["stateFingerprint"],
                    failure_signature=evidence["failureSignature"],
                    root_cause_scope="CUSTOMER_ONLY",validated_result=result,
                    evidence_references=result["evidenceReferences"],request_id=request_id,
                    conflict_report=None)
                self.repository.add_event("INSPECTION_VALIDATED",inspection_id=inspection_id,
                    event_data={"evidenceDigest":evidence["evidenceDigest"],
                                "failureSignature":"SEND_UNCERTAIN",
                                "rootCauseScope":"CUSTOMER_ONLY",
                                "deliveryEvidence":result["deliveryEvidence"]})
                return {"inspection":stored,"result":result,"plan":None}
            candidate=self.provider.inspect({**evidence,"inspectionId":str(inspection_id),
                                             "inspectedAt":now})
            result,conflict=self._validate_candidate(candidate,evidence=evidence,
                inspection_id=inspection_id,inspected_at=now)
            stored=self.repository.create_inspection(
            inspection_id=inspection_id,creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,relationship_key=relationship_key,
            telegram_user_id=telegram_user_id,attention_occurrence_id=occurrence_id,
            evidence_digest=evidence["evidenceDigest"],
            state_fingerprint=evidence["stateFingerprint"],
            failure_signature=evidence["failureSignature"],
            root_cause_scope=result.rootCauseScope.value,
            validated_result=result.model_dump(mode="json"),
            evidence_references=result.evidenceReferences,request_id=request_id,
            conflict_report=conflict)
            self.repository.add_event("INSPECTION_VALIDATED",inspection_id=inspection_id,
            event_data={"evidenceDigest":evidence["evidenceDigest"],
                        "failureSignature":evidence["failureSignature"],
                        "rootCauseScope":result.rootCauseScope.value,
                        "validationReasonCode":(conflict or {}).get("reasonCode")})
            plan=None
            if result.recommendedResolutionType in EXECUTABLE_ACTIONS:
                plan=self._create_plan(stored=stored,result=result,evidence=evidence)
            return {"inspection":stored,"result":result.model_dump(mode="json"),"plan":plan}

    def _delivery_uncertain_result(self,evidence,inspection_id,inspected_at):
        delivery=dict(evidence.get("commercialDeliveryEvidence") or {})
        qualifying=bool(delivery.get("qualifyingCommercialPresentation"))
        return {
          "schemaVersion":SCHEMA_VERSION,"inspectionId":str(inspection_id),
          "relationshipKey":evidence["relationshipKey"],
          "attentionOccurrenceId":evidence["attentionOccurrenceId"],
          "inspectedAt":inspected_at,"stateFingerprint":evidence["stateFingerprint"],
          "evidenceReferences":evidence["evidenceReferences"],
          "failureSignature":"SEND_UNCERTAIN",
          "whyFlagged":"Telegram delivery completed without durable provider-confirmed message identity.",
          "currentImpact":"The commercial presentation outcome requires explicit operator resolution.",
          "currentObligation":"Review delivery evidence and attest delivered or not delivered.",
          "willAvaContinueAutomatically":False,"avaAutoState":self._automation_state(evidence),
          "currentOperationState":"NO_FURTHER_AUTOMATIC_ATTEMPT",
          "isConditionStillRelevant":True,"rootCauseScope":"CUSTOMER_ONLY",
          "rootCauseSummary":"The original operation remains SEND_UNCERTAIN.",
          "affectedCurrentCustomersCount":1,"similarCurrentCases":[],
          "futureCustomersPotentiallyAffected":False,
          "globalRepairAlreadyExists":True,
          "recommendedResolutionType":"NO_AUTOMATED_RESOLUTION",
          "recommendedResolutionSummary":"Choose an explicit delivery outcome.",
          "operatorExplanation":"Operator attestation preserves SEND_UNCERTAIN history and never claims provider confirmation.",
          "exactProposedActions":[],"customerVisibleSendPossible":False,
          "providerGenerationPossible":False,"codeChangeRequired":False,
          "databaseChangeRequired":True,"schemaChangeRequired":False,
          "configChangeRequired":False,"runtimeRestartRequired":False,
          "globalImpactPossible":False,"riskLevel":"LOW","approvalRequired":True,
          "dispositionReason":None,"confidence":1.0,"unsupportedAssertions":[],
          "inspectionWarnings":([] if qualifying else
              ["Persisted evidence does not establish the known commercial presentation class."]),
          "cannotSafelyResolveReason":None if qualifying else
              "Commercial delivery evidence is incomplete.",
          "deliveryEvidence":delivery,
          "resolutionChoices":["CONFIRM_DELIVERED","CONFIRM_NOT_DELIVERED","LEAVE_UNRESOLVED"],
        }

    def create_delivery_plan(self, inspection_id, *, creator_profile_id,
                             fanvue_account_id, outcome):
        action=ResolutionAction(str(outcome))
        if action not in {ResolutionAction.CONFIRM_DELIVERED,
                          ResolutionAction.CONFIRM_NOT_DELIVERED}:
            raise ValueError("Unsupported delivery resolution choice.")
        stored=self.repository.get_inspection(inspection_id,
            creator_profile_id=creator_profile_id,fanvue_account_id=fanvue_account_id)
        if not stored or stored["failure_signature"] != "SEND_UNCERTAIN":
            raise LookupError("Qualifying uncertain-delivery inspection was not found.")
        evidence=self.evidence.build(creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,telegram_user_id=stored["telegram_user_id"],
            relationship_key=stored["relationship_key"],
            occurrence_id=stored["attention_occurrence_id"])
        if evidence["stateFingerprint"] != stored["state_fingerprint"]:
            raise RuntimeError("RESOLUTION PLAN OUT OF DATE: re-inspection required.")
        delivery=dict(evidence.get("commercialDeliveryEvidence") or {})
        if not delivery.get("qualifyingCommercialPresentation"):
            raise PermissionError("Persisted evidence does not authorize delivery resolution.")
        return self._create_delivery_plan(stored=stored,evidence=evidence,action=action)

    def _create_delivery_plan(self, *, stored, evidence, action):
        plan_id=uuid4(); idempotency=str(uuid4())
        unsigned={"planId":str(plan_id),"inspectionId":str(stored["inspection_id"]),
          "relationshipKey":stored["relationship_key"],
          "attentionOccurrenceId":evidence["attentionOccurrenceId"],
          "stateFingerprint":evidence["stateFingerprint"],"scope":"CUSTOMER_ONLY",
          "targetOperationId":evidence["targetOperationId"],
          "causalOperationId":evidence["causalOperationId"],
          "action":action.value,"idempotencyKey":idempotency}
        signature=self._sign(unsigned)
        delivery=dict(evidence["commercialDeliveryEvidence"])
        plan=self.repository.create_plan(plan_id=plan_id,inspection_id=stored["inspection_id"],
          creator_profile_id=stored["creator_profile_id"],fanvue_account_id=stored["fanvue_account_id"],
          relationship_key=stored["relationship_key"],telegram_user_id=stored["telegram_user_id"],
          attention_occurrence_id=evidence["attentionOccurrenceId"],
          state_fingerprint=evidence["stateFingerprint"],root_cause_scope="CUSTOMER_ONLY",
          target_operation_id=evidence["targetOperationId"],
          causal_operation_id=evidence["causalOperationId"],action_type=action.value,
          parameters={"purchaseIntentId":delivery["purchaseIntentId"],
                      "presentationMode":delivery["presentationMode"]},
          expected_mutation_entities=["operator_delivery_resolutions","purchase_intents"],
          provider_generation_possible=False,customer_visible_send_possible=False,
          risk_level="LOW",signature=signature,idempotency_key=idempotency)
        self.repository.add_event("PLAN_CREATED",inspection_id=stored["inspection_id"],
            plan_id=plan_id,event_data={"action":action.value,"signature":signature})
        return plan

    def _validate_candidate(self, candidate, *, evidence, inspection_id, inspected_at):
        try:
            parsed=InspectionNarrative.model_validate(candidate)
        except Exception as exc:
            report=self._conflict_report(candidate,exc)
            return (self._ambiguous(evidence,inspection_id,inspected_at,
                                   "Structured diagnostic output was rejected."),report)
        server_scope=self._server_scope(evidence)
        if server_scope is RootCauseScope.AMBIGUOUS:
            return (self._ambiguous(evidence,inspection_id,inspected_at,
                    "Authoritative evidence cannot safely select a resolution."),
                    {"reasonCode":"AUTHORITATIVE_EVIDENCE_AMBIGUOUS","mismatches":[]})
        action=self._server_action(evidence)
        if action is ResolutionAction.NO_AUTOMATED_RESOLUTION:
            return (self._ambiguous(evidence,inspection_id,inspected_at,
                    "Authoritative evidence cannot safely select an action."),
                    {"reasonCode":"ACTION_NOT_AUTHORIZED","mismatches":[]})
        similar=self._canonical_similar(evidence["similarCurrentCases"])
        automation=self._automation_state(evidence)
        operation=self._current_operation_state(evidence)
        values={**parsed.model_dump(mode="json"),
            "schemaVersion":SCHEMA_VERSION,"inspectionId":str(inspection_id),
            "inspectedAt":inspected_at,"evidenceReferences":evidence["evidenceReferences"],
            "relationshipKey":evidence["relationshipKey"],
            "attentionOccurrenceId":evidence["attentionOccurrenceId"],
            "stateFingerprint":evidence["stateFingerprint"],
            "failureSignature":evidence["failureSignature"],
            "rootCauseScope":server_scope.value,"similarCurrentCases":similar,
            "affectedCurrentCustomersCount":1+len(similar),
            "globalRepairAlreadyExists":bool(evidence["globalRepairAlreadyExists"]),
            "futureCustomersPotentiallyAffected":False,
            "isConditionStillRelevant":not self._superseded(evidence),
            "willAvaContinueAutomatically":operation not in {"NO_FURTHER_AUTOMATIC_ATTEMPT","COMPLETED"},
            "avaAutoState":automation,"currentOperationState":operation,
            "recommendedResolutionType":action.value,
            "exactProposedActions":[self._action_description(action)],
            "approvalRequired":action in EXECUTABLE_ACTIONS,
            "dispositionReason":"SUPERSEDED" if action is ResolutionAction.RESOLVE_AS_SUPERSEDED else None,
            "unsupportedAssertions":[],"cannotSafelyResolveReason":None,
            "codeChangeRequired":False,"schemaChangeRequired":False,
            "configChangeRequired":False,"runtimeRestartRequired":False,
            "globalImpactPossible":False,"databaseChangeRequired":action in EXECUTABLE_ACTIONS}
        if action == ResolutionAction.REQUEUE_CORRECTIVE_REPLY:
            values["providerGenerationPossible"]=True
            values["customerVisibleSendPossible"]=True
            values["databaseChangeRequired"]=True
            values["riskLevel"]="MEDIUM"
        elif action in EXECUTABLE_ACTIONS:
            values["providerGenerationPossible"]=False
            values["customerVisibleSendPossible"]=False
            values["databaseChangeRequired"]=True
            values["riskLevel"]="LOW"
        return InspectionResult.model_validate(values),None

    def _ambiguous(self,evidence,inspection_id,inspected_at,reason):
        similar=self._canonical_similar(evidence["similarCurrentCases"])
        return InspectionResult.model_validate({
          "schemaVersion":SCHEMA_VERSION,"inspectionId":str(inspection_id),
          "relationshipKey":evidence["relationshipKey"],
          "attentionOccurrenceId":evidence["attentionOccurrenceId"],"inspectedAt":inspected_at,
          "stateFingerprint":evidence["stateFingerprint"],
          "evidenceReferences":evidence["evidenceReferences"],
          "failureSignature":evidence["failureSignature"],"whyFlagged":evidence["operationalStatusReason"],
          "currentImpact":"Authoritative resolution could not be selected.",
          "currentObligation":"Manual review required.","willAvaContinueAutomatically":False,
          "avaAutoState":self._automation_state(evidence),
          "currentOperationState":self._current_operation_state(evidence),
          "isConditionStillRelevant":True,"rootCauseScope":"AMBIGUOUS",
          "rootCauseSummary":reason,"affectedCurrentCustomersCount":1+len(similar),
          "similarCurrentCases":similar,
          "futureCustomersPotentiallyAffected":False,
          "globalRepairAlreadyExists":evidence["globalRepairAlreadyExists"],
          "recommendedResolutionType":"NO_AUTOMATED_RESOLUTION",
          "recommendedResolutionSummary":"No mutation is authorized.",
          "operatorExplanation":"Manual review is required because authoritative evidence could not select a safe action.",
          "exactProposedActions":[],"customerVisibleSendPossible":False,
          "providerGenerationPossible":False,"codeChangeRequired":False,
          "databaseChangeRequired":False,"schemaChangeRequired":False,
          "configChangeRequired":False,"runtimeRestartRequired":False,
          "globalImpactPossible":False,"riskLevel":"HIGH","approvalRequired":False,
          "dispositionReason":None,"confidence":0.0,"unsupportedAssertions":[],
          "inspectionWarnings":[reason],"cannotSafelyResolveReason":reason})

    @staticmethod
    def _canonical_similar(items):
        return sorted((dict(item) for item in items),
                      key=lambda item:(item["relationshipKey"],item["attentionOccurrenceId"]))

    @staticmethod
    def _automation_state(evidence):
        if evidence.get("automationMode") == "HUMAN_OPERATOR": return "MANUAL"
        return "ON" if (evidence.get("permissions") or {}).get("effective",{}).get("chatAllowed") else "OFF"

    @staticmethod
    def _current_operation_state(evidence):
        operation=evidence.get("currentAuthorityOperation") or evidence.get("causalOperation") or {}
        if operation.get("hasClaim"): return "PROCESSING"
        state=operation.get("state")
        if state == "SENT_CONFIRMED": return "COMPLETED"
        if operation.get("nextRetryAt"): return "REPLY_SCHEDULED"
        if state in {"SUPPRESSED","TERMINAL_FAILED","SEND_UNCERTAIN"}: return "NO_FURTHER_AUTOMATIC_ATTEMPT"
        return "WAITING"

    @classmethod
    def _server_action(cls,evidence):
        eligibility=dict(evidence.get("recoveryEligibility") or {})
        if (evidence.get("failureSignature") == "SEND_UNCERTAIN"
                and eligibility.get("eligible") is True
                and eligibility.get("category") in {
                    "CANONICALLY_CONFIRMED_NOT_DELIVERED",
                    "RECOVERY_CONSTRAINT_FAILURE_NOT_DELIVERED",
                }):
            return ResolutionAction.REQUEUE_CORRECTIVE_REPLY
        if evidence.get("failureSignature") in {
                "REQUIRED_RESPONSE_QUALITY_FAILURE", "FINAL_REPETITION_FAILURE",
                "MANUFACTURED_ENGAGEMENT_QUESTION", "RETRY_EXHAUSTED"}:
            if cls._superseded(evidence):
                return ResolutionAction.RESOLVE_AS_SUPERSEDED
            if (evidence.get("recoveryEligibility") or {}).get("eligible") is True:
                return ResolutionAction.REQUEUE_CORRECTIVE_REPLY
        return ResolutionAction.NO_AUTOMATED_RESOLUTION

    @staticmethod
    def _action_description(action):
        if action is ResolutionAction.REQUEUE_CORRECTIVE_REPLY:
            return "Create one current customer-scoped corrective reply obligation."
        if action is ResolutionAction.RESOLVE_AS_SUPERSEDED:
            return "Resolve this occurrence as superseded by a later confirmed response."
        return "Acknowledge this occurrence only."

    @staticmethod
    def _conflict_report(candidate, error):
        """Persist bounded shape diagnostics, never raw payload or customer text."""
        allowed={"rootCauseScope","failureSignature","affectedCurrentCustomersCount",
                 "futureCustomersPotentiallyAffected","globalRepairAlreadyExists",
                 "recommendedResolutionType","isConditionStillRelevant",
                 "willAvaContinueAutomatically","customerVisibleSendPossible",
                 "providerGenerationPossible","riskLevel"}
        mismatches=[]
        if isinstance(candidate,dict):
            for field in sorted(set(candidate).intersection(allowed)):
                value=candidate[field]
                if isinstance(value,(str,bool,int,float)) or value is None:
                    mismatches.append({"field":field,"aiValue":value})
        errors=[]
        if hasattr(error,"errors"):
            for item in error.errors()[:20]:
                errors.append({"field":".".join(str(x) for x in item.get("loc",()))[:120],
                               "code":str(item.get("type") or "validation_error")[:80]})
        return {"reasonCode":"STRUCTURED_DIAGNOSTIC_REJECTED",
                "mismatches":mismatches,"validationErrors":errors}

    @staticmethod
    def _server_scope(evidence):
        failure=evidence["failureSignature"]
        if failure == "UNKNOWN": return RootCauseScope.AMBIGUOUS
        if (failure == "SEND_UNCERTAIN"
                and (evidence.get("recoveryEligibility") or {}).get("eligible") is True
                and (evidence.get("recoveryEligibility") or {}).get("category")
                in {"CANONICALLY_CONFIRMED_NOT_DELIVERED",
                    "RECOVERY_CONSTRAINT_FAILURE_NOT_DELIVERED"}):
            return RootCauseScope.CUSTOMER_ONLY
        if evidence["similarCurrentCases"]: return RootCauseScope.MULTIPLE_CUSTOMERS
        if failure in {"SEND_UNCERTAIN"}: return RootCauseScope.AMBIGUOUS
        return RootCauseScope.CUSTOMER_ONLY

    def _create_plan(self, *, stored, result, evidence):
        scope=result.rootCauseScope
        action=result.recommendedResolutionType
        if scope not in {RootCauseScope.CUSTOMER_ONLY,RootCauseScope.MULTIPLE_CUSTOMERS}:
            return None
        if action not in EXECUTABLE_ACTIONS: return None
        if not self.secret: raise RuntimeError("Resolution plan signing secret is not configured.")
        plan_id=uuid4(); idempotency=str(uuid4())
        entities=([] if action is ResolutionAction.ACKNOWLEDGE_ONLY else
                  ["conversation_attention_acknowledgements"] if action is ResolutionAction.RESOLVE_AS_SUPERSEDED else
                  ["ordinary_chat_reply_operations"])
        unsigned={"planId":str(plan_id),"inspectionId":str(stored["inspection_id"]),
          "relationshipKey":stored["relationship_key"],"attentionOccurrenceId":evidence["attentionOccurrenceId"],
          "stateFingerprint":evidence["stateFingerprint"],"scope":scope.value,
          "targetOperationId":evidence["targetOperationId"],"causalOperationId":evidence["causalOperationId"],
          "action":action.value,"idempotencyKey":idempotency}
        signature=self._sign(unsigned)
        parameters=self.recovery_plan_parameters(
            evidence, disposition_reason=result.dispositionReason)
        plan=self.repository.create_plan(plan_id=plan_id,inspection_id=stored["inspection_id"],
          creator_profile_id=stored["creator_profile_id"],fanvue_account_id=stored["fanvue_account_id"],
          relationship_key=stored["relationship_key"],telegram_user_id=stored["telegram_user_id"],
          attention_occurrence_id=evidence["attentionOccurrenceId"],state_fingerprint=evidence["stateFingerprint"],
          root_cause_scope=scope.value,target_operation_id=evidence["targetOperationId"],
          causal_operation_id=evidence["causalOperationId"],action_type=action.value,
          parameters=parameters,
          expected_mutation_entities=entities,
          provider_generation_possible=result.providerGenerationPossible,
          customer_visible_send_possible=result.customerVisibleSendPossible,
          risk_level=result.riskLevel,signature=signature,idempotency_key=idempotency)
        self.repository.add_event("PLAN_CREATED",inspection_id=stored["inspection_id"],
            plan_id=plan_id,event_data={"action":action.value,"signature":signature})
        return plan

    @staticmethod
    def recovery_plan_parameters(evidence, *, disposition_reason=None):
        """Pure planning projection; safe for read-only preflight and tests."""
        parameters={"singleTarget":True,"dispositionReason":disposition_reason}
        if ((evidence.get("recoveryEligibility") or {}).get("category")
                in {"CANONICALLY_CONFIRMED_NOT_DELIVERED",
                    "RECOVERY_CONSTRAINT_FAILURE_NOT_DELIVERED"}):
            from app.services.recovery_execution_constraint_service import (
                RecoveryExecutionConstraintService,
            )
            parameters["recoveryExecutionConstraint"]=(
                RecoveryExecutionConstraintService.authority())
        return parameters

    def approve(self, plan_id, *, creator_profile_id, fanvue_account_id, operator):
        plan=self.repository.approve(plan_id,creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,approved_by=operator)
        if not plan: raise ValueError("Plan is unavailable, expired, or already reviewed.")
        self.repository.add_event("PLAN_APPROVED",plan_id=plan_id,
                                  event_data={"approvedBy":operator})
        return plan

    def reject(self, plan_id, *, creator_profile_id, fanvue_account_id, operator):
        plan=self.repository.reject(plan_id,creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,rejected_by=operator)
        if not plan: raise ValueError("Plan is unavailable or already reviewed.")
        self.repository.add_event("PLAN_REJECTED",plan_id=plan_id,
                                  event_data={"rejectedBy":operator})
        return plan

    def execute(self, plan_id, *, creator_profile_id, fanvue_account_id, operator):
        plan=self.repository.get_plan(plan_id,creator_profile_id=creator_profile_id,
                                      fanvue_account_id=fanvue_account_id)
        if not plan: raise LookupError("Resolution plan was not found.")
        self._validate_plan_shape(plan)
        unsigned={"planId":str(plan["plan_id"]),"inspectionId":str(plan["inspection_id"]),
          "relationshipKey":plan["relationship_key"],"attentionOccurrenceId":plan["attention_occurrence_id"],
          "stateFingerprint":plan["state_fingerprint"],"scope":plan["root_cause_scope"],
          "targetOperationId":str(plan["target_operation_id"]) if plan["target_operation_id"] else None,
          "causalOperationId":str(plan["causal_operation_id"]) if plan["causal_operation_id"] else None,
          "action":plan["action_type"],"idempotencyKey":plan["idempotency_key"]}
        signature=self._sign(unsigned)
        try:
            current=self.evidence.build(creator_profile_id=creator_profile_id,
              fanvue_account_id=fanvue_account_id,telegram_user_id=plan["telegram_user_id"],
              relationship_key=plan["relationship_key"],occurrence_id=plan["attention_occurrence_id"])
        except (LookupError,PermissionError,ValueError) as exc:
            self.repository.mark_stale(plan_id,creator_profile_id=creator_profile_id,
                fanvue_account_id=fanvue_account_id,reason=str(exc))
            self.repository.add_event("PLAN_EXECUTION_REJECTED",plan_id=plan_id,
                event_data={"reason":"RESOLUTION_PLAN_OUT_OF_DATE"})
            raise RuntimeError("RESOLUTION PLAN OUT OF DATE: re-inspection required.") from exc
        action=ResolutionAction(plan["action_type"]); service=self.ACTION_SERVICES[action]
        try:
            execution,reused=self.repository.claim_execution(plan_id,
              creator_profile_id=creator_profile_id,fanvue_account_id=fanvue_account_id,
              signature=signature,current_fingerprint=current["stateFingerprint"],canonical_service=service)
        except RuntimeError as exc:
            self.repository.add_event("PLAN_EXECUTION_REJECTED",plan_id=plan_id,
                event_data={"reason":str(exc)})
            raise
        if reused: return execution
        self.repository.add_event("EXECUTION_CLAIMED",plan_id=plan_id,
            execution_id=execution["execution_id"],
            event_data={"canonicalService":service,"operator":operator})
        try:
            result=self._execute_action(action,plan,current,operator)
            finished=self.repository.finish_execution(execution["execution_id"],status="SUCCEEDED",
                result=result,records_changed=result.get("recordsChanged") or ())
            self.repository.add_event("EXECUTION_SUCCEEDED",plan_id=plan_id,
                execution_id=execution["execution_id"],event_data=result)
            return finished
        except Exception as exc:
            self.repository.finish_execution(execution["execution_id"],status="FAILED",
                result={"error":str(exc),"errorType":type(exc).__name__})
            self.repository.add_event("EXECUTION_FAILED",plan_id=plan_id,
                execution_id=execution["execution_id"],
                event_data={"error":str(exc),"errorType":type(exc).__name__})
            raise

    def _execute_action(self, action, plan, evidence, operator):
        if action in {ResolutionAction.CONFIRM_DELIVERED,
                      ResolutionAction.CONFIRM_NOT_DELIVERED}:
            from app.repositories.operator_delivery_resolution_repository import (
                OperatorDeliveryResolutionRepository,
            )
            delivery=dict(evidence.get("commercialDeliveryEvidence") or {})
            if not delivery.get("qualifyingCommercialPresentation"):
                raise PermissionError("Current evidence no longer authorizes attestation.")
            outcome=("DELIVERED" if action is ResolutionAction.CONFIRM_DELIVERED
                     else "NOT_DELIVERED")
            row,reused=OperatorDeliveryResolutionRepository(
                self.repository.connection_factory).resolve(
                operation_id=plan["target_operation_id"],
                creator_profile_id=plan["creator_profile_id"],
                fanvue_account_id=plan["fanvue_account_id"],
                relationship_key=plan["relationship_key"],
                telegram_user_id=plan["telegram_user_id"],
                telegram_chat_id=int((evidence.get("currentAuthorityOperation") or
                                      evidence.get("causalOperation"))["inboundMessageId"] and
                                     self._chat_id_for_operation(plan["target_operation_id"])),
                purchase_intent_id=UUID(delivery["purchaseIntentId"]),outcome=outcome,
                presentation_mode=delivery["presentationMode"],
                provider_acceptance_evidence=delivery["providerAcceptanceEvidence"],
                provider_readback_evidence=delivery["providerReadbackEvidence"],
                resolved_by=operator,evidence={"evidenceDigest":evidence["evidenceDigest"],
                                               "legacyEvidenceClass":delivery["legacyEvidenceClass"]})
            return {"action":action.value,"outcome":outcome,
                    "provenance":"OPERATOR_ATTESTED","resolutionId":str(row["resolution_id"]),
                    "idempotentReuse":reused,"providerConfirmed":False,
                    "telegramMessageId":row["telegram_message_id"],
                    "recordsChanged":["operator_delivery_resolutions","purchase_intents"]}
        if action is ResolutionAction.ACKNOWLEDGE_ONLY:
            value=self.relationships.acknowledge_attention(
              creator_profile_id=plan["creator_profile_id"],fanvue_account_id=plan["fanvue_account_id"],
              telegram_user_id=plan["telegram_user_id"],occurrence_id=plan["attention_occurrence_id"],
              acknowledged_by=operator)
            return {"action":action.value,"projection":value,
                    "recordsChanged":["conversation_attention_acknowledgements"]}
        if action is ResolutionAction.RESOLVE_AS_SUPERSEDED:
            if not self._superseded(evidence):
                raise PermissionError("Server evidence does not prove authoritative supersession.")
            value=self.relationships.acknowledge_attention(
              creator_profile_id=plan["creator_profile_id"],fanvue_account_id=plan["fanvue_account_id"],
              telegram_user_id=plan["telegram_user_id"],occurrence_id=plan["attention_occurrence_id"],
              acknowledged_by=operator)
            return {"action":action.value,"disposition":"SUPERSEDED","projection":value,
                    "supportingEvidence":evidence["evidenceReferences"],
                    "recordsChanged":["conversation_attention_acknowledgements"]}
        operation=self.ordinary.requeue_historical_corrective(
          target_operation_id=plan["target_operation_id"],
          causal_operation_id=plan["causal_operation_id"],
          creator_profile_id=plan["creator_profile_id"],fanvue_account_id=plan["fanvue_account_id"],
          telegram_user_id=plan["telegram_user_id"],
          occurrence_id=plan["attention_occurrence_id"],
          resolution_plan_id=plan["plan_id"],approved_by=operator,
          idempotency_key=plan["idempotency_key"],
          recovery_execution_constraint=dict(
              (plan.get("parameters") or {}).get("recoveryExecutionConstraint") or {}))
        if not operation: raise RuntimeError("Historical corrective obligation was not requeued.")
        return {"action":action.value,"ordinaryReplyOperationId":str(operation.operation_id),
                "state":operation.state.value,"providerCallPerformed":False,
                "telegramSendPerformed":False,"recordsChanged":["ordinary_chat_reply_operations"]}

    def _chat_id_for_operation(self, operation_id):
        operation=self.ordinary.get(operation_id)
        if not operation: raise LookupError("Ordinary reply operation was not found.")
        return operation.telegram_chat_id

    @staticmethod
    def _superseded(evidence):
        inbound=evidence.get("latestTriggeringInbound") or {}
        outbound=evidence.get("latestConfirmedOutbound") or {}
        return bool(outbound.get("timestamp") and inbound.get("timestamp")
                    and str(outbound["timestamp"]) > str(inbound["timestamp"]))

    @staticmethod
    def _validate_plan_shape(plan):
        if plan["root_cause_scope"] not in {"CUSTOMER_ONLY","MULTIPLE_CUSTOMERS"}:
            raise PermissionError("Customer execution cannot perform global or ambiguous repair.")
        if ResolutionAction(plan["action_type"]) not in EXECUTABLE_ACTIONS:
            raise PermissionError("Resolution action is not executable.")
        if any(plan[name] for name in ("code_change_required","schema_change_required",
               "config_change_required","runtime_restart_required","global_impact_possible")):
            raise PermissionError("Customer plan contains forbidden impact flags.")

    def _sign(self, value):
        if not self.secret: raise RuntimeError("Resolution plan signing secret is not configured.")
        payload=json.dumps(value,sort_keys=True,separators=(",",":"),default=str).encode()
        return hmac.new(self.secret,payload,hashlib.sha256).hexdigest()
