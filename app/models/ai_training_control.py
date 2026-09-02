"""Typed, account-scoped runtime AI training contracts."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID


class AiTrainingInstructionType(str, Enum):
    CONVERSATION_RULE = "CONVERSATION_RULE"
    SALES_RULE = "SALES_RULE"
    SAFETY_RULE = "SAFETY_RULE"
    SAFETY_HARD_STOP = "SAFETY_HARD_STOP"
    HARD_STOP = "HARD_STOP"
    KNOWLEDGE = "KNOWLEDGE"
    ENGAGEMENT_RULE = "ENGAGEMENT_RULE"


class AiTrainingInstructionStatus(str, Enum):
    DRAFT = "DRAFT"
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"
    ARCHIVED = "ARCHIVED"
    REQUIRES_IMPLEMENTATION = "REQUIRES_IMPLEMENTATION"


@dataclass(frozen=True)
class AiTrainingInstruction:
    instruction_id: UUID
    creator_profile_id: int
    fanvue_account_id: int
    scope: str
    instruction_type: AiTrainingInstructionType
    original_operator_text: str
    normalized_instruction: str
    status: AiTrainingInstructionStatus
    priority: int
    source: str
    classification_reason: str | None
    policy_key: str | None
    enforcement_mode: str
    version: int
    created_at: datetime
    updated_at: datetime
    enabled_at: datetime | None = None
    disabled_at: datetime | None = None
    archived_at: datetime | None = None
    policy_configuration: dict | None = None

    @classmethod
    def from_row(cls, row):
        value = dict(row)
        return cls(
            instruction_id=value["instruction_id"],
            creator_profile_id=int(value["creator_profile_id"]),
            fanvue_account_id=int(value["fanvue_account_id"]),
            scope=value["scope"],
            instruction_type=AiTrainingInstructionType(value["instruction_type"]),
            original_operator_text=value["original_operator_text"],
            normalized_instruction=value["normalized_instruction"],
            status=AiTrainingInstructionStatus(value["status"]),
            priority=int(value["priority"]), source=value["source"],
            classification_reason=value.get("classification_reason"),
            policy_key=value.get("policy_key"),
            enforcement_mode=value.get("enforcement_mode") or "PROMPT",
            version=int(value["version"]), created_at=value["created_at"],
            updated_at=value["updated_at"], enabled_at=value.get("enabled_at"),
            disabled_at=value.get("disabled_at"), archived_at=value.get("archived_at"),
            policy_configuration=dict(value.get("policy_configuration") or {}),
        )
