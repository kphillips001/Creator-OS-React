"""Generation-only consumer of the authoritative Phase 1 Peak decision."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class PeakEngagementConversationDirective:
    supplied: bool
    active: bool
    treatment: str | None
    phase1_suppressed_by: str | None
    superseded_by: str | None

    @classmethod
    def from_phase1(cls, decision: Mapping[str, Any] | None, *,
                    ordinary_generation: bool,
                    protected_commercial_semantics: bool,
                    effort_mode: str, sleep_state: str | None):
        phase1 = dict(decision or {})
        treatment = phase1.get("investmentAdjustment")
        phase1_suppressed = phase1.get("suppressedBy")
        authoritative = bool(
            phase1.get("policy") == "PEAK_ENGAGEMENT_V1"
            and phase1.get("active") is True
            and treatment == "ORDINARY_BALANCED_TO_ENGAGED"
            and not phase1_suppressed
        )
        superseded = None
        if authoritative:
            if not ordinary_generation:
                superseded = "NON_ORDINARY_GENERATION"
            elif protected_commercial_semantics:
                superseded = "CURRENT_COMMERCIAL_AUTHORITY"
            elif str(effort_mode or "").upper() in {"MINIMAL", "COMPRESSED"}:
                superseded = "REDUCED_INVESTMENT"
            elif str(sleep_state or "").upper() in {
                "SLEEP_PENDING_SIGNOFF", "OVERRIDE_HOT_COMMERCIAL",
            }:
                superseded = "CONVERSATIONAL_AVAILABILITY_AUTHORITY"
        active = bool(authoritative and superseded is None)
        return cls(bool(phase1), active, treatment if authoritative else None,
                   str(phase1_suppressed) if phase1_suppressed else None,
                   superseded)

    def diagnostics(self) -> dict[str, Any]:
        return {
            "policy": "PEAK_ENGAGEMENT_CONVERSATION_V1",
            "phase1DecisionReceived": self.supplied,
            "conversationalAdjustmentEligible": self.active,
            "suppliedToGeneration": self.active,
            "treatmentRequested": self.treatment,
            "phase1SuppressedBy": self.phase1_suppressed_by,
            "strongerGenerationAuthoritySuperseded": self.superseded_by is not None,
            "supersededBy": self.superseded_by,
        }

    def prompt_block(self) -> str:
        if not self.active:
            return ""
        return """
PEAK ENGAGEMENT ORDINARY-CONVERSATION GUIDANCE
- Be subtly more present and rewarding in this ordinary conversation turn.
- When the customer offers a meaningful detail, opinion, story, humor, playfulness,
  or genuine effort, usually contribute something contextual rather than replying
  with a bare acknowledgement.
- Continue the topic the customer just supplied. Prefer a specific reaction,
  playful observation, mild tease, relevant callback, personal-style contribution,
  or unfinished conversational hook over a generic topic change.
- A question is optional, never a quota. Ask at most one, only when it follows the
  active thread and adds real value. If Ava asked recently, prefer a non-question
  hook. Never ask for known information, stack questions, or conduct an interview.
- Avoid accidental dead ends during an active exchange, but allow a natural close,
  low energy, disengagement, restraint, or sign-off when the context calls for it.
- Do not become longer, clingier, more enthusiastic, more sexual, more flirtatious,
  or more sales-oriented merely because this guidance is active. One concise
  sentence can fully satisfy it.
- This is advisory ordinary-conversation treatment only. Every safety, control,
  freshness, sleep, commercial, buyer, reduced-investment, repetition, persona,
  question-pressure, and final delivery authority remains stronger.
"""
