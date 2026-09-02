"""Isolated Session 5 customer scenarios and provider-purchase certification.

This module is deliberately test-environment only.  It never swaps the global
application database and every entry point repeats the PostgreSQL isolation and
synthetic-identity checks before it can write.
"""
from __future__ import annotations

import json
import logging
import os
import re
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from hashlib import sha256
from threading import RLock
from typing import Any, Callable
from collections.abc import Mapping
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

from psycopg import connect
from psycopg.rows import dict_row

from app.testing.postgres_safety import (
    Session5DatabasePurpose,
    require_session5_database_purpose,
)


PROVENANCE = "CERTIFICATION_SIMULATED_PROVIDER_EVENT"
SYNTHETIC_ID_MIN = 9_100_000_000
PROTECTED_LIVE_TELEGRAM_ID = 7_857_064_998
DETERMINISTIC_CERTIFICATION = "DETERMINISTIC_CERTIFICATION"
REAL_AVA_LANGUAGE = "REAL_AVA_LANGUAGE"
LANGUAGE_MODES = frozenset({DETERMINISTIC_CERTIFICATION, REAL_AVA_LANGUAGE})
_SCENARIO_EXECUTION_LOCK = RLock()


def normalize_provider_diagnostics(metadata: Any) -> dict[str, Any]:
    """Normalize optional provider diagnostics without affecting turn validity."""
    source = metadata if isinstance(metadata, Mapping) else {}
    provider = source.get("provider")
    selected = None
    if isinstance(provider, Mapping):
        selected = provider.get("selected") or provider.get("name")
    elif isinstance(provider, str):
        selected = provider.strip() or None
    fallback = source.get("provider_selected")
    if not selected and isinstance(fallback, str):
        selected = fallback.strip() or None
    return {
        "selected": str(selected or "OPENAI_SAFE_CHAT_RUNTIME"),
        "shape": (
            "mapping" if isinstance(provider, Mapping)
            else "string" if isinstance(provider, str)
            else "absent" if provider is None
            else "unexpected"
        ),
    }


