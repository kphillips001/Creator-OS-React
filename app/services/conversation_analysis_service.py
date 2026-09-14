"""Diagnostic-only orchestration with server-owned scope validation."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.models.conversation_analysis import (AnalysisScope, AnalysisSeverity,
    ProviderAnalysis, RootCauseCategory, SCHEMA_VERSION)
from app.repositories.conversation_analysis_repository import ConversationAnalysisRepository
from app.services.conversation_analysis_evidence_service import ConversationAnalysisEvidenceService
from app.services.conversation_analysis_provider import ConversationAnalysisProvider


class ConversationAnalysisService:
    EXECUTABLE=re.compile(r"(^|\s)(sudo|curl|powershell|cmd\.exe|rm\s|delete\s+from|update\s+\w+\s+set|git\s|apply_patch|python\s+-m)(\s|$)",re.I)

    def __init__(self, *, evidence=None, provider=None, repository=None, now=None):
        self.evidence=evidence or ConversationAnalysisEvidenceService()
        self.provider=provider or ConversationAnalysisProvider()
        self.repository=repository or ConversationAnalysisRepository()
        self.now=now or (lambda:datetime.now(timezone.utc))

    def analyze(self, **scope):
        evidence=self.evidence.build(**scope)
        candidate,provider_metadata=self.provider.analyze(evidence)
        result,signatures=self._validate(candidate,evidence,scope)
        similar=self.repository.similar([s["signature"] for s in signatures],
          creator_profile_id=scope["creator_profile_id"],fanvue_account_id=scope["fanvue_account_id"],
          exclude_relationship_key=scope["relationship_key"])
        structural=getattr(self.repository,"structural_similar",lambda *a,**k:[])(
          [s["signature"] for s in signatures],creator_profile_id=scope["creator_profile_id"],
          fanvue_account_id=scope["fanvue_account_id"],
          exclude_telegram_user_id=scope["telegram_user_id"])
        similar=[*similar,*structural]
        labels=sorted({"relationship:"+hashlib.sha256(row["relationship_key"].encode()).hexdigest()[:16]
                       for row in similar})
        similar_summary={"similarCaseCount":len(labels),"relationshipReferences":labels,
                         "searchBasis":"MATCHING_SERVER_FAILURE_SIGNATURE"}
        validated_scopes=[]
        for finding in result["findings"]:
            validated=self._scope_for(finding, len(labels))
            finding["validatedScope"]=validated
            finding["similarCaseCount"]=len(labels) if finding["severity"] in {"MATERIAL","CRITICAL"} else 0
            finding["repairCandidate"]=bool(finding["severity"] in {"MATERIAL","CRITICAL"}
                 and validated not in {"AMBIGUOUS","OBSOLETE"})
            validated_scopes.append(validated)
        overall_scope=("GLOBAL_SYSTEM" if "GLOBAL_SYSTEM" in validated_scopes else
                       "MULTIPLE_CUSTOMERS" if "MULTIPLE_CUSTOMERS" in validated_scopes else
                       "AMBIGUOUS" if "AMBIGUOUS" in validated_scopes else "CONVERSATION_ONLY")
        global_candidate=any(f["repairCandidate"] and f["validatedScope"]=="GLOBAL_SYSTEM"
                             for f in result["findings"])
        result.update({"analysisId":str(uuid4()),"relationshipKey":evidence["relationshipReference"],
          "analyzedAt":self.now().isoformat(),"similarCaseSummary":similar_summary,
          "globalRepairCandidate":global_candidate,"validatedScope":overall_scope,
          "schemaVersion":SCHEMA_VERSION,"staleState":"CURRENT"})
        stored=self.repository.create(analysis_id=UUID(result["analysisId"]),
          creator_profile_id=scope["creator_profile_id"],fanvue_account_id=scope["fanvue_account_id"],
          relationship_key=scope["relationship_key"],telegram_user_id=scope["telegram_user_id"],
          telegram_chat_id=scope["telegram_chat_id"],target_type=scope.get("target_type","CONVERSATION"),
          target_message_reference=scope.get("target_message_reference"),
          evidence_fingerprint=evidence["evidenceFingerprint"],evidence_digest=self.evidence.fingerprint(evidence),
          structured_result=result,validated_scope=overall_scope,
          failure_signatures=[s["signature"] for s in signatures],similar_case_summary=similar_summary,
          global_repair_candidate=global_candidate,provider_metadata=provider_metadata,
          schema_version=SCHEMA_VERSION)
        return self._response(stored,result,"CURRENT")

    def retrieve(self, analysis_id, **scope):
        stored=self.repository.get(analysis_id,creator_profile_id=scope["creator_profile_id"],
            fanvue_account_id=scope["fanvue_account_id"],relationship_key=scope["relationship_key"])
        if not stored: raise LookupError("Conversation analysis was not found.")
        current=self.evidence.build(**scope,target_type=stored["target_type"],
                                   target_message_reference=stored.get("target_message_reference"))
        stale="CURRENT" if current["evidenceFingerprint"]==stored["evidence_fingerprint"] else "STALE"
        result=dict(stored["structured_result"]);result["staleState"]=stale
        if stale=="STALE":result["globalRepairCandidate"]=False
        return self._response(stored,result,stale)

    def _validate(self,candidate:ProviderAnalysis,evidence,scope):
        signatures=evidence.get("serverFailureSignatures") or []
        known_refs={m["messageReference"] for m in evidence["boundedTranscript"]}
        if scope.get("target_type")=="TURN" and scope.get("target_message_reference") not in known_refs:
            raise ValueError("Selected turn is outside the bounded conversation evidence.")
        findings=[]
        for index,finding in enumerate(candidate.findings):
            value=finding.model_dump(mode="json")
            value["findingId"]=f"finding-{index+1}"
            matching=next((s for s in signatures if s["targetMessageReference"]==value["targetMessageReference"]),None)
            conflict=(value["targetMessageReference"] not in known_refs or
              (value["severity"] in {"MATERIAL","CRITICAL"} and
               (not matching or value["rootCauseCategory"] not in matching["allowedRootCauses"])))
            if self.EXECUTABLE.search(value["suggestedCorrection"]): conflict=True
            if conflict:
                value["proposedScope"]="AMBIGUOUS";value["rootCauseCategory"]="UNKNOWN"
                value["suggestedCorrection"]="Manual diagnostic review is required; no repair is authorized."
                value["confidence"]=0.0;value["authorityConflict"]=True
            else:value["authorityConflict"]=False
            value["authoritativeEvidenceSummary"]=(matching["signature"] if matching else
                "No server failure signature; provider interpretation only.")
            findings.append(value)
        return {"conversationSummary":candidate.conversationSummary,
          "overallQuality":candidate.overallQuality.value,"findings":findings,
          "operatorSummary":candidate.operatorSummary},signatures

    @staticmethod
    def _scope_for(finding,similar_count):
        if finding.get("authorityConflict"):return AnalysisScope.AMBIGUOUS.value
        if finding["severity"] not in {"MATERIAL","CRITICAL"}:return AnalysisScope.CONVERSATION_ONLY.value
        if similar_count>=3:return AnalysisScope.GLOBAL_SYSTEM.value
        if similar_count:return AnalysisScope.MULTIPLE_CUSTOMERS.value
        return AnalysisScope.CONVERSATION_ONLY.value

    @staticmethod
    def _response(stored,result,stale):
        return {"analysis":result,"analysisId":str(stored["analysis_id"]),"staleState":stale,
                "findings":result["findings"],"similarCaseSummary":result["similarCaseSummary"]}
