"""Canonical vocabulary for customer-contact timing decisions."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


class ContactPurpose(str, Enum):
    REACTIVE_CONVERSATION = "REACTIVE_CONVERSATION"
    REACTIVE_COMMERCIAL = "REACTIVE_COMMERCIAL"
    PURCHASE_ACKNOWLEDGEMENT = "PURCHASE_ACKNOWLEDGEMENT"
    SESSION_CONTINUATION = "SESSION_CONTINUATION"
    ACTIVE_OFFER_FOLLOWUP = "ACTIVE_OFFER_FOLLOWUP"
    FREE_ENGAGEMENT = "FREE_ENGAGEMENT"
    RE_ENGAGEMENT = "RE_ENGAGEMENT"
    OUTREACH = "OUTREACH"
    DELAYED_FOLLOWUP = "DELAYED_FOLLOWUP"
    MASS_PPV = "MASS_PPV"


class ContactPolicyResult(str, Enum):
    ALLOW = "ALLOW"
    SUPPRESS = "SUPPRESS"
    DEFER = "DEFER"


@dataclass(frozen=True)
class CustomerContactDecision:
    purpose: ContactPurpose
    reactive: bool
    result: ContactPolicyResult
    reason: str
    priority: int
    competing_interaction: str | None = None
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))

    def to_mapping(self) -> Mapping[str, Any]:
        return MappingProxyType({
            "schemaVersion": "customer_contact_policy_v1",
            "authority": "CustomerContactAuthorityService",
            "purpose": self.purpose.value,
            "reactive": self.reactive,
            "result": self.result.value,
            "reason": self.reason,
            "priority": self.priority,
            "competingActiveInteraction": self.competing_interaction,
            "evidence": dict(self.evidence),
        })
