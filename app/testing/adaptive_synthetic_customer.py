"""Phase-authoritative, context-adaptive customer language for Scenario Lab."""
from __future__ import annotations

import re
from hashlib import sha256
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from enum import Enum
from typing import Any, Callable, Mapping, Sequence


class CustomerBehaviorPhase(str, Enum):
    QUIET_LOW_RETURN = "QUIET_LOW_RETURN"
    ATTRACTION = "ATTRACTION"
    COMMERCIAL_CURIOSITY = "COMMERCIAL_CURIOSITY"
    REVEAL_INTEREST = "REVEAL_INTEREST"
    BUYING_INTEREST = "BUYING_INTEREST"
    OFFER_REACTION = "OFFER_REACTION"
    POST_PURCHASE_ACKNOWLEDGEMENT = "POST_PURCHASE_ACKNOWLEDGEMENT"
    POST_PURCHASE_CONTINUITY = "POST_PURCHASE_CONTINUITY"
    DISCRETE_CONTINUATION = "DISCRETE_CONTINUATION"
    ONGOING_EXPERIENCE_CONTINUATION = "ONGOING_EXPERIENCE_CONTINUATION"
    SESSION_PROPOSAL_REACTION = "SESSION_PROPOSAL_REACTION"
    SESSION_DECLINE_DISCRETE_CONTINUATION = "SESSION_DECLINE_DISCRETE_CONTINUATION"
    HOT_PRAISE_NO_MORE_REQUEST = "HOT_PRAISE_NO_MORE_REQUEST"
    COMMERCIAL_REJECTION = "COMMERCIAL_REJECTION"


@dataclass(frozen=True)
class CustomerPhaseConstraints:
    engagement: str
    reciprocity: str
    verbosity: str
    friendliness: str
    attraction: str
    sexual_interest: str
    commercial_curiosity: str
    buying_intent: bool
    price_sensitivity: str
    rejection_state: str
    purchase_readiness: str
    relationship_depth: str
    time_waster_behavior: str
    offer_reaction: str = "NONE"
    disclosed_facts: tuple[str, ...] = ()
    fixture_buyer_state: str = "UNCHANGED"


@dataclass(frozen=True)
class AdaptiveCustomerTurn:
    scenario_id: str
    scenario_attempt: int
    logical_turn: int
    behavioral_phase: str
    customer_constraints: Mapping[str, Any]
    previous_ava_response: str
    authoritative_offer_context: Mapping[str, Any]
    recent_transcript: tuple[Mapping[str, str], ...]
    generated_customer_candidate: str | None
    validation_result: Mapping[str, Any]
    final_customer_message: str | None
    phase_transition_reason: str
    wording_source: str
    provider_metadata: Mapping[str, Any]
    blocked_reason: str | None = None

    def to_mapping(self) -> dict[str, Any]:
        return asdict(self)


class AdaptiveCustomerTrajectoryBlocked(RuntimeError):
    def __init__(self, audit: AdaptiveCustomerTurn):
        self.audit = audit
        super().__init__(audit.blocked_reason or "CUSTOMER_TRAJECTORY_BLOCKED_BY_AVA")


