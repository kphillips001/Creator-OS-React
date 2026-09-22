"""Closed contracts for customer-scoped attention inspection and resolution."""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


SCHEMA_VERSION = "CONVERSATION_ATTENTION_RESOLUTION_V1"


class RootCauseScope(str, Enum):
    CUSTOMER_ONLY = "CUSTOMER_ONLY"
    MULTIPLE_CUSTOMERS = "MULTIPLE_CUSTOMERS"
    GLOBAL_SYSTEM = "GLOBAL_SYSTEM"
    OBSOLETE = "OBSOLETE"
    AMBIGUOUS = "AMBIGUOUS"


class ResolutionAction(str, Enum):
    ACKNOWLEDGE_ONLY = "ACKNOWLEDGE_ONLY"
    REQUEUE_CORRECTIVE_REPLY = "REQUEUE_CORRECTIVE_REPLY"
    RESOLVE_AS_SUPERSEDED = "RESOLVE_AS_SUPERSEDED"
    CONFIRM_DELIVERED = "CONFIRM_DELIVERED"
    CONFIRM_NOT_DELIVERED = "CONFIRM_NOT_DELIVERED"
    WAIT_FOR_AUTOMATION = "WAIT_FOR_AUTOMATION"
    REVIEW_SIMILAR_CASES = "REVIEW_SIMILAR_CASES"
    ESCALATE_GLOBAL_REPAIR = "ESCALATE_GLOBAL_REPAIR"
    NO_AUTOMATED_RESOLUTION = "NO_AUTOMATED_RESOLUTION"


class ResolutionRisk(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class AvaAutoState(str, Enum):
    ON = "ON"
    OFF = "OFF"
    MANUAL = "MANUAL"


class CurrentOperationState(str, Enum):
    REPLY_SCHEDULED = "REPLY_SCHEDULED"
    PROCESSING = "PROCESSING"
    NO_FURTHER_AUTOMATIC_ATTEMPT = "NO_FURTHER_AUTOMATIC_ATTEMPT"
    COMPLETED = "COMPLETED"
    WAITING = "WAITING"


class InspectionNarrative(BaseModel):
    """Provider-owned interpretation only; no authorization-bearing fields."""
    model_config = ConfigDict(extra="forbid")
    whyFlagged: str = Field(max_length=1200)
    currentImpact: str = Field(max_length=1200)
    currentObligation: str = Field(max_length=1200)
    rootCauseSummary: str = Field(max_length=1200)
    recommendedResolutionSummary: str = Field(max_length=1200)
    operatorExplanation: str = Field(max_length=1800)
    confidence: float = Field(ge=0, le=1)
    inspectionWarnings: list[str] = Field(max_length=10)


EXECUTABLE_ACTIONS = frozenset({
    ResolutionAction.ACKNOWLEDGE_ONLY,
    ResolutionAction.RESOLVE_AS_SUPERSEDED,
    ResolutionAction.CONFIRM_DELIVERED,
    ResolutionAction.CONFIRM_NOT_DELIVERED,
    ResolutionAction.REQUEUE_CORRECTIVE_REPLY,
})


class SimilarCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    relationshipKey: str
    attentionOccurrenceId: str
    displayLabel: str


class InspectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schemaVersion: str
    inspectionId: str
    relationshipKey: str
    attentionOccurrenceId: str
    inspectedAt: str
    stateFingerprint: str
    evidenceReferences: list[str]
    failureSignature: str
    whyFlagged: str
    currentImpact: str
    currentObligation: str
    willAvaContinueAutomatically: bool
    avaAutoState: AvaAutoState
    currentOperationState: CurrentOperationState
    isConditionStillRelevant: bool
    rootCauseScope: RootCauseScope
    rootCauseSummary: str
    affectedCurrentCustomersCount: int = Field(ge=0)
    similarCurrentCases: list[SimilarCase]
    futureCustomersPotentiallyAffected: bool
    globalRepairAlreadyExists: bool
    recommendedResolutionType: ResolutionAction
    recommendedResolutionSummary: str
    operatorExplanation: str
    exactProposedActions: list[str]
    customerVisibleSendPossible: bool
    providerGenerationPossible: bool
    codeChangeRequired: bool
    databaseChangeRequired: bool
    schemaChangeRequired: bool
    configChangeRequired: bool
    runtimeRestartRequired: bool
    globalImpactPossible: bool
    riskLevel: ResolutionRisk
    approvalRequired: bool
    dispositionReason: str | None
    confidence: float = Field(ge=0, le=1)
    unsupportedAssertions: list[str]
    inspectionWarnings: list[str]
    cannotSafelyResolveReason: str | None


def inspection_json_schema() -> dict[str, Any]:
    """Strict provider schema contains narrative, never server authority."""
    schema = InspectionNarrative.model_json_schema()
    schema["additionalProperties"] = False
    return {"type": "json_schema", "name": "attention_inspection_v1",
            "schema": schema, "strict": True}
