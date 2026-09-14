"""Closed, non-executable contracts for conversation quality analysis."""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "CONVERSATION_ANALYSIS_V1"


class AnalysisSeverity(str, Enum):
    OK = "OK"
    MINOR = "MINOR"
    MATERIAL = "MATERIAL"
    CRITICAL = "CRITICAL"


class FindingCategory(str, Enum):
    CONTEXTUAL_RELEVANCE = "CONTEXTUAL_RELEVANCE"
    QUESTION_ANSWERING = "QUESTION_ANSWERING"
    CONVERSATIONAL_CONTINUITY = "CONVERSATIONAL_CONTINUITY"
    INTENT_INTERPRETATION = "INTENT_INTERPRETATION"
    COMMERCIAL_INTENT_ACCURACY = "COMMERCIAL_INTENT_ACCURACY"
    PREMATURE_SELLING = "PREMATURE_SELLING"
    MISSED_COMMERCIAL_OPPORTUNITY = "MISSED_COMMERCIAL_OPPORTUNITY"
    PERSONA_CONSISTENCY = "PERSONA_CONSISTENCY"
    TEMPORAL_CONSISTENCY = "TEMPORAL_CONSISTENCY"
    MEMORY_RELEVANCE = "MEMORY_RELEVANCE"
    REPETITION = "REPETITION"
    EXCESSIVE_FOLLOW_UP = "EXCESSIVE_FOLLOW_UP"
    ROBOTIC_LANGUAGE = "ROBOTIC_LANGUAGE"
    WORDINESS = "WORDINESS"
    INAPPROPRIATE_ESCALATION = "INAPPROPRIATE_ESCALATION"
    TURN_OBLIGATION = "TURN_OBLIGATION"
    QUALITY_GATE_EFFECTIVENESS = "QUALITY_GATE_EFFECTIVENESS"


class RootCauseCategory(str, Enum):
    GENERATION_QUALITY = "GENERATION_QUALITY"
    CONTEXT_ASSEMBLY = "CONTEXT_ASSEMBLY"
    MEMORY_RETRIEVAL = "MEMORY_RETRIEVAL"
    TURN_OBLIGATION = "TURN_OBLIGATION"
    COMMERCIAL_CLASSIFICATION = "COMMERCIAL_CLASSIFICATION"
    COMMERCIAL_PROGRESSION = "COMMERCIAL_PROGRESSION"
    SALES_BRAIN = "SALES_BRAIN"
    QUALITY_GATE = "QUALITY_GATE"
    TEMPORAL_CONTEXT = "TEMPORAL_CONTEXT"
    AVAILABILITY = "AVAILABILITY"
    STALE_RESPONSE = "STALE_RESPONSE"
    DELIVERY_LIFECYCLE = "DELIVERY_LIFECYCLE"
    OPERATOR_POLICY = "OPERATOR_POLICY"
    UNKNOWN = "UNKNOWN"


class AnalysisScope(str, Enum):
    CONVERSATION_ONLY = "CONVERSATION_ONLY"
    MULTIPLE_CUSTOMERS = "MULTIPLE_CUSTOMERS"
    GLOBAL_SYSTEM = "GLOBAL_SYSTEM"
    OBSOLETE = "OBSOLETE"
    AMBIGUOUS = "AMBIGUOUS"


class ProviderFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    targetMessageReference: str = Field(max_length=200)
    severity: AnalysisSeverity
    category: FindingCategory
    whatHappened: str = Field(max_length=1000)
    whyItIsProblematic: str = Field(max_length=1000)
    rootCauseCategory: RootCauseCategory
    proposedScope: AnalysisScope
    suggestedCorrection: str = Field(max_length=1000)
    confidence: float = Field(ge=0, le=1)


class ProviderAnalysis(BaseModel):
    """Provider interpretation only. Server authority is deliberately absent."""
    model_config = ConfigDict(extra="forbid")
    conversationSummary: str = Field(max_length=1600)
    overallQuality: AnalysisSeverity
    findings: list[ProviderFinding] = Field(max_length=50)
    operatorSummary: str = Field(max_length=1600)


def provider_json_schema() -> dict[str, Any]:
    schema = ProviderAnalysis.model_json_schema()
    schema["additionalProperties"] = False
    return {"type": "json_schema", "name": "conversation_analysis_v1",
            "schema": schema, "strict": True}


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    targetType: Literal["CONVERSATION", "TURN"] = "CONVERSATION"
    targetMessageReference: str | None = Field(default=None, max_length=200)