class AdaptiveSyntheticCustomerService:
    """Realize scenario-owned truth as a short reply to Ava's actual response."""

    _BUYING = re.compile(r"\b(?:buy|pay|purchase|unlock|send it|i(?:'|’)ll take|how much|price)\b", re.I)
    _CONTENT = re.compile(r"\b(?:private|content|pics?|photos?|videos?|something more|show me|send)\b", re.I)
    _ACCEPT = re.compile(r"\b(?:send it|i(?:'|’)ll take it|deal|unlock it for me)\b", re.I)
    _PRICE = re.compile(r"(?:\$\s*\d+(?:\.\d{1,2})?|\b\d+(?:\.\d{1,2})?\s*(?:usd|dollars?)\b)", re.I)
    _HIGH_SEXUAL_INTEREST = re.compile(
        r"\b(?:turn(?:ing)? me on|can(?:not|'t) keep (?:this|my thoughts) innocent|"
        r"my thoughts (?:are|keep getting) (?:dirty|naughty)|"
        r"making my thoughts (?:dirty|naughty)|"
        r"(?:dirty|naughty) thoughts|"
        r"(?:my |these )?(?:thoughts|mind).{0,25}(?:dirty|naughty)|"
        r"making me (?:feel|think) (?:dirty|naughty)|"
        r"want to know what you(?:'d| would) do to me|"
        r"cannot stop thinking about you that way)\b",
        re.I,
    )

    def __init__(self, generator: Callable[[Mapping[str, Any]], str] | None = None):
        self.generator = generator

    @staticmethod
    def constraints_for(scenario_id: str, phase: CustomerBehaviorPhase,
                        *, offer_reaction: str = "NONE",
                        disclosed_facts: Sequence[str] = (),
                        fixture_buyer_state: str = "UNCHANGED") -> CustomerPhaseConstraints:
        scenario = scenario_id.upper()
        verbosity = "HIGH" if scenario == "C07" else "LOW" if scenario == "C02" else "MEDIUM"
        friendliness = "RUDE" if scenario == "C03" else "FRIENDLY"
        values = {
            CustomerBehaviorPhase.QUIET_LOW_RETURN: ("LOW", "LOW", "NONE", "NONE", False, "NONE"),
            CustomerBehaviorPhase.ATTRACTION: ("MEDIUM", "LOW", "MILD", "MILD", False, "NONE"),
            CustomerBehaviorPhase.COMMERCIAL_CURIOSITY: ("MEDIUM", "MEDIUM", "MILD", "MILD", False, "PRESENT"),
            CustomerBehaviorPhase.REVEAL_INTEREST: ("HIGH", "HIGH", "MILD", "MILD", False, "PRESENT"),
            CustomerBehaviorPhase.BUYING_INTEREST: ("HIGH", "MEDIUM", "MILD", "MILD", True, "READY"),
            CustomerBehaviorPhase.OFFER_REACTION: ("HIGH", "MEDIUM", "MILD", "MILD", offer_reaction == "ACCEPT", "OFFER_DEPENDENT"),
            CustomerBehaviorPhase.POST_PURCHASE_ACKNOWLEDGEMENT: ("HIGH", "HIGH", "MILD", "MILD", False, "PURCHASED"),
            CustomerBehaviorPhase.POST_PURCHASE_CONTINUITY: ("HIGH", "HIGH", "MILD", "MILD", False, "PURCHASED"),
            CustomerBehaviorPhase.DISCRETE_CONTINUATION: ("HIGH", "HIGH", "MILD", "MILD", True, "READY"),
            CustomerBehaviorPhase.ONGOING_EXPERIENCE_CONTINUATION: ("HIGH", "HIGH", "MILD", "MILD", True, "READY"),
            CustomerBehaviorPhase.SESSION_PROPOSAL_REACTION: ("HIGH", "HIGH", "MILD", "MILD", True, "READY"),
            CustomerBehaviorPhase.SESSION_DECLINE_DISCRETE_CONTINUATION: ("HIGH", "HIGH", "MILD", "MILD", True, "READY"),
            CustomerBehaviorPhase.HOT_PRAISE_NO_MORE_REQUEST: ("HIGH", "HIGH", "HIGH", "HIGH", False, "PURCHASED"),
            CustomerBehaviorPhase.COMMERCIAL_REJECTION: ("LOW", "LOW", "MILD", "MILD", False, "NONE"),
        }[phase]
        high_sexual = scenario in {"C05", "C06"} and phase in {
            CustomerBehaviorPhase.ATTRACTION,
            CustomerBehaviorPhase.COMMERCIAL_CURIOSITY,
            CustomerBehaviorPhase.REVEAL_INTEREST,
            CustomerBehaviorPhase.BUYING_INTEREST,
        }
        return CustomerPhaseConstraints(
            engagement=values[0], reciprocity=values[1], verbosity=verbosity,
            friendliness=friendliness,
            attraction="HIGH" if high_sexual else values[2],
            sexual_interest="HIGH" if high_sexual else values[3],
            commercial_curiosity=values[5], buying_intent=values[4],
            price_sensitivity="MODERATE" if phase is CustomerBehaviorPhase.OFFER_REACTION else "NONE",
            rejection_state="NONE", purchase_readiness=values[5], relationship_depth="SCENARIO_CONTROLLED",
            time_waster_behavior="IDLE_LOW_RETURN" if phase is CustomerBehaviorPhase.QUIET_LOW_RETURN else "NONE",
            offer_reaction=offer_reaction, disclosed_facts=tuple(disclosed_facts),
            fixture_buyer_state=fixture_buyer_state,
        )

    def generate_turn(self, *, scenario_id: str, scenario_attempt: int, logical_turn: int,
                      phase: CustomerBehaviorPhase, constraints: CustomerPhaseConstraints,
                      previous_ava_response: str,
                      recent_transcript: Sequence[Mapping[str, str]],
                      phase_transition_reason: str,
                      authoritative_offer_context: Mapping[str, Any] | None = None,
                      purchase_ordinal: int | None = None,
                      ) -> AdaptiveCustomerTurn:
        ava = str(previous_ava_response or "").strip()
        # Keep six complete exchanges so repeated adaptive phases can vary
        # sustainably while retaining a bounded prompt/validation window.
        transcript = tuple(dict(item) for item in recent_transcript[-12:])
        offer = self._offer_context(
            ava, authoritative_offer_context=authoritative_offer_context,
        )
        if not ava and logical_turn > 1:
            return self._blocked(scenario_id, scenario_attempt, logical_turn, phase,
                                 constraints, ava, transcript, phase_transition_reason,
                                 "CUSTOMER_TRAJECTORY_BLOCKED_BY_AVA: previous Ava response is empty")
        if re.search(r"\b(?:leave me alone|stop messaging|don(?:'|’)t want to talk|go away)\b", ava, re.I):
            return self._blocked(scenario_id, scenario_attempt, logical_turn, phase,
                                 constraints, ava, transcript, phase_transition_reason,
                                 "CUSTOMER_TRAJECTORY_BLOCKED_BY_AVA: Ava explicitly ended the conversation")
        prompt = {
            "scenarioId": scenario_id, "phase": phase.value,
            "constraints": asdict(constraints), "previousAvaResponse": ava,
            "recentTranscript": transcript, "offerContext": offer,
            "purchaseOrdinal": purchase_ordinal,
            "fidelityRequirements": {
                "expressAttractionIntensity": constraints.attraction,
                "expressSexualInterestIntensity": constraints.sexual_interest,
                "commercialCuriosityMustRemain": constraints.commercial_curiosity,
                "buyingIntentMustRemain": constraints.buying_intent,
                "purchaseReadinessMustRemain": constraints.purchase_readiness,
                "avoidRecentCustomerWording": [
                    str(item.get("content") or "") for item in transcript
                    if str(item.get("role") or "").lower() == "customer"
                ],
                "maximumWords": (
                    8 if constraints.verbosity == "LOW"
                    else 30 if constraints.verbosity == "HIGH" else 16
                ),
                "highSexualInterestMeaning": (
                    "Unmistakably provocative sexual attraction or excitement; "
                    "romantic admiration or a mild compliment is insufficient."
                    if constraints.sexual_interest == "HIGH" else None
                ),
                "mustRespondToAvaLatestMessage": bool(ava),
                "mustAnswerAvaQuestion": "?" in ava,
            },
            "instruction": (
                "Return only one customer text. Realize every structured category and "
                "intensity without adding commerce. Use natural varied wording responsive "
                "to Ava's latest message. Never change structured customer truth."
            ),
        }
        candidate = str(self.generator(prompt)).strip() if self.generator else None
        generated_candidate = candidate
        generated_validation = None
        source = "PROVIDER" if candidate else "DETERMINISTIC_PHASE_SAFE_FALLBACK"
        if candidate:
            generated_validation = self.validate(
                candidate, phase=phase, constraints=constraints,
                previous_ava_response=ava, offer_context=offer,
                recent_transcript=transcript,
            )
            if not generated_validation["valid"]:
                candidate = None
                source = "DETERMINISTIC_PHASE_SAFE_FALLBACK_AFTER_REJECTION"
        final = candidate or self._fallback(
            phase, constraints, ava, offer, transcript=transcript,
        )
        validation = self.validate(final, phase=phase, constraints=constraints,
                                   previous_ava_response=ava, offer_context=offer,
                                   recent_transcript=transcript)
        if not validation["valid"]:
            return self._blocked(scenario_id, scenario_attempt, logical_turn, phase,
                                 constraints, ava, transcript, phase_transition_reason,
                                 "CUSTOMER_TRAJECTORY_BLOCKED_BY_AVA: " + "; ".join(validation["reasons"]),
                                 candidate=final, validation=validation, source=source)
        validation = {**validation, "generatedCandidateValidation": generated_validation}
        return AdaptiveCustomerTurn(
            scenario_id, scenario_attempt, logical_turn, phase.value, asdict(constraints),
            ava, offer, transcript, generated_candidate, validation, final, phase_transition_reason,
            source, {
                "providerUsed": bool(self.generator),
                "hiddenReasoningPersisted": False,
                "purchaseOrdinal": purchase_ordinal,
            },
        )

    def validate(self, message: str, *, phase: CustomerBehaviorPhase,
                 constraints: CustomerPhaseConstraints, previous_ava_response: str,
                 offer_context: Mapping[str, Any],
                 recent_transcript: Sequence[Mapping[str, str]] = ()) -> dict[str, Any]:
        reasons = []
        from app.services.conversational_sales_progression_service import (
            ConversationalSalesProgressionService,
        )
        buying = bool(
            self._BUYING.search(message)
            or ConversationalSalesProgressionService().has_direct_purchase_intent(
                message
            )
        )
        content = bool(self._CONTENT.search(message))
        accepts = bool(self._ACCEPT.search(message)) and buying
        attraction = bool(re.search(
            r"\b(?:hot|cute|pretty|gorgeous|beautiful|attractive|sexy|"
            r"look good|into you|intrigued by you|captivat(?:ed|ing))\b", message, re.I,
        ))
        high_sexual = bool(self._HIGH_SEXUAL_INTEREST.search(message))
        attraction = attraction or high_sexual
        from app.services.contextual_customer_tone_service import (
            ContextualCustomerToneService,
        )
        runtime_sexual = bool(
            ContextualCustomerToneService().classify(
                message=message, recent_transcript=(),
            ).get("sexualOrProvocative")
        )
        if phase is CustomerBehaviorPhase.ATTRACTION and not attraction:
            reasons.append("ATTRACTION_PHASE_WITHOUT_ATTRACTION")
        if constraints.sexual_interest == "HIGH" and not high_sexual:
            reasons.append("REQUIRED_HIGH_SEXUAL_INTEREST_NOT_EXPRESSED")
        trajectory_alignment_required = constraints.sexual_interest == "HIGH"
        trajectory_alignment_satisfied = (
            runtime_sexual if trajectory_alignment_required else True
        )
        if trajectory_alignment_required and not trajectory_alignment_satisfied:
            reasons.append("RUNTIME_SEXUAL_PROVOCATIVE_ALIGNMENT_MISSING")
        if constraints.sexual_interest not in {"HIGH", "STRONG"} and high_sexual:
            reasons.append("SEXUAL_INTEREST_INTENSITY_EXCEEDED")
        prices = self._PRICE.findall(message)
        if buying and not constraints.buying_intent:
            reasons.append("WORDING_INTRODUCED_BUYING_INTENT")
        if phase is CustomerBehaviorPhase.QUIET_LOW_RETURN and content:
            reasons.append("QUIET_PHASE_INTRODUCED_CONTENT_INTEREST")
        if phase is CustomerBehaviorPhase.ATTRACTION and (content or buying):
            reasons.append("ATTRACTION_PHASE_BLURRED_COMMERCIAL_TRUTH")
        progression_features = (
            ConversationalSalesProgressionService.transition_features(message)
        )
        if phase is CustomerBehaviorPhase.COMMERCIAL_CURIOSITY:
            if not progression_features["commercial_response_interest"]:
                reasons.append(
                    "COMMERCIAL_CURIOSITY_WITHOUT_RECOGNIZABLE_INTEREST"
                )
        if phase is CustomerBehaviorPhase.REVEAL_INTEREST:
            if not progression_features["reveal_request"]:
                reasons.append("REVEAL_INTEREST_PHASE_WITHOUT_REVEAL_REQUEST")
        if phase in {
            CustomerBehaviorPhase.DISCRETE_CONTINUATION,
            CustomerBehaviorPhase.ONGOING_EXPERIENCE_CONTINUATION,
            CustomerBehaviorPhase.SESSION_PROPOSAL_REACTION,
            CustomerBehaviorPhase.SESSION_DECLINE_DISCRETE_CONTINUATION,
            CustomerBehaviorPhase.HOT_PRAISE_NO_MORE_REQUEST,
        }:
            from app.services.session_escalation_decision_service import (
                SessionEscalationDecisionService,
            )
            continuation = SessionEscalationDecisionService.continuation_intent(message)
            reaction = SessionEscalationDecisionService.proposal_reaction(
                message, proposal_pending=True,
            )
            if phase is CustomerBehaviorPhase.DISCRETE_CONTINUATION and continuation != "DISCRETE_ITEM":
                reasons.append("DISCRETE_CONTINUATION_SEMANTICS_MISSING")
            if phase is CustomerBehaviorPhase.ONGOING_EXPERIENCE_CONTINUATION and continuation != "ONGOING_EXPERIENCE":
                reasons.append("ONGOING_EXPERIENCE_SEMANTICS_MISSING")
            if phase is CustomerBehaviorPhase.SESSION_PROPOSAL_REACTION and reaction != "ACCEPT_OR_LEAN_IN":
                reasons.append("SESSION_ACCEPTANCE_SEMANTICS_MISSING")
            if phase is CustomerBehaviorPhase.SESSION_DECLINE_DISCRETE_CONTINUATION and reaction != "DECLINE_SESSION_BUT_WANTS_MORE":
                reasons.append("SESSION_DECLINE_DISCRETE_SEMANTICS_MISSING")
            if phase is CustomerBehaviorPhase.HOT_PRAISE_NO_MORE_REQUEST and continuation != "NONE":
                reasons.append("PRAISE_ONLY_INTRODUCED_CONTINUATION")
        recent_customer = [
            str(item.get("content") or "").strip()
            for item in recent_transcript
            if str(item.get("role") or "").lower() == "customer"
        ]
        normalized = self._normalize(message)
        if any(normalized and normalized == self._normalize(prior) for prior in recent_customer):
            reasons.append("REPEATED_RECENT_CUSTOMER_WORDING")
        elif any(
            normalized and SequenceMatcher(None, normalized, self._normalize(prior)).ratio() >= .86
            for prior in recent_customer
        ):
            reasons.append("NEAR_DUPLICATE_RECENT_CUSTOMER_WORDING")
        recent_repetition_risk = any(reason in {
            "REPEATED_RECENT_CUSTOMER_WORDING",
            "NEAR_DUPLICATE_RECENT_CUSTOMER_WORDING",
        } for reason in reasons)
        if prices and not offer_context.get("priceText"):
            reasons.append("CUSTOMER_REFERENCED_UNSUPPLIED_PRICE")
        if prices and offer_context.get("priceText"):
            authoritative_price = self._price_minor(offer_context["priceText"])
            if any(self._price_minor(value) != authoritative_price for value in prices):
                reasons.append("CUSTOMER_REFERENCED_DIFFERENT_PRICE")
        if accepts and not offer_context.get("offerPresented"):
            reasons.append("CUSTOMER_ACCEPTED_NONEXISTENT_OFFER")
        if phase is CustomerBehaviorPhase.OFFER_REACTION and not offer_context.get("offerPresented"):
            reasons.append("OFFER_REACTION_WITHOUT_ACTUAL_OFFER")
        if constraints.offer_reaction == "HESITATE" and accepts:
            reasons.append("HESITATION_PHASE_ACCEPTED_OFFER")
        disclosed = {
            key.strip().lower(): value.strip().lower()
            for fact in constraints.disclosed_facts if "=" in fact
            for key, value in (fact.split("=", 1),)
        }
        location_claim = re.search(r"\bi live in\s+([A-Za-z ]{2,30})", message, re.I)
        if location_claim and disclosed.get("location"):
            claimed = location_claim.group(1).strip().lower()
            if claimed != disclosed["location"]:
                reasons.append("CUSTOMER_FACT_CONTRADICTED_LOCATION")
        max_words = 8 if constraints.verbosity == "LOW" else 30 if constraints.verbosity == "HIGH" else 16
        if len(re.findall(r"\b\w+\b", message)) > max_words:
            reasons.append("CUSTOMER_VERBOSITY_EXCEEDED_PHASE")
        return {"valid": not reasons, "reasons": reasons,
                "trajectorySexualAlignmentRequired": trajectory_alignment_required,
                "trajectorySexualAlignmentSatisfied": trajectory_alignment_satisfied,
                "trajectorySexualAlignmentSource": (
                    "ContextualCustomerToneService.sexualOrProvocative"
                ),
                "recentCustomerRepetitionRisk": recent_repetition_risk,
                "derivedSignals": {"buyingIntent": buying, "contentInterest": content,
                                   "offerAcceptance": accepts, "priceReferences": prices,
                                   "attraction": attraction,
                                   "sexualInterestIntensity": "HIGH" if high_sexual else "MILD_OR_NONE",
                                   "runtimeSexualOrProvocative": runtime_sexual},
                "structuredTruthUnchanged": not reasons}

    def _fallback(self, phase, constraints, ava, offer, *, transcript=()):
        question = "?" in ava
        lower = ava.lower()
        rude = constraints.friendliness == "RUDE"
        if phase is CustomerBehaviorPhase.QUIET_LOW_RETURN:
            if constraints.verbosity == "HIGH":
                return "not much honestly, just winding down and seeing where the night goes"
            if re.search(r"\b(?:what are you|what(?:'|’)re you|doing|up to)\b", lower):
                return "not much honestly"
            if re.search(r"\b(?:plans?|anything fun)\b", lower):
                return "nah not really"
            if question:
                return "idk honestly"
            return "yeah just scrolling"
        if phase is CustomerBehaviorPhase.ATTRACTION:
            if constraints.sexual_interest == "HIGH":
                return self._high_sexual_fallback(ava, transcript)
            return "you look pretty hot though" if not rude else "you look hot, at least"
        if phase is CustomerBehaviorPhase.COMMERCIAL_CURIOSITY:
            return (
                self._commercial_curiosity_fallback(ava, transcript)
                if constraints.sexual_interest == "HIGH"
                else "tell me more about that private side"
                if constraints.verbosity == "LOW"
                else self._bounded_nonrepeating_fallback((
                    "okay, I'm curious... tell me a little more",
                    "you've got my attention now, give me another hint",
                    "hmm, I'm intrigued... go on",
                    "alright, tell me a bit more about what you're teasing",
                ), transcript)
            )
        if phase is CustomerBehaviorPhase.REVEAL_INTEREST:
            return self._reveal_interest_fallback(
                ava, transcript,
                high_sexual=constraints.sexual_interest == "HIGH",
            )
        if phase is CustomerBehaviorPhase.BUYING_INTEREST:
            return "okay, how much is it?" if not offer.get("priceText") else "okay how do I unlock it?"
        if phase is CustomerBehaviorPhase.POST_PURCHASE_ACKNOWLEDGEMENT:
            return self._bounded_nonrepeating_fallback((
                "okay I unlocked it, that was hot",
                "yeah I got it, I like that one",
                "got it, that one was good",
                "unlocked it, definitely into that",
                "yep got it, nice choice",
                "okay, that one hit",
            ), transcript)
        if phase is CustomerBehaviorPhase.POST_PURCHASE_CONTINUITY:
            return "yeah, you definitely know what I like now"
        if phase is CustomerBehaviorPhase.DISCRETE_CONTINUATION:
            return "that was hot, got another one?"
        if phase is CustomerBehaviorPhase.ONGOING_EXPERIENCE_CONTINUATION:
            return "don't stop, I want to keep this going with you"
        if phase is CustomerBehaviorPhase.SESSION_PROPOSAL_REACTION:
            return "yeah I'm in, let's keep it going"
        if phase is CustomerBehaviorPhase.SESSION_DECLINE_DISCRETE_CONTINUATION:
            return "I'd rather just see another one instead"
        if phase is CustomerBehaviorPhase.HOT_PRAISE_NO_MORE_REQUEST:
            return "damn, that was seriously hot"
        if phase is CustomerBehaviorPhase.COMMERCIAL_REJECTION:
            return "nah, let's leave the selling out of it"
        if constraints.offer_reaction == "ACCEPT":
            candidates = (
                "alright yeah, send it",
                "okay, I'll take it",
                "yeah, unlock it for me",
            )
            recent_customer = {
                self._normalize(str(item.get("content") or ""))
                for item in transcript
                if str(item.get("role") or "").lower() == "customer"
            }
            return next(
                (candidate for candidate in candidates
                 if self._normalize(candidate) not in recent_customer),
                candidates[-1],
            )
        if constraints.offer_reaction == "REJECT":
            return "nah, I'll pass"
        return (f"hmm, {offer['priceText']} is more than I expected"
                if offer.get("priceText") else "hmm maybe, let me think")

    def _bounded_nonrepeating_fallback(self, candidates, transcript):
        """Return the first phase-safe candidate outside recent exact/near history."""
        recent_customer = [
            self._normalize(str(item.get("content") or ""))
            for item in transcript
            if str(item.get("role") or "").lower() == "customer"
        ]
        for candidate in candidates:
            normalized = self._normalize(candidate)
            if all(
                normalized != prior
                and SequenceMatcher(None, normalized, prior).ratio() < .86
                for prior in recent_customer if prior
            ):
                return candidate
        # Validation remains the fail-closed authority when the bounded pool is
        # exhausted; returning the final candidate cannot bypass that guard.
        return candidates[-1]

    def _offer_context(
        self, ava: str, *, authoritative_offer_context: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        structured = dict(authoritative_offer_context or {})
        structured_intent = dict(structured.get("purchaseIntent") or {})
        structured_cta = dict(structured.get("cta") or {})
        if structured.get("offeringId") and structured_intent.get("id"):
            return {
                "offerPresented": True,
                "offeringId": str(structured["offeringId"]),
                "offeringName": structured.get("name"),
                "offeringType": structured.get("type"),
                "priceText": structured.get("price"),
                "priceMinor": structured.get("priceMinor"),
                "currency": structured.get("currency"),
                "ctaPresent": bool(structured_cta),
                "cta": structured_cta,
                "purchaseIntentId": str(structured_intent["id"]),
                "purchaseIntentState": structured_intent.get("state"),
                "authority": "SYNTHETIC_PPV_PRESENTATION",
            }
        price = self._PRICE.search(ava)
        has_cta = bool(re.search(r"\b(?:unlock|buy|grab|get it|tap|link|send it)\b", ava, re.I))
        content = bool(self._CONTENT.search(ava))
        return {"offerPresented": bool(price and (has_cta or content)),
                "priceText": price.group(0) if price else None, "ctaPresent": has_cta,
                "authority": "AVA_TEXT_INFERENCE"}

    @staticmethod
    def _price_minor(value: Any) -> int | None:
        match = re.search(r"\d+(?:\.\d{1,2})?", str(value or ""))
        if not match:
            return None
        return int(round(float(match.group(0)) * 100))

    @staticmethod
    def _normalize(value: Any) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", str(value or "").lower()))

    def _high_sexual_fallback(self, ava: str, transcript) -> str:
        """Compose bounded sexual-only wording without a static sentence cycle."""
        recent = [
            str(item.get("content") or "").strip()
            for item in transcript
            if str(item.get("role") or "").lower() == "customer"
        ]
        question_response = bool(
            "?" in ava and re.search(
                r"\b(?:what|imagining|thinking|mind|thoughts|tell me)\b", ava, re.I,
            )
        )
        openings = (
            ("let's just say", "honestly", "right now", "the way you're talking")
            if question_response else
            ("you look dangerously good", "you're really getting to me",
             "that side of you is trouble", "you're making it hard to behave")
        )
        continuations = (
            "my thoughts about you are getting dirty",
            "these naughty thoughts keep getting worse",
            "my mind is going somewhere dirty with you",
            "naughty thoughts about you keep taking over",
        )
        candidates = [
            f"{opening}, {continuation}"
            for opening in openings for continuation in continuations
        ]
        seed = int.from_bytes(
            sha256((ava + "|" + "|".join(recent)).encode()).digest()[:4], "big"
        )
        for offset in range(len(candidates)):
            candidate = candidates[(seed + offset) % len(candidates)]
            normalized = self._normalize(candidate)
            if all(
                SequenceMatcher(None, normalized, self._normalize(prior)).ratio() < .86
                for prior in recent
            ):
                return candidate
        return candidates[seed % len(candidates)]

    def _commercial_curiosity_fallback(self, ava: str, transcript) -> str:
        candidates = [
            "my thoughts are getting dirty... give me a hint about that private side",
            "you're turning me on now... tell me more about that private side",
            "these naughty thoughts are getting worse... what are you hinting at",
            "okay now my mind is getting dirty... what exactly are you teasing me about",
            "you're making my thoughts naughty... tell me a bit more about that private side",
            "that tease has my thoughts going somewhere naughty... tell me a little more",
        ]
        return self._nonrepeating_fallback(candidates, ava, transcript)

    def _reveal_interest_fallback(
        self, ava: str, transcript, *, high_sexual: bool = False,
    ) -> str:
        """Stronger post-BUILD_INTEREST lean-in, without asserting purchase intent."""
        candidates = (
            [
                "my thoughts are getting dirty... you've teased me enough",
                "you're really turning me on now... tell me what you mean",
                "my thoughts are getting naughty... tell me what you're teasing",
                "these naughty thoughts keep getting worse... enough with the teasing",
            ]
            if high_sexual else
            [
                "okay, now I'm really intrigued... tell me what you mean",
                "you've definitely got my attention... tell me what you mean",
                "alright, you've teased me enough",
                "now I'm even more curious... what exactly are you hinting about",
                "you've built enough suspense... tell me what you mean",
                "okay, that got my attention... enough with the teasing",
            ]
        )
        return self._nonrepeating_fallback(
            candidates, ava, transcript,
            contextual_endings=(
                "tell me what you mean", "give me one more hint",
                "explain the tease a little more", "what are you hinting at",
            ),
        )

    def _nonrepeating_fallback(
        self, candidates, ava: str, transcript, *, contextual_endings=None,
    ) -> str:
        """Choose bounded phase-safe wording; final validation remains authoritative."""
        recent = [
            str(item.get("content") or "").strip()
            for item in transcript
            if str(item.get("role") or "").lower() == "customer"
        ]
        contextual = [
            f"my thoughts are getting naughty from that... {ending}"
            for ending in (contextual_endings or (
                "tell me another hint", "tell me a little more",
                "what exactly are you teasing about", "reveal what you're teasing",
            ))
        ]
        pool = list(candidates) + contextual
        seed = int.from_bytes(
            sha256((str(ava or "") + "|" + "|".join(recent)).encode()).digest()[:4],
            "big",
        )
        for offset in range(len(pool)):
            candidate = pool[(seed + offset) % len(pool)]
            normalized = self._normalize(candidate)
            if all(
                SequenceMatcher(None, normalized, self._normalize(prior)).ratio() < .86
                for prior in recent
            ):
                return candidate
        # Deliberately return a candidate for the existing validator to reject
        # fail-closed when no safe bounded variation remains.
        return pool[seed % len(pool)]

    def _blocked(self, scenario_id, attempt, turn, phase, constraints, ava, transcript,
                 transition_reason, reason, *, candidate=None, validation=None, source="BLOCKED"):
        return AdaptiveCustomerTurn(
            scenario_id, attempt, turn, phase.value, asdict(constraints), ava,
            {}, transcript, candidate, validation or {"valid": False, "reasons": [reason]},
            None, transition_reason, source,
            {"providerUsed": bool(self.generator), "hiddenReasoningPersisted": False}, reason,
        )