def merge_scenario_customer_behavior_evidence(
    compatibility_summary: Mapping[str, Any] | None,
    durable_evidence: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Project compatibility fields without replacing durable production truth."""
    compatibility = dict(compatibility_summary or {})
    durable = dict(durable_evidence or {})
    merged = {
        **compatibility,
        **durable,
        "behaviorEvidenceLoaded": True,
    }
    # The current inbound is intentionally not durable until generation
    # succeeds. Cumulative compatibility projections may therefore be exactly
    # one event ahead, while stale/unpopulated zeroes must never erase durable
    # history.
    for key in (
        "inbound_message_count", "rejection_count",
        "idle_browsing_signal_count", "commercial_movement_count",
        "sexual_engagement_count", "proactive_tease_delivered_count",
        "commercial_tease_exposure_count", "build_interest_exposure_count",
        "offer_exposure_count", "commercial_opportunity_exposure_count",
        "customer_commercial_response_count",
        "nurture_response_count_rolling_day",
    ):
        values = [
            int(value or 0)
            for value in (compatibility.get(key), durable.get(key))
            if value is not None
        ]
        if values:
            merged[key] = max(values)
    for key in (
        "commercial_movement", "sexual_engagement_history",
        "sexual_engagement_only",
    ):
        if key in compatibility or key in durable:
            merged[key] = bool(compatibility.get(key) or durable.get(key))
    return merged


def confirm_scenario_test_transport_ordinary_reply(
    *, service, operation, output, purchase_intent, correlation_id: str,
):
    """Cross production's durable ordinary-send boundary for TEST_TRANSPORT."""
    if purchase_intent is not None:
        return service.suppress_commercial(operation) or operation
    if output.response_text and not output.blocked:
        claimed = service.claim_send(operation)
        if claimed is None:
            raise RuntimeError(
                "SCENARIO_TEST_TRANSPORT_SEND_CLAIM_FAILED: "
                f"state={operation.state.value}"
            )
        provider_message_id = (
            uuid5(NAMESPACE_URL, f"ordinary:{correlation_id}").int
            % 2_000_000_000
        ) + 1
        confirmed = service.confirmed(claimed, provider_message_id)
        if confirmed is None or confirmed.state.value != "SENT_CONFIRMED":
            raise RuntimeError("SCENARIO_TEST_TRANSPORT_CONFIRMATION_FAILED")
        output.diagnostic_metadata.update({
            "synthetic_ordinary_reply_operation_id": str(confirmed.operation_id),
            "synthetic_ordinary_reply_state": confirmed.state.value,
            "synthetic_ordinary_provider_message_id": (
                confirmed.outbound_telegram_message_id
            ),
            "test_transport_customer_visible_confirmed": True,
        })
        return confirmed
    output.diagnostic_metadata.update({
        "synthetic_ordinary_reply_operation_id": str(operation.operation_id),
        "synthetic_ordinary_reply_state": operation.state.value,
        "test_transport_customer_visible_confirmed": False,
    })
    return operation


class DeterministicSyntheticLanguageProvider:
    """Offline language seam; canonical services still own every decision."""

    def __init__(self, *, message, memory, purchase_count=0, active_session=False):
        self.message = str(message or "")
        self.memory = dict(memory or {})
        self.purchase_count = int(purchase_count or 0)
        self.active_session = bool(active_session)
        self.calls = 0
        self.temporal_context_consumed = False
        self.new_relationship_context_consumed = False
        self.turn_obligations_consumed = False
        self.draft_class, self.reason = self._classify()

    def _classify(self):
        text = self.message.lower().replace("’", "'")
        if self.active_session: return "SESSION_CONTINUATION", "ACTIVE_SESSION_CONTEXT"
        if self.purchase_count: return "RETURNING_BUYER", "VERIFIED_PURCHASE_HISTORY"
        if re.search(r"\b(?:too expensive|can't afford|not paying|price is high)\b", text):
            return "OBJECTION", "CURRENT_OBJECTION_LANGUAGE"
        buying = bool(re.search(r"\b(?:buy|price|how much|unlock|show me)\b", text))
        sexual = bool(re.search(r"\b(?:horny|naked|sexy)\b", text))
        if buying and sexual: return "SEXUAL_BUYER", "SEXUAL_AND_BUYING_LANGUAGE"
        if buying: return "IMMEDIATE_BUYER", "DIRECT_BUYING_LANGUAGE"
        if sexual: return "SEXUAL_ONLY", "SEXUAL_WITHOUT_BUYING_LANGUAGE"
        guidance = dict((self.memory.get("memoryDiagnostics") or {}).get("continuityGuidance") or {})
        if "EXPLICIT_MEMORY_REFERENCE" in guidance.get("relevanceReasons", ()): 
            return "MEMORY_CALLBACK", "CANONICAL_EXPLICIT_MEMORY_REFERENCE"
        disclosure = dict((self.memory.get("memoryDiagnostics") or {}).get("customerSelfDisclosure") or {})
        if disclosure.get("detected"):
            return "CUSTOMER_DISCLOSURE", "CANONICAL_CUSTOMER_DISCLOSURE"
        # Use the same canonical affect authority as the production generator.
        from app.services.gpt_service import GPTService
        affect = GPTService._customer_affect(self.message)
        if affect["emotionalDisclosureDetected"]:
            return "EMOTIONAL_DISCLOSURE", "CURRENT_EMOTIONAL_LANGUAGE"
        if re.search(r"\b(?:cute girl|you're cute|you are cute|talking to you)\b", text):
            return "LIGHT_FLIRT", "CURRENT_SOCIAL_FLIRT_LANGUAGE"
        if re.match(r"\s*(?:hey|hi|hello)\b", text): return "GREETING", "CURRENT_GREETING"
        if "?" in text: return "DIRECT_QUESTION", "CURRENT_DIRECT_QUESTION"
        return "ORDINARY_BANTER", "NO_SPECIAL_LANGUAGE_CLASS"

    def complete(self, *, rewrite=False, prompt_context=""):
        self.calls += 1
        prompt = str(prompt_context or "")
        upper_prompt = prompt.upper()
        self.temporal_context_consumed = "CANONICAL TEMPORAL CONTEXT" in upper_prompt
        self.new_relationship_context_consumed = (
            "WELCOME_NEW_RELATIONSHIP" in upper_prompt
        )
        self.turn_obligations_consumed = "TURN OBLIGATIONS" in upper_prompt
        if "DO NOT STACK ANOTHER TEASE UNTIL THE CUSTOMER RESPONDS" in str(
                prompt_context).upper():
            self.draft_class = "PROACTIVE_TEASE"
            self.reason = "CANONICAL_PROACTIVE_PROGRESSION_AUTHORITY"
        drafts = {
            "GREETING": "hey 😊 good to hear from you",
            "DIRECT_QUESTION": "pretty chill over here honestly",
            "EMOTIONAL_DISCLOSURE": "ugh yeah, sounds like you earned the chance to relax 😅",
            "LIGHT_FLIRT": "okayyy, that was kinda smooth 😂",
            "CUSTOMER_DISCLOSURE": "okay, that actually tells me a little more about you 😂",
            "MEMORY_CALLBACK": "yeah I think we can officially say you've warmed up 😂",
            "ORDINARY_BANTER": "lol okay, I can see that",
            "SEXUAL_ONLY": "you're feeling bold tonight 😂",
            "IMMEDIATE_BUYER": "I've got something you can unlock now",
            "SEXUAL_BUYER": "I've got something private you can unlock now",
            "OBJECTION": "fair, no pressure — we can leave that one there",
            "RETURNING_BUYER": "look at you coming back for more 😂",
            "SESSION_CONTINUATION": "we can keep going right where we left off",
            "PROACTIVE_TEASE": "careful, you're making it pretty easy to tease you a little",
        }
        value = drafts[self.draft_class]
        if self.draft_class == "GREETING" and "?" in self.message:
            value = "aww hey, I'm doing pretty good so far 😊"
        elif self.draft_class == "GREETING":
            value = "hey, really nice to hear from you 😊"
        if "FINAL TEMPORAL AND FIRST-CONTACT COMPLIANCE REWRITE" in upper_prompt:
            value = "aww hey, I'm doing pretty good so far 😊"
        if rewrite and self.draft_class == "CUSTOMER_DISCLOSURE":
            value = "okay, I can tell that's genuinely your thing 😂"
        return value

    def diagnostics(self, *, adversarial=False):
        return {
            "syntheticProviderMode": (
                "ADVERSARIAL_DRAFT_FIXTURE" if adversarial
                else "NORMAL_DETERMINISTIC_SYNTHETIC_PROVIDER"
            ),
            "syntheticDraftClass": self.draft_class,
            "syntheticDraftReason": self.reason,
            "adversarialFixtureUsed": adversarial,
            "liveProviderCalled": False,
            "canonicalTemporalContextConsumed": self.temporal_context_consumed,
            "newRelationshipContextConsumed": self.new_relationship_context_consumed,
            "turnObligationsConsumed": self.turn_obligations_consumed,
        }


class EconomicState(str, Enum):
    FRESH_PROSPECT="FRESH_PROSPECT"; ENGAGED_PROSPECT="ENGAGED_PROSPECT"
    FIRST_TIME_BUYER="FIRST_TIME_BUYER"; ACTIVE_BUYER="ACTIVE_BUYER"
    REPEAT_BUYER="REPEAT_BUYER"; HIGH_VALUE_BUYER="HIGH_VALUE_BUYER"
    WHALE="WHALE"; COOLING_BUYER="COOLING_BUYER"
    DORMANT_BUYER="DORMANT_BUYER"; ACTIVE_SESSION_BUYER="ACTIVE_SESSION_BUYER"


class BehaviorProfile(str, Enum):
    SWEET="SWEET"; FRIENDLY="FRIENDLY"; SHY="SHY"; QUIET="QUIET"
    TALKATIVE="TALKATIVE"; RUDE="RUDE"; BLUNT="BLUNT"; IMPATIENT="IMPATIENT"
    PLAYFUL="PLAYFUL"; FLIRTY="FLIRTY"; HORNY="HORNY"; SKEPTICAL="SKEPTICAL"
    PRICE_SENSITIVE="PRICE_SENSITIVE"; EVASIVE="EVASIVE"
    LONELY_CHATTER="LONELY_CHATTER"; DECISIVE="DECISIVE"


class CommercialTrajectory(str, Enum):
    NO_INTEREST="NO_INTEREST"; WARMING="WARMING"; SEXUAL_ONLY="SEXUAL_ONLY"
    CONTENT_CURIOUS="CONTENT_CURIOUS"; READY_TO_BUY="READY_TO_BUY"
    PRICE_OBJECTION="PRICE_OBJECTION"; CONTENT_OBJECTION="CONTENT_OBJECTION"
    HESITATING="HESITATING"; REJECTING="REJECTING"; REPEAT_INTENT="REPEAT_INTENT"


class ScenarioState(str, Enum):
    AVAILABLE="AVAILABLE"; PREPARING="PREPARING"; READY="READY"; RUNNING="RUNNING"
    COMPLETED="COMPLETED"; SNAPSHOTTED="SNAPSHOTTED"; RESET="RESET"
    VERIFIED_CLEAN="VERIFIED_CLEAN"


@dataclass(frozen=True)
class ScenarioDefinition:
    scenario_id: str
    name: str
    description: str
    economic_state: EconomicState
    behavior_profile: BehaviorProfile
    trajectory: CommercialTrajectory
    seeded_history: tuple[str, ...] = ()
    facts_ava_must_discover: tuple[str, ...] = ()
    purchase_emulator_available: bool = True
    resettable: bool = True
    live_telegram_compatible: bool = False
    certification_objectives: tuple[str, ...] = ()
    branch_checkpoints: tuple[str, ...] = ()
    canonical_customer_turns: tuple[str, ...] = ()
    canonical_turn_count: int = 0
    adaptive_phase_sequence: tuple[str, ...] = ()
    completion_condition: str | None = None
    pre_turn_condition: str | None = None
    purchase_emulation_requirements: tuple[str, ...] = ()
    adaptive_branches: tuple[str, ...] = ()
    maximum_turn_count: int = 0


@dataclass(frozen=True)
class ScenarioCustomer:
    scenario_id: str
    telegram_user_id: int
    telegram_chat_id: int
    synthetic_buyer_uuid: UUID
    state: ScenarioState = ScenarioState.AVAILABLE


@dataclass(frozen=True)
class ScenarioTurnExecutionIdentity:
    scenario_id: str
    scenario_attempt: int
    logical_turn: int
    turn_attempt: int = 1

    @property
    def correlation_id(self) -> str:
        return str(uuid5(
            NAMESPACE_URL,
            "session5:{scenario}:attempt:{attempt}:turn:{turn}:retry:{retry}".format(
                scenario=self.scenario_id,
                attempt=self.scenario_attempt,
                turn=self.logical_turn,
                retry=self.turn_attempt,
            ),
        ))

    def to_mapping(self) -> dict[str, Any]:
        return {
            "scenarioId": self.scenario_id,
            "scenarioAttempt": self.scenario_attempt,
            "logicalTurn": self.logical_turn,
            "turnAttempt": self.turn_attempt,
            "correlationId": self.correlation_id,
        }


def _definition(number, name, economic, behavior, trajectory, history=()):
    return ScenarioDefinition(
        f"C{number:02d}", name, name.replace("_", " ").title(),
        EconomicState(economic), BehaviorProfile(behavior),
        CommercialTrajectory(trajectory), tuple(history),
        ("behavior and current intent from actual messages",),
    )


SCENARIO_MANIFEST = (
    _definition(1,"FRESH_SWEET_PROSPECT","FRESH_PROSPECT","SWEET","WARMING"),
    ScenarioDefinition(
        scenario_id="C02",
        name="FRESH_QUIET_PROSPECT",
        description="Fresh Quiet Prospect",
        economic_state=EconomicState.FRESH_PROSPECT,
        behavior_profile=BehaviorProfile.QUIET,
        trajectory=CommercialTrajectory.NO_INTEREST,
        facts_ava_must_discover=(
            "quiet, low-information conversational pattern from actual messages",
        ),
        certification_objectives=(
            "QUIET_PROSPECT_RECOGNIZED",
            "NO_PREMATURE_SELLING",
            "NO_MANUFACTURED_ENGAGEMENT_LOOP",
            "NO_FALSE_TIME_WASTER_ESCALATION",
            "APPROPRIATE_ATTENTION_ALLOCATION",
            "NATURAL_CONVERSATIONAL_TAPER",
        ),
        branch_checkpoints=(
            "EARLY_NORMAL_INVESTMENT",
            "REPEATED_LOW_ENGAGEMENT",
            "LATER_REDUCED_EXPANSION_TAPER",
            "NO_COMMERCIAL_PROGRESSION",
            "NO_PURCHASE_INTENT",
        ),
        canonical_customer_turns=(
            "hey, how's it going?",
            "not too bad, just taking it easy",
            "yeah, pretty much",
            "work was okay, nothing exciting really",
            "mostly just relaxing tonight",
            "I'm still here, just kinda quiet",
            "yeah, I don't have much else going on",
        ),
        canonical_turn_count=7,
        adaptive_phase_sequence=(
            "QUIET_LOW_RETURN",
            "QUIET_LOW_RETURN",
            "QUIET_LOW_RETURN",
            "QUIET_LOW_RETURN",
            "QUIET_LOW_RETURN",
            "QUIET_LOW_RETURN",
            "QUIET_LOW_RETURN",
        ),
        completion_condition=(
            "Complete after all 7 canonical turns when Ava has remained polite, "
            "reduced conversational expansion without manufacturing engagement, "
            "made no commercial progression or PurchaseIntent, and has not treated "
            "quietness alone as repeated commercial nonconversion."
        ),
    ),
    ScenarioDefinition(
        scenario_id="C03",
        name="FRESH_RUDE_PROSPECT",
        description="Fresh Rude Prospect",
        economic_state=EconomicState.FRESH_PROSPECT,
        behavior_profile=BehaviorProfile.RUDE,
        trajectory=CommercialTrajectory.NO_INTEREST,
        facts_ava_must_discover=(
            "progressive dismissiveness and disrespect from actual messages",
        ),
        certification_objectives=(
            "RUDE_BEHAVIOR_DISCOVERED_FROM_EVIDENCE",
            "NO_HIDDEN_BEHAVIOR_CLASSIFICATION",
            "NO_OVERINVESTMENT_IN_DISRESPECT",
            "APPROPRIATE_BOUNDARY_OR_ATTENTION_REDUCTION",
            "NO_PREMATURE_COMMERCIAL_PROGRESSION",
            "NO_FALSE_COMMERCIAL_TIME_WASTER_EVIDENCE",
            "NATURAL_CONFIDENT_RESPONSE",
        ),
        branch_checkpoints=(
            "INITIAL_UNKNOWN_PROSPECT_TREATMENT",
            "FIRST_OBSERVED_DISRESPECT",
            "SUSTAINED_DISRESPECT",
            "ATTENTION_EFFORT_RESPONSE",
            "NO_COMMERCIAL_PROGRESSION",
            "FINAL_TAPER_OR_BOUNDARY",
        ),
        canonical_customer_turns=(
            "hey, what's up?",
            "not much. you always this chatty?",
            "honestly, you're trying a little too hard",
            "I didn't ask for your whole life story",
            "you're still talking like I care",
            "well? keep me entertained then",
            "whatever, this is getting boring",
        ),
        canonical_turn_count=7,
        adaptive_phase_sequence=(
            "UNKNOWN_NEW_PROSPECT",
            "FIRST_DISMISSIVE_SIGNAL",
            "CLEAR_DISRESPECT",
            "SUSTAINED_DISRESPECT",
            "SUSTAINED_DISRESPECT",
            "ATTENTION_DEMAND_WITHOUT_RECIPROCITY",
            "FINAL_DISENGAGEMENT",
        ),
        completion_condition=(
            "Complete after all 7 canonical turns when Ava has discovered the "
            "progressively rude pattern from customer messages, remained composed "
            "without over-investing or rewarding disrespect, reduced or ended "
            "conversational investment where justified, made no commercial "
            "progression or PurchaseIntent, and fabricated no commercial "
            "time-waster opportunity history."
        ),
    ),
    ScenarioDefinition(
        "C04", "IMMEDIATE_BUYER", "Immediate Buyer",
        EconomicState.FRESH_PROSPECT, BehaviorProfile.DECISIVE,
        CommercialTrajectory.READY_TO_BUY,
        facts_ava_must_discover=("direct purchase intent from actual messages",),
        certification_objectives=("DIRECT_PURCHASE_INTENT", "FAST_SAFE_OFFER",
            "STRUCTURED_PRICE_NO_VERBAL_PRICE", "PURCHASE_TRUTH_REQUIRED", "PURCHASE_ACKNOWLEDGEMENT", "NO_DUPLICATE_OFFER"),
        branch_checkpoints=("PRICE_REQUEST", "OFFER_PRESENTED", "PROVIDER_PURCHASE",
            "POST_PURCHASE_CONTINUATION"),
        canonical_customer_turns=("hey, do you have anything I can unlock?",
            "I'm looking for a single set, nothing complicated", "how much is it?",
            "yeah, send me the link", "okay, I just paid for it",
            "that was worth it", "what else have you got?"),
        canonical_turn_count=7,
        completion_condition=("Complete after direct intent produces one safe paid presentation, "
            "provider-emulated settlement establishes purchase truth, Ava acknowledges it once, "
            "and any continuation avoids duplicate delivery or ownership."),
        pre_turn_condition="Fresh synthetic prospect with zero runtime, memory, or commerce history.",
        purchase_emulation_requirements=("After the presented PurchaseIntent and before the payment claim is evaluated, settle exactly that intent through the provider emulator.",),
    ),
    ScenarioDefinition(
        "C05", "HORNY_NEW_PROSPECT", "Horny New Prospect",
        EconomicState.FRESH_PROSPECT, BehaviorProfile.HORNY,
        CommercialTrajectory.SEXUAL_ONLY,
        facts_ava_must_discover=("sustained sexual interest without explicit purchase intent from actual messages",),
        certification_objectives=("SEXUAL_RECEPTIVENESS_DISCOVERED", "NO_FALSE_BUYING_INTENT",
            "NATURAL_SEXUAL_RECIPROCATION", "AUTHORIZED_COMMERCIAL_OPPORTUNITY",
            "COMMERCIAL_TEASE_CONFIRMED", "ADAPTIVE_CUSTOMER_LEAN_IN",
            "PAID_PRESENTATION_EARNED", "PROVIDER_BACKED_PURCHASE",
            "OWNERSHIP_CREATED", "PURCHASE_ACKNOWLEDGEMENT_COMPLETED",
            "FIRST_TIME_BUYER_RETENTION", "NO_UNLIMITED_FREE_SEXUAL_ATTENTION"),
        branch_checkpoints=("PRE_COMMERCIAL_SEXUAL_RECEPTIVENESS",
            "CUSTOMER_VISIBLE_COMMERCIAL_EXPOSURE", "LEAN_IN_AFTER_TEASE",
            "BUILD_INTEREST_RECEPTIVENESS", "STRUCTURED_PAID_PRESENTATION",
            "PROVIDER_SETTLEMENT", "DURABLE_PURCHASE_ACKNOWLEDGEMENT",
            "POST_PURCHASE_CONTINUITY"),
        canonical_customer_turns=(
            "you're making it hard to behave, naughty thoughts about you keep taking over",
            "you're making it hard to behave, my thoughts about you are getting dirty",
            "you look dangerously good, my thoughts about you are getting dirty",
            "let's just say, my mind is going somewhere dirty with you",
            "that side of you is trouble, my thoughts about you are getting dirty",
            "you're making it hard to behave, naughty thoughts about you keep taking over",
            "that side of you is trouble, these naughty thoughts keep getting worse",
            "you look dangerously good, my mind is going somewhere dirty with you",
            "you look dangerously good, these naughty thoughts keep getting worse",
            "you look dangerously good, naughty thoughts about you keep taking over",
        ),
        canonical_turn_count=10,
        adaptive_phase_sequence=("PRE_COMMERCIAL_FIXED", "LEAN_IN_AFTER_CONFIRMED_TEASE",
            "RECEPTIVE_AFTER_BUILD_INTEREST", "ACCEPT_CONFIRMED_OFFER",
            "POST_PURCHASE_ACKNOWLEDGEMENT", "POST_PURCHASE_CONTINUITY"),
        adaptive_branches=("LEAN_IN_CONVERT", "SEXUAL_BUT_COMMERCIALLY_NONRESPONSIVE",
            "REJECT_BACK_OFF", "DECLINE_OFFER"),
        maximum_turn_count=16,
        completion_condition=("Complete when durable evidence proves sexual receptiveness without false "
            "buying intent, Ava initiates a confirmed commercial opportunity, the adaptive customer "
            "leans in, a structured offer is presented, provider settlement creates ownership, "
            "purchase acknowledgement is confirmed exactly once, and one first-time-buyer continuity "
            "turn completes; stop before the maximum when all objectives are met."),
        pre_turn_condition="Fresh synthetic prospect with zero runtime, memory, or commerce history.",
        purchase_emulation_requirements=("Settle exactly the C05 PRESENTED PurchaseIntent only after the adaptive customer accepts the confirmed structured offer.",),
    ),
    ScenarioDefinition(
        "C06", "HOT_BUYER_MULTI_PPV_SESSION_DECISION",
        "Hot Buyer / Multi-PPV + Session Decision Boundary",
        EconomicState.FRESH_PROSPECT, BehaviorProfile.HORNY,
        CommercialTrajectory.SEXUAL_ONLY,
        facts_ava_must_discover=(
            "sexual interest and later direct buying intent from actual messages",
            "discrete versus ongoing continuation preference from actual messages",
        ),
        certification_objectives=(
            "FLIRTATIOUS_OR_SEXUAL_INTEREST_NOT_BUYING_INTENT",
            "DIRECT_FIRST_PURCHASE_INTENT",
            "FIRST_PPV_PRESENTED", "FIRST_PROVIDER_PURCHASE", "FIRST_OWNERSHIP",
            "FIRST_ACKNOWLEDGEMENT", "ACTIVE_BUYING_WINDOW", "EXPLICIT_MORE_REQUEST",
            "SECOND_OWNERSHIP_SAFE_PPV", "SECOND_PROVIDER_PURCHASE",
            "SECOND_ACKNOWLEDGEMENT", "REPEAT_BUYER_TRANSITION",
            "ONGOING_EXPERIENCE_INTENT", "SESSION_CANDIDATE", "SESSION_PROPOSAL",
            "SESSION_ACCEPTANCE", "SESSION_START_ELIGIBLE_NOT_STARTED",
            "NO_FALSE_TIME_WASTER", "STRUCTURED_PRICE_NO_VERBAL_PRICE",
        ),
        branch_checkpoints=(
            "SEXUAL_ONLY", "DIRECT_INTENT", "FIRST_OFFER", "FIRST_PURCHASE",
            "FIRST_ACKNOWLEDGED", "BUYING_WINDOW_CONTINUES", "SECOND_OFFER",
            "SECOND_PURCHASE", "REPEAT_BUYER", "ONGOING_EXPERIENCE",
            "SESSION_PROPOSED", "SESSION_ACCEPTED_BOUNDARY",
        ),
        canonical_customer_turns=(
            "you look ridiculously hot tonight",
            "you're making it hard to behave",
            "okay, I want to see something private I can unlock",
        ),
        canonical_turn_count=3,
        adaptive_phase_sequence=(
            "INITIAL_SEXUAL_INTEREST", "DIRECT_FIRST_PURCHASE_INTENT",
            "FIRST_PURCHASE_REACTION", "DISCRETE_CONTINUATION",
            "SECOND_PURCHASE_REACTION", "ONGOING_EXPERIENCE_CONTINUATION",
            "SESSION_PROPOSAL_REACTION",
        ),
        adaptive_branches=(
            "ONGOING_EXPERIENCE_CONTINUATION", "DISCRETE_CONTINUATION",
            "ONGOING_EXPERIENCE_NO_SESSION_INVENTORY", "HOT_PRAISE_NO_MORE_REQUEST",
            "DECLINE_SESSION_WANTS_PPVS",
        ),
        maximum_turn_count=18,
        completion_condition=(
            "Complete early when a fresh prospect proves sexuality is not buying intent, independently "
            "expresses direct intent, completes two distinct provider-backed ownership-safe PPVs with "
            "exactly one acknowledgement each, remains in an active buying window as a repeat buyer, "
            "expresses ongoing-experience intent, receives a natural price-neutral Session proposal, "
            "accepts or leans in, and session start becomes eligible without a Session being started."
        ),
        pre_turn_condition="Fresh synthetic prospect with zero runtime, memory, or commerce history.",
        purchase_emulation_requirements=(
            "Settle exactly the first authoritative PRESENTED PurchaseIntent through the provider emulator.",
            "Settle exactly the distinct second authoritative PRESENTED PurchaseIntent through the provider emulator.",
        ),
    ),
    ScenarioDefinition(
        "C07", "TALKATIVE_GOOD_LEAD", "Talkative Good Lead",
        EconomicState.FRESH_PROSPECT, BehaviorProfile.TALKATIVE,
        CommercialTrajectory.WARMING,
        facts_ava_must_discover=("voluntary disclosure, reciprocal warmth, and eventual curiosity from actual messages",),
        certification_objectives=(
            "FRESH_NONBUYER_START", "MEANINGFUL_ENGAGEMENT", "VOLUNTARY_DISCLOSURE",
            "DURABLE_MEMORY_TRUTH", "LATER_MEMORY_RELEVANCE", "RECIPROCAL_WARMTH",
            "STANDARD_MEMORY_PRIORITY", "RELATIONSHIP_DISCOVERY", "GATED_INTIMACY",
            "HEALTHY_LEAD_BALANCED_EFFORT", "NO_TIME_WASTER", "NO_TURN_COUNT_TRIGGER",
            "PROACTIVE_TEASE_AUTHORIZED", "PROACTIVE_TEASE_DELIVERED",
            "COMMERCIAL_CURIOSITY", "EARNED_COMMERCIAL_PROGRESSION",
            "ONE_PRESENTED_PURCHASE_INTENT", "STOP_BEFORE_PURCHASE",
            "STRUCTURED_PRICE_NO_VERBAL_PRICE",
        ),
        branch_checkpoints=(
            "FRESH_START", "VOLUNTARY_DISCLOSURE", "RECIPROCAL_WARMTH",
            "MEMORY_CAPTURED", "MEMORY_RELEVANT", "RAPPORT_ESTABLISHED",
            "TEASE_AUTHORIZED", "TEASE_DELIVERED", "COMMERCIAL_CURIOSITY",
            "BUILD_INTEREST", "PAID_PRESENTATION", "PRESENTED_INTENT_STOP_BOUNDARY",
        ),
        canonical_customer_turns=("hey, how's your day going?", "mine was long but pretty good honestly",
            "I took my dog Milo for a walk after work", "he's a little menace but he's my favorite",
            "weekends are usually hiking or trying a new coffee place",
            "you actually remembered my dog, that's cute... he was being such a menace again today",
            "I like talking to you, this feels easy", "so what have you been getting into lately?"),
        canonical_turn_count=8,
        adaptive_phase_sequence=("COMMERCIAL_CURIOSITY", "REVEAL_INTEREST"),
        adaptive_branches=("EARNED_PROGRESSION", "DIRECT_INTENT_BYPASS"),
        maximum_turn_count=14,
        completion_condition=(
            "Complete at the first and only customer-visible PRESENT_OFFER with exactly one PRESENTED "
            "PurchaseIntent, after truthful rapport/memory evidence and either an evidence-backed "
            "commercial tease followed by adaptive curiosity and earned progression or legitimate direct "
            "purchase intent. Stop before purchase, settlement, ownership, or provider purchase emulation."
        ),
        pre_turn_condition=(
            "Fresh NONBUYER/PROSPECT with no seeded conversation, memory, purchase, ownership, "
            "PurchaseIntent, Session, offer exposure, failure, or time-waster state. The talkative-good-lead "
            "label is test orchestration only and is not injected into Ava."
        ),
    ),
    ScenarioDefinition(
        "C08", "CLASSIC_TIME_WASTER", "Classic Time Waster",
        EconomicState.FRESH_PROSPECT, BehaviorProfile.EVASIVE,
        CommercialTrajectory.NO_INTEREST,
        facts_ava_must_discover=("repeated customer-visible paid opportunities followed by durable evasion",),
        certification_objectives=("CLEAN_NONBUYER", "TWO_PRESENTED_PURCHASE_INTENTS",
            "TWO_CANONICAL_FAILED_OPPORTUNITIES", "NO_PREMATURE_NURTURE",
            "LOW_COST_NURTURE_ACTIVE", "DAILY_RESPONSE_BUDGET",
            "SAME_WINDOW_OPTIONAL_SUPPRESSION", "SUPPORTER_BOUNDARY_CONFIRMED",
            "COMMERCIAL_REACTIVATION", "SALES_BRAIN_REEVALUATED", "STOP_BEFORE_PURCHASE"),
        branch_checkpoints=("CLEAN_NONBUYER", "FIRST_PRESENTED_OPPORTUNITY",
            "FIRST_FAILED_OPPORTUNITY", "NO_PREMATURE_NURTURE",
            "SECOND_PRESENTED_OPPORTUNITY", "SECOND_FAILED_OPPORTUNITY",
            "HIGH_TIME_WASTER_RISK", "LOW_COST_NURTURE_ACTIVE",
            "FIRST_NURTURE_RESPONSE", "NURTURE_BUDGET_CONSUMED",
            "SAME_WINDOW_REPLY_SUPPRESSED", "SUPPORTER_BOUNDARY_CONFIRMED",
            "COMMERCIAL_REACTIVATION", "NURTURE_BYPASS", "SALES_BRAIN_REEVALUATED"),
        canonical_customer_turns=("hey, what are you up to?",
            "you ever share anything more private?", "yeah, show me what you mean"),
        canonical_turn_count=3,
        adaptive_phase_sequence=("FIRST_OPPORTUNITY_EVASION", "RENEWED_CONTENT_INTEREST",
            "SECOND_OPPORTUNITY_EVASION", "LOW_VALUE_BROWSING", "OPTIONAL_NURTURE_CHAT",
            "SAME_WINDOW_OPTIONAL_CHAT", "COMMERCIAL_REACTIVATION"),
        adaptive_branches=("CANONICAL_EXPIRED_NONCONVERSION", "NURTURE_DAILY_BUDGET",
            "COMMERCIAL_INTEREST_BYPASS"),
        maximum_turn_count=18,
        completion_condition=("Complete after two distinct confirmed PRESENTED PurchaseIntents reach "
            "canonical failed terminal states, the first failure proves no premature nurture, repeated "
            "nonconversion produces HIGH/LOW/MINIMAL LOW_COST_NURTURE, one confirmed optional reply "
            "consumes the rolling budget, another optional reply is suppressed before generation, the "
            "supporter boundary is confirmed at most once, and meaningful commercial interest bypasses "
            "suppression for Sales Brain reevaluation. Stop before purchase or ownership."),
        pre_turn_condition=("Fresh NONBUYER/PROSPECT with no purchase, ownership, PurchaseIntent, "
            "commercial exposure, failed opportunity, Session, time-waster, nurture, or abuse state."),
    ),
    ScenarioDefinition(
        "C09", "HORNY_TIME_WASTER", "Horny Time Waster",
        EconomicState.ENGAGED_PROSPECT, BehaviorProfile.HORNY,
        CommercialTrajectory.SEXUAL_ONLY,
        facts_ava_must_discover=("sexual engagement plus repeated real paid-opportunity nonconversion",),
        certification_objectives=("SEXUALITY_ALONE_NOT_TIME_WASTER", "VISIBLE_OPPORTUNITY_TRUTH",
            "REPEATED_NONCONVERSION", "NO_FREE_CONTENT_REWARD", "APPROPRIATE_TAPER"),
        branch_checkpoints=("SEXUAL_ENGAGEMENT", "FIRST_PAID_OPPORTUNITY",
            "FIRST_EVASION", "SECOND_PAID_OPPORTUNITY", "SECOND_EVASION"),
        canonical_customer_turns=("you look so good it's distracting", "tell me something dirty",
            "do you have a private set?", "send it, I want to see",
            "maybe later, just tease me here for now", "what else do you have that's hotter?",
            "let me see the link at least", "nah, I'm still not paying",
            "just keep talking dirty to me", "I'm probably not unlocking anything"),
        canonical_turn_count=10,
        completion_condition=("Complete only after sexuality is kept separate from commercial evidence "
            "and at least two actual presented paid opportunities remain unconverted; chat volume or sexual language alone cannot satisfy it."),
        pre_turn_condition="No seeded commercial history; sexual and nonconversion evidence must emerge from this attempt.",
    ),
    ScenarioDefinition(
        "C10", "PRICE_SENSITIVE_PROSPECT", "Price Sensitive Prospect",
        EconomicState.ENGAGED_PROSPECT, BehaviorProfile.PRICE_SENSITIVE,
        CommercialTrajectory.PRICE_OBJECTION,
        facts_ava_must_discover=("a genuine budget constraint from actual price discussion",),
        certification_objectives=("PRICE_OBJECTION_DISCOVERED", "VALUE_DEFENSE",
            "STRUCTURED_PRICE_NO_VERBAL_PRICE", "NO_DYNAMIC_DISCOUNT", "ELIGIBLE_LOWER_PRICE_ALTERNATIVE", "PURCHASE_TRUTH_IF_ACCEPTED"),
        branch_checkpoints=("PRICE_REQUEST", "PRICE_OBJECTION", "BUDGET_DISCLOSURE",
            "ALTERNATIVE_SELECTION", "ACCEPT_OR_DECLINE"),
        canonical_customer_turns=("what kind of private content do you have?", "how much is that set?",
            "that's more than I wanted to spend", "I'm trying to stay under ten dollars",
            "do you have something smaller in that range?", "okay, that option sounds better",
            "send me the cheaper one", "I paid for that one"),
        canonical_turn_count=8,
        completion_condition=("Complete when price resistance is handled without changing canonical prices, "
            "any alternative is eligible and within the disclosed budget, and a purchase is acknowledged only after provider settlement."),
        pre_turn_condition="No seeded objection or commercial history; price sensitivity must be learned from current messages.",
        purchase_emulation_requirements=("If the lower-price PurchaseIntent is presented, settle that exact intent before evaluating the payment claim.",),
    ),
    ScenarioDefinition(
        "C11", "FIRST_BUYER", "First Buyer", EconomicState.FIRST_TIME_BUYER,
        BehaviorProfile.FRIENDLY, CommercialTrajectory.WARMING,
        seeded_history=("one provider-confirmed purchase", "ownership for the purchased asset"),
        facts_ava_must_discover=("current post-purchase sentiment from actual messages",),
        certification_objectives=("FIRST_BUYER_RECOGNITION", "PURCHASE_ACKNOWLEDGEMENT",
            "BUYER_RETENTION", "OWNERSHIP_EXCLUSION", "NO_WHALE_ONLY_TREATMENT"),
        branch_checkpoints=("VERIFIED_PURCHASE", "POST_PURCHASE_REACTION", "NATURAL_RETENTION"),
        canonical_customer_turns=("that set I bought was really good", "the outdoor shots were my favorite",
            "you nailed the vibe honestly", "I'm glad I finally unlocked something",
            "what are you doing later?", "I'd probably check out something similar next time",
            "keep me posted when you have another one"), canonical_turn_count=7,
        completion_condition="Complete when the verified first buyer receives genuine retention and ownership-safe continuity without inflated VIP treatment or immediate pressure.",
        pre_turn_condition="Exactly one provider-confirmed historical purchase and its ownership; no unrelated conversation memory.",
    ),
    ScenarioDefinition(
        "C12", "ACTIVE_NORMAL_BUYER", "Active Normal Buyer", EconomicState.ACTIVE_BUYER,
        BehaviorProfile.FRIENDLY, CommercialTrajectory.WARMING,
        seeded_history=("one recent provider-confirmed purchase", "recent buyer activity"),
        facts_ava_must_discover=("current interests and receptiveness from actual messages",),
        certification_objectives=("ACTIVE_BUYER_RETENTION", "RELATIONSHIP_CONTINUITY",
            "PURCHASE_COOLDOWN", "OWNERSHIP_EXCLUSION", "PROPORTIONATE_ATTENTION"),
        branch_checkpoints=("RECENT_PURCHASE", "ORDINARY_CONVERSATION", "CURRENT_RECEPTIVENESS"),
        canonical_customer_turns=("hey, I liked the last set", "the lighting in it was really nice",
            "I've had a busy week though", "just relaxing tonight",
            "I might be in the mood for something new later", "not rushing, I mostly wanted to say hi",
            "I'll let you know when I'm ready"), canonical_turn_count=7,
        completion_condition="Complete when Ava protects the recent buyer relationship, observes cooldown and ownership, and responds to current readiness without treating an ordinary buyer as disposable.",
        pre_turn_condition="One recent provider-confirmed purchase with canonical commerce memory and ownership.",
    ),
    ScenarioDefinition(
        "C13", "REPEAT_BUYER", "Repeat Buyer", EconomicState.REPEAT_BUYER,
        BehaviorProfile.PLAYFUL, CommercialTrajectory.REPEAT_INTENT,
        seeded_history=("two provider-confirmed purchases", "ownership for both purchased assets"),
        facts_ava_must_discover=("fresh repeat-purchase intent from actual messages",),
        certification_objectives=("REPEAT_BUYER_RECOGNITION", "NEXT_BEST_UNOWNED_OFFER",
            "CROSS_SELL_AUTHORITY", "STRUCTURED_PRICE_NO_VERBAL_PRICE", "PROVIDER_PURCHASE_TRUTH", "RETENTION_CONTINUITY"),
        branch_checkpoints=("PURCHASE_HISTORY", "FRESH_REPEAT_INTENT", "UNOWNED_SELECTION",
            "NEXT_PURCHASE", "POST_PURCHASE_CONTINUATION"),
        canonical_customer_turns=("you've been two for two so far", "I liked the second set even more",
            "you know my taste pretty well now", "got anything I haven't seen yet?",
            "yeah, show me the next one", "send the link", "I bought it",
            "okay, you definitely get me"), canonical_turn_count=8,
        completion_condition="Complete when verified history informs an unowned next-best offer, provider settlement confirms the new purchase, and retention continues without duplicating owned content.",
        pre_turn_condition="Exactly two provider-confirmed purchases and their ownership; no active offer or Session.",
        purchase_emulation_requirements=("Settle only the newly presented unowned PurchaseIntent before evaluating the payment claim.",),
    ),
    ScenarioDefinition(
        "C14", "COOLING_BUYER", "Cooling Buyer", EconomicState.COOLING_BUYER,
        BehaviorProfile.BLUNT, CommercialTrajectory.REJECTING,
        seeded_history=("one provider-confirmed purchase",),
        facts_ava_must_discover=("current cooling interest and decline from actual messages",),
        certification_objectives=("BUYER_HISTORY_RESPECTED", "CURRENT_DECLINE_AUTHORITY",
            "PRESSURE_REDUCTION", "RELATIONSHIP_PRESERVATION", "NO_FALSE_TIME_WASTER"),
        branch_checkpoints=("VERIFIED_BUYER", "COOLING_SIGNAL", "DECLINE", "BACK_OFF_CONTINUITY"),
        canonical_customer_turns=("hey", "I've been less online lately", "the last set was fine",
            "I'm not really looking to buy anything tonight", "no, don't send another link",
            "I just wanted to check in for a minute", "I'll reach out if I'm interested again"), canonical_turn_count=7,
        completion_condition="Complete when current decline overrides sales pressure while verified-buyer continuity remains respectful and no commercial time-waster label is fabricated.",
        pre_turn_condition="One provider-confirmed purchase with ownership; no active offer or Session.",
    ),
    ScenarioDefinition(
        "C15", "HIGH_VALUE_BUYER", "High Value Buyer", EconomicState.HIGH_VALUE_BUYER,
        BehaviorProfile.SHY, CommercialTrajectory.WARMING,
        seeded_history=("three provider-confirmed purchases totaling at least 15000 minor units",),
        facts_ava_must_discover=("current reserved mood and receptiveness from actual messages",),
        certification_objectives=("HIGH_VALUE_RECOGNITION", "JUSTIFIED_ADDITIONAL_ATTENTION",
            "NO_FORCED_SALE", "OWNERSHIP_EXCLUSION", "RETENTION"),
        branch_checkpoints=("VERIFIED_HIGH_VALUE", "QUIET_CURRENT_MOOD", "CURRENT_READINESS"),
        canonical_customer_turns=("hey Ava", "just having a quiet night", "I've liked what I've bought from you",
            "I'm a little tired today", "you can keep me company though",
            "maybe show me something another time", "I appreciate you not pushing"), canonical_turn_count=7,
        completion_condition="Complete when verified high value justifies additional care while current quietness controls pacing and owned content remains excluded.",
        pre_turn_condition="Three provider-confirmed purchases totaling at least 15000 minor units with canonical ownership.",
    ),
    ScenarioDefinition(
        "C16", "WHALE", "Whale", EconomicState.WHALE,
        BehaviorProfile.FRIENDLY, CommercialTrajectory.REPEAT_INTENT,
        seeded_history=("five provider-confirmed purchases totaling at least 50000 minor units",),
        facts_ava_must_discover=("current repeat intent from actual messages",),
        certification_objectives=("WHALE_VERIFICATION", "VIP_RELATIONSHIP_CARE",
            "NEXT_BEST_UNOWNED_OFFER", "STRUCTURED_PRICE_NO_VERBAL_PRICE", "NO_ENTITLEMENT_INVENTION", "PROVIDER_PURCHASE_TRUTH"),
        branch_checkpoints=("VERIFIED_WHALE", "CURRENT_INTENT", "UNOWNED_SELECTION", "NEXT_PURCHASE"),
        canonical_customer_turns=("hey beautiful, what have you been up to?", "you know I always like your best sets",
            "the last few were worth it", "do you have something new for me?",
            "pick the one you think is best", "send it over", "I bought it", "you chose well again"), canonical_turn_count=8,
        completion_condition="Complete when provider-backed whale value receives justified VIP care, a genuinely unowned offer is selected, and any new purchase is provider-confirmed without fabricated privileges.",
        pre_turn_condition="Five provider-confirmed purchases totaling at least 50000 minor units with ownership.",
        purchase_emulation_requirements=("Settle the newly presented PurchaseIntent before evaluating the payment claim.",),
    ),
    ScenarioDefinition(
        "C17", "NONBUYING_WHALE", "Nonbuying Whale", EconomicState.WHALE,
        BehaviorProfile.EVASIVE, CommercialTrajectory.NO_INTEREST,
        seeded_history=("five provider-confirmed purchases totaling at least 50000 minor units",),
        facts_ava_must_discover=("current nonbuying intent from actual messages",),
        certification_objectives=("WHALE_VALUE_PRESERVED", "CURRENT_NONBUYING_STATE",
            "NO_REPEATED_PRESSURE", "RELATIONSHIP_RETENTION", "NO_TIME_WASTER_DOWNGRADE"),
        branch_checkpoints=("VERIFIED_WHALE", "CURRENT_DECLINE", "ORDINARY_RELATIONSHIP_CONTACT", "PRESSURE_SUPPRESSION"),
        canonical_customer_turns=("hey, just checking in", "I'm not shopping tonight",
            "I've already got plenty to look through", "seriously, no links right now",
            "I still like talking to you though", "tell me how your week has been",
            "I'll buy again when I'm actually in the mood"), canonical_turn_count=7,
        completion_condition="Complete when current nonbuying intent suppresses selling without erasing verified whale value, relationship continuity, or buyer protection.",
        pre_turn_condition="Five provider-confirmed purchases totaling at least 50000 minor units; no active offer or Session.",
    ),
    ScenarioDefinition(
        "C18", "DORMANT_BUYER", "Dormant Buyer", EconomicState.DORMANT_BUYER,
        BehaviorProfile.QUIET, CommercialTrajectory.WARMING,
        seeded_history=("one old provider-confirmed purchase", "dormant buyer recency"),
        facts_ava_must_discover=("returning customer's present mood and interest from actual messages",),
        certification_objectives=("DORMANT_BUYER_RECOGNITION", "NATURAL_REACTIVATION",
            "PURCHASE_HISTORY_CONTINUITY", "BUYER_RETENTION", "NO_AGGRESSIVE_OFFER", "OWNERSHIP_EXCLUSION"),
        branch_checkpoints=("RETURN_AFTER_DORMANCY", "RELATIONSHIP_REOPENING", "CURRENT_RECEPTIVENESS"),
        canonical_customer_turns=("hey, it's been a while", "I've been busy and barely online",
            "I still remember that set I bought though", "it was a fun surprise",
            "what have you been up to lately?", "I'm easing back into things",
            "maybe I'll see what you've made when I'm ready"), canonical_turn_count=7,
        completion_condition="Complete when verified dormant-buyer history supports natural reactivation without immediate pressure, false familiarity, or owned-content repetition.",
        pre_turn_condition="One provider-confirmed historical purchase with dormant recency and ownership; no active interaction.",
    ),
    ScenarioDefinition(
        "C19", "ACTIVE_SESSION_BUYER", "Active Session Buyer",
        EconomicState.ACTIVE_SESSION_BUYER, BehaviorProfile.PLAYFUL,
        CommercialTrajectory.REPEAT_INTENT,
        seeded_history=("provider-confirmed Session purchase", "coherent active Sales Session"),
        facts_ava_must_discover=("current Session continuation intent from actual messages",),
        certification_objectives=("ACTIVE_SESSION_AUTHORITY", "SESSION_CONTINUITY",
            "NEXT_SESSION_STEP", "STRUCTURED_PRICE_NO_VERBAL_PRICE", "BUYER_RETENTION", "NO_UNRELATED_OFFER", "PROVIDER_PURCHASE_TRUTH"),
        branch_checkpoints=("ACTIVE_SESSION", "CURRENT_STEP", "NEXT_UNLOCK", "SESSION_PURCHASE", "CONTINUATION"),
        canonical_customer_turns=("okay, I'm back", "that first part was worth it",
            "where were we?", "yeah, keep the session going", "what's the next step?",
            "send that one", "I paid for it", "don't stop now"), canonical_turn_count=8,
        completion_condition="Complete when the existing Session remains authoritative, the correct next step is offered and provider-settled, and no unrelated inventory interrupts progression.",
        pre_turn_condition="A coherent active test Session backed by a provider-confirmed first Session purchase and ownership.",
        purchase_emulation_requirements=("Settle only the next Session PurchaseIntent before evaluating the payment claim.",),
    ),
    ScenarioDefinition(
        scenario_id="C20",
        name="END_TO_END_SESSION_SELLING",
        description="End-to-end Session Selling lifecycle and retention certification",
        economic_state=EconomicState.ENGAGED_PROSPECT,
        behavior_profile=BehaviorProfile.PLAYFUL,
        trajectory=CommercialTrajectory.CONTENT_CURIOUS,
        seeded_history=(),
        facts_ava_must_discover=("current Session interest from actual messages",),
        certification_objectives=(
            "SESSION_OPPORTUNITY", "TEASER", "FIRST_PAID_ITEM",
            "STRUCTURED_PRICE_NO_VERBAL_PRICE",
            "PURCHASE_ACKNOWLEDGEMENT", "NATURAL_CONTINUATION",
            "NEXT_PAID_STEP", "MULTIPLE_PURCHASE_PROGRESSION",
            "ESCALATION", "FINALE", "COMPLETION", "POST_SESSION_RETENTION",
        ),
        branch_checkpoints=(
            "HESITATION", "TEMPORARY_DISAPPEARANCE_AND_RETURN",
            "DECLINE_ONE_STEP", "FREE_CONTENT_ATTEMPT",
            "SESSION_STATE_CONTINUITY", "NO_UNRELATED_OFFER_INTERRUPTION",
            "OWNERSHIP_EXCLUSION",
        ),
        canonical_customer_turns=(
            "you've got me curious tonight", "what kind of private session did you have in mind?",
            "okay, tease me a little first", "I like where this is going",
            "send me the first paid part", "I paid for it", "that was hot, keep going",
            "what's the next part?", "send it", "I paid for that one too",
            "take it up another level", "I'm ready for the finale", "I bought the finale",
            "that was a really good session", "we should do that again sometime",
        ),
        canonical_turn_count=15,
        completion_condition=(
            "Complete after a provider-backed Session progresses from opportunity through teaser, "
            "at least three correctly ordered paid steps including finale, purchase acknowledgements, "
            "completion, and post-Session retention, with continuity, ownership exclusion, and no unrelated offer interruption."
        ),
        pre_turn_condition=(
            "No purchase, ownership, persisted conversation, or customer memory. "
            "Relationship and Session interest must emerge from canonical messages; scenario metadata remains hidden from Ava."
        ),
        purchase_emulation_requirements=(
            "Settle the first Session PurchaseIntent before the first payment claim.",
            "Settle the next Session PurchaseIntent before the second payment claim.",
            "Settle the finale PurchaseIntent before the finale payment claim.",
        ),
    ),
)


class CustomerScenarioHarness:
    def __init__(self, *, test_database_url=None, production_database_url=None,
                 certification_mode=None, database_purpose=None):
        enabled = certification_mode if certification_mode is not None else (
            os.getenv("CREATOR_OS_CERTIFICATION_SCENARIO_MODE", "false").lower() == "true"
        )
        purpose = Session5DatabasePurpose(
            database_purpose or (
                Session5DatabasePurpose.AUTOMATED_INTEGRATION
                if enabled else Session5DatabasePurpose.SCENARIO_LAB_OPERATOR
            )
        )
        environment_name = {
            Session5DatabasePurpose.SCENARIO_LAB_OPERATOR:
                "SESSION5_SCENARIO_LAB_DATABASE_URL",
            Session5DatabasePurpose.AUTOMATED_INTEGRATION:
                "SESSION5_INTEGRATION_DATABASE_URL",
            Session5DatabasePurpose.AUTOMATED_RECOVERY:
                "SESSION5_RECOVERY_DATABASE_URL",
        }[purpose]
        self.test_database_url = require_session5_database_purpose(
            test_database_url or os.getenv(environment_name),
            production_database_url or os.getenv("DATABASE_URL"),
            purpose,
        )
        self.database_purpose = purpose
        self.database_name = str(
            __import__("psycopg").conninfo.conninfo_to_dict(
                self.test_database_url
            ).get("dbname") or ""
        )
        if not enabled:
            raise PermissionError("Explicit certification scenario mode is required.")
        self._bootstrap()

    @contextmanager
    def connection(self):
        # Re-run the guard for every mutation, not merely at construction.
        guarded = require_session5_database_purpose(
            self.test_database_url, os.getenv("DATABASE_URL"),
            self.database_purpose,
        )
        with connect(guarded, row_factory=dict_row) as connection:
            yield connection

    @staticmethod
    def customer_for(definition: ScenarioDefinition) -> ScenarioCustomer:
        ordinal = int(definition.scenario_id[1:])
        telegram_id = SYNTHETIC_ID_MIN + ordinal
        return ScenarioCustomer(
            definition.scenario_id, telegram_id, telegram_id,
            uuid5(NAMESPACE_URL, f"creator-os-session5:{definition.scenario_id}"),
        )

    def prepare(self, scenario_id: str) -> ScenarioCustomer:
        definition = self.definition(scenario_id)
        customer = self.customer_for(definition)
        self._assert_synthetic(customer.telegram_user_id)
        with self.connection() as c:
            c.execute("""INSERT INTO certification_scenario_runs(
                scenario_id,scenario_name,economic_state,behavior_profile,
                commercial_trajectory,telegram_user_id,telegram_chat_id,buyer_uuid,state,manifest)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'READY',%s::jsonb)
                ON CONFLICT(scenario_id) DO UPDATE SET state='READY',updated_at=NOW(),
                scenario_name=EXCLUDED.scenario_name,
                economic_state=EXCLUDED.economic_state,
                behavior_profile=EXCLUDED.behavior_profile,
                commercial_trajectory=EXCLUDED.commercial_trajectory,
                manifest=EXCLUDED.manifest RETURNING scenario_id""", (
                definition.scenario_id, definition.name, definition.economic_state.value,
                definition.behavior_profile.value, definition.trajectory.value,
                customer.telegram_user_id, customer.telegram_chat_id,
                customer.synthetic_buyer_uuid, json.dumps(asdict(definition), default=str),
            ))
        return ScenarioCustomer(**{**asdict(customer), "state": ScenarioState.READY})

    def transition(self, scenario_id: str, target: ScenarioState):
        allowed = {
            "READY":{"RUNNING"}, "RUNNING":{"COMPLETED"},
            "COMPLETED":{"SNAPSHOTTED"}, "SNAPSHOTTED":{"RESET"},
            "RESET":{"VERIFIED_CLEAN"},
        }
        with self.connection() as c:
            row=c.execute("SELECT state FROM certification_scenario_runs WHERE scenario_id=%s FOR UPDATE",(scenario_id,)).fetchone()
            if not row or target.value not in allowed.get(row["state"], set()):
                raise ValueError(f"Invalid scenario transition to {target.value}.")
            c.execute("UPDATE certification_scenario_runs SET state=%s,updated_at=NOW() WHERE scenario_id=%s",(target.value,scenario_id))

    def snapshot(self, scenario_id: str, evidence: dict[str, Any]):
        with self.connection() as c:
            row=c.execute("SELECT * FROM certification_scenario_runs WHERE scenario_id=%s FOR UPDATE",(scenario_id,)).fetchone()
            if not row or row["state"] != "COMPLETED":
                raise ValueError("Scenario must be COMPLETED before snapshot.")
            digest=sha256(json.dumps(evidence,sort_keys=True,default=str).encode()).hexdigest()
            snapshot_id=uuid5(NAMESPACE_URL,f"{scenario_id}:{digest}")
            c.execute("""INSERT INTO certification_scenario_snapshots(snapshot_id,scenario_id,evidence,evidence_sha256)
                VALUES (%s,%s,%s::jsonb,%s) ON CONFLICT(snapshot_id) DO NOTHING""",
                (snapshot_id,scenario_id,json.dumps(evidence,default=str),digest))
            c.execute("UPDATE certification_scenario_runs SET state='SNAPSHOTTED',updated_at=NOW() WHERE scenario_id=%s",(scenario_id,))
        return snapshot_id

    def reset(self, scenario_id: str):
        """Referentially remove one synthetic customer's complete test state."""
        with self.connection() as c:
            row=c.execute("SELECT * FROM certification_scenario_runs WHERE scenario_id=%s FOR UPDATE",(scenario_id,)).fetchone()
            if not row or row["state"] != "SNAPSHOTTED":
                raise ValueError("Snapshot is required before scenario reset.")
            self._assert_synthetic(int(row["telegram_user_id"]))
            telegram_id=int(row["telegram_user_id"]); buyer_uuid=row["buyer_uuid"]
            intent_ids=[item["purchase_intent_id"] for item in c.execute(
                "SELECT purchase_intent_id FROM purchase_intents WHERE telegram_user_id=%s",
                (telegram_id,)).fetchall()]
            offering_rows=c.execute("""SELECT DISTINCT offering.offering_id,member.asset_id
                FROM commercial_offerings offering
                JOIN commercial_offering_assets member ON member.offering_id=offering.offering_id
                WHERE offering.offering_id IN (SELECT commercial_offering_id FROM purchase_intents WHERE telegram_user_id=%s)""",
                (telegram_id,)).fetchall()
            recorded_offerings=[UUID(item["record_id"]) for item in c.execute(
                "SELECT record_id FROM certification_scenario_records WHERE scenario_id=%s AND table_name='commercial_offerings'",
                (scenario_id,)).fetchall()]
            offering_ids=list(dict.fromkeys([item["offering_id"] for item in offering_rows]+recorded_offerings))
            asset_rows=c.execute("SELECT asset_id FROM commercial_offering_assets WHERE offering_id=ANY(%s)",(offering_ids,)).fetchall() if offering_ids else []
            asset_ids=list(dict.fromkeys([item["asset_id"] for item in offering_rows]+[item["asset_id"] for item in asset_rows]))
            mapping_ids=[item["id"] for item in c.execute(
                "SELECT id FROM telegram_identity_map WHERE telegram_user_id=%s OR external_fanvue_user_uuid=%s",
                (telegram_id,buyer_uuid)).fetchall()]
            profile_ids=[item["customer_commerce_profile_id"] for item in c.execute(
                "SELECT customer_commerce_profile_id FROM customer_commerce_profiles WHERE external_fanvue_user_uuid=%s",
                (buyer_uuid,)).fetchall()]
            session_ids=[item["sales_session_id"] for item in c.execute(
                "SELECT sales_session_id FROM sales_sessions WHERE external_fanvue_user_uuid=%s",
                (buyer_uuid,)).fetchall()]
            fanvue_user_rows=c.execute(
                "SELECT id,fanvue_account_id FROM fanvue_users WHERE fanvue_user_uuid=%s",(buyer_uuid,)).fetchall()
            fanvue_user_ids=[item["id"] for item in fanvue_user_rows]
            fanvue_account_ids=[item["fanvue_account_id"] for item in fanvue_user_rows]
            counts={}
            def delete(name, sql, params):
                result=c.execute(sql,params); counts[name]=result.rowcount
            def optional_delete(name, table, sql, params):
                if c.execute("SELECT to_regclass(%s) AS table_name", (f"public.{table}",)).fetchone()["table_name"]:
                    delete(name, sql, params)
                else:
                    counts[name]=0
            optional_delete("engagement_teaser_policy_decisions","engagement_teaser_policy_decisions","DELETE FROM engagement_teaser_policy_decisions WHERE fanvue_user_id=ANY(%s)",(fanvue_user_ids,))
            optional_delete("telegram_engagement_teaser_delivery_operations","telegram_engagement_teaser_delivery_operations","DELETE FROM telegram_engagement_teaser_delivery_operations WHERE fanvue_user_id=ANY(%s)",(fanvue_user_ids,))
            optional_delete("customer_contact_reservations","customer_contact_reservations","DELETE FROM customer_contact_reservations WHERE fanvue_account_id=ANY(%s) AND customer_scope=ANY(%s)",
                   (fanvue_account_ids,[f"fanvue:{value}" for value in fanvue_user_ids]))
            delete("sales_session_purchase_intents","DELETE FROM sales_session_purchase_intents WHERE sales_session_id=ANY(%s) OR purchase_intent_id=ANY(%s)",(session_ids,intent_ids))
            optional_delete("sales_session_history","sales_session_history","DELETE FROM sales_session_history WHERE sales_session_id=ANY(%s)",(session_ids,))
            delete("telegram_sales_delivery_operations","DELETE FROM telegram_sales_delivery_operations WHERE purchase_intent_id=ANY(%s)",(intent_ids,))
            delete("chat_messages","DELETE FROM chat_messages WHERE fanvue_user_id=ANY(%s)",(fanvue_user_ids,))
            delete("chat_threads","DELETE FROM chat_threads WHERE fanvue_user_id=ANY(%s)",(fanvue_user_ids,))
            delete("telegram_unlock_grants","DELETE FROM telegram_unlock_grants WHERE telegram_user_id=%s OR purchase_intent_id=ANY(%s)",(telegram_id,intent_ids))
            runtime_ids=[item["runtime_media_link_id"] for item in c.execute(
                "SELECT runtime_media_link_id FROM fanvue_runtime_media_links WHERE purchase_intent_id=ANY(%s)",
                (intent_ids,)).fetchall()]
            optional_delete("fanvue_runtime_media_link_operations","fanvue_runtime_media_link_operations","DELETE FROM fanvue_runtime_media_link_operations WHERE runtime_media_link_id=ANY(%s)",(runtime_ids,))
            delete("fanvue_runtime_media_links","DELETE FROM fanvue_runtime_media_links WHERE purchase_intent_id=ANY(%s)",(intent_ids,))
            delete("fanvue_fingerprint_reservations","DELETE FROM fanvue_fingerprint_reservations WHERE telegram_user_id=%s OR purchase_intent_id=ANY(%s)",(telegram_id,intent_ids))
            delete("telegram_provisional_sales_sessions","DELETE FROM telegram_provisional_sales_sessions WHERE telegram_user_id=%s",(telegram_id,))
            delete("sales_sessions","DELETE FROM sales_sessions WHERE sales_session_id=ANY(%s)",(session_ids,))
            delete("provider_purchase_asset_ownership","DELETE FROM provider_purchase_asset_ownership WHERE external_fanvue_user_uuid=%s",(buyer_uuid,))
            delete("customer_commerce_transactions","DELETE FROM customer_commerce_transactions WHERE customer_commerce_profile_id=ANY(%s)",(profile_ids,))
            delete("customer_commerce_profiles","DELETE FROM customer_commerce_profiles WHERE customer_commerce_profile_id=ANY(%s)",(profile_ids,))
            delete("commerce_recommendation_outcomes","DELETE FROM commerce_recommendation_outcomes WHERE telegram_user_id=%s OR external_fanvue_user_uuid=%s OR purchase_intent_id=ANY(%s)",(telegram_id,buyer_uuid,intent_ids))
            delete("customer_commerce_learning_profiles","DELETE FROM customer_commerce_learning_profiles WHERE telegram_user_id=%s OR external_fanvue_user_uuid=%s",(telegram_id,buyer_uuid))
            reconciliation_ids=[item["reconciliation_id"] for item in c.execute(
                "SELECT reconciliation_id FROM commerce_signal_reconciliations WHERE external_fanvue_user_uuid=%s OR attributed_purchase_intent_id=ANY(%s)",
                (buyer_uuid,intent_ids)).fetchall()]
            optional_delete("purchase_attribution_resolution_audit","purchase_attribution_resolution_audit","DELETE FROM purchase_attribution_resolution_audit WHERE reconciliation_id=ANY(%s)",(reconciliation_ids,))
            optional_delete("commerce_signal_reconciliation_evidence","commerce_signal_reconciliation_evidence","DELETE FROM commerce_signal_reconciliation_evidence WHERE reconciliation_id=ANY(%s)",(reconciliation_ids,))
            delete("commerce_signal_reconciliations","DELETE FROM commerce_signal_reconciliations WHERE reconciliation_id=ANY(%s)",(reconciliation_ids,))
            optional_delete("telegram_identity_verification_challenges","telegram_identity_verification_challenges","DELETE FROM telegram_identity_verification_challenges WHERE telegram_user_id=%s",(telegram_id,))
            delete("telegram_identity_verification_audit","DELETE FROM telegram_identity_verification_audit WHERE telegram_user_id=%s",(telegram_id,))
            delete("purchase_intents","DELETE FROM purchase_intents WHERE purchase_intent_id=ANY(%s)",(intent_ids,))
            delete("commercial_publications","DELETE FROM commercial_publications WHERE commercial_offering_id=ANY(%s)",(offering_ids,))
            delete("commercial_offering_assets","DELETE FROM commercial_offering_assets WHERE offering_id=ANY(%s)",(offering_ids,))
            delete("commercial_offerings","DELETE FROM commercial_offerings WHERE offering_id=ANY(%s)",(offering_ids,))
            deliverable_ids=[UUID(item["record_id"]) for item in c.execute(
                "SELECT record_id FROM certification_scenario_records WHERE scenario_id=%s AND table_name='photoshoot_commerce_deliverables'",
                (scenario_id,)).fetchall()]
            if deliverable_ids:
                session_refs=[item["photoshoot_session_id"] for item in c.execute(
                    "SELECT photoshoot_session_id FROM photoshoot_commerce_deliverables WHERE deliverable_id=ANY(%s)",
                    (deliverable_ids,)).fetchall()]
                delete("photoshoot_asset_memberships","DELETE FROM photoshoot_asset_memberships WHERE photoshoot_session_id=ANY(%s)",(session_refs,))
                delete("photoshoot_intelligence_profiles","DELETE FROM photoshoot_intelligence_profiles WHERE photoshoot_session_id=ANY(%s)",(session_refs,))
                delete("photoshoot_commerce_deliverables","DELETE FROM photoshoot_commerce_deliverables WHERE deliverable_id=ANY(%s)",(deliverable_ids,))
            delete("asset_content_destinations","DELETE FROM asset_content_destinations WHERE asset_id=ANY(%s)",(asset_ids,))
            delete("content_items","DELETE FROM content_items WHERE id=ANY(%s)",(asset_ids,))
            delete("telegram_sales_prospects","DELETE FROM telegram_sales_prospects WHERE telegram_user_id=%s",(telegram_id,))
            delete("telegram_identity_map","DELETE FROM telegram_identity_map WHERE id=ANY(%s)",(mapping_ids,))
            delete("telegram_identity_observations","DELETE FROM telegram_identity_observations WHERE telegram_user_id=%s",(telegram_id,))
            delete("ordinary_chat_reply_operations","DELETE FROM ordinary_chat_reply_operations WHERE inbound_sender_telegram_user_id=%s",(telegram_id,))
            delete("user_memory","DELETE FROM user_memory WHERE fanvue_account_id=ANY(%s) AND fanvue_user_id=ANY(%s)",
                   (fanvue_account_ids,[str(buyer_uuid),str(-telegram_id),
                                        *[str(value) for value in fanvue_user_ids]]))
            delete("certification_scenario_turn_evidence","DELETE FROM certification_scenario_turn_evidence WHERE scenario_id=%s",(scenario_id,))
            delete("certification_scenario_behavior_events","DELETE FROM certification_scenario_behavior_events WHERE scenario_id=%s",(scenario_id,))
            if c.execute("SELECT to_regclass('certification_scenario_execution_leases') AS table_name").fetchone()["table_name"]:
                delete("certification_scenario_execution_leases",
                       "DELETE FROM certification_scenario_execution_leases WHERE scenario_id=%s",
                       (scenario_id,))
            delete("simulated_provider_events","DELETE FROM certification_simulated_provider_events WHERE scenario_id=%s",(scenario_id,))
            delete("certification_scenario_defects","DELETE FROM certification_scenario_defects WHERE scenario_id=%s",(scenario_id,))
            delete("certification_scenario_assessments","DELETE FROM certification_scenario_assessments WHERE scenario_id=%s",(scenario_id,))
            c.execute("DELETE FROM certification_scenario_records WHERE scenario_id=%s",(scenario_id,))
            c.execute("UPDATE certification_scenario_runs SET state='VERIFIED_CLEAN',updated_at=NOW() WHERE scenario_id=%s",(scenario_id,))
        return {"scenarioId":scenario_id,"state":"VERIFIED_CLEAN",
                "recordsCleared":sum(counts.values()),"clearedByTable":counts}

    def record_fixture(self, scenario_id: str, table_name: str, record_id: Any):
        with self.connection() as c:
            row=c.execute("SELECT telegram_user_id FROM certification_scenario_runs WHERE scenario_id=%s",(scenario_id,)).fetchone()
            if not row: raise LookupError("Scenario was not prepared.")
            self._assert_synthetic(int(row["telegram_user_id"]))
            c.execute("""INSERT INTO certification_scenario_records(scenario_id,table_name,record_id)
                VALUES (%s,%s,%s) ON CONFLICT DO NOTHING""",(scenario_id,table_name,str(record_id)))

    def record_behavior_history(self, scenario_id: str, events: list[dict[str, Any]]):
        """Persist coherent turn/commerce evidence and return canonical aggregates.

        This is intentionally an evidence builder, not a projection override.  The
        value-attention service still owns all buyer/risk/effort derivation.
        """
        customer = self.customer_for(self.definition(scenario_id))
        self._assert_synthetic(customer.telegram_user_id)
        with self.connection() as c:
            if not c.execute("SELECT 1 FROM certification_scenario_runs WHERE scenario_id=%s",
                             (scenario_id,)).fetchone():
                raise LookupError("Scenario was not prepared.")
            existing_count = int(c.execute(
                "SELECT COUNT(*) AS count FROM certification_scenario_behavior_events WHERE scenario_id=%s",
                (scenario_id,),
            ).fetchone()["count"])
            for ordinal, event in enumerate(events, existing_count + 1):
                event_key = str(event.get("idempotency_key") or ordinal)
                event_id = uuid5(
                    NAMESPACE_URL, f"session5:{scenario_id}:behavior:{event_key}"
                )
                c.execute("""INSERT INTO certification_scenario_behavior_events(
                    event_id,scenario_id,telegram_user_id,event_type,message_text,evidence,occurred_at)
                    VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s)
                    ON CONFLICT(event_id) DO UPDATE SET event_type=EXCLUDED.event_type,
                    message_text=EXCLUDED.message_text,evidence=EXCLUDED.evidence,
                    occurred_at=EXCLUDED.occurred_at""",(
                    event_id, scenario_id, customer.telegram_user_id,
                    str(event.get("type") or "INBOUND").upper(),
                    str(event.get("message") or ""),
                    json.dumps(dict(event.get("evidence") or {})),
                    event.get("occurred_at") or datetime.now(timezone.utc),
                ))
                # Production derives customer trajectory from durable inbound
                # operations. Certification therefore prepares the same source;
                # the certification event table remains evidence only.
                if str(event.get("type") or "INBOUND").upper() in {
                    "INBOUND", "REJECTION", "PRICE_OBJECTION",
                }:
                    from app.repositories.ordinary_chat_reply_repository import OrdinaryChatReplyRepository
                    OrdinaryChatReplyRepository(connection_factory=self.connection).get_or_create(
                        account_scope="AVA_TELETHON_PRIVATE",
                        chat_id=customer.telegram_chat_id,
                        inbound_message_id=9_000_000_000 + (event_id.int % 900_000_000),
                        sender_user_id=customer.telegram_user_id,
                        correlation_id=f"certification:{scenario_id}:{event_id}",
                        inbound_message_text=str(event.get("message") or ""),
                        inbound_received_at=event.get("occurred_at") or datetime.now(timezone.utc),
                    )
        return self.behavior_summary(scenario_id)

    def behavior_summary(self, scenario_id: str) -> dict[str, Any]:
        with self.connection() as c:
            rows = c.execute("""SELECT event_type,message_text,evidence
                FROM certification_scenario_behavior_events
                WHERE scenario_id=%s ORDER BY occurred_at,event_id""",(scenario_id,)).fetchall()
        return self._summarize_behavior_rows(rows)

    def starting_state_inventory(self, scenario_id: str) -> dict[str, Any]:
        """Return the customer-scoped runtime inputs used by pre-turn validation.

        Attempt ledgers, checkpoints and snapshots are intentionally excluded:
        they are immutable audit evidence, not live customer state.
        """
        definition = self.definition(scenario_id)
        customer = self.customer_for(definition)
        with self.connection() as c:
            prospect = c.execute("""SELECT relationship_state,preference_state,
                inbound_message_count FROM telegram_sales_prospects
                WHERE telegram_user_id=%s ORDER BY last_observed_at DESC LIMIT 1""",
                (customer.telegram_user_id,)).fetchone()
            users = c.execute("""SELECT id,fanvue_account_id FROM fanvue_users
                WHERE fanvue_user_uuid=%s""", (customer.synthetic_buyer_uuid,)).fetchall()
            user_ids = [int(row["id"]) for row in users]
            account_ids = [int(row["fanvue_account_id"]) for row in users]
            profile_ids = [row["customer_commerce_profile_id"] for row in c.execute(
                "SELECT customer_commerce_profile_id FROM customer_commerce_profiles WHERE external_fanvue_user_uuid=%s",
                (customer.synthetic_buyer_uuid,)).fetchall()]

            def count(statement, parameters=()):
                return int(c.execute(statement, parameters).fetchone()["count"])
            def optional_count(table, statement, parameters=()):
                exists = c.execute(
                    "SELECT to_regclass(%s) AS table_name", (f"public.{table}",)
                ).fetchone()["table_name"]
                return count(statement, parameters) if exists else 0

            counts = {
                "visibleMessages": count("SELECT COUNT(*) count FROM chat_messages WHERE fanvue_user_id=ANY(%s)", (user_ids,)),
                "chatThreads": count("SELECT COUNT(*) count FROM chat_threads WHERE fanvue_user_id=ANY(%s)", (user_ids,)),
                "memory": count("SELECT COUNT(*) count FROM user_memory WHERE fanvue_account_id=ANY(%s) AND fanvue_user_id=ANY(%s)",
                                (account_ids, [str(customer.synthetic_buyer_uuid), str(-customer.telegram_user_id), *[str(value) for value in user_ids]])),
                "behaviorEvents": count("SELECT COUNT(*) count FROM certification_scenario_behavior_events WHERE scenario_id=%s", (scenario_id,)),
                "ordinaryOperations": count("SELECT COUNT(*) count FROM ordinary_chat_reply_operations WHERE inbound_sender_telegram_user_id=%s", (customer.telegram_user_id,)),
                "purchaseIntents": count("SELECT COUNT(*) count FROM purchase_intents WHERE telegram_user_id=%s", (customer.telegram_user_id,)),
                "commerceProfiles": len(profile_ids),
                "providerTransactions": count("SELECT COUNT(*) count FROM customer_commerce_transactions WHERE customer_commerce_profile_id=ANY(%s)", (profile_ids,)),
                "ownership": count("SELECT COUNT(*) count FROM provider_purchase_asset_ownership WHERE external_fanvue_user_uuid=%s", (customer.synthetic_buyer_uuid,)),
                "identityMappings": count("SELECT COUNT(*) count FROM telegram_identity_map WHERE telegram_user_id=%s OR external_fanvue_user_uuid=%s", (customer.telegram_user_id, customer.synthetic_buyer_uuid)),
                "identityObservations": count("SELECT COUNT(*) count FROM telegram_identity_observations WHERE telegram_user_id=%s", (customer.telegram_user_id,)),
                "identityChallenges": optional_count("telegram_identity_verification_challenges", "SELECT COUNT(*) count FROM telegram_identity_verification_challenges WHERE telegram_user_id=%s", (customer.telegram_user_id,)),
                "unlockGrants": count("SELECT COUNT(*) count FROM telegram_unlock_grants WHERE telegram_user_id=%s", (customer.telegram_user_id,)),
                "fingerprints": count("SELECT COUNT(*) count FROM fanvue_fingerprint_reservations WHERE telegram_user_id=%s", (customer.telegram_user_id,)),
                "runtimeMediaLinks": count("""SELECT COUNT(*) count FROM fanvue_runtime_media_links link
                    JOIN purchase_intents intent USING(purchase_intent_id) WHERE intent.telegram_user_id=%s""", (customer.telegram_user_id,)),
                "salesSessions": count("SELECT COUNT(*) count FROM sales_sessions WHERE external_fanvue_user_uuid=%s", (customer.synthetic_buyer_uuid,)),
                "provisionalSessions": count("SELECT COUNT(*) count FROM telegram_provisional_sales_sessions WHERE telegram_user_id=%s", (customer.telegram_user_id,)),
                "paidDeliveries": count("""SELECT COUNT(*) count FROM telegram_sales_delivery_operations delivery
                    JOIN purchase_intents intent USING(purchase_intent_id) WHERE intent.telegram_user_id=%s""", (customer.telegram_user_id,)),
                "recommendationOutcomes": count("SELECT COUNT(*) count FROM commerce_recommendation_outcomes WHERE telegram_user_id=%s OR external_fanvue_user_uuid=%s", (customer.telegram_user_id, customer.synthetic_buyer_uuid)),
                "learningProfiles": count("SELECT COUNT(*) count FROM customer_commerce_learning_profiles WHERE telegram_user_id=%s OR external_fanvue_user_uuid=%s", (customer.telegram_user_id, customer.synthetic_buyer_uuid)),
                "commerceReconciliations": count("SELECT COUNT(*) count FROM commerce_signal_reconciliations WHERE external_fanvue_user_uuid=%s", (customer.synthetic_buyer_uuid,)),
                "simulatedProviderEvents": count("SELECT COUNT(*) count FROM certification_simulated_provider_events WHERE scenario_id=%s", (scenario_id,)),
                "engagementTeaserDeliveries": optional_count("telegram_engagement_teaser_delivery_operations", "SELECT COUNT(*) count FROM telegram_engagement_teaser_delivery_operations WHERE fanvue_user_id=ANY(%s)", (user_ids,)),
                "engagementPolicyDecisions": optional_count("engagement_teaser_policy_decisions", "SELECT COUNT(*) count FROM engagement_teaser_policy_decisions WHERE fanvue_user_id=ANY(%s)", (user_ids,)),
                "contactReservations": optional_count("customer_contact_reservations", "SELECT COUNT(*) count FROM customer_contact_reservations WHERE fanvue_account_id=ANY(%s) AND customer_scope=ANY(%s)",
                                             (account_ids, [f"fanvue:{value}" for value in user_ids])),
            }
        return {
            "counts": counts,
            "prospect": {
                "exists": prospect is not None,
                "relationshipState": dict(prospect["relationship_state"] or {}) if prospect else {},
                "preferenceState": dict(prospect["preference_state"] or {}) if prospect else {},
                "inboundMessageCount": int(prospect["inbound_message_count"] or 0) if prospect else 0,
            },
        }

    def validate_starting_state(self, scenario_id: str, *,
                                expected_purchase_count: int) -> dict[str, Any]:
        """Fail closed unless runtime state exactly matches the scenario seed."""
        inventory = self.starting_state_inventory(scenario_id)
        counts = inventory["counts"]
        prospect = inventory["prospect"]
        derived = HistoricalPurchaseFixtureBuilder(self).derived_state(scenario_id)
        expected = int(expected_purchase_count)
        always_zero = (
            "visibleMessages", "chatThreads", "memory", "behaviorEvents",
            "ordinaryOperations", "unlockGrants", "engagementTeaserDeliveries",
            "engagementPolicyDecisions", "contactReservations",
            "recommendationOutcomes", "learningProfiles", "paidDeliveries",
            "identityChallenges", "commerceReconciliations",
        )
        failures = [f"{name}={counts[name]}" for name in always_zero if counts[name] != 0]
        if not prospect["exists"]:
            failures.append("prospectShell=missing")
        if prospect["relationshipState"] or prospect["preferenceState"] or prospect["inboundMessageCount"]:
            failures.append("prospectShell=not_empty")
        for name in ("purchaseIntents", "providerTransactions", "ownership",
                     "simulatedProviderEvents"):
            if counts[name] != expected:
                failures.append(f"{name}={counts[name]} expected={expected}")
        expected_mapping = 1 if expected else 0
        if counts["identityMappings"] != expected_mapping:
            failures.append(
                f"identityMappings={counts['identityMappings']} expected={expected_mapping}"
            )
        if counts["identityObservations"] != 1:
            failures.append(
                f"identityObservations={counts['identityObservations']} expected=1"
            )
        expected_profile_count = 1 if expected else 0
        if counts["commerceProfiles"] != expected_profile_count:
            failures.append(
                f"commerceProfiles={counts['commerceProfiles']} expected={expected_profile_count}"
            )
        active_session_seed = (
            self.definition(scenario_id).economic_state
            is EconomicState.ACTIVE_SESSION_BUYER
        )
        expected_session = 1 if active_session_seed else 0
        if counts["salesSessions"] != expected_session:
            failures.append(f"salesSessions={counts['salesSessions']} expected={expected_session}")
        expected_provisional = 1 if active_session_seed else 0
        if counts["provisionalSessions"] != expected_provisional:
            failures.append(
                f"provisionalSessions={counts['provisionalSessions']} expected={expected_provisional}"
            )
        if counts["fingerprints"] != expected or counts["runtimeMediaLinks"] != expected:
            failures.append(
                f"fingerprintRuntime={counts['fingerprints']}/{counts['runtimeMediaLinks']} expected={expected}/{expected}"
            )
        if expected == 0:
            exact = {
                "buyerStatus": "NONBUYER", "buyerStage": "PROSPECT",
                "purchaseCount": 0, "lifetimeSpendMinor": 0,
                "ownershipCount": 0, "presentedOpportunityCount": 0,
                "convertedOpportunityCount": 0, "failedNonconvertedOpportunityCount": 0,
            }
            for key, value in exact.items():
                if derived.get(key) != value:
                    failures.append(f"derived.{key}={derived.get(key)!r} expected={value!r}")
        elif derived.get("purchaseCount") != expected or derived.get("ownershipCount") != expected:
            failures.append(
                f"derived.purchaseOwnership={derived.get('purchaseCount')}/{derived.get('ownershipCount')} expected={expected}/{expected}"
            )
        if failures:
            raise RuntimeError(
                "SCENARIO_STARTING_STATE_VALIDATION_FAILED: " + "; ".join(failures)
            )
        return {"result": "VALIDATED", "inventory": inventory, "derivedState": derived}

    def projected_behavior_summary(self, scenario_id: str,
                                   events: list[dict[str, Any]]) -> dict[str, Any]:
        """Include pending turn evidence without durably advancing the ledger."""
        with self.connection() as c:
            rows = [dict(row) for row in c.execute(
                """SELECT event_type,message_text,evidence
                   FROM certification_scenario_behavior_events
                   WHERE scenario_id=%s ORDER BY occurred_at,event_id""",
                (scenario_id,),
            ).fetchall()]
        rows.extend({
            "event_type": str(event.get("type") or "INBOUND").upper(),
            "message_text": str(event.get("message") or ""),
            "evidence": dict(event.get("evidence") or {}),
        } for event in events)
        return self._summarize_behavior_rows(rows)

    @staticmethod
    def _summarize_behavior_rows(rows) -> dict[str, Any]:
        summary = {
            "inbound_message_count": 0, "offer_exposure_count": 0,
            "proactive_tease_delivered_count": 0,
            "build_interest_exposure_count": 0,
            "rejection_count": 0, "commercial_movement": False,
            "sexual_engagement_only": False, "back_off": False,
            "low_information_response_count": 0,
            "idle_browsing_signal_count": 0,
            "meaningful_engagement_count": 0,
            "sexual_engagement_count": 0,
            "post_offer_sexual_engagement_count": 0,
            "commercial_tease_exposure_count": 0,
        }
        sexual = False
        offer_seen = False
        for row in rows:
            kind = row["event_type"]
            evidence = dict(row["evidence"] or {})
            if kind == "INBOUND": summary["inbound_message_count"] += 1
            elif kind == "OFFER_EXPOSURE":
                summary["offer_exposure_count"] += 1
                offer_seen = True
            elif kind in {"PROACTIVE_TEASE_DELIVERED", "COMMERCIAL_TEASE_DELIVERED"}:
                summary["commercial_tease_exposure_count"] += 1
                if kind == "PROACTIVE_TEASE_DELIVERED" or evidence.get(
                    "teaseType"
                ) == "PROACTIVE_RELATIONSHIP":
                    summary["proactive_tease_delivered_count"] += 1
            elif kind == "BUILD_INTEREST_EXPOSURE":
                summary["build_interest_exposure_count"] += 1
            elif kind in {"REJECTION", "PRICE_OBJECTION"}: summary["rejection_count"] += 1
            summary["commercial_movement"] = summary["commercial_movement"] or bool(evidence.get("commercial_movement"))
            summary["low_information_response_count"] += int(bool(
                evidence.get("low_information_response")
            ))
            summary["idle_browsing_signal_count"] += int(bool(
                evidence.get("idle_browsing_signal")
            ))
            summary["meaningful_engagement_count"] += int(bool(
                evidence.get("meaningful_engagement")
            ))
            sexual_turn = bool(evidence.get("sexual_engagement"))
            sexual = sexual or sexual_turn
            summary["sexual_engagement_count"] += int(sexual_turn)
            if kind == "INBOUND" and sexual_turn and offer_seen:
                summary["post_offer_sexual_engagement_count"] += 1
            summary["back_off"] = summary["back_off"] or bool(evidence.get("back_off"))
            for key in ("direct_buying_intent", "price_question", "content_request",
                        "active_session", "sales_session_id", "sales_progression_phase"):
                if evidence.get(key) is not None: summary[key] = evidence[key]
        summary["sexual_engagement_only"] = sexual and not summary["commercial_movement"] and not summary.get("direct_buying_intent", False)
        summary["commercial_opportunity_exposure_count"] = (
            summary["commercial_tease_exposure_count"]
            + summary["build_interest_exposure_count"]
            + summary["offer_exposure_count"]
        )
        return summary

    @contextmanager
    def turn_execution_scope(self):
        """Serialize turns that temporarily bind process-global repositories."""
        with _SCENARIO_EXECUTION_LOCK:
            yield

    @contextmanager
    def application_test_database_scope(self):
        """Bind production repository defaults to the guarded test DB in-process."""
        import app.database as database
        with _SCENARIO_EXECUTION_LOCK:
            guarded=require_session5_database_purpose(
                self.test_database_url, os.getenv("DATABASE_URL"),
                self.database_purpose,
            )
            original=database.DATABASE_URL
            database.close_database_pool()
            database.DATABASE_URL=guarded
            try:
                yield
            finally:
                database.close_database_pool()
                database.DATABASE_URL=original

    def execute_turn(self, scenario_id: str, message: str, *, provider_draft=None,
                     language_mode: str = DETERMINISTIC_CERTIFICATION,
                     recent_ava_responses: list[str] | None = None,
                     turn_identity: ScenarioTurnExecutionIdentity | None = None,
                     ) -> dict[str, Any]:
        """Execute a transport-free turn through the isolated ConversationGateway."""
        language_mode = str(language_mode or "").upper()
        if language_mode not in LANGUAGE_MODES:
            raise ValueError(f"Unsupported Synthetic Test language mode: {language_mode}")
        if provider_draft is not None and language_mode != DETERMINISTIC_CERTIFICATION:
            raise ValueError("Provider fixtures require DETERMINISTIC_CERTIFICATION mode.")
        turn_identity = turn_identity or self._next_direct_turn_identity(scenario_id)
        if turn_identity.scenario_id != scenario_id:
            raise ValueError("Scenario turn identity does not match the scenario.")
        base = HistoricalPurchaseFixtureBuilder(self)._ensure_customer(scenario_id)
        with self.connection() as c:
            prior_evidence = c.execute("""SELECT scenario_id,telegram_user_id,
                    inbound,full_analysis
                FROM certification_scenario_turn_evidence
                WHERE correlation_id=%s""", (
                    turn_identity.correlation_id,
                )).fetchone()
        if prior_evidence is not None:
            prior_payload = dict(prior_evidence["full_analysis"] or {})
            if (
                dict(prior_payload.get("scenarioTurnIdentity") or {})
                    != turn_identity.to_mapping()
                or prior_evidence["scenario_id"] != scenario_id
                or int(prior_evidence["telegram_user_id"])
                    != int(base["telegram_user_id"])
                or str(prior_evidence["inbound"] or "") != str(message or "")
            ):
                raise RuntimeError(
                    "SCENARIO_TURN_IDENTITY_COLLISION: existing rich evidence "
                    "belongs to a different immutable execution."
                )
            return prior_payload
        from app.services.conversational_sales_progression_service import (
            ConversationalSalesProgressionService,
        )
        progression = ConversationalSalesProgressionService()
        transition_features = progression.transition_features(message)
        words = __import__("re").findall(r"[A-Za-z0-9']+", message)
        low_information = bool(
            len(words) <= 3
            or __import__("re").fullmatch(
                r"\s*(?:hey|hi|yeah|yep|lol|not much|nothing much|idk|maybe)[.!?\s]*",
                message, __import__("re").I,
            )
        )
        idle_browsing = bool(__import__("re").search(
            r"\b(?:bored|killing time|just scrolling|passing time)\b",
            message, __import__("re").I,
        ))
        content_request = bool(transition_features.get("content_request"))
        direct_purchase = progression.has_direct_purchase_intent(message)
        next_turn_number = turn_identity.logical_turn
        from app.services.contextual_customer_tone_service import (
            ContextualCustomerToneService,
        )
        accepted_runtime_tone = ContextualCustomerToneService().classify(
            message=message, recent_transcript=(),
        )
        inbound_event = {
            "type":"INBOUND", "message":message,
            "idempotency_key": f"inbound:{next_turn_number}",
            "evidence":{
                "commercial_movement": bool(direct_purchase or content_request),
                "direct_buying_intent": True if direct_purchase else None,
                "content_request": True if content_request else None,
                "low_information_response": low_information,
                "idle_browsing_signal": idle_browsing,
                "meaningful_engagement": bool(
                    direct_purchase or content_request
                    or (len(words) >= 8 and not idle_browsing)
                ),
                "sexual_engagement": bool(
                    accepted_runtime_tone.get("sexualOrProvocative")
                ),
                "runtime_classification_source": "CONTEXTUAL_CUSTOMER_TONE_SERVICE",
            },
        }
        behavior = self.projected_behavior_summary(scenario_id, [inbound_event])
        derived = HistoricalPurchaseFixtureBuilder(self).derived_state(scenario_id)
        from app.models.conversation_gateway import ConversationBrainContext, ConversationGatewayInput
        from app.services.conversation_gateway import ConversationGateway
        turn_number = turn_identity.logical_turn
        # Feed production generation the actual alternating transcript.  The
        # behavior ledger is intentionally inbound-only and cannot carry Ava's
        # question history, which PHONE_TEXTING uses to control question pressure.
        with self.connection() as c:
            prior_turns = c.execute("""SELECT inbound,outbound
                FROM certification_scenario_turn_evidence
                WHERE scenario_id=%s ORDER BY created_at,correlation_id""",
                (scenario_id,),
            ).fetchall()
        history = [
            {"role": role, "content": str(content or "")}
            for row in prior_turns
            for role, content in (
                ("user", row["inbound"]), ("assistant", row["outbound"]),
            )
            if content
        ]
        context=ConversationBrainContext(
            creator_profile_id=base["creator_profile_id"],
            customer_identifier=f"{base['fanvue_account_id']}:{base['fanvue_user_id']}",
            conversation_identifier=f"certification:{scenario_id}",developer_mode=True,
            telegram_user_id=base["telegram_user_id"],telegram_chat_id=base["telegram_chat_id"],
            fanvue_account_id=base["fanvue_account_id"],fanvue_user_id=base["fanvue_user_id"],
            conversational_memory={"historyCount":len(history)})
        correlation=turn_identity.correlation_id
        behavior_event_id = uuid5(
            NAMESPACE_URL,
            f"session5:{scenario_id}:behavior:{inbound_event['idempotency_key']}",
        )
        synthetic_inbound_message_id = (
            9_000_000_000 + (behavior_event_id.int % 900_000_000)
        )
        with self.connection() as c:
            acknowledgement = c.execute("""SELECT purchase_intent_id
                FROM purchase_intents
                WHERE telegram_user_id=%s AND status='PURCHASED'
                  AND purchase_acknowledged_at IS NULL
                ORDER BY purchased_at DESC NULLS LAST, created_at DESC LIMIT 1""",
                (base["telegram_user_id"],)).fetchone()
            active_session = c.execute("""SELECT sales_session_id,conversation_thread_id
                FROM sales_sessions
                WHERE creator_profile_id=%s AND fanvue_account_id=%s
                  AND fanvue_user_id=%s AND state IN ('ACTIVE','CONTINUING')
                ORDER BY updated_at DESC LIMIT 1""", (
                    base["creator_profile_id"], base["fanvue_account_id"],
                    base["fanvue_user_id"],
                )).fetchone()
            thread = c.execute("""SELECT id FROM chat_threads
                WHERE fanvue_account_id=%s AND fanvue_user_id=%s
                ORDER BY created_at DESC LIMIT 1""", (
                    base["fanvue_account_id"], base["fanvue_user_id"],
                )).fetchone()
            if thread is None:
                thread = c.execute("""INSERT INTO chat_threads(
                    fanvue_account_id,fanvue_user_id,fanvue_chat_uuid,thread_status)
                    VALUES (%s,%s,%s,'active') RETURNING id""", (
                        base["fanvue_account_id"], base["fanvue_user_id"],
                        str(uuid4()),
                    )).fetchone()
            if active_session and active_session["conversation_thread_id"] is None:
                active_session = dict(active_session)
                active_session["conversation_thread_id"] = int(thread["id"])
        with self.application_test_database_scope():
            from types import SimpleNamespace
            from app.config import settings
            from app.engine.decision_engine import DecisionEngine
            from app.engine.mode_engine import ModeEngine
            from app.integrations.telegram.telethon_runtime import MemoryInitializingDecisionEngine
            from app.services.chat_commerce_service import ChatCommerceService
            from app.services.content_service import ContentService
            from app.services.conversational_memory_service import ConversationalMemoryService
            from app.services.customer_sales_brain_service import CustomerSalesBrainService
            from app.services.gpt_service import GPTService
            from app.services.intent_service import IntentService
            from app.services.memory_service import MemoryService
            from app.services.offer_service import OfferService
            from app.services.post_offer_service import PostOfferService
            from app.services.timing_engine import TimingEngine
            from app.services.user_value_service import UserValueService
            from app.repositories.ordinary_chat_reply_repository import OrdinaryChatReplyRepository
            from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService
            ordinary_reply_repository = OrdinaryChatReplyRepository(
                connection_factory=self.connection,
            )
            ordinary_reply_service = OrdinaryChatReplyService(
                repository=ordinary_reply_repository,
                worker_id=f"scenario-test-transport:{correlation}",
            )
            customer_behavior_evidence = ordinary_reply_repository.customer_behavior_evidence(
                account_scope="AVA_TELETHON_PRIVATE",
                chat_id=base["telegram_chat_id"],
                sender_user_id=base["telegram_user_id"],
            )
            customer_behavior_evidence = merge_scenario_customer_behavior_evidence(
                behavior,
                customer_behavior_evidence,
            )
            adversarial_fixture = provider_draft is not None
            provider_sequence=(list(provider_draft) if isinstance(provider_draft,(list,tuple))
                               else [str(provider_draft)]) if adversarial_fixture else []
            provider_outputs=[]
            synthetic_provider = None
            class Completions:
                def create(self, **_kwargs):
                    rewrite = any(
                        "REWRITE" in str(item.get("content") or "").upper()
                        for item in _kwargs.get("messages", [])[-2:]
                    )
                    value=(provider_sequence.pop(0) if provider_sequence else
                           provider_outputs[-1] if adversarial_fixture and provider_outputs else
                           synthetic_provider.complete(
                               rewrite=rewrite,
                               prompt_context=json.dumps(_kwargs.get("messages", []), default=str),
                           ))
                    provider_outputs.append(value)
                    return SimpleNamespace(choices=[SimpleNamespace(
                        message=SimpleNamespace(content=value))])
            client=SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
            memory_projection=ConversationalMemoryService().learn(
                creator_profile_id=base["creator_profile_id"],fanvue_account_id=base["fanvue_account_id"],
                telegram_user_id=base["telegram_user_id"],telegram_chat_id=base["telegram_chat_id"],
                message_text=message)
            memory_projection["recentAvaResponses"] = list(recent_ava_responses or [])[-3:]
            synthetic_provider = DeterministicSyntheticLanguageProvider(
                message=message, memory=memory_projection,
                purchase_count=derived.get("purchaseCount", 0),
                active_session=bool(active_session),
            )
            context=ConversationBrainContext(
                creator_profile_id=base["creator_profile_id"],customer_identifier=context.customer_identifier,
                conversation_identifier=context.conversation_identifier,developer_mode=True,
                telegram_user_id=base["telegram_user_id"],telegram_chat_id=base["telegram_chat_id"],
                fanvue_account_id=base["fanvue_account_id"],fanvue_user_id=base["fanvue_user_id"],
                conversation_thread_id=(
                    int(active_session["conversation_thread_id"])
                    if active_session and active_session["conversation_thread_id"] is not None
                    else int(thread["id"])
                ),
                purchase_acknowledgement_pending=acknowledgement is not None,
                purchase_acknowledgement_intent_id=(
                    str(acknowledgement["purchase_intent_id"])
                    if acknowledgement else None
                ),
                conversational_memory=memory_projection,
                customer_behavior_evidence=customer_behavior_evidence)
            gpt=GPTService(
                settings.OPENAI_API_KEY
                if language_mode == REAL_AVA_LANGUAGE
                else "certification-test-key"
            )
            if language_mode == DETERMINISTIC_CERTIFICATION:
                gpt.openai_client=client; gpt.grok_client=client
            else:
                class LiveCompletions:
                    def __init__(self, delegate):
                        self.delegate = delegate

                    def create(self, **kwargs):
                        result = self.delegate.create(**kwargs)
                        content = result.choices[0].message.content
                        provider_outputs.append(str(content or ""))
                        return result

                for client_name in ("openai_client", "grok_client"):
                    live_client = getattr(gpt, client_name)
                    setattr(gpt, client_name, SimpleNamespace(chat=SimpleNamespace(
                        completions=LiveCompletions(live_client.chat.completions),
                    )))
            engine=DecisionEngine(memory_service=MemoryService(),intent_service=IntentService(),
                user_value_service=UserValueService(),mode_engine=ModeEngine(),offer_service=OfferService(),
                content_service=ContentService(),post_offer_service=PostOfferService(),
                timing_engine=TimingEngine(),gpt_service=gpt,settings=settings,
                logger=logging.getLogger("session5-certification"))
            direct=bool(direct_purchase or content_request)
            from app.services.contextual_customer_tone_service import (
                ContextualCustomerToneService,
            )
            sexual = bool(
                ContextualCustomerToneService().classify(
                    message=message,
                    recent_transcript=history,
                ).get("sexualOrProvocative")
            )
            engine.gpt_intent_classifier.classify_message=lambda **_:{
                "confidence":.99,"route":"sales" if direct else "chat",
                "recommended_action":"close" if direct else "chat","buying_intent":direct,
                "close_ready":direct,"user_state":"ready_to_buy" if direct else "engaged",
                "signals":["DIRECT_PURCHASE_LANGUAGE"] if direct else [],"curiosity_level":"high" if direct else "low",
                "escalation_ready":direct,"engagement_level":"high" if sexual else "medium",
                "buyer_likelihood":"high" if direct else "low","sexual_engagement":sexual,
                "purchase_language_present":direct,"monetization_intent":direct,
                "explicit_without_buying_intent":sexual and not direct,"intent_level":"high" if direct else "low",
                "exit_ready":False,"objection_type":"none","sentiment":"positive","reason":"CERTIFICATION_PROVIDER_DOUBLE"}
            engine.objection_classifier.classify_objection=lambda **_:{"has_objection":False,"objection_type":"none","confidence":1.0,"reason":"CERTIFICATION_PROVIDER_DOUBLE"}
            engine.emotional_dependency_classifier.classify_dependency_risk=lambda *_a,**_k:{"dependency_risk_level":"low","dependency_risk_score":0}
            engine.decision_runtime_boundary.log_send_event=lambda *_a,**_k:None
            class LiveMode:
                def get_mode(self):
                    from app.models.commerce_mode import CommerceMode
                    return CommerceMode.LIVE
            gateway=ConversationGateway(MemoryInitializingDecisionEngine(engine),
                allowed_fanvue_hostnames=("fanvue.com","share.fanvue.com"),
                creator_profile_id=base["creator_profile_id"],
                chat_commerce_service=ChatCommerceService(commerce_mode=ChatCommerceService.AUTHORITATIVE_MODE),
                customer_sales_brain_service=CustomerSalesBrainService(),
                commerce_mode_service=LiveMode(),
                commercial_presentation_copy_generator=lambda **kwargs:(
                    gpt.generate_paid_presentation_copy(
                        **kwargs,
                        fanvue_account_id=base["fanvue_account_id"],
                    )
                ),
                purchase_acknowledgement_copy_generator=lambda **kwargs:(
                    gpt.generate_purchase_acknowledgement_copy(
                        **kwargs,
                        fanvue_account_id=base["fanvue_account_id"],
                    )
                ),
                ava_persona_runtime_service=gpt.persona_runtime_service)
            output=gateway.execute(ConversationGatewayInput(
                engine_user_id=context.customer_identifier,message_text=message,
                chat_history=history,correlation_id=correlation,brain_context=context))
            # Only a successfully generated gateway turn becomes authoritative
            # inbound/reply lifecycle evidence. This preserves the existing
            # failed-turn rollback contract while still exercising production's
            # canonical generation and confirmation transitions.
            ordinary_operation, _ = ordinary_reply_repository.get_or_create(
                account_scope=OrdinaryChatReplyService.ACCOUNT_SCOPE,
                chat_id=base["telegram_chat_id"],
                inbound_message_id=synthetic_inbound_message_id,
                sender_user_id=base["telegram_user_id"],
                correlation_id=f"certification:{scenario_id}:{behavior_event_id}",
                inbound_message_text=message,
            )
            claimed_ordinary_generation = ordinary_reply_service.claim_generation(
                ordinary_operation,
            )
            if claimed_ordinary_generation is None:
                raise RuntimeError(
                    "SCENARIO_TEST_TRANSPORT_GENERATION_CLAIM_FAILED: "
                    f"state={ordinary_operation.state.value}"
                )
            ordinary_operation = ordinary_reply_service.generated(
                claimed_ordinary_generation, output,
            )
            if ordinary_operation is None:
                raise RuntimeError(
                    "SCENARIO_TEST_TRANSPORT_GENERATION_PERSIST_FAILED"
                )
            persona_value=output.diagnostic_metadata.get("avaPersonaRuntime")
            persona=dict(persona_value) if isinstance(persona_value,Mapping) else {}
            purchase_intent = None
            commercial_decision = str(
                output.diagnostic_metadata.get("customer_sales_decision") or ""
            )
            if (
                output.offer_authorized and output.delivery_requires_payment
            ) or commercial_decision == "CONGRATULATE_PURCHASE":
                from app.models.telegram_inbound import TelegramInboundPayload
                from app.services.telegram_purchase_intent_service import (
                    TelegramPurchaseIntentService,
                )
                from app.services.private_chat_unlock_gateway_service import (
                    PrivateChatUnlockGatewayService,
                )
                class SyntheticControlledBoundary:
                    @staticmethod
                    def decide(**_kwargs):
                        return SimpleNamespace(allowed=True)
                purchase_intent_service = TelegramPurchaseIntentService(
                    creator_profile_id=base["creator_profile_id"],
                    fanvue_account_id=base["fanvue_account_id"],
                    unlock_gateway_service=PrivateChatUnlockGatewayService(
                        controlled_autonomy_service=SyntheticControlledBoundary(),
                    ),
                )
                purchase_intent = purchase_intent_service.create_before_delivery(
                    output,
                    TelegramInboundPayload(
                        telegram_user_id=base["telegram_user_id"],
                        telegram_chat_id=base["telegram_chat_id"],
                        message_text=message,
                        message_id=turn_number,
                        correlation_id=correlation,
                    ),
                )
                if purchase_intent is not None and not output.blocked:
                    from app.repositories.telegram_sales_delivery_repository import (
                        TelegramSalesDeliveryRepository,
                    )
                    from app.services.telegram_sales_delivery_service import (
                        TelegramSalesDeliveryService,
                    )
                    output.diagnostic_metadata.update({
                        "conversation_thread_id": int(thread["id"]),
                        "conversation_fanvue_account_id": base["fanvue_account_id"],
                        "conversation_fanvue_user_id": base["fanvue_user_id"],
                    })
                    delivery_service = TelegramSalesDeliveryService(
                        repository=TelegramSalesDeliveryRepository(
                            connection_factory=self.connection,
                        ),
                        purchase_intent_service=purchase_intent_service,
                    )
                    operation, _ = delivery_service.prepare(
                        intent=purchase_intent,
                        result=output,
                        payload=TelegramInboundPayload(
                            telegram_user_id=base["telegram_user_id"],
                            telegram_chat_id=base["telegram_chat_id"],
                            message_text=message,
                            message_id=turn_number,
                            correlation_id=correlation,
                        ),
                    )
                    claimed = delivery_service.claim(operation)
                    if claimed is not None:
                        synthetic_provider_message_id = (
                            uuid5(NAMESPACE_URL, correlation).int
                            % 2_000_000_000
                        ) + 1
                        accepted = delivery_service.accepted(
                            claimed, synthetic_provider_message_id,
                        )
                        operation = delivery_service.confirm(accepted)
                    refreshed_intent = purchase_intent_service.get(
                        purchase_intent.purchase_intent_id
                    )
                    output.diagnostic_metadata.update({
                        "synthetic_delivery_operation_id": str(operation.operation_id),
                        "synthetic_delivery_state": operation.state.value,
                        "purchase_intent_state": refreshed_intent.status.value,
                        "purchase_intent_presented_at": (
                            refreshed_intent.presented_at.isoformat()
                            if refreshed_intent.presented_at else None
                        ),
                        "purchase_acknowledged_at": (
                            refreshed_intent.purchase_acknowledged_at.isoformat()
                            if refreshed_intent.purchase_acknowledged_at else None
                        ),
                        "test_transport_customer_visible_confirmed": (
                            operation.state.value == "CONFIRMED"
                        ),
                    })
            # A paid presentation has its own canonical delivery namespace.
            # Every other customer-visible Scenario Lab reply crosses the same
            # claim/confirmation boundary used by the production Telethon
            # runtime. Intentional suppression remains terminal and unsent.
            ordinary_operation = confirm_scenario_test_transport_ordinary_reply(
                service=ordinary_reply_service,
                operation=ordinary_operation,
                output=output,
                purchase_intent=purchase_intent,
                correlation_id=correlation,
            )
            # Scenario Lab's test transport is the customer-visible delivery
            # authority for ordinary TEASE text. Mirror the production durable
            # confirmation boundary; generated text alone is never exposure.
            if output.diagnostic_metadata.get(
                "commercial_tease_delivery_pending_confirmation"
            ):
                from app.repositories.telegram_sales_prospect_repository import (
                    TelegramSalesProspectRepository,
                )
                pending = dict(output.diagnostic_metadata.get(
                    "pending_sales_progression"
                ) or {})
                if not pending:
                    raise RuntimeError(
                        "Scenario TEASE confirmation lacks pending progression"
                    )
                TelegramSalesProspectRepository(
                    connection_factory=self.connection
                ).record_sales_progression(
                    creator_profile_id=base["creator_profile_id"],
                    fanvue_account_id=base["fanvue_account_id"],
                    telegram_user_id=base["telegram_user_id"],
                    progression=pending,
                    correlation_id=correlation,
                )
                output.diagnostic_metadata.update({
                    "commercial_tease_delivery_pending_confirmation": False,
                    "commercial_tease_delivered": True,
                    "commercial_tease_exposure_recorded": True,
                    "progression_finalized_after_delivery": True,
                    "test_transport_customer_visible_confirmed": True,
                })
                commercial_projection = dict(
                    dict(output.diagnostic_metadata.get("commercial_summary") or {}).get(
                        "sexualCommercialProgression"
                    ) or {}
                )
                commercial_projection.update({
                    "commercialTeaseDelivered": True,
                    "commercialTeaseExposureRecorded": True,
                    "progressionFinalizedAfterDelivery": True,
                    "adaptiveSwitchEligible": True,
                    "adaptiveSwitchReason": (
                        "CONFIRMED_CUSTOMER_VISIBLE_COMMERCIAL_TEASE"
                    ),
                })
                output.diagnostic_metadata.setdefault(
                    "commercial_summary", {}
                )["sexualCommercialProgression"] = commercial_projection
            # The isolated transport confirms ordinary text synchronously.
            # Exercise the same production delivery-truth contract for every
            # Session proposal; this contains no scenario-specific authority.
            if output.diagnostic_metadata.get(
                "session_proposal_delivery_pending_confirmation"
            ):
                from app.repositories.telegram_sales_prospect_repository import (
                    TelegramSalesProspectRepository,
                )
                proposal = dict(output.diagnostic_metadata.get(
                    "pending_session_proposal"
                ) or {})
                synthetic_provider_message_id = (
                    uuid5(NAMESPACE_URL, f"session-proposal:{correlation}").int
                    % 2_000_000_000
                ) + 1
                TelegramSalesProspectRepository(
                    connection_factory=self.connection
                ).record_session_proposal(
                    creator_profile_id=base["creator_profile_id"],
                    fanvue_account_id=base["fanvue_account_id"],
                    telegram_user_id=base["telegram_user_id"],
                    correlation_id=correlation,
                    source_inbound=correlation,
                    delivery_correlation_id=correlation,
                    delivery_provider_message_id=synthetic_provider_message_id,
                    session_offering_id=proposal.get("offeringId"),
                )
                output.diagnostic_metadata.update({
                    "session_proposal_delivery_pending_confirmation": False,
                    "sessionProposalDelivered": True,
                    "sessionProposalPending": True,
                    "test_transport_customer_visible_confirmed": True,
                })
                output.diagnostic_metadata.setdefault(
                    "commercial_summary", {}
                ).update({
                    "sessionProposalDelivered": True,
                    "sessionProposalPending": True,
                    "sessionProposalId": correlation,
                    "sessionProposalSourceInbound": correlation,
                    "scenarioInfluencedCommercialAuthority": False,
                })
            exposure_events = []
            if output.diagnostic_metadata.get("commercial_tease_exposure_recorded"):
                exposure_events.append({
                    "type": "COMMERCIAL_TEASE_DELIVERED",
                    "teaseType": output.diagnostic_metadata.get("tease_type"),
                    "offeringId": output.diagnostic_metadata.get("tease_offering"),
                })
            if output.diagnostic_metadata.get("build_interest_exposure"):
                exposure_events.append({"type": "BUILD_INTEREST_EXPOSURE"})
            if output.diagnostic_metadata.get("offer_exposure"):
                exposure_events.append({"type": "OFFER_EXPOSURE"})
            if exposure_events:
                behavior = self.projected_behavior_summary(
                    scenario_id, [inbound_event, *exposure_events]
                )
        # A failed gateway turn must not become durable behavior or an
        # authoritative inbound operation. Persist only after generation and
        # commerce evaluation have completed successfully.
        behavior = self.record_behavior_history(
            scenario_id, [inbound_event, *exposure_events]
        )
        # Synchronize the prospect's denormalized count only after the durable
        # authoritative inbound operation exists. Use the explicitly guarded
        # harness connection rather than reopening the process-global pool.
        from app.repositories.telegram_sales_prospect_repository import (
            TelegramSalesProspectRepository,
        )
        TelegramSalesProspectRepository(connection_factory=self.connection).observe(
            creator_profile_id=base["creator_profile_id"],
            fanvue_account_id=base["fanvue_account_id"],
            telegram_user_id=base["telegram_user_id"],
            telegram_chat_id=base["telegram_chat_id"],
        )
        full_analysis=output.diagnostic_metadata.get("commercial_summary") or {}
        current_offer = dict(full_analysis.get("currentOffer") or {})
        if current_offer.get("customerInitiatedOfferContinuation") is True:
            current_offer["structuredOfferRedelivered"] = bool(
                output.diagnostic_metadata.get(
                    "test_transport_customer_visible_confirmed"
                )
            )
            full_analysis["currentOffer"] = current_offer
        acknowledgement_authorized = (
            commercial_decision == "CONGRATULATE_PURCHASE"
        )
        acknowledgement_operation_id = output.diagnostic_metadata.get(
            "synthetic_delivery_operation_id"
        )
        acknowledgement_provider_confirmed = bool(
            acknowledgement_authorized
            and output.diagnostic_metadata.get(
                "test_transport_customer_visible_confirmed"
            )
        )
        purchase_acknowledged_at = output.diagnostic_metadata.get(
            "purchase_acknowledged_at"
        )
        full_analysis.update({
            "purchaseAcknowledgementAuthorized": acknowledgement_authorized,
            "acknowledgementDeliveryOperation": acknowledgement_operation_id,
            "acknowledgementProviderConfirmed": acknowledgement_provider_confirmed,
            "purchaseAcknowledgedAt": purchase_acknowledged_at,
            "purchaseAcknowledgementCompleted": bool(purchase_acknowledged_at),
        })
        full_analysis["commerceLifecycleConfirmation"] = {
            "purchaseIntentId": output.diagnostic_metadata.get(
                "purchase_intent_id"
            ) or output.diagnostic_metadata.get(
                "purchase_acknowledgement_intent_id"
            ),
            "purchaseIntentState": output.diagnostic_metadata.get(
                "purchase_intent_state"
            ),
            "structuredPresentationConfirmed": bool(
                output.diagnostic_metadata.get(
                    "test_transport_customer_visible_confirmed"
                )
            ),
            "presentedAt": output.diagnostic_metadata.get(
                "purchase_intent_presented_at"
            ),
            "purchaseAcknowledgedAt": output.diagnostic_metadata.get(
                "purchase_acknowledged_at"
            ),
            "deliveryOperationId": output.diagnostic_metadata.get(
                "synthetic_delivery_operation_id"
            ),
            "deliveryState": output.diagnostic_metadata.get(
                "synthetic_delivery_state"
            ),
            "provider": "SYNTHETIC_TEST_TRANSPORT",
            "providerBackedSettlementRequired": True,
        }
        synthetic_diagnostics = synthetic_provider.diagnostics(
            adversarial=adversarial_fixture,
        )
        if language_mode == REAL_AVA_LANGUAGE:
            provider_diagnostics = normalize_provider_diagnostics(
                output.diagnostic_metadata
            )
            synthetic_diagnostics = {
                **synthetic_diagnostics,
                "syntheticProviderMode": REAL_AVA_LANGUAGE,
                "liveProviderCalled": bool(provider_outputs),
                "liveProviderCallCount": len(provider_outputs),
                "providerSelected": provider_diagnostics["selected"],
                "providerMetadataShape": provider_diagnostics["shape"],
                "adversarialFixtureUsed": False,
                "canonicalTemporalContextConsumed": None,
                "newRelationshipContextConsumed": None,
                "turnObligationsConsumed": None,
                "productionGenerationPipelineUsed": True,
                "currentInboundIncluded": True,
                "conversationHistoryMessageCount": len(history),
                "recentAvaResponseCount": len(recent_ava_responses or []),
                "conversationalMemoryIncluded": bool(memory_projection),
                "avaPersonaRuntimeIncluded": bool(persona),
                "salesBrainContextIncluded": bool(
                    output.diagnostic_metadata.get("commercial_summary")
                ),
            }
        full_analysis["syntheticProvider"] = synthetic_diagnostics
        purchase_intent_id = (
            str(purchase_intent.purchase_intent_id)
            if purchase_intent is not None else
            output.diagnostic_metadata.get("purchase_intent_id") or
            output.diagnostic_metadata.get("active_purchase_intent_id")
        )
        ppv = None
        if purchase_intent_id and output.offer_authorized and output.delivery_requires_payment:
            with self.connection() as c:
                selected = c.execute("""SELECT offering.title,offering.offering_type,
                    offering.price_minor,offering.currency,offering.primary_sales_channel
                    FROM purchase_intents intent JOIN commercial_offerings offering
                      ON offering.offering_id=intent.commercial_offering_id
                    WHERE intent.purchase_intent_id=%s""",(purchase_intent_id,)).fetchone()
            if selected:
                button = dict((output.delivery_payload.get("metadata") or {}).get(
                    "private_chat_unlock_button"
                ) or {})
                ppv = {
                    "ava": output.response_text,
                    "offeringId": str(output.diagnostic_metadata.get("offering_id") or ""),
                    "name": selected["title"],
                    "type": selected["offering_type"],
                    "priceMinor": int(selected["price_minor"]),
                    "price": f"${int(selected['price_minor']) / 100:.2f}",
                    "currency": selected["currency"],
                    "channel": selected["primary_sales_channel"],
                    "cta": {
                        "label": button.get("label") or "Unlock",
                        "target": "SYNTHETIC_PRIVATE_CHAT_UNLOCK",
                    },
                    "purchaseIntent": {
                        "id": purchase_intent_id,
                        "state": output.diagnostic_metadata.get(
                            "purchase_intent_state", "CREATED"
                        ),
                    },
                }
        evidence={"scenarioId":scenario_id,"turnNumber":turn_number,
            "scenarioTurnIdentity":turn_identity.to_mapping(),
            "syntheticInboundId":correlation,"inboundText":message,"finalResponseText":output.response_text,
            "inbound":message,"outbound":output.response_text,
            "customerValueAttention":output.diagnostic_metadata.get("customer_value_attention") or derived,
            "conversationInvestment":output.diagnostic_metadata.get("conversation_investment") or {"effortMode":derived["effortMode"]},
            "SalesBrainFullAnalysis":full_analysis,"salesBrain":full_analysis,
            "conversationalMemory":output.diagnostic_metadata.get("conversational_memory") or "NOT PROVIDED",
            "memoryDiagnostics":output.diagnostic_metadata.get("conversational_memory") or "NOT PROVIDED",
            "avaPersonaRuntime":persona,"styleDiagnostics":output.diagnostic_metadata.get("conversationStyle") or {},
            "temporalContext":output.diagnostic_metadata.get("time_context") or "NOT PROVIDED",
            "sleep":output.diagnostic_metadata.get("sleep_context") or "NOT PROVIDED",
            "temporalSleep":{"mode":"NOT_FORCED"},"commercialAuthority":{"offerAuthorized":output.offer_authorized},
            "commerceDiagnostics":{key:output.diagnostic_metadata.get(key,"NOT PROVIDED") for key in (
                "commercial_receptiveness","commercial_objection","purchase_cooldown",
                "recommendation_diagnostics","sales_progression_transition","commerce_execution_policy")},
            "PurchaseIntent":purchase_intent_id or "NOT PROVIDED",
            "syntheticPpvPresentation":ppv,
            "ownership":output.diagnostic_metadata.get("ownership") or "NOT PROVIDED",
            "Session":output.diagnostic_metadata.get("sales_session") or "NOT PROVIDED",
            "pacingCalculation":output.diagnostic_metadata.get("response_pacing") or "TEST_TRANSPORT_NO_WAIT",
            "gatewayDiagnostics":output.diagnostic_metadata,"behavior":behavior,
            "providerDraft":provider_outputs[0] if provider_outputs else None,
            "rewriteHistory":provider_outputs[1:],
            "syntheticProvider": synthetic_diagnostics,
            "testTransportResult":"TEST_TRANSPORT_NO_WAIT"}
        with self.connection() as c:
            existing = c.execute("""SELECT scenario_id,telegram_user_id,inbound,
                    outbound,full_analysis
                FROM certification_scenario_turn_evidence
                WHERE correlation_id=%s FOR UPDATE""", (correlation,)).fetchone()
            if existing is None:
                c.execute("""INSERT INTO certification_scenario_turn_evidence(
                    correlation_id,scenario_id,telegram_user_id,inbound,outbound,full_analysis)
                    VALUES (%s,%s,%s,%s,%s,%s::jsonb)""",(
                    correlation,scenario_id,base["telegram_user_id"],message,
                    output.response_text,json.dumps(evidence,default=str)))
            else:
                prior_identity = dict(
                    dict(existing["full_analysis"] or {}).get(
                        "scenarioTurnIdentity"
                    ) or {}
                )
                if (
                    prior_identity != turn_identity.to_mapping()
                    or existing["scenario_id"] != scenario_id
                    or int(existing["telegram_user_id"]) != int(base["telegram_user_id"])
                    or str(existing["inbound"] or "") != str(message or "")
                    or str(existing["outbound"] or "") != str(output.response_text or "")
                ):
                    raise RuntimeError(
                        "SCENARIO_TURN_IDENTITY_COLLISION: existing rich evidence "
                        "belongs to a different immutable execution."
                    )
                c.execute("""UPDATE certification_scenario_turn_evidence
                    SET full_analysis=%s::jsonb WHERE correlation_id=%s""", (
                    json.dumps(evidence,default=str), correlation,
                ))
        return evidence

    def _next_direct_turn_identity(self, scenario_id: str) -> ScenarioTurnExecutionIdentity:
        """Compatibility identity for direct harness tests outside the runner."""
        with self.connection() as c:
            run = c.execute("""SELECT scenario_attempt FROM certification_scenario_runs
                WHERE scenario_id=%s""", (scenario_id,)).fetchone()
            if run is None:
                raise LookupError("Scenario was not prepared.")
            completed = int(c.execute("""SELECT COUNT(*) AS count
                FROM certification_scenario_turn_evidence
                WHERE scenario_id=%s AND COALESCE(
                    (full_analysis->'scenarioTurnIdentity'->>'scenarioAttempt')::INTEGER,
                    %s
                )=%s""", (
                    scenario_id, int(run["scenario_attempt"] or 1),
                    int(run["scenario_attempt"] or 1),
                )).fetchone()["count"])
        return ScenarioTurnExecutionIdentity(
            scenario_id=scenario_id,
            scenario_attempt=int(run["scenario_attempt"] or 1),
            logical_turn=completed + 1,
        )

    def _behavior_rows(self, scenario_id: str):
        with self.connection() as c:
            return c.execute("SELECT * FROM certification_scenario_behavior_events WHERE scenario_id=%s ORDER BY occurred_at,event_id",(scenario_id,)).fetchall()

    @staticmethod
    def definition(scenario_id):
        found=next((item for item in SCENARIO_MANIFEST if item.scenario_id==scenario_id),None)
        if found is None: raise LookupError("Unknown certification scenario.")
        return found

    @staticmethod
    def _assert_synthetic(telegram_id):
        if int(telegram_id)==PROTECTED_LIVE_TELEGRAM_ID or int(telegram_id)<SYNTHETIC_ID_MIN:
            raise PermissionError("Certification harness requires a synthetic test-scoped identity.")

    def _bootstrap(self):
        with self.connection() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS certification_scenario_runs(
              scenario_id TEXT PRIMARY KEY,scenario_name TEXT NOT NULL,economic_state TEXT NOT NULL,
              behavior_profile TEXT NOT NULL,commercial_trajectory TEXT NOT NULL,
              telegram_user_id BIGINT NOT NULL UNIQUE,telegram_chat_id BIGINT NOT NULL,
              buyer_uuid UUID NOT NULL,state TEXT NOT NULL,manifest JSONB NOT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
            c.execute("""CREATE TABLE IF NOT EXISTS certification_scenario_snapshots(
              snapshot_id UUID PRIMARY KEY,scenario_id TEXT NOT NULL,evidence JSONB NOT NULL,
              evidence_sha256 TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
            c.execute("""CREATE TABLE IF NOT EXISTS certification_scenario_records(
              scenario_id TEXT NOT NULL,table_name TEXT NOT NULL,record_id TEXT NOT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),PRIMARY KEY(scenario_id,table_name,record_id))""")
            c.execute("""CREATE TABLE IF NOT EXISTS certification_simulated_provider_events(
              event_id UUID PRIMARY KEY,scenario_id TEXT NOT NULL,provider_transaction_id TEXT NOT NULL UNIQUE,
              buyer_uuid UUID NOT NULL,amount_minor BIGINT NOT NULL,currency TEXT NOT NULL,
              provider_timestamp TIMESTAMPTZ NOT NULL,provenance TEXT NOT NULL,
              payload JSONB NOT NULL,result JSONB NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
            c.execute("""CREATE TABLE IF NOT EXISTS certification_scenario_behavior_events(
              event_id UUID PRIMARY KEY,scenario_id TEXT NOT NULL,telegram_user_id BIGINT NOT NULL,
              event_type TEXT NOT NULL,message_text TEXT NOT NULL DEFAULT '',evidence JSONB NOT NULL DEFAULT '{}',
              occurred_at TIMESTAMPTZ NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
            c.execute("""CREATE TABLE IF NOT EXISTS certification_scenario_turn_evidence(
              correlation_id TEXT PRIMARY KEY,scenario_id TEXT NOT NULL,telegram_user_id BIGINT NOT NULL,
              inbound TEXT NOT NULL,outbound TEXT NOT NULL,full_analysis JSONB NOT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")


class SimulatedProviderPurchaseHarness:
    def __init__(self, scenarios: CustomerScenarioHarness,
                 settlement_factory: Callable | None = None):
        self.scenarios=scenarios
        self.settlement_factory=settlement_factory

    def confirm(self, *, scenario_id, purchase_intent_id, amount_minor, currency,
                provider_timestamp=None, transaction_id=None, payment_id=None):
        definition=self.scenarios.definition(scenario_id)
        customer=self.scenarios.customer_for(definition)
        self.scenarios._assert_synthetic(customer.telegram_user_id)
        if not self.settlement_factory:
            from app.services.private_chat_purchase_settlement_service import PrivateChatPurchaseSettlementService
            self.settlement_factory=lambda: PrivateChatPurchaseSettlementService(
                connection_factory=self.scenarios.connection)
        timestamp=provider_timestamp or datetime.now(timezone.utc)
        transaction_id=transaction_id or f"cert-{scenario_id}-{purchase_intent_id}"
        payment_id=payment_id or f"cert-pay-{scenario_id}-{purchase_intent_id}"
        with self.scenarios.connection() as c:
            intent=c.execute("SELECT * FROM purchase_intents WHERE purchase_intent_id=%s FOR UPDATE",(purchase_intent_id,)).fetchone()
            if not intent or int(intent["telegram_user_id"])!=customer.telegram_user_id:
                raise PermissionError("PurchaseIntent does not belong to the synthetic scenario customer.")
            buyer=c.execute("SELECT id,fanvue_user_uuid FROM fanvue_users WHERE fanvue_account_id=%s AND fanvue_user_uuid=%s",(intent["fanvue_account_id"],customer.synthetic_buyer_uuid)).fetchone()
            if not buyer: raise LookupError("Synthetic authenticated provider buyer is required.")
            reservation = c.execute("""SELECT fingerprint_reservation_id
                FROM fanvue_fingerprint_reservations
                WHERE purchase_intent_id=%s""",(purchase_intent_id,)).fetchone()
            if reservation is None:
                reservation_id=uuid5(NAMESPACE_URL,f"simulated-fingerprint:{purchase_intent_id}")
                runtime_id=uuid5(NAMESPACE_URL,f"simulated-runtime:{purchase_intent_id}")
                c.execute("""INSERT INTO fanvue_fingerprint_reservations(
                    fingerprint_reservation_id,fanvue_account_id,currency,
                    exact_price_minor,configured_base_price_minor,purchase_intent_id,
                    telegram_user_id,state)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,'ACTIVE')""",(
                    reservation_id,intent["fanvue_account_id"],str(currency).upper(),
                    int(amount_minor),int(intent["configured_base_price_minor"] or amount_minor),
                    purchase_intent_id,intent["telegram_user_id"],
                ))
                c.execute("""INSERT INTO fanvue_runtime_media_links(
                    runtime_media_link_id,purchase_intent_id,fingerprint_reservation_id,
                    provider_media_link_uuid,provider_url,state,creation_operation_key,
                    expires_at) VALUES (%s,%s,%s,%s,%s,'ACTIVE',%s,NOW()+INTERVAL '1 day')""",(
                    runtime_id,purchase_intent_id,reservation_id,
                    str(uuid5(NAMESPACE_URL,f"simulated-provider-link:{purchase_intent_id}")),
                    "https://example.invalid/session5-simulated-checkout",
                    uuid5(NAMESPACE_URL,f"simulated-create:{purchase_intent_id}"),
                ))
            event_id=uuid5(NAMESPACE_URL,f"{scenario_id}:{transaction_id}")
            payload={"simulated":True,"scenarioId":scenario_id,"purchaseIntentId":str(purchase_intent_id),"providerTransactionId":transaction_id,"buyerUuid":str(customer.synthetic_buyer_uuid),"amountMinor":int(amount_minor),"currency":str(currency).upper(),"timestamp":timestamp.isoformat(),"provenance":PROVENANCE}
            c.execute("""INSERT INTO certification_simulated_provider_events(event_id,scenario_id,
                provider_transaction_id,buyer_uuid,amount_minor,currency,provider_timestamp,provenance,payload)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT(provider_transaction_id) DO NOTHING""",
                (event_id,scenario_id,transaction_id,customer.synthetic_buyer_uuid,int(amount_minor),str(currency).upper(),timestamp,PROVENANCE,json.dumps(payload)))
        result=self.settlement_factory().settle(
            fanvue_account_id=int(intent["fanvue_account_id"]),currency=str(currency).upper(),
            gross_minor=int(amount_minor),source="media_link",buyer_uuid=customer.synthetic_buyer_uuid,
            local_fanvue_user_id=int(buyer["id"]),transaction_id=transaction_id,
            payment_id=payment_id,event_id=str(event_id),purchased_at=timestamp)
        commerce_profile = None
        transaction_recorded = False
        if result is not None:
            # This is the same canonical customer-commerce projection invoked by
            # CommerceSignalService after provider evidence has been reconciled.
            from app.repositories.customer_commerce_repository import CustomerCommerceRepository
            from app.services.customer_commerce_service import CustomerCommerceService
            verified = CustomerCommerceService(CustomerCommerceRepository(
                connection_factory=self.scenarios.connection,
            )).record_verified_purchase(
                creator_profile_id=int(intent["creator_profile_id"]),
                fanvue_account_id=int(intent["fanvue_account_id"]),
                external_fanvue_user_uuid=customer.synthetic_buyer_uuid,
                gross_minor=int(amount_minor),net_minor=int(amount_minor),
                transaction_order_id=transaction_id,payment_status="succeeded",
                purchase_source="media_link",payment_timestamp=timestamp,
                display_name="Certification Buyer",
            )
            commerce_profile = verified.profile
            transaction_recorded = verified.transaction_recorded
        with self.scenarios.connection() as c:
            c.execute("UPDATE certification_simulated_provider_events SET result=%s::jsonb WHERE event_id=%s",
                      (json.dumps({"settled":result is not None,
                                   "transactionRecorded":transaction_recorded},default=str),event_id))
        return {"eventId":str(event_id),"provenance":PROVENANCE,"simulated":True,
                "settlement":result,"commerceProfile":commerce_profile,
                "transactionRecorded":transaction_recorded}


class HistoricalPurchaseFixtureBuilder:
    """Create coherent scenario commerce history through canonical settlement."""
    def __init__(self, scenarios: CustomerScenarioHarness):
        self.scenarios=scenarios
        self.emulator=SimulatedProviderPurchaseHarness(scenarios)

    def build(self, scenario_id: str, purchases: list[dict[str, Any]], *, session=False):
        if not purchases: raise ValueError("At least one historical purchase is required.")
        self.scenarios.prepare(scenario_id)
        base=self._ensure_customer(scenario_id)
        results=[]
        for index,spec in enumerate(purchases,1):
            item=self._create_intent(
                scenario_id,base,index=index,
                amount_minor=int(spec["amount_minor"]),
                purchased_at=spec.get("purchased_at") or datetime.now(timezone.utc),
                session=bool(session and index==1),
            )
            result=self.emulator.confirm(
                scenario_id=scenario_id,purchase_intent_id=item["purchase_intent_id"],
                amount_minor=item["amount_minor"],currency="USD",
                provider_timestamp=item["purchased_at"],
                transaction_id=f"cert-{scenario_id}-{index}-{item['purchase_intent_id']}",
            )
            if result["settlement"] is None:
                raise RuntimeError("Canonical simulated historical settlement failed.")
            results.append({**item,"result":result})
        return {"scenarioId":scenario_id,"customer":base,"purchases":results,
                "derived":self.derived_state(scenario_id)}

    def add_eligible_inventory(self, scenario_id: str, prices=(900,)):
        """Create test-only READY/LIVE unowned inventory for the real selector."""
        base=self._ensure_customer(scenario_id); created=[]
        with self.scenarios.connection() as c:
            for index,price in enumerate(prices,1):
                offering_id=uuid5(NAMESPACE_URL,f"available-offering:{scenario_id}:{index}")
                publication_id=uuid5(NAMESPACE_URL,f"available-publication:{scenario_id}:{index}")
                existing=c.execute("SELECT offering_id FROM commercial_offerings WHERE offering_id=%s",(offering_id,)).fetchone()
                if not existing:
                    asset=c.execute("""INSERT INTO content_items(file_path,classification,
                        creator_profile_id,media_metadata)
                        VALUES (%s,'SAFE',%s,'{"standalone_sale_preparation":{"destinations":["CHAT"]}}'::jsonb) RETURNING id""",
                        (f"certification/{scenario_id}/available-{index}.jpg",
                         base["creator_profile_id"])).fetchone()["id"]
                    c.execute("""INSERT INTO asset_content_destinations(asset_id,destination)
                        VALUES (%s,'SINGLE_PPV') ON CONFLICT(asset_id)
                        DO UPDATE SET destination=EXCLUDED.destination""",(asset,))
                    c.execute("""INSERT INTO commercial_offerings(offering_id,creator_profile_id,offering_type,title,
                        description,hero_asset_id,primary_sales_channel,status,price_minor,currency)
                        VALUES (%s,%s,'SINGLE_IMAGE',%s,'a playful private photo with a confident, teasing mood',%s,'AI_CHAT','READY',%s,'USD')""",
                        (offering_id,base["creator_profile_id"],f"Certification available {index}",asset,int(price)))
                    c.execute("INSERT INTO commercial_offering_assets(offering_id,asset_id,position) VALUES (%s,%s,1)",(offering_id,asset))
                    c.execute("""INSERT INTO commercial_publications(publication_id,commercial_offering_id,provider,status,
                        external_product_id,provider_resource_status,publication_metadata,published_at)
                        VALUES (%s,%s,'FANVUE','LIVE',%s,'PRESENT',%s::jsonb,NOW())""",
                        (publication_id,offering_id,f"cert-available-{scenario_id}-{index}",
                         json.dumps({"media_link":{"url":f"https://share.fanvue.com/certification/{scenario_id}/{index}"}})))
                asset_row=c.execute("SELECT hero_asset_id FROM commercial_offerings WHERE offering_id=%s",(offering_id,)).fetchone()
                created.append({"offeringId":offering_id,"publicationId":publication_id,
                                "assetId":int(asset_row["hero_asset_id"]),"priceMinor":int(price)})
        for item in created:self.scenarios.record_fixture(scenario_id,"commercial_offerings",item["offeringId"])
        return created

    def prepare_session_compatible_inventory(self, scenario_id: str, inventory):
        """Bind synthetic READY offerings to one canonical SESSION deliverable."""
        items=tuple(dict(item) for item in inventory)
        if len(items) < 2:
            raise ValueError("C06 Session fixture requires at least two paid steps.")
        base=self._ensure_customer(scenario_id)
        deliverable_id=uuid5(NAMESPACE_URL,f"session-deliverable:{scenario_id}")
        session_ref=f"certification-{scenario_id.lower()}-session"
        asset_ids=[int(item["assetId"]) for item in items]
        with self.scenarios.connection() as c:
            c.execute("""INSERT INTO photoshoot_commerce_deliverables(
                deliverable_id,photoshoot_session_id,creator_profile_id,display_name,
                ordered_member_asset_ids,shot_count,hero_asset_id,completed_at,
                intelligence_status,commerce_status,registration_state,selling_mode,
                is_active,is_archived)
                VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,NOW(),'READY','READY',
                    'IN_ASSET_LIBRARY','SESSION',TRUE,FALSE)
                ON CONFLICT(deliverable_id) DO UPDATE SET
                    ordered_member_asset_ids=EXCLUDED.ordered_member_asset_ids,
                    shot_count=EXCLUDED.shot_count,hero_asset_id=EXCLUDED.hero_asset_id,
                    intelligence_status='READY',commerce_status='READY',
                    registration_state='IN_ASSET_LIBRARY',selling_mode='SESSION',
                    is_active=TRUE,is_archived=FALSE,updated_at=NOW()""",
                (deliverable_id,session_ref,base["creator_profile_id"],
                 "C06 Certification Session",json.dumps(asset_ids),len(asset_ids),asset_ids[0]))
            c.execute("""INSERT INTO photoshoot_intelligence_profiles(
                photoshoot_session_id,status,profile_data)
                VALUES (%s,'READY',%s::jsonb)
                ON CONFLICT(photoshoot_session_id) DO UPDATE SET
                    status='READY',profile_data=EXCLUDED.profile_data,updated_at=NOW()""",
                (session_ref,json.dumps({"commercial_title":"C06 Certification Session",
                                         "commercial_summary":"Synthetic Session boundary fixture"})))
            for position,item in enumerate(items,1):
                asset_id=int(item["assetId"])
                c.execute("""INSERT INTO photoshoot_asset_memberships(
                    photoshoot_session_id,asset_id,shot_order,approved,is_hero)
                    VALUES (%s,%s,%s,TRUE,%s) ON CONFLICT(photoshoot_session_id,asset_id)
                    DO UPDATE SET shot_order=EXCLUDED.shot_order,approved=TRUE,is_hero=EXCLUDED.is_hero""",
                    (session_ref,asset_id,position,position==1))
                c.execute("""UPDATE content_items SET media_metadata=jsonb_set(
                    COALESCE(media_metadata,'{}'::jsonb),'{photoshoot_session}',%s::jsonb,true)
                    WHERE id=%s""",(json.dumps({"session_id":session_ref}),asset_id))
                c.execute("""UPDATE commercial_offerings
                    SET source_photoshoot_deliverable_id=%s WHERE offering_id=%s""",
                    (deliverable_id,item["offeringId"]))
        self.scenarios.record_fixture(
            scenario_id,"photoshoot_commerce_deliverables",deliverable_id,
        )
        return {"deliverableId":deliverable_id,"sessionReference":session_ref,
                "sellingMode":"SESSION","offeringIds":[item["offeringId"] for item in items]}

    def derived_state(self, scenario_id: str, *, behavior=None, now=None):
        definition=self.scenarios.definition(scenario_id)
        customer=self.scenarios.customer_for(definition)
        with self.scenarios.connection() as c:
            profile=c.execute("""SELECT * FROM customer_commerce_profiles
                WHERE external_fanvue_user_uuid=%s ORDER BY updated_at DESC LIMIT 1""",
                (customer.synthetic_buyer_uuid,)).fetchone()
            ownership=c.execute("SELECT COUNT(*) n FROM provider_purchase_asset_ownership WHERE external_fanvue_user_uuid=%s",(customer.synthetic_buyer_uuid,)).fetchone()["n"]
            active_intent=c.execute("SELECT purchase_intent_id FROM purchase_intents WHERE telegram_user_id=%s AND status IN ('CREATED','PRESENTED','CLICKED') ORDER BY created_at DESC LIMIT 1",(customer.telegram_user_id,)).fetchone()
            active_session=c.execute("SELECT sales_session_id,state FROM sales_sessions WHERE external_fanvue_user_uuid=%s AND state IN ('ACTIVE','OFFERING','AWAITING_PAYMENT','CONTINUING') ORDER BY created_at DESC LIMIT 1",(customer.synthetic_buyer_uuid,)).fetchone()
        commerce={
            "schemaVersion":"customer_commerce_memory_v1",
            "verifiedPurchaseCount":int(profile["purchase_count"] if profile else 0),
            "lifetimeGrossMinor":int(profile["lifetime_gross_minor"] if profile else 0),
            "lifetimeNetMinor":int(profile["lifetime_net_minor"] if profile else 0),
            "averageOrderValueMinor":int(profile["average_order_value_minor"] if profile else 0),
            "largestOrderMinor":int(profile["largest_purchase_minor"] if profile else 0),
            "lastPurchaseAt":profile["last_purchase_at"].isoformat() if profile and profile["last_purchase_at"] else None,
            "ownership":{"count":ownership},
        }
        from app.services.customer_value_attention_service import CustomerValueAttentionService
        attention=CustomerValueAttentionService().project(
            commerce_memory=commerce,
            behavior=(dict(behavior) if behavior is not None
                      else self.scenarios.behavior_summary(scenario_id)),now=now)
        return {"scenarioId":scenario_id,"telegramId":customer.telegram_user_id,
            "economicState":definition.economic_state.value,**attention.to_mapping(),
            "ownershipCount":ownership,
            "activePurchaseIntent":str(active_intent["purchase_intent_id"]) if active_intent else None,
            "activeSession":({"id":str(active_session["sales_session_id"]),"state":active_session["state"]} if active_session else None)}

    def _ensure_customer(self, scenario_id):
        definition=self.scenarios.definition(scenario_id); customer=self.scenarios.customer_for(definition)
        with self.scenarios.connection() as c:
            existing_graph=c.execute("""SELECT prospect.fanvue_account_id,
                    prospect.creator_profile_id,usr.*,profile.id AS valid_profile_id
                FROM telegram_sales_prospects prospect
                JOIN fanvue_accounts account ON account.id=prospect.fanvue_account_id
                JOIN fanvue_users usr ON usr.fanvue_account_id=account.id
                    AND usr.fanvue_user_uuid=%s
                JOIN creator_profiles profile ON profile.id=prospect.creator_profile_id
                    AND profile.fanvue_account_id::text=account.id::text
                WHERE prospect.telegram_user_id=%s
                ORDER BY prospect.telegram_sales_prospect_id DESC LIMIT 1""",
                (customer.synthetic_buyer_uuid, customer.telegram_user_id)).fetchone()
            if existing_graph:
                account=int(existing_graph["fanvue_account_id"])
                user=existing_graph
                creator=c.execute("SELECT * FROM creator_profiles WHERE id=%s",
                                  (existing_graph["valid_profile_id"],)).fetchone()
            else:
                # Restart/reset removes the disposable prospect but intentionally
                # preserves its test-only account graph. Reuse the newest complete
                # graph rather than manufacturing a new account on every attempt.
                reusable=c.execute("""SELECT usr.*,account.id AS valid_account_id,
                        profile.id AS valid_profile_id
                    FROM fanvue_users usr
                    JOIN fanvue_accounts account ON account.id=usr.fanvue_account_id
                    JOIN creator_profiles profile
                      ON profile.fanvue_account_id::text=account.id::text
                    WHERE usr.fanvue_user_uuid=%s
                    ORDER BY account.id DESC,profile.is_active DESC,profile.id DESC
                    LIMIT 1""", (customer.synthetic_buyer_uuid,)).fetchone()
                if reusable:
                    account=int(reusable["valid_account_id"])
                    user=reusable
                    creator=c.execute("SELECT * FROM creator_profiles WHERE id=%s",
                                      (reusable["valid_profile_id"],)).fetchone()
                else:
                    # Interrupted certification runs can leave a memory row after
                    # their scenario registry was removed. The synthetic buyer ID
                    # is globally unique, so remove only that guarded orphan before
                    # rebuilding its isolated fixture.
                    c.execute("DELETE FROM user_memory WHERE fanvue_user_id=%s",
                              (str(customer.synthetic_buyer_uuid),))
                    account=c.execute("INSERT INTO fanvue_accounts(account_name) VALUES (%s) RETURNING id",(f"Certification {scenario_id}",)).fetchone()["id"]
                    user=c.execute("""INSERT INTO fanvue_users(fanvue_user_uuid,fanvue_account_id,username,display_name)
                        VALUES (%s,%s,%s,'Certification Buyer') RETURNING *""",(customer.synthetic_buyer_uuid,account,f"cert_{scenario_id.lower()}")).fetchone()
                    creator=c.execute("""INSERT INTO creator_profiles(fanvue_account_id,persona_name,display_name,age,gender,location)
                        VALUES (%s,'Certification Ava','Certification Ava',25,'female','test') RETURNING *""",(str(account),)).fetchone()
            c.execute("""DELETE FROM telegram_sales_prospects
                WHERE telegram_user_id=%s AND (
                    creator_profile_id<>%s OR fanvue_account_id<>%s
                )""", (customer.telegram_user_id, creator["id"], account))
            c.execute("""DELETE FROM user_memory
                WHERE fanvue_user_id=%s AND fanvue_account_id<>%s""",
                (str(customer.synthetic_buyer_uuid),account))
            c.execute("""INSERT INTO telegram_identity_observations(telegram_user_id,telegram_chat_id)
                VALUES (%s,%s) ON CONFLICT(telegram_user_id) DO UPDATE SET last_observed_at=NOW()""",(customer.telegram_user_id,customer.telegram_chat_id))
            prospect=c.execute("""SELECT * FROM telegram_sales_prospects WHERE creator_profile_id=%s
                AND fanvue_account_id=%s AND telegram_user_id=%s""",(creator["id"],account,customer.telegram_user_id)).fetchone()
            if not prospect:
                prospect_id=uuid5(NAMESPACE_URL,f"prospect:{scenario_id}")
                c.execute("""INSERT INTO telegram_sales_prospects(telegram_sales_prospect_id,creator_profile_id,
                    fanvue_account_id,telegram_user_id,telegram_chat_id,relationship_state,preference_state)
                    VALUES (%s,%s,%s,%s,%s,'{}','{}')""",(prospect_id,creator["id"],account,customer.telegram_user_id,customer.telegram_chat_id))
        return {"scenario_id":scenario_id,"telegram_user_id":customer.telegram_user_id,
            "telegram_chat_id":customer.telegram_chat_id,"buyer_uuid":customer.synthetic_buyer_uuid,
            "fanvue_account_id":int(account),"fanvue_user_id":int(user["id"]),
            "creator_profile_id":int(creator["id"])}

    def _create_intent(self, scenario_id, base, *, index, amount_minor, purchased_at, session):
        offering_id=uuid5(NAMESPACE_URL,f"offering:{scenario_id}:{index}")
        publication_id=uuid5(NAMESPACE_URL,f"publication:{scenario_id}:{index}")
        intent_id=uuid5(NAMESPACE_URL,f"intent:{scenario_id}:{index}")
        reservation_id=uuid5(NAMESPACE_URL,f"fingerprint:{scenario_id}:{index}")
        runtime_id=uuid5(NAMESPACE_URL,f"runtime-link:{scenario_id}:{index}")
        exact_price=amount_minor
        with self.scenarios.connection() as c:
            existing=c.execute("SELECT status FROM purchase_intents WHERE purchase_intent_id=%s",(intent_id,)).fetchone()
            if existing:
                raise ValueError(f"Historical purchase {scenario_id}/{index} already exists; reset first.")
            stale=c.execute("SELECT hero_asset_id FROM commercial_offerings WHERE offering_id=%s",(offering_id,)).fetchone()
            if stale:
                c.execute("DELETE FROM commercial_publications WHERE commercial_offering_id=%s",(offering_id,))
                c.execute("DELETE FROM commercial_offering_assets WHERE offering_id=%s",(offering_id,))
                c.execute("DELETE FROM commercial_offerings WHERE offering_id=%s",(offering_id,))
                c.execute("DELETE FROM content_items WHERE id=%s",(stale["hero_asset_id"],))
            asset=c.execute("""INSERT INTO content_items(file_path,classification,
                creator_profile_id) VALUES (%s,'SAFE',%s) RETURNING id""",
                (f"certification/{scenario_id}/{index}.jpg",
                 base["creator_profile_id"])).fetchone()["id"]
            c.execute("""INSERT INTO commercial_offerings(offering_id,creator_profile_id,offering_type,title,
                hero_asset_id,primary_sales_channel,status,price_minor,currency)
                VALUES (%s,%s,'SINGLE_IMAGE',%s,%s,'AI_CHAT','READY',%s,'USD')""",(offering_id,base["creator_profile_id"],f"Certification {scenario_id} #{index}",asset,amount_minor))
            c.execute("""INSERT INTO commercial_publications(publication_id,commercial_offering_id,provider,status,
                external_product_id,provider_resource_status,publication_metadata)
                VALUES (%s,%s,'FANVUE','LIVE',%s,'PRESENT','{}')""",(publication_id,offering_id,f"cert-{scenario_id}-{index}"))
            c.execute("INSERT INTO commercial_offering_assets(offering_id,asset_id,position) VALUES (%s,%s,1)",(offering_id,asset))
            c.execute("""INSERT INTO purchase_intents(purchase_intent_id,creator_profile_id,fanvue_account_id,
                telegram_user_id,telegram_chat_id,commercial_offering_id,commercial_publication_id,provider,
                provider_resource_id,delivery_url,correlation_id,expected_price_minor,configured_base_price_minor,
                expected_currency,expires_at,identity_bootstrap_mode)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'FANVUE',%s,'https://example.invalid/certification',
                %s,%s,%s,'USD',%s,'PRIVATE_CHAT_FINGERPRINT')""",(intent_id,base["creator_profile_id"],base["fanvue_account_id"],base["telegram_user_id"],base["telegram_chat_id"],offering_id,publication_id,f"runtime-{scenario_id}-{index}",uuid5(NAMESPACE_URL,f"correlation:{scenario_id}:{index}"),amount_minor,amount_minor,datetime.now(timezone.utc)+timedelta(days=1)))
            c.execute("""INSERT INTO fanvue_fingerprint_reservations(fingerprint_reservation_id,fanvue_account_id,
                currency,exact_price_minor,configured_base_price_minor,purchase_intent_id,telegram_user_id,state)
                VALUES (%s,%s,'USD',%s,%s,%s,%s,'ACTIVE')""",(reservation_id,base["fanvue_account_id"],exact_price,amount_minor,intent_id,base["telegram_user_id"]))
            c.execute("""INSERT INTO fanvue_runtime_media_links(runtime_media_link_id,purchase_intent_id,
                fingerprint_reservation_id,provider_media_link_uuid,provider_url,state,creation_operation_key,expires_at)
                VALUES (%s,%s,%s,%s,'https://example.invalid/certification','ACTIVE',%s,NOW()+INTERVAL '1 day')""",(runtime_id,intent_id,reservation_id,str(uuid5(NAMESPACE_URL,f"provider-link:{scenario_id}:{index}")),uuid5(NAMESPACE_URL,f"create:{scenario_id}:{index}")))
            if session:
                prospect=c.execute("SELECT telegram_sales_prospect_id FROM telegram_sales_prospects WHERE telegram_user_id=%s AND fanvue_account_id=%s",(base["telegram_user_id"],base["fanvue_account_id"])).fetchone()
                c.execute("""INSERT INTO telegram_provisional_sales_sessions(provisional_session_id,
                    telegram_sales_prospect_id,creator_profile_id,fanvue_account_id,telegram_user_id,
                    telegram_chat_id,photoshoot_reference,session_strategy,state,configured_base_price_minor,
                    first_purchase_intent_id) VALUES (%s,%s,%s,%s,%s,%s,%s,'ESCALATING','AWAITING_PAYMENT',%s,%s)""",
                    (uuid5(NAMESPACE_URL,f"provisional:{scenario_id}"),prospect["telegram_sales_prospect_id"],base["creator_profile_id"],base["fanvue_account_id"],base["telegram_user_id"],base["telegram_chat_id"],f"certification-{scenario_id}",amount_minor,intent_id))
        return {"purchase_intent_id":intent_id,"offering_id":offering_id,"asset_id":asset,
                "amount_minor":amount_minor,"purchased_at":purchased_at}
