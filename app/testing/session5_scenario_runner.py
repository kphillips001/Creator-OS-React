"""Operator CLI for the isolated Session 5 customer-scenario laboratory."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from psycopg import sql

from app.testing.session5_scenario_harness import (
    CustomerScenarioHarness, HistoricalPurchaseFixtureBuilder,
    SCENARIO_MANIFEST, ScenarioState, SimulatedProviderPurchaseHarness,
    DETERMINISTIC_CERTIFICATION, REAL_AVA_LANGUAGE,
    ScenarioTurnExecutionIdentity,
)
from app.testing.session5_scenario_recovery import ScenarioRecoveryService
from app.testing.postgres_safety import Session5DatabasePurpose


EXECUTION_STATES = ("PREPARING", "READY", "RUNNING")
TERMINAL_STATES = ("COMPLETED", "SNAPSHOTTED")
INSPECTABLE_STATES = EXECUTION_STATES + TERMINAL_STATES
GRADES = {"PASS", "PASS_WITH_NOTES", "FAIL"}
SEVERITIES = {"CRITICAL", "MAJOR", "QUALITY"}
PURCHASE_PLANS = {
    "C11": [1400], "C12": [1400], "C13": [1200, 1800], "C14": [1400],
    "C15": [5000, 5001, 5002], "C16": [10000, 10001, 10002, 10003, 10004],
    "C17": [10000, 10001, 10002, 10003, 10004], "C18": [1400], "C19": [2200],
}


class Session5ScenarioRunner:
    """Thin operator interface. All behavior remains owned by the harness."""

    def __init__(self, harness: CustomerScenarioHarness | None = None):
        self.harness = harness or CustomerScenarioHarness(
            database_purpose=Session5DatabasePurpose.SCENARIO_LAB_OPERATOR,
        )
        self.builder = HistoricalPurchaseFixtureBuilder(self.harness)
        self._bootstrap_ledger()
        self.recovery = ScenarioRecoveryService(self.harness)

    def list(self) -> list[dict[str, Any]]:
        with self.harness.connection() as connection:
            states = {row["scenario_id"]: row["state"] for row in connection.execute(
                "SELECT scenario_id,state FROM certification_scenario_runs"
            ).fetchall()}
        return [{
            "scenario": item.scenario_id, "name": item.name,
            "description": item.description,
            "economicStartingState": item.economic_state.value,
            "syntheticTelegramId": self.harness.customer_for(item).telegram_user_id,
            "lifecycle": states.get(item.scenario_id, "AVAILABLE"),
        } for item in SCENARIO_MANIFEST]

    def prepare(self, scenario_id: str) -> dict[str, Any]:
        # Serialize the read-before-create boundary so two operators cannot both
        # observe an empty execution slot and prepare different scenarios.
        with self.harness.connection() as slot_connection:
            slot_connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                ("session5-scenario-execution-slot",),
            )
            return self._prepare_with_slot(scenario_id)

    def _prepare_with_slot(self, scenario_id: str) -> dict[str, Any]:
        scenario_id = scenario_id.upper()
        active = self._active(optional=True)
        if active is not None:
            raise RuntimeError(f"Active scenario {active['scenario_id']} must be snapshotted/reset first.")
        existing = self._run(scenario_id)
        if existing is not None:
            if existing["state"] == "SNAPSHOTTED":
                self.harness.reset(scenario_id)
            elif existing["state"] == "VERIFIED_CLEAN":
                clean = self.verify_clean(scenario_id)
                if clean["result"] != "VERIFIED_CLEAN":
                    raise RuntimeError(
                        "SCENARIO PREPARE BLOCKED: prior VERIFIED_CLEAN runtime is contaminated."
                    )
            elif existing["state"] == "COMPLETED":
                raise RuntimeError(
                    f"Scenario {scenario_id} must be snapshotted before a new attempt is prepared."
                )
            else:
                raise RuntimeError(
                    f"Scenario {scenario_id} cannot be prepared from lifecycle {existing['state']}."
                )
        plan = PURCHASE_PLANS.get(scenario_id)
        if plan:
            purchases = [{"amount_minor": value} for value in plan]
            if scenario_id == "C18":
                purchases[0]["purchased_at"] = (
                    datetime.now(timezone.utc) - timedelta(days=120)
                )
            self.builder.build(
                scenario_id, purchases,
                session=scenario_id == "C19",
            )
        else:
            self.harness.prepare(scenario_id)
        # Every scenario receives deterministic, account-scoped, test-only
        # inventory. Historical buyer fixtures still exercise ownership and
        # ranking exclusions against these unowned alternatives.
        inventory = self.builder.add_eligible_inventory(
            scenario_id,
            prices=((900, 1900, 2900, 3900, 4900)
                    if scenario_id == "C06" else (900, 1900, 2900)),
        )
        if scenario_id == "C06":
            self.builder.prepare_session_compatible_inventory(
                scenario_id, inventory[-3:],
            )
        validation = self.harness.validate_starting_state(
            scenario_id, expected_purchase_count=len(plan or ()),
        )
        self.harness.transition(scenario_id, ScenarioState.RUNNING)
        scenario_attempt = self.recovery.start_attempt(scenario_id)
        state = self.builder.derived_state(scenario_id)
        return {"scenario": scenario_id, "lifecycle": "RUNNING",
                "startingState": state, "readyForTurn": True,
                "scenarioAttempt": scenario_attempt,
                "startingStateValidation": validation}

    def status(self) -> dict[str, Any]:
        active = self._active()
        scenario_id = active["scenario_id"]
        scenario_attempt = self.recovery.scenario_attempt(scenario_id)
        definition = self.harness.definition(scenario_id)
        canonical_turn_count = int(
            definition.maximum_turn_count or definition.canonical_turn_count or 0
        )
        return {"scenario": scenario_id, "lifecycle": active["state"],
                "state": self.builder.derived_state(scenario_id),
                "turnCount": len(self._turns(scenario_id)),
                "defectCount": len(self._defects(scenario_id)),
                "execution": self.recovery.execution_status(
                    scenario_id, scenario_attempt, canonical_turn_count,
                )}

    def turn(self, message: str, *, language_mode: str = DETERMINISTIC_CERTIFICATION) -> dict[str, Any]:
        active = self._active(required_state="RUNNING")
        scenario_id = active["scenario_id"]
        scenario_attempt = self.recovery.scenario_attempt(scenario_id)
        definition = self.harness.definition(scenario_id)
        canonical_turn_count = int(
            definition.maximum_turn_count or definition.canonical_turn_count or 0
        )
        next_turn = self.recovery.next_logical_turn(scenario_id, scenario_attempt)
        if canonical_turn_count and next_turn > canonical_turn_count:
            raise RuntimeError(
                f"CANONICAL_SCENARIO_COMPLETE: scenario={scenario_id} "
                f"attempt={scenario_attempt} canonicalTurns={canonical_turn_count}"
            )
        attempt_owner = getattr(self, "_attempt_wide_owner", None)
        if attempt_owner is not None:
            if (
                attempt_owner["scenario_id"] != scenario_id
                or attempt_owner["scenario_attempt"] != scenario_attempt
            ):
                raise RuntimeError("ATTEMPT_WIDE_EXECUTION_OWNER_SCOPE_MISMATCH")
            return self._turn_owned(
                message, language_mode=language_mode,
                owner_id=attempt_owner["owner_id"],
                expected_scenario=scenario_id,
                expected_attempt=scenario_attempt,
            )
        owner_id = self.recovery.claim_execution(
            scenario_id, scenario_attempt,
            requested_start_turn=next_turn, requested_end_turn=next_turn,
        )
        try:
            result = self._turn_owned(
                message, language_mode=language_mode, owner_id=owner_id,
                expected_scenario=scenario_id,
                expected_attempt=scenario_attempt,
            )
        except Exception as error:
            self.recovery.release_execution(
                scenario_id, scenario_attempt, owner_id,
                failed=True, reason=f"{type(error).__name__}: {error}",
            )
            raise
        self.recovery.release_execution(
            scenario_id, scenario_attempt, owner_id,
        )
        return result

    def _execute_with_attempt_owner(self, scenario_id: str, maximum_turns: int,
                                    operation):
        """Keep one durable lease across a full fixed/adaptive execution."""
        attempt = self.recovery.scenario_attempt(scenario_id)
        start_turn = self.recovery.next_logical_turn(scenario_id, attempt)
        owner_id = self.recovery.claim_execution(
            scenario_id, attempt,
            requested_start_turn=start_turn,
            requested_end_turn=maximum_turns,
        )
        if getattr(self, "_attempt_wide_owner", None) is not None:
            self.recovery.release_execution(
                scenario_id, attempt, owner_id, failed=True,
                reason="NESTED_ATTEMPT_WIDE_EXECUTION_NOT_ALLOWED",
            )
            raise RuntimeError("NESTED_ATTEMPT_WIDE_EXECUTION_NOT_ALLOWED")
        self._attempt_wide_owner = {
            "scenario_id": scenario_id,
            "scenario_attempt": attempt,
            "owner_id": owner_id,
        }
        try:
            result = operation()
        except Exception as error:
            self.recovery.release_execution(
                scenario_id, attempt, owner_id, failed=True,
                reason=f"{type(error).__name__}: {error}",
            )
            raise
        else:
            self.recovery.release_execution(
                scenario_id, attempt, owner_id,
            )
            return result
        finally:
            del self._attempt_wide_owner

    def _turn_owned(self, message: str, *, language_mode: str,
                    owner_id: str, expected_scenario: str,
                    expected_attempt: int) -> dict[str, Any]:
        with self.harness.turn_execution_scope():
            active = self._active(required_state="RUNNING")
            scenario_id = active["scenario_id"]
            scenario_attempt = self.recovery.scenario_attempt(scenario_id)
            if scenario_id != expected_scenario or scenario_attempt != expected_attempt:
                raise RuntimeError("SCENARIO_EXECUTION_ATTEMPT_CHANGED")
            self.recovery.heartbeat_execution(
                scenario_id, scenario_attempt, owner_id,
            )
            logical_turn = self.recovery.next_logical_turn(
                scenario_id, scenario_attempt,
            )
            definition = self.harness.definition(scenario_id)
            canonical_turn_count = int(
                definition.maximum_turn_count or definition.canonical_turn_count or 0
            )
            if canonical_turn_count and logical_turn > canonical_turn_count:
                raise RuntimeError(
                    f"CANONICAL_SCENARIO_COMPLETE: scenario={scenario_id} "
                    f"attempt={scenario_attempt} canonicalTurns={canonical_turn_count}"
                )
            recent_ava_responses = self.recovery.current_outbound_transcript(
                scenario_id, scenario_attempt,
            )
            before = self.builder.derived_state(scenario_id)
            checkpoint = self.recovery.checkpoint(
                scenario_id, scenario_attempt, logical_turn, 1, before,
            )
            checkpoint["scenarioId"] = scenario_id
            evidence = self.harness.execute_turn(
                scenario_id, message, language_mode=language_mode,
                recent_ava_responses=recent_ava_responses,
                turn_identity=ScenarioTurnExecutionIdentity(
                    scenario_id=scenario_id,
                    scenario_attempt=scenario_attempt,
                    logical_turn=logical_turn,
                    turn_attempt=1,
                ),
            )
            after = self.builder.derived_state(scenario_id)
            changes = self._changes(before, after, evidence)
            projection = self._turn_projection(evidence, changes)
            projection["scenarioAttempt"] = scenario_attempt
            projection["turnAttempt"] = 1
            with self.harness.connection() as connection:
                connection.execute("""UPDATE certification_scenario_turn_evidence
                    SET full_analysis=jsonb_set(full_analysis,'{operatorResult}',%s::jsonb,true)
                    WHERE correlation_id=%s""", (
                        json.dumps(projection, default=str), evidence["syntheticInboundId"],
                    ))
            self.recovery.record_turn(
                checkpoint, message, evidence["finalResponseText"],
                evidence.get("SalesBrainFullAnalysis") or {}, after,
            )
            self.recovery.heartbeat_execution(
                scenario_id, scenario_attempt, owner_id,
            )
            return projection

    def execute_canonical(self, *,
                          language_mode: str = REAL_AVA_LANGUAGE) -> dict[str, Any]:
        """Execute remaining canonical turns under one durable attempt owner."""
        active = self._active(required_state="RUNNING")
        scenario_id = active["scenario_id"]
        if scenario_id == "C05":
            return self._execute_c05_primary(language_mode=language_mode)
        if scenario_id == "C06":
            return self._execute_c06_primary(language_mode=language_mode)
        if scenario_id == "C07":
            return self._execute_c07_primary(language_mode=language_mode)
        if scenario_id == "C08":
            return self._execute_c08_primary(language_mode=language_mode)
        scenario_attempt = self.recovery.scenario_attempt(scenario_id)
        definition = self.harness.definition(scenario_id)
        messages = tuple(definition.canonical_customer_turns or ())
        canonical_turn_count = int(definition.canonical_turn_count or len(messages))
        if not messages or canonical_turn_count != len(messages):
            raise RuntimeError("CANONICAL_SCENARIO_TURNS_NOT_CONFIGURED")
        next_turn = self.recovery.next_logical_turn(scenario_id, scenario_attempt)
        if next_turn > canonical_turn_count:
            raise RuntimeError(
                f"CANONICAL_SCENARIO_COMPLETE: scenario={scenario_id} "
                f"attempt={scenario_attempt} canonicalTurns={canonical_turn_count}"
            )
        owner_id = self.recovery.claim_execution(
            scenario_id, scenario_attempt,
            requested_start_turn=next_turn,
            requested_end_turn=canonical_turn_count,
        )
        results = []
        try:
            for logical_turn in range(next_turn, canonical_turn_count + 1):
                results.append(self._turn_owned(
                    messages[logical_turn - 1], language_mode=language_mode,
                    owner_id=owner_id, expected_scenario=scenario_id,
                    expected_attempt=scenario_attempt,
                ))
        except Exception as error:
            self.recovery.release_execution(
                scenario_id, scenario_attempt, owner_id,
                failed=True, reason=f"{type(error).__name__}: {error}",
            )
            raise
        self.recovery.release_execution(
            scenario_id, scenario_attempt, owner_id,
        )
        return {
            "scenario": scenario_id,
            "scenarioAttempt": scenario_attempt,
            "execution": "COMPLETED",
            "canonicalTurnCount": canonical_turn_count,
            "completedTurns": len(results),
            "turns": results,
        }

    @staticmethod
    def _early_interest_type(message: str) -> str:
        """Describe early interest with existing production language semantics."""
        from app.services.contextual_customer_tone_service import (
            ContextualCustomerToneService,
        )
        from app.services.gpt_service import GPTService
        value = str(message or "")
        social = GPTService._social_flirtation(value)
        sexual = bool(
            social.get("sexual")
            or ContextualCustomerToneService().classify(
                message=value, recent_transcript=(),
            ).get("sexualOrProvocative")
        )
        flirtation = bool(
            social.get("detected")
            or re.search(
                r"\b(?:you(?:'re| are| look)\s+(?:ridiculously\s+)?"
                r"(?:hot|cute|pretty|beautiful|gorgeous))\b",
                value, re.I,
            )
        )
        return (
            "BOTH" if sexual and flirtation else "SEXUAL" if sexual
            else "FLIRTATION" if flirtation else "NONE"
        )

    @staticmethod
    def c05_next_action(turns, state, *, branch="LEAN_IN_CONVERT",
                        fixed_messages=()):
        """Choose customer behavior solely from durable Ava/commerce evidence."""
        turns = list(turns or ())
        state = dict(state or {})
        latest = dict(turns[-1] if turns else {})
        analysis = dict(
            latest.get("salesBrainFullAnalysis")
            or latest.get("fullAnalysis") or {}
        )
        sexual = dict(analysis.get("sexualCommercialProgression") or {})
        decision = dict(analysis.get("finalSalesDecision") or {}).get("decision")
        progression = dict(analysis.get("salesProgression") or {})
        adaptive = dict(latest.get("adaptiveCustomer") or {})
        adaptive_phase = adaptive.get("behavioral_phase")
        accepted = bool(
            adaptive_phase == "OFFER_REACTION"
            and dict(adaptive.get("validation_result") or {}).get(
                "derivedSignals", {}
            ).get("offerAcceptance") is True
        )
        if int(state.get("purchaseCount") or 0) > 0:
            acknowledged = bool(analysis.get("purchaseAcknowledgementCompleted"))
            if acknowledged and adaptive_phase == "POST_PURCHASE_CONTINUITY":
                return {"kind": "COMPLETE"}
            return {"kind": "ADAPTIVE", "phase": (
                "POST_PURCHASE_CONTINUITY" if acknowledged
                else "POST_PURCHASE_ACKNOWLEDGEMENT"
            ), "offer_reaction": "NONE"}
        if accepted:
            return {"kind": "SIMULATE_PURCHASE"}
        offer_presented = bool(
            latest.get("syntheticPpvPresentation")
            or decision == "PRESENT_OFFER"
            and dict(analysis.get("commerceLifecycleConfirmation") or {}).get(
                "structuredPresentationConfirmed"
            )
        )
        if offer_presented:
            reaction = "REJECT" if branch == "DECLINE_OFFER" else "ACCEPT"
            return {"kind": "ADAPTIVE", "phase": "OFFER_REACTION",
                    "offer_reaction": reaction}
        confirmed_exposure = next((dict(
            dict(turn.get("salesBrainFullAnalysis") or turn.get("fullAnalysis") or {}).get(
                "sexualCommercialProgression"
            ) or {}
        ) for turn in reversed(turns) if dict(
            dict(turn.get("salesBrainFullAnalysis") or turn.get("fullAnalysis") or {}).get(
                "sexualCommercialProgression"
            ) or {}
        ).get("adaptiveSwitchEligible") is True), None)
        if confirmed_exposure:
            if branch == "REJECT_BACK_OFF":
                return {"kind": "ADAPTIVE", "phase": "COMMERCIAL_REJECTION",
                        "offer_reaction": "NONE"}
            if branch == "SEXUAL_BUT_COMMERCIALLY_NONRESPONSIVE":
                return {"kind": "ADAPTIVE", "phase": "ATTRACTION",
                        "offer_reaction": "NONE"}
            if (
                decision == "BUILD_INTEREST"
                or str(progression.get("phase") or "").upper() == "BUILD_INTEREST"
            ):
                return {
                    "kind": "ADAPTIVE", "phase": "REVEAL_INTEREST",
                    "offer_reaction": "NONE",
                    "progression": progression.get("phase"),
                    "adaptive_switch_reason": "AVA_BUILD_INTEREST_CONFIRMED",
                }
            return {"kind": "ADAPTIVE", "phase": "COMMERCIAL_CURIOSITY",
                    "offer_reaction": "NONE", "progression": progression.get("phase"),
                    "adaptive_switch_reason": confirmed_exposure.get(
                        "adaptiveSwitchReason"
                    ) or "CONFIRMED_CUSTOMER_VISIBLE_COMMERCIAL_EXPOSURE"}
        index = len(turns)
        if index >= len(tuple(fixed_messages or ())):
            return {"kind": "BLOCKED", "reason": "C05_NO_CONFIRMED_COMMERCIAL_EXPOSURE"}
        return {"kind": "FIXED", "message": tuple(fixed_messages)[index]}

    @staticmethod
    def c05_completion_evidence(turns, state):
        turns = list(turns or ())
        state = dict(state or {})
        analyses = [dict(
            turn.get("salesBrainFullAnalysis") or turn.get("fullAnalysis") or {}
        ) for turn in turns]
        sexual = [dict(item.get("sexualCommercialProgression") or {})
                  for item in analyses]
        latest = analyses[-1] if analyses else {}
        adaptive = dict(turns[-1].get("adaptiveCustomer") or {}) if turns else {}
        first_exposure = next((index for index, (turn, item) in enumerate(
            zip(turns, sexual)
        ) if item.get("commercialTeaseDelivered") is True
            or turn.get("syntheticPpvPresentation")), len(turns))
        pre_exposure = analyses[:first_exposure]
        acknowledgement_count = sum(bool(
            item.get("purchaseAcknowledgementAuthorized")
            and item.get("acknowledgementProviderConfirmed")
        ) for item in analyses)
        presentation_analyses = [
            dict(item.get("finalSalesDecision") or {}) for item in analyses
            if dict(item.get("finalSalesDecision") or {}).get("decision")
            == "PRESENT_OFFER"
        ]
        direct_intent_bypass = any(
            item.get("reasonCode") in {
                "DIRECT_PURCHASE_INTENT", "PRICE_REQUEST",
                "SESSION_NEXT_UNLOCK_REQUEST",
            }
            for item in presentation_analyses
        )
        build_interest_observed = any(
            dict(item.get("finalSalesDecision") or {}).get("decision")
            == "BUILD_INTEREST"
            or dict(item.get("sexualCommercialProgression") or {}).get(
                "buildInterestObserved"
            ) is True
            for item in analyses
        )
        earned_progression = bool(
            presentation_analyses and build_interest_observed
        )
        realized_conversion_path = (
            "DIRECT_INTENT_BYPASS" if direct_intent_bypass
            else "EARNED_PROGRESSION" if earned_progression else None
        )
        purchase_intent_ids = {
            str(dict(turn.get("syntheticPpvPresentation") or {}).get(
                "purchaseIntent", {}
            ).get("id"))
            for turn in turns
            if dict(turn.get("syntheticPpvPresentation") or {}).get(
                "purchaseIntent", {}
            ).get("id")
        }
        numeric_price_in_ava_prose = any(re.search(
            r"(?:\$\s*\d+(?:\.\d{1,2})?|\b\d+(?:\.\d{1,2})?\s*(?:usd|dollars?)\b)",
            str(turn.get("ava") or ""), re.I,
        ) for turn in turns)
        checks = {
            "sexualReceptivenessDiscovered": any(
                item.get("sustainedSexualReceptiveness") is True for item in sexual
            ),
            "commercialOpportunityConfirmed": any(
                item.get("commercialTeaseDelivered") is True for item in sexual
            ) or any(turn.get("syntheticPpvPresentation") for turn in turns),
            "noFalseBuyingIntent": all(
                not bool(dict(item.get("socialFlirtation") or {}).get("buyingIntent"))
                for item in pre_exposure
            ),
            "adaptiveCustomerLeanIn": any(
                dict(turn.get("adaptiveCustomer") or {}).get("behavioral_phase")
                in {"COMMERCIAL_CURIOSITY", "REVEAL_INTEREST", "BUYING_INTEREST", "OFFER_REACTION"}
                for turn in turns
            ),
            "paidPresentationAuthorizedPath": bool(realized_conversion_path),
            "oneCanonicalPurchaseIntentLifecycle": len(purchase_intent_ids) == 1,
            "paidPresentation": any(turn.get("syntheticPpvPresentation") for turn in turns),
            "providerBackedPurchase": int(state.get("purchaseCount") or 0) == 1,
            "ownershipCreated": int(state.get("ownershipCount") or 0) >= 1,
            "acknowledgementCompletedExactlyOnce": acknowledgement_count == 1,
            "firstTimeBuyer": state.get("buyerStage") == "FIRST_TIME_BUYER",
            "postPurchaseContinuity": (
                adaptive.get("behavioral_phase") == "POST_PURCHASE_CONTINUITY"
            ),
            "boundedFreeSexualAttention": bool(
                first_exposure < len(turns) and len(turns) <= 16
            ),
            "noFalseTimeWasterClassification": not bool(
                state.get("timeWaster") or state.get("isTimeWaster")
            ),
            "noNumericPaidPriceInAvaProse": not numeric_price_in_ava_prose,
        }
        return {
            "complete": all(checks.values()),
            "checks": checks,
            "realizedConversionPath": realized_conversion_path,
            "buildInterestObserved": build_interest_observed,
            "revealInterestObserved": any(
                dict(turn.get("adaptiveCustomer") or {}).get(
                    "behavioral_phase"
                ) == "REVEAL_INTEREST" for turn in turns
            ),
            "directIntentBypassUsed": direct_intent_bypass,
            "purchaseIntentIds": sorted(purchase_intent_ids),
        }

    @staticmethod
    def c06_next_action(turns, state, *,
                        branch="ONGOING_EXPERIENCE_CONTINUATION",
                        fixed_messages=()):
        """Drive C06 from durable commerce evidence, never hidden buyer metadata."""
        turns = list(turns or ())
        state = dict(state or {})
        latest = dict(turns[-1] if turns else {})
        analysis = dict(
            latest.get("salesBrainFullAnalysis") or latest.get("fullAnalysis") or {}
        )
        adaptive = dict(latest.get("adaptiveCustomer") or {})
        phase = adaptive.get("behavioral_phase")
        accepted_offer = bool(
            phase == "OFFER_REACTION"
            and dict(adaptive.get("validation_result") or {}).get(
                "derivedSignals", {}
            ).get("offerAcceptance") is True
        )
        decision = dict(analysis.get("finalSalesDecision") or {}).get("decision")
        purchase_count = int(state.get("purchaseCount") or 0)
        acknowledgement_count = sum(bool(
            dict(turn.get("salesBrainFullAnalysis") or turn.get("fullAnalysis") or {}).get(
                "purchaseAcknowledgementCompleted"
            )
        ) for turn in turns)
        escalation = dict(analysis.get("sessionEscalation") or {})
        if not escalation:
            escalation = {
                key: analysis.get(key) for key in (
                    "sessionCandidate", "sessionEscalationDecision",
                    "sessionProposalAuthorized", "sessionProposalPending",
                    "sessionProposalCustomerReaction", "sessionUnavailableFallback",
                ) if key in analysis
            }

        if purchase_count >= 2:
            if acknowledgement_count < 2:
                return {"kind": "ADAPTIVE", "phase": "POST_PURCHASE_ACKNOWLEDGEMENT"}
            if escalation.get("sessionEscalationDecision") == "SESSION_ACCEPTED":
                return {"kind": "COMPLETE"}
            if escalation.get("sessionEscalationDecision") == "PROPOSE_SESSION":
                if branch == "DECLINE_SESSION_WANTS_PPVS":
                    return {"kind": "ADAPTIVE", "phase": "SESSION_DECLINE_DISCRETE_CONTINUATION"}
                return {"kind": "ADAPTIVE", "phase": "SESSION_PROPOSAL_REACTION"}
            if branch == "DISCRETE_CONTINUATION":
                return {"kind": "ADAPTIVE", "phase": "DISCRETE_CONTINUATION"}
            if branch == "HOT_PRAISE_NO_MORE_REQUEST":
                return {"kind": "ADAPTIVE", "phase": "HOT_PRAISE_NO_MORE_REQUEST"}
            return {"kind": "ADAPTIVE", "phase": "ONGOING_EXPERIENCE_CONTINUATION"}

        if purchase_count == 1:
            if acknowledgement_count < 1:
                return {"kind": "ADAPTIVE", "phase": "POST_PURCHASE_ACKNOWLEDGEMENT"}
            if accepted_offer:
                return {"kind": "SIMULATE_PURCHASE"}
            if decision == "PRESENT_OFFER" or latest.get("syntheticPpvPresentation"):
                return {"kind": "ADAPTIVE", "phase": "OFFER_REACTION",
                        "offer_reaction": "ACCEPT"}
            return {"kind": "ADAPTIVE", "phase": "DISCRETE_CONTINUATION"}

        if accepted_offer:
            return {"kind": "SIMULATE_PURCHASE"}
        if decision == "PRESENT_OFFER" or latest.get("syntheticPpvPresentation"):
            return {"kind": "ADAPTIVE", "phase": "OFFER_REACTION",
                    "offer_reaction": "ACCEPT"}
        index = len(turns)
        if index < len(tuple(fixed_messages or ())):
            return {"kind": "FIXED", "message": tuple(fixed_messages)[index]}
        return {"kind": "BLOCKED", "reason": "C06_FIRST_PPV_NOT_PRESENTED"}

    @staticmethod
    def c07_next_action(turns, state, *, fixed_messages=()):
        """Advance C07 only from customer-visible, durable runtime evidence."""
        turns = list(turns or ())
        state = dict(state or {})
        latest = dict(turns[-1] if turns else {})
        analysis = dict(
            latest.get("salesBrainFullAnalysis")
            or latest.get("fullAnalysis") or {}
        )
        decision = dict(analysis.get("finalSalesDecision") or {}).get("decision")
        progression = dict(analysis.get("salesProgression") or {})
        if latest.get("syntheticPpvPresentation"):
            return {"kind": "COMPLETE"}
        confirmed_exposure = next((
            dict(dict(
                turn.get("salesBrainFullAnalysis") or turn.get("fullAnalysis") or {}
            ).get("sexualCommercialProgression") or {})
            for turn in reversed(turns)
            if dict(dict(
                turn.get("salesBrainFullAnalysis") or turn.get("fullAnalysis") or {}
            ).get("sexualCommercialProgression") or {}).get(
                "adaptiveSwitchEligible"
            ) is True
        ), None)
        if confirmed_exposure:
            if (
                decision == "BUILD_INTEREST"
                or str(progression.get("phase") or "").upper() == "BUILD_INTEREST"
            ):
                return {
                    "kind": "ADAPTIVE", "phase": "REVEAL_INTEREST",
                    "offer_reaction": "NONE",
                    "adaptive_switch_reason": "AVA_BUILD_INTEREST_CONFIRMED",
                }
            return {
                "kind": "ADAPTIVE", "phase": "COMMERCIAL_CURIOSITY",
                "offer_reaction": "NONE",
                "adaptive_switch_reason": confirmed_exposure.get(
                    "adaptiveSwitchReason"
                ) or "CONFIRMED_CUSTOMER_VISIBLE_COMMERCIAL_EXPOSURE",
            }
        index = len(turns)
        fixed_messages = tuple(fixed_messages or ())
        if index >= len(fixed_messages):
            return {
                "kind": "BLOCKED",
                "reason": "C07_NO_CONFIRMED_COMMERCIAL_EXPOSURE_WITHIN_FIXED_RAPPORT",
            }
        return {"kind": "FIXED", "message": fixed_messages[index]}

    @staticmethod
    def c07_completion_evidence(turns, state):
        """Certify C07 at presentation, explicitly before any purchase truth."""
        turns = list(turns or ())
        state = dict(state or {})
        analyses = [dict(
            turn.get("salesBrainFullAnalysis") or turn.get("fullAnalysis") or {}
        ) for turn in turns]
        first_analysis = analyses[0] if analyses else {}
        latest_analysis = analyses[-1] if analyses else {}
        first_retention = dict(first_analysis.get("buyerRetention") or {})
        latest_retention = dict(latest_analysis.get("buyerRetention") or {})
        latest_attention = dict(latest_analysis.get("attentionEconomics") or {})
        presentations = [dict(turn.get("syntheticPpvPresentation") or {})
                         for turn in turns if turn.get("syntheticPpvPresentation")]
        intent_ids = {
            str(dict(item.get("purchaseIntent") or {}).get("id"))
            for item in presentations
            if dict(item.get("purchaseIntent") or {}).get("id")
        }
        presentation_confirmations = [
            dict(item.get("commerceLifecycleConfirmation") or {})
            for item in analyses
            if dict(item.get("commerceLifecycleConfirmation") or {}).get(
                "structuredPresentationConfirmed"
            ) is True
        ]
        tease_rows = [dict(item.get("sexualCommercialProgression") or {})
                      for item in analyses]
        phases = [dict(turn.get("adaptiveCustomer") or {}).get("behavioral_phase")
                  for turn in turns]
        first_adaptive_index = next((
            index for index, phase in enumerate(phases)
            if phase in {"COMMERCIAL_CURIOSITY", "REVEAL_INTEREST"}
        ), None)
        first_adaptive_nonbuying = bool(
            first_adaptive_index is not None
            and dict(analyses[first_adaptive_index].get("socialFlirtation") or {}).get(
                "buyingIntent"
            ) is False
        )
        decisions = [dict(item.get("finalSalesDecision") or {}) for item in analyses]
        actionable_interest_types = {
            "DIRECT_CONTENT_INTENT", "PRICE_REQUEST",
            "SEND_OR_LINK_REQUEST", "PURCHASE_ACCEPTANCE",
        }
        legitimate_direct_intent = []
        contradictions = []
        for index, item in enumerate(decisions):
            if item.get("decision") != "PRESENT_OFFER" or item.get(
                "reasonCode"
            ) not in {"DIRECT_PURCHASE_INTENT", "PRICE_REQUEST"}:
                continue
            analysis = analyses[index]
            interest_type = str(dict(
                analysis.get("customerValueAttention") or {}
            ).get("commercialInterestType") or dict(
                analysis.get("commercialReactivation") or {}
            ).get("commercialInterestType") or "NONE").upper()
            fresh_direct = bool(dict(
                analysis.get("buyingSignals") or {}
            ).get("freshDirectIntent"))
            buying_intent = bool(dict(
                analysis.get("socialFlirtation") or {}
            ).get("buyingIntent"))
            legitimate = bool(
                interest_type in actionable_interest_types
                or fresh_direct or buying_intent
            )
            legitimate_direct_intent.append(legitimate)
            if not legitimate:
                contradictions.append({
                    "turnIndex": index + 1,
                    "salesBrainReason": item.get("reasonCode"),
                    "commercialInterestType": interest_type,
                    "freshDirectIntentDetected": fresh_direct,
                    "buyingIntent": buying_intent,
                    "reason": "DIRECT_INTENT_REASON_WITHOUT_ACTIONABLE_EVIDENCE",
                })
        direct_intent = any(legitimate_direct_intent)
        build_interest = any(
            item.get("decision") == "BUILD_INTEREST" for item in decisions
        ) or any(
            dict(item.get("salesProgression") or {}).get("phase") == "BUILD_INTEREST"
            for item in analyses
        )
        numeric_price = any(re.search(
            r"(?:\$\s*\d+(?:\.\d{1,2})?|\b\d+(?:\.\d{1,2})?\s*(?:usd|dollars?)\b)",
            str(turn.get("ava") or ""), re.I,
        ) for turn in turns)
        presented_states = {
            str(dict(item.get("purchaseIntent") or {}).get("state") or "").upper()
            for item in presentations
        }
        confirmed_intent_states = {
            str(item.get("purchaseIntentState") or "").upper()
            for item in presentation_confirmations
            if item.get("purchaseIntentState")
        }
        authoritative_intent_states = confirmed_intent_states or presented_states
        checks = {
            "freshNonbuyerStart": (
                int(state.get("startingPurchaseCount") or 0) == 0
                and first_retention.get("verifiedBuyerStatus") == "NONBUYER"
                and first_retention.get("buyerStage") == "PROSPECT"
            ),
            "rapportAndDisclosureObserved": len(turns) >= 6,
            "standardMemoryPriority": latest_retention.get("memoryPriority") == "STANDARD",
            "truthfulMemoryUsed": any(
                bool(dict(item.get("buyerRetention") or {}).get("memoryCandidatesUsed"))
                for item in analyses
            ),
            "relationshipDiscoveryAuthorized": any(
                dict(item.get("buyerRetention") or {}).get(
                    "relationshipDiscoveryAuthorized"
                ) is True for item in analyses
            ),
            "healthyBalancedEffort": (
                latest_attention.get("effortMode") not in {"MINIMAL", "COMPRESSED"}
                and latest_attention.get("attentionTier") not in {None, "LOW"}
            ),
            "gatedIntimacy": latest_analysis.get("intimacyEntitlement") == "GATED",
            "confirmedCommercialTease": any(
                row.get("commercialTeaseDelivered") is True
                and row.get("adaptiveSwitchEligible") is True
                for row in tease_rows
            ) or direct_intent,
            "adaptiveNonbuyingCuriosity": direct_intent or first_adaptive_nonbuying,
            "earnedProgressionOrDirectIntent": build_interest or direct_intent,
            "noCommercialIntentContradiction": not contradictions,
            "oneCustomerVisiblePresentation": len(presentations) == 1,
            "oneCanonicalPurchaseIntent": len(intent_ids) == 1,
            "purchaseIntentPresented": authoritative_intent_states == {"PRESENTED"},
            "deliveryConfirmed": bool(presentation_confirmations),
            "noPurchase": int(state.get("purchaseCount") or 0) == 0,
            "noOwnership": int(state.get("ownershipCount") or 0) == 0,
            "noSettlement": int(state.get("settledPurchaseCount") or 0) == 0,
            "noTimeWaster": str(state.get("timeWasterRisk") or "NONE").upper() == "NONE",
            "noScenarioCommercialAuthority": all(
                item.get("scenarioInfluencedCommercialAuthority") is not True
                for item in analyses
            ),
            "noNumericPaidPriceInAvaProse": not numeric_price,
        }
        return {
            "complete": all(checks.values()), "checks": checks,
            "purchaseIntentIds": sorted(intent_ids),
            "buildInterestObserved": build_interest,
            "directIntentBypassUsed": direct_intent,
            "commercialIntentContradictions": contradictions,
            "adaptivePhases": [phase for phase in phases if phase],
        }

    @staticmethod
    def c06_completion_evidence(turns, state):
        """Prove the hot-buyer handoff boundary without executing a Session."""
        turns = list(turns or ())
        state = dict(state or {})
        analyses = [dict(
            turn.get("salesBrainFullAnalysis") or turn.get("fullAnalysis") or {}
        ) for turn in turns]
        phases = [dict(turn.get("adaptiveCustomer") or {}).get("behavioral_phase")
                  for turn in turns]
        presentations = [turn.get("syntheticPpvPresentation") for turn in turns
                         if turn.get("syntheticPpvPresentation")]
        intent_ids = [str(dict(item.get("purchaseIntent") or {}).get("id"))
                      for item in presentations
                      if dict(item.get("purchaseIntent") or {}).get("id")]
        offering_ids = [str(item.get("offeringId")) for item in presentations
                        if item.get("offeringId")]
        acknowledgements = sum(bool(item.get("purchaseAcknowledgementCompleted"))
                               for item in analyses)
        escalation_keys = (
            "sessionCandidate", "sessionCandidateReason",
            "sessionCompatibleInventoryAvailable", "sessionEscalationDecision",
            "sessionEscalationReason", "continueDiscretePpvsAuthorized",
            "sessionProposalAuthorized", "sessionProposalPending",
            "sessionProposalCustomerReaction", "sessionUnavailableFallback",
            "purchaseStreakCount", "recentPurchaseVelocity",
        )
        escalation_rows = []
        for item in analyses:
            row = dict(item.get("sessionEscalation") or {})
            if not row:
                row = {key: item.get(key) for key in escalation_keys if key in item}
            escalation_rows.append(row)
        latest_escalation = next((row for row in reversed(escalation_rows) if row), {})
        session_proposed = any(
            row.get("sessionEscalationDecision") == "PROPOSE_SESSION"
            and row.get("sessionProposalAuthorized") is True
            for row in escalation_rows
        )
        direct_intent = any(
            dict(item.get("finalSalesDecision") or {}).get("reasonCode")
            in {"DIRECT_PURCHASE_INTENT", "PRICE_REQUEST"}
            for item in analyses
        )
        first_presentation = next((i for i, turn in enumerate(turns)
                                   if turn.get("syntheticPpvPresentation")), len(turns))
        early_interest_types = [
            Session5ScenarioRunner._early_interest_type(turn.get("customer"))
            for turn in turns[:first_presentation]
        ]
        early_interest_safe = bool(early_interest_types) and all(
            interest in {"FLIRTATION", "SEXUAL", "BOTH"}
            for interest in early_interest_types
        ) and all(
            not bool(dict(item.get("socialFlirtation") or {}).get("buyingIntent"))
            and dict(item.get("finalSalesDecision") or {}).get("decision") != "PRESENT_OFFER"
            for item in analyses[:first_presentation]
        )
        numeric_price_in_prose = any(re.search(
            r"(?:\$\s*\d|\b\d+(?:\.\d{1,2})?\s*(?:usd|dollars?)\b)",
            str(turn.get("ava") or ""), re.I,
        ) for turn in turns)
        state_window = state.get("activeBuyingWindow")
        active_window = dict(state_window) if isinstance(state_window, dict) else {
            "active": bool(state_window) or any(
                item.get("activeBuyingWindow") is True for item in analyses
            )
        }
        accepted_boundary = bool(
            latest_escalation.get("sessionEscalationDecision") == "SESSION_ACCEPTED"
            and latest_escalation.get("sessionProposalCustomerReaction")
            == "ACCEPT_OR_LEAN_IN"
        )
        checks = {
            "freshProspectStart": bool(state.get("startingPurchaseCount", 0) == 0),
            "flirtatiousOrSexualInterestNotBuyingIntent": early_interest_safe,
            "directFirstPurchaseIntent": direct_intent,
            "twoDistinctPurchaseIntents": len(set(intent_ids)) >= 2,
            "twoDistinctOfferings": len(set(offering_ids)) >= 2,
            "twoProviderPurchases": int(state.get("purchaseCount") or 0) >= 2,
            "twoOwnershipRecords": int(state.get("ownershipCount") or 0) >= 2,
            "twoAcknowledgements": acknowledgements == 2,
            "explicitDiscreteContinuation": "DISCRETE_CONTINUATION" in phases,
            "activeBuyingWindow": bool(active_window.get("active", state.get("activeBuyingWindow") is True)),
            "repeatBuyerTransition": state.get("buyerStage") == "REPEAT_BUYER",
            "ongoingExperienceIntent": "ONGOING_EXPERIENCE_CONTINUATION" in phases,
            "sessionCandidate": any(row.get("sessionCandidate") is True for row in escalation_rows),
            "sessionProposal": session_proposed,
            "sessionAccepted": accepted_boundary,
            "sessionStartEligible": bool(
                latest_escalation.get("sessionStartAuthorityEligible") is True
                or accepted_boundary
            ),
            "sessionNotStarted": bool(
                latest_escalation.get("sessionStarted") is not True
                and not state.get("activeSession")
            ),
            "noFalseTimeWaster": not bool(state.get("timeWaster") or state.get("isTimeWaster")),
            "noNumericPriceInAvaProse": not numeric_price_in_prose,
        }
        return {
            "complete": all(checks.values()), "checks": checks,
            "purchaseIntentIds": intent_ids, "offeringIds": offering_ids,
            "sessionEscalation": latest_escalation,
            "earlyInterestTypes": early_interest_types,
            "opportunityAccounting": {
                "uniquePurchaseIntentCount": len(set(intent_ids)),
                "convertedOpportunities": int(state.get("purchaseCount") or 0),
                "failedOpportunities": int(state.get("failedOpportunityCount") or 0),
                "customerVisibleExposureCount": len(presentations),
                "activeBuyingWindow": active_window or state.get("activeBuyingWindow"),
                "purchaseStreakCount": latest_escalation.get("purchaseStreakCount"),
                "recentPurchaseVelocity": latest_escalation.get("recentPurchaseVelocity"),
                "timeWasterRisk": state.get("timeWasterRisk", "NONE"),
            },
        }

    def _execute_c05_primary(self, *, language_mode):
        definition = self.harness.definition("C05")
        return self._execute_with_attempt_owner(
            "C05", int(definition.maximum_turn_count or 16),
            lambda: self._execute_c05_primary_owned(language_mode=language_mode),
        )

    def _execute_c05_primary_owned(self, *, language_mode):
        definition = self.harness.definition("C05")
        attempt = self.recovery.scenario_attempt("C05")
        results = []
        while True:
            turns = self._current_attempt_turn_projections("C05", attempt)
            state = self.builder.derived_state("C05")
            completion = self.c05_completion_evidence(turns, state)
            if completion["complete"]:
                return {"scenario": "C05", "scenarioAttempt": attempt,
                        "execution": "OBJECTIVES_COMPLETE",
                        "completedTurns": len(results), "turns": results,
                        "completion": completion}
            if len(turns) >= int(definition.maximum_turn_count or 16):
                raise RuntimeError("C05_MAXIMUM_TURNS_REACHED_BEFORE_OBJECTIVES")
            action = self.c05_next_action(
                turns, state, fixed_messages=definition.canonical_customer_turns,
            )
            if action["kind"] == "BLOCKED":
                raise RuntimeError(action["reason"])
            if action["kind"] == "SIMULATE_PURCHASE":
                results.append(self.simulate_purchase())
                continue
            if action["kind"] == "FIXED":
                results.append(self.turn(action["message"], language_mode=language_mode))
                continue
            from app.testing.adaptive_synthetic_customer import (
                AdaptiveSyntheticCustomerService, CustomerBehaviorPhase,
            )
            phase = CustomerBehaviorPhase(action["phase"])
            constraints = AdaptiveSyntheticCustomerService.constraints_for(
                "C05", phase, offer_reaction=action.get("offer_reaction", "NONE"),
            )
            results.append(self.adaptive_turn(
                phase=phase, constraints=constraints,
                phase_transition_reason="DURABLE_CUSTOMER_VISIBLE_COMMERCE_EVIDENCE",
                language_mode=language_mode,
            ))

    def _execute_c06_primary(self, *, language_mode):
        definition = self.harness.definition("C06")
        return self._execute_with_attempt_owner(
            "C06", int(definition.maximum_turn_count or 18),
            lambda: self._execute_c06_primary_owned(language_mode=language_mode),
        )

    def _execute_c06_primary_owned(self, *, language_mode):
        """Run C06 adaptively and stop at accepted Session entry authority."""
        definition = self.harness.definition("C06")
        attempt = self.recovery.scenario_attempt("C06")
        results = []
        while True:
            turns = self._current_attempt_turn_projections("C06", attempt)
            state = self.builder.derived_state("C06")
            completion = self.c06_completion_evidence(turns, state)
            if completion["complete"]:
                return {
                    "scenario": "C06", "scenarioAttempt": attempt,
                    "execution": "OBJECTIVES_COMPLETE_AT_SESSION_ENTRY_BOUNDARY",
                    "completedTurns": len(results), "turns": results,
                    "completion": completion,
                }
            if len(turns) >= int(definition.maximum_turn_count or 18):
                raise RuntimeError("C06_MAXIMUM_TURNS_REACHED_BEFORE_OBJECTIVES")
            action = self.c06_next_action(
                turns, state, fixed_messages=definition.canonical_customer_turns,
            )
            if action["kind"] == "BLOCKED":
                raise RuntimeError(action["reason"])
            if action["kind"] == "COMPLETE":
                raise RuntimeError("C06_COMPLETION_EVIDENCE_INCOMPLETE")
            if action["kind"] == "SIMULATE_PURCHASE":
                results.append(self.simulate_purchase())
                continue
            if action["kind"] == "FIXED":
                results.append(self.turn(action["message"], language_mode=language_mode))
                continue
            from app.testing.adaptive_synthetic_customer import (
                AdaptiveSyntheticCustomerService, CustomerBehaviorPhase,
            )
            phase = CustomerBehaviorPhase(action["phase"])
            constraints = AdaptiveSyntheticCustomerService.constraints_for(
                "C06", phase, offer_reaction=action.get("offer_reaction", "NONE"),
            )
            results.append(self.adaptive_turn(
                phase=phase, constraints=constraints,
                phase_transition_reason="C06_DURABLE_COMMERCE_AND_SESSION_EVIDENCE",
                language_mode=language_mode,
            ))

    def _execute_c07_primary(self, *, language_mode):
        definition = self.harness.definition("C07")
        return self._execute_with_attempt_owner(
            "C07", int(definition.maximum_turn_count or 14),
            lambda: self._execute_c07_primary_owned(language_mode=language_mode),
        )

    def _execute_c07_primary_owned(self, *, language_mode):
        """Run C07 adaptively and stop at the first confirmed paid presentation."""
        definition = self.harness.definition("C07")
        attempt = self.recovery.scenario_attempt("C07")
        results = []
        while True:
            turns = self._current_attempt_turn_projections("C07", attempt)
            state = self.builder.derived_state("C07")
            completion = self.c07_completion_evidence(turns, state)
            if completion["complete"]:
                return {
                    "scenario": "C07", "scenarioAttempt": attempt,
                    "execution": "OBJECTIVES_COMPLETE_BEFORE_PURCHASE",
                    "completedTurns": len(results), "turns": results,
                    "completion": completion,
                }
            if len(turns) >= int(definition.maximum_turn_count or 14):
                raise RuntimeError("C07_MAXIMUM_TURNS_REACHED_BEFORE_OBJECTIVES")
            action = self.c07_next_action(
                turns, state, fixed_messages=definition.canonical_customer_turns,
            )
            if action["kind"] == "BLOCKED":
                raise RuntimeError(action["reason"])
            if action["kind"] == "COMPLETE":
                raise RuntimeError("C07_PRESENTATION_EVIDENCE_INCOMPLETE")
            if action["kind"] == "FIXED":
                results.append(self.turn(action["message"], language_mode=language_mode))
                continue
            from app.testing.adaptive_synthetic_customer import (
                AdaptiveSyntheticCustomerService, CustomerBehaviorPhase,
            )
            phase = CustomerBehaviorPhase(action["phase"])
            constraints = AdaptiveSyntheticCustomerService.constraints_for(
                "C07", phase, offer_reaction="NONE",
            )
            results.append(self.adaptive_turn(
                phase=phase, constraints=constraints,
                phase_transition_reason=action["adaptive_switch_reason"],
                language_mode=language_mode,
            ))

    @staticmethod
    def c08_completion_evidence(turns, state):
        """Certify only the nonbuyer nurture boundary; never require purchase."""
        turns, state = list(turns or ()), dict(state or {})
        presentations = [dict(t.get("syntheticPpvPresentation") or {}) for t in turns
                         if t.get("syntheticPpvPresentation")]
        intent_ids = {str(dict(p.get("purchaseIntent") or {}).get("id"))
                      for p in presentations if dict(p.get("purchaseIntent") or {}).get("id")}
        analyses = [dict(t.get("salesBrainFullAnalysis") or t.get("fullAnalysis") or {})
                    for t in turns]
        values = [dict(t.get("customerValueAttention") or a.get("attentionEconomics") or {})
                  for t, a in zip(turns, analyses)]
        intent_states = {
            str(item.get("id") or item.get("purchaseIntentId")): str(
                item.get("state") or item.get("status") or ""
            ).upper()
            for item in state.get("purchaseIntents") or ()
            if item.get("id") or item.get("purchaseIntentId")
        }
        failed_states = {"EXPIRED", "ABANDONED", "SUPERSEDED", "ADMIN_CLOSED"}
        one_failure_safe = any(
            int(v.get("failedNonconvertedOpportunityCount") or 0) == 1
            and v.get("lowCostNurtureActive") is False
            and v.get("timeWasterRisk") != "HIGH" for v in values
        )
        nurture = next((v for v in values if v.get("lowCostNurtureActive") is True), {})
        suppression = any(
            v.get("optionalOrdinaryReplySuppressed") is True
            and v.get("suppressionReason") == "LOW_COST_NURTURE_DAILY_BUDGET_CONSUMED"
            for v in values
        )
        suppression_before_ai = any(
            v.get("optionalOrdinaryReplySuppressed") is True
            and not str(t.get("ava") or "").strip()
            and not t.get("providerDraft")
            and not list(t.get("rewriteHistory") or ())
            for t, v in zip(turns, values)
        )
        confirmed_nurture_response = any(
            int(v.get("nurtureResponsesUsed") or 0) == 1 for v in values
        )
        boundary_deliveries = sum(
            bool(dict(a.get("nurture") or {}).get(
                "supporterAttentionBoundaryDelivered"
            ))
            or dict(t.get("finalState") or {}).get("supporterAttentionBoundaryDelivered") is True
            for a, t in zip(analyses, turns)
        )
        reactivated = any(
            dict(a.get("commercialReactivation") or {}).get(
                "commercialInterestType"
            ) not in {None, "NONE"}
            and dict(a.get("commercialReactivation") or {}).get(
                "nurtureBypassedForCommercialInterest"
            ) is True for a in analyses
        )
        reevaluated = any(
            dict(a.get("commercialReactivation") or {}).get(
                "nurtureBypassedForCommercialInterest"
            ) is True and bool(dict(a.get("finalSalesDecision") or {}).get("decision"))
            for a in analyses
        )
        numeric_price = any(re.search(
            r"(?:\$\s*\d+(?:\.\d{1,2})?|\b\d+(?:\.\d{1,2})?\s*(?:usd|dollars?)\b)",
            str(t.get("ava") or ""), re.I) for t in turns)
        checks = {
            "cleanNonbuyerStart": int(state.get("startingPurchaseCount") or 0) == 0,
            "twoDistinctPresentedIntents": len(intent_ids) == 2,
            "twoCanonicalFailedOpportunities": (
                len(intent_ids) == 2
                and all(intent_states.get(intent_id) in failed_states for intent_id in intent_ids)
                and int(state.get("failedNonconvertedOpportunityCount") or 0) >= 2
            ),
            "firstFailureDidNotPrematurelyNurture": one_failure_safe,
            "highTimeWasterRisk": nurture.get("timeWasterRisk") == "HIGH",
            "lowCostNurtureActive": bool(nurture),
            "lowMinimalTreatment": nurture.get("attentionTier") == "LOW" and nurture.get("effortMode") == "MINIMAL",
            "oneResponseBudget": int(nurture.get("nurtureResponseBudget") or 0) == 1,
            "oneNurtureResponseConfirmed": confirmed_nurture_response,
            "sameWindowSuppression": suppression,
            "sameWindowSuppressedBeforeAi": suppression_before_ai,
            "supporterBoundaryConfirmedAtMostOnce": boundary_deliveries == 1,
            "commercialReactivation": reactivated,
            "salesBrainReevaluated": reevaluated,
            "noPurchase": int(state.get("purchaseCount") or 0) == 0,
            "noOwnership": int(state.get("ownershipCount") or 0) == 0,
            "nonbuyerOnly": state.get("buyerStatus", "NONBUYER") == "NONBUYER",
            "noAbuse": not bool(state.get("qualifyingAbuse") or state.get("interactionReviewHoldActive")),
            "noNumericPriceInAvaProse": not numeric_price,
        }
        return {"complete": all(checks.values()), "checks": checks,
                "purchaseIntentIds": sorted(intent_ids)}

    @staticmethod
    def c08_next_action(turns, state, *, fixed_messages=()):
        """Choose evidence-driven C08 work without scenario-conditioned production authority."""
        turns, state = list(turns or ()), dict(state or {})
        latest_analysis = dict(
            dict(turns[-1]).get("salesBrainFullAnalysis") or {}
        ) if turns else {}
        latest_value = dict(
            dict(turns[-1]).get("customerValueAttention")
            or latest_analysis.get("attentionEconomics") or {}
        ) if turns else {}
        # The runtime state contains post-turn durable lifecycle truth; the
        # latest turn snapshot may predate an administrative terminalization.
        current = {**latest_value, **state}
        failed = int(current.get("failedNonconvertedOpportunityCount") or 0)
        presentations = [t for t in turns if t.get("syntheticPpvPresentation")]
        presented_ids = {
            str(dict(dict(turn.get("syntheticPpvPresentation") or {}).get(
                "purchaseIntent"
            ) or {}).get("id"))
            for turn in presentations
            if dict(dict(turn.get("syntheticPpvPresentation") or {}).get(
                "purchaseIntent"
            ) or {}).get("id")
        }
        eligible_intents = [
            dict(intent) for intent in current.get("purchaseIntents") or ()
            if str(dict(intent).get("id")) in presented_ids
            and dict(intent).get("state") == "PRESENTED"
        ]
        if eligible_intents:
            return {
                "kind": "TERMINALIZE_LATEST",
                "state": "ADMIN_CLOSED",
                "purchaseIntentId": eligible_intents[-1]["id"],
            }
        if not presentations:
            index = min(len(turns), max(0, len(tuple(fixed_messages or ())) - 1))
            return {"kind": "FIXED", "message": tuple(fixed_messages)[index]}
        if failed == 1 and len(presentations) == 1:
            return {"kind": "FIXED", "message": "what other private sets do you have? show me another option"}
        if failed < 2:
            return {"kind": "FIXED", "message": "I'm still browsing for now, not buying yet"}
        if not current.get("lowCostNurtureActive"):
            return {"kind": "FIXED", "message": "I'm only browsing again, I still don't feel like paying"}
        used = int(current.get("nurtureResponsesUsed") or 0)
        if used == 0:
            return {"kind": "FIXED", "message": "hey, what are you up to today?"}
        if not current.get("optionalOrdinaryReplySuppressed"):
            return {"kind": "FIXED", "message": "anything interesting going on?"}
        return {"kind": "FIXED", "message": "okay, what private content do you actually have available?"}

    def _c08_expire_latest_presented(self, purchase_intent_id=None):
        """Atomically close one scenario-owned intent and revoke its Unlock."""
        active = self._active(required_state="RUNNING")
        if active["scenario_id"] != "C08":
            raise RuntimeError("C08_TERMINALIZATION_SCOPE_MISMATCH")
        reason = "SCENARIO_LAB_C08_CANONICAL_NONCONVERSION"
        with self.harness.connection() as connection:
            row = connection.execute(
                """SELECT purchase_intent_id,telegram_user_id,telegram_chat_id
                   FROM purchase_intents
                   WHERE telegram_user_id=%s
                     AND (%s::uuid IS NULL OR purchase_intent_id=%s::uuid)
                     AND (
                       (status='PRESENTED' AND presented_at IS NOT NULL)
                       OR (status='ADMIN_CLOSED'
                           AND administrative_close_reason=%s)
                     )
                   ORDER BY CASE WHEN status='PRESENTED' THEN 0 ELSE 1 END,
                            created_at DESC
                   LIMIT 1""",
                (int(active["telegram_user_id"]), purchase_intent_id,
                 purchase_intent_id, reason),
            ).fetchone()
            if not row:
                raise RuntimeError("C08_NO_PRESENTED_INTENT_TO_EXPIRE")
            intent_id = row["purchase_intent_id"]
        # This existing production repository operation owns one transaction
        # containing both the PurchaseIntent close and Unlock revocation.
        from app.repositories.purchase_intent_repository import PurchaseIntentRepository
        closed = PurchaseIntentRepository(
            connection_factory=self.harness.connection
        ).close_administratively(
            intent_id, reason_code=reason,
            expected_telegram_user_id=int(row["telegram_user_id"]),
            expected_telegram_chat_id=int(row["telegram_chat_id"]),
            at=datetime.now(timezone.utc),
        )
        from app.repositories.private_chat_fingerprint_repository import (
            PrivateChatFingerprintRepository,
        )
        grant = PrivateChatFingerprintRepository(
            connection_factory=self.harness.connection
        ).get_grant_for_intent(intent_id)
        if closed.status.value != "ADMIN_CLOSED":
            raise RuntimeError("C08_CANONICAL_CLOSE_DID_NOT_TERMINALIZE_TARGET")
        if grant is not None and (grant.state != "REVOKED" or grant.use_count != 0):
            raise RuntimeError("C08_CANONICAL_CLOSE_DID_NOT_REVOKE_UNUSED_UNLOCK")
        return {
            "purchaseIntentId": str(intent_id),
            "terminalState": "ADMIN_CLOSED",
            "unlockState": grant.state if grant is not None else None,
        }

    def _c08_runtime_state(self, turns):
        state = dict(self.builder.derived_state("C08"))
        customer = self.harness.customer_for(self.harness.definition("C08"))
        with self.harness.connection() as connection:
            rows = connection.execute(
                """SELECT purchase_intent_id,status,creator_profile_id,
                          fanvue_account_id
                   FROM purchase_intents
                   WHERE telegram_user_id=%s ORDER BY created_at,purchase_intent_id""",
                (customer.telegram_user_id,),
            ).fetchall()
        state["purchaseIntents"] = [
            {"id": str(row["purchase_intent_id"]), "state": row["status"]}
            for row in rows
        ]
        if turns:
            latest = dict(turns[-1])
            analysis = dict(latest.get("salesBrainFullAnalysis") or {})
            state.update(dict(
                latest.get("customerValueAttention")
                or analysis.get("attentionEconomics") or {}
            ))
        # Durable PurchaseIntent lifecycle truth is authoritative over the
        # latest turn's pre-terminalization attention snapshot.
        if rows:
            scopes = {
                (int(row["creator_profile_id"]), int(row["fanvue_account_id"]))
                for row in rows
            }
            if len(scopes) != 1:
                raise RuntimeError("C08_PURCHASE_INTENT_SCOPE_AMBIGUOUS")
            creator_profile_id, fanvue_account_id = next(iter(scopes))
            from app.repositories.purchase_intent_repository import (
                PurchaseIntentRepository,
            )
            evidence = PurchaseIntentRepository(
                connection_factory=self.harness.connection
            ).get_customer_opportunity_evidence(
                creator_profile_id=creator_profile_id,
                fanvue_account_id=fanvue_account_id,
                telegram_user_id=int(customer.telegram_user_id),
            )
            state.update({
                "commercialOpportunityEvidenceSource": evidence[
                    "commercial_opportunity_evidence_source"
                ],
                "presentedOpportunityCount": evidence[
                    "presented_opportunity_count"
                ],
                "failedNonconvertedOpportunityCount": evidence[
                    "failed_nonconverted_opportunity_count"
                ],
                "convertedOpportunityCount": evidence[
                    "converted_opportunity_count"
                ],
                "activeUnresolvedOpportunity": evidence[
                    "active_unresolved_opportunity"
                ],
            })
        return state

    def _execute_c08_primary(self, *, language_mode):
        definition = self.harness.definition("C08")
        return self._execute_with_attempt_owner(
            "C08", int(definition.maximum_turn_count or 18),
            lambda: self._execute_c08_primary_owned(language_mode=language_mode),
        )

    def _execute_c08_primary_owned(self, *, language_mode):
        definition = self.harness.definition("C08")
        attempt = self.recovery.scenario_attempt("C08")
        results = []
        previous_internal_action = None
        while True:
            turns = self._current_attempt_turn_projections("C08", attempt)
            state = self._c08_runtime_state(turns)
            completion = self.c08_completion_evidence(turns, state)
            if completion["complete"]:
                return {"scenario": "C08", "scenarioAttempt": attempt,
                        "execution": "OBJECTIVES_COMPLETE_BEFORE_PURCHASE",
                        "completedTurns": len(results), "turns": results,
                        "completion": completion}
            if len(turns) >= int(definition.maximum_turn_count or 18):
                raise RuntimeError("C08_MAXIMUM_TURNS_REACHED_BEFORE_OBJECTIVES")
            action = self.c08_next_action(
                turns, state, fixed_messages=definition.canonical_customer_turns,
            )
            if action["kind"] == "TERMINALIZE_LATEST":
                marker = (
                    len(turns), action["kind"], action.get("purchaseIntentId"),
                    tuple((item.get("id"), item.get("state"))
                          for item in state.get("purchaseIntents") or ()),
                )
                if marker == previous_internal_action:
                    raise RuntimeError(
                        "C08_NON_PROGRESSING_ORCHESTRATION: internal action "
                        "did not advance PurchaseIntent lifecycle or logical turn"
                    )
                previous_internal_action = marker
                results.append(self._c08_expire_latest_presented(
                    action["purchaseIntentId"]
                ))
            else:
                previous_internal_action = None
                results.append(self.turn(action["message"], language_mode=language_mode))

    def recover_stale_execution(self) -> dict[str, Any]:
        active = self._active(required_state="RUNNING")
        scenario_id = active["scenario_id"]
        scenario_attempt = self.recovery.scenario_attempt(scenario_id)
        return self.recovery.recover_stale_execution(
            scenario_id, scenario_attempt,
        )

    def adaptive_turn(self, *, phase, constraints, phase_transition_reason: str,
                      language_mode: str = REAL_AVA_LANGUAGE,
                      customer_service=None) -> dict[str, Any]:
        """Generate one phase-bound customer message, then run the canonical turn."""
        from app.testing.adaptive_synthetic_customer import (
            AdaptiveSyntheticCustomerService, CustomerBehaviorPhase,
        )
        active = self._active(required_state="RUNNING")
        scenario_id = active["scenario_id"]
        scenario_attempt = self.recovery.scenario_attempt(scenario_id)
        turns = self._current_attempt_turn_projections(scenario_id, scenario_attempt)
        durable_adaptive_switch = any(
            dict(dict(
                turn.get("salesBrainFullAnalysis") or turn.get("fullAnalysis") or {}
            ).get("sexualCommercialProgression") or {}).get(
                "adaptiveSwitchEligible"
            ) is True
            for turn in turns
        )
        if (
            scenario_id in {"C05", "C07"}
            and CustomerBehaviorPhase(phase) in {
                CustomerBehaviorPhase.COMMERCIAL_CURIOSITY,
                CustomerBehaviorPhase.REVEAL_INTEREST,
            }
            and not durable_adaptive_switch
        ):
            raise RuntimeError(
                f"{scenario_id}_ADAPTIVE_SWITCH_REQUIRES_DURABLE_COMMERCIAL_EXPOSURE"
            )
        if turns:
            previous_analysis = dict(turns[-1].get("salesBrainFullAnalysis") or {})
            previous_decision = dict(
                previous_analysis.get("finalSalesDecision") or {}
            )
            if (
                previous_decision.get("decision") == "BACK_OFF"
                and previous_decision.get("reasonCode") == "CUSTOMER_DECLINED"
            ):
                raise RuntimeError(
                    "SCENARIO_TERMINAL_BACKOFF: adaptive continuation is not allowed"
                )
        recent = [
            {"role": role, "content": content}
            for turn in turns[-6:]
            for role, content in (("customer", turn["customer"]), ("ava", turn["ava"]))
        ]
        service = customer_service or AdaptiveSyntheticCustomerService()
        authoritative_offer = next((
            turn.get("syntheticPpvPresentation") for turn in reversed(turns)
            if turn.get("syntheticPpvPresentation")
        ), None)
        if (
            scenario_id not in {"C05", "C06"}
            and
            CustomerBehaviorPhase(phase) is CustomerBehaviorPhase.OFFER_REACTION
            and getattr(constraints, "offer_reaction", "NONE") == "ACCEPT"
        ):
            previous = turns[-1] if turns else {}
            previous_adaptive = dict(previous.get("adaptiveCustomer") or {})
            previous_analysis = dict(
                previous.get("salesBrainFullAnalysis")
                or previous.get("fullAnalysis")
                or {}
            )
            recovery = dict(previous_analysis.get("objectionRecovery") or {})
            style = dict(previous_analysis.get("conversationStyle") or {})
            if not (
                previous_adaptive.get("behavioral_phase") == "OFFER_REACTION"
                and dict(previous_adaptive.get("customer_constraints") or {}).get(
                    "offer_reaction"
                ) == "HESITATE"
                and recovery.get("authorized") is True
                and style.get("objectionResponseSatisfied") is True
            ):
                raise RuntimeError(
                    "CUSTOMER_TRAJECTORY_BLOCKED_BY_AVA: "
                    "ACCEPT_REQUIRES_VALID_OBJECTION_RESPONSE"
                )
        audit = service.generate_turn(
            scenario_id=scenario_id, scenario_attempt=scenario_attempt,
            logical_turn=len(turns) + 1, phase=CustomerBehaviorPhase(phase),
            constraints=constraints,
            previous_ava_response=(turns[-1]["ava"] if turns else ""),
            authoritative_offer_context=authoritative_offer,
            recent_transcript=recent,
            phase_transition_reason=phase_transition_reason,
            purchase_ordinal=int(
                self.builder.derived_state(scenario_id).get("purchaseCount") or 0
            ) or None,
        )
        if audit.final_customer_message is None:
            self.harness.record_behavior_history(scenario_id, [{
                "type": "ADAPTIVE_CUSTOMER_BLOCKED",
                "message": "CUSTOMER_TRAJECTORY_BLOCKED_BY_AVA",
                "evidence": {"adaptiveCustomer": audit.to_mapping()},
            }])
            raise RuntimeError(audit.blocked_reason or "CUSTOMER_TRAJECTORY_BLOCKED_BY_AVA")
        result = self.turn(audit.final_customer_message, language_mode=language_mode)
        payload = json.dumps(audit.to_mapping(), default=str)
        purchase_emulator_projection = None
        authoritative_intent = dict(
            dict(authoritative_offer or {}).get("purchaseIntent") or {}
        )
        if authoritative_intent.get("id"):
            purchase_emulator_projection = self.purchase_emulator_eligibility(
                scenario_id=scenario_id,
                turns=[*turns, {
                    **result,
                    "adaptiveCustomer": audit.to_mapping(),
                }],
                purchase_intent_id=authoritative_intent["id"],
                purchase_intent_state=str(
                    authoritative_intent.get("state") or "PRESENTED"
                ),
                telegram_commerce=True,
            )
        adaptive_projection = json.dumps({
            "adaptiveSwitchEligible": durable_adaptive_switch,
            "adaptiveSwitchReason": (
                phase_transition_reason if durable_adaptive_switch else None
            ),
            "adaptiveCustomerPhase": audit.behavioral_phase,
            "adaptiveCustomerService": "AdaptiveSyntheticCustomerService",
            "adaptiveCustomerWordingSource": audit.wording_source,
            "adaptiveCustomerSource": audit.wording_source,
            "adaptivePhaseReason": audit.phase_transition_reason,
            "progressionBefore": (
                dict(dict(turns[-1].get("salesBrainFullAnalysis") or {}).get(
                    "salesProgression"
                ) or {}).get("phase") if turns else None
            ),
            "progressionAfter": dict(
                dict(result.get("fullAnalysis") or result.get("salesBrainFullAnalysis") or {}).get(
                    "salesProgression"
                ) or {}
            ).get("phase"),
            "recentCustomerRepetitionRisk": bool(
                audit.validation_result.get("recentCustomerRepetitionRisk")
            ),
            "purchaseOrdinal": audit.provider_metadata.get("purchaseOrdinal"),
            "trajectorySexualAlignmentRequired": bool(
                audit.validation_result.get("trajectorySexualAlignmentRequired")
            ),
            "trajectorySexualAlignmentSatisfied": audit.validation_result.get(
                "trajectorySexualAlignmentSatisfied"
            ),
            "trajectorySexualAlignmentSource": audit.validation_result.get(
                "trajectorySexualAlignmentSource"
            ),
        })
        purchase_emulator_payload = json.dumps(
            purchase_emulator_projection or {}, default=str,
        )
        with self.harness.connection() as connection:
            connection.execute("""UPDATE certification_scenario_turn_evidence
                SET full_analysis=jsonb_set(
                    jsonb_set(
                      jsonb_set(full_analysis,'{adaptiveCustomer}',%s::jsonb,true),
                      '{SalesBrainFullAnalysis,sexualCommercialProgression}',
                      COALESCE(full_analysis->'SalesBrainFullAnalysis'->'sexualCommercialProgression','{}'::jsonb)
                        || %s::jsonb,true),
                    '{SalesBrainFullAnalysis,scenarioPurchaseEmulator}',%s::jsonb,true)
                WHERE scenario_id=%s AND inbound=%s AND outbound=%s
                  AND (full_analysis->'operatorResult'->>'turnNumber')::integer=%s""", (
                payload, adaptive_projection, purchase_emulator_payload,
                scenario_id, result["customer"], result["ava"],
                result["turnNumber"],
            ))
            connection.execute("""UPDATE certification_scenario_turn_attempts
                SET full_analysis=jsonb_set(
                    jsonb_set(
                      jsonb_set(full_analysis,'{adaptiveCustomer}',%s::jsonb,true),
                      '{sexualCommercialProgression}',
                      COALESCE(full_analysis->'sexualCommercialProgression','{}'::jsonb)
                        || %s::jsonb,true),
                    '{scenarioPurchaseEmulator}',%s::jsonb,true)
                WHERE scenario_id=%s AND scenario_attempt=%s AND logical_turn=%s
                  AND status='CURRENT'""", (
                payload, adaptive_projection, purchase_emulator_payload,
                scenario_id, scenario_attempt, result["turnNumber"],
            ))
        result["adaptiveCustomer"] = audit.to_mapping()
        if purchase_emulator_projection is not None:
            result["scenarioPurchaseEmulator"] = purchase_emulator_projection
        return result

    def retry_previous_turn(self, reason: str | None = None, *,
                            recovery_operation_id: str | None = None) -> dict[str, Any]:
        active = self._active(required_state="RUNNING")
        scenario_id = active["scenario_id"]
        scenario_attempt = self.recovery.scenario_attempt(scenario_id)
        latest = self.recovery.latest_current_turn(scenario_id, scenario_attempt)
        logical_turn = int(latest["logical_turn"]) if latest is not None else 1
        owner_id = self.recovery.claim_execution(
            scenario_id, scenario_attempt,
            requested_start_turn=logical_turn,
            requested_end_turn=logical_turn,
        )
        try:
            result = self._retry_previous_turn_owned(
                reason, recovery_operation_id=recovery_operation_id,
            )
        except Exception as error:
            self.recovery.release_execution(
                scenario_id, scenario_attempt, owner_id,
                failed=True, reason=f"{type(error).__name__}: {error}",
            )
            raise
        self.recovery.release_execution(
            scenario_id, scenario_attempt, owner_id,
        )
        return result

    def _retry_previous_turn_owned(self, reason: str | None = None, *,
                                   recovery_operation_id: str | None = None) -> dict[str, Any]:
        active = self._active(required_state="RUNNING")
        scenario_id = active["scenario_id"]
        scenario_attempt = self.recovery.scenario_attempt(scenario_id)
        operation_id = str(recovery_operation_id or uuid4())
        marker = f"RECOVERY_OPERATION:{operation_id}"
        with self.harness.connection() as lock_connection:
            locked = lock_connection.execute(
                "SELECT pg_try_advisory_lock(hashtext(%s)) AS locked",
                (f"session5-retry:{scenario_id}",),
            ).fetchone()["locked"]
            if not locked:
                raise RuntimeError("RETRY ALREADY IN PROGRESS")
            try:
                with self.harness.connection() as connection:
                    prior = connection.execute("""SELECT logical_turn FROM
                        certification_scenario_turn_attempts WHERE scenario_id=%s
                        AND scenario_attempt=%s AND reason LIKE %s
                        ORDER BY logical_turn DESC LIMIT 1""",
                        (scenario_id, scenario_attempt, marker + "%"),
                    ).fetchone()
                if prior:
                    logical_turn = int(prior["logical_turn"])
                    for row in reversed(self._turns(scenario_id)):
                        result = dict(dict(row["full_analysis"] or {}).get("operatorResult") or {})
                        if int(result.get("turnNumber") or 0) == logical_turn:
                            result["idempotentRecoveryReplay"] = True
                            return result
                    raise RuntimeError("IDEMPOTENT RETRY RESULT IS NOT AVAILABLE")
                return self._retry_previous_turn_locked(
                    reason, recovery_operation_marker=marker,
                )
            finally:
                lock_connection.execute(
                    "SELECT pg_advisory_unlock(hashtext(%s))",
                    (f"session5-retry:{scenario_id}",),
                )

    def _retry_previous_turn_locked(self, reason: str | None = None, *,
                                    recovery_operation_marker: str) -> dict[str, Any]:
        active = self._active(required_state="RUNNING")
        scenario_id = active["scenario_id"]
        scenario_attempt = self.recovery.scenario_attempt(scenario_id)
        allowed, blocker, latest = self.recovery.retry_boundary(scenario_id, scenario_attempt)
        if not allowed or latest is None:
            raise RuntimeError(blocker or "Retry is not safe.")
        original = dict(latest)
        attempt_rows = self.recovery.turn_attempt_rows(scenario_id, scenario_attempt)
        self.recovery.restore(original)
        restored = self.builder.derived_state(scenario_id)
        if json.dumps(restored, sort_keys=True, default=str) != json.dumps(
                original["checkpoint_state"], sort_keys=True, default=str):
            raise RuntimeError("PRE_TURN restoration verification failed; replay was not attempted.")
        self.recovery.preserve_checkpoint_record(original)
        retry_reason = recovery_operation_marker + " | " + (
            reason or "Latest synthetic turn retried after repair."
        )
        self.recovery.preserve_turn_attempt_rows(
            attempt_rows, original["attempt_id"], retry_reason,
        )
        old_checkpoint = {
            "checkpointId": str(original["checkpoint_id"]), "scenarioId": scenario_id,
            "scenarioAttempt": int(original["scenario_attempt"]),
            "logicalTurn": int(original["logical_turn"]), "turnAttempt": int(original["turn_attempt"]),
        }
        evidence = self.harness.execute_turn(
            scenario_id, original["inbound"],
            turn_identity=ScenarioTurnExecutionIdentity(
                scenario_id=scenario_id,
                scenario_attempt=scenario_attempt,
                logical_turn=int(original["logical_turn"]),
                turn_attempt=int(original["turn_attempt"]) + 1,
            ),
        )
        after = self.builder.derived_state(scenario_id)
        changes = self._changes(restored, after, evidence)
        projection = self._turn_projection(evidence, changes)
        projection["turnNumber"] = int(original["logical_turn"])
        projection["turnAttempt"] = int(original["turn_attempt"]) + 1
        with self.harness.connection() as connection:
            connection.execute("""UPDATE certification_scenario_turn_evidence
                SET full_analysis=jsonb_set(full_analysis,'{operatorResult}',%s::jsonb,true)
                WHERE correlation_id=%s""", (
                json.dumps(projection, default=str), evidence["syntheticInboundId"],
            ))
        new_checkpoint = dict(old_checkpoint)
        new_checkpoint["turnAttempt"] = projection["turnAttempt"]
        self.recovery.record_turn(
            new_checkpoint, original["inbound"], evidence["finalResponseText"],
            evidence.get("SalesBrainFullAnalysis") or {}, after,
        )
        return projection

    def restart_scenario(self, scenario_id: str,
                         reason: str | None = None) -> dict[str, Any]:
        """Restart one explicit scenario through retryable durable boundaries."""
        scenario_id = str(scenario_id or "").strip().upper()
        if scenario_id not in {item.scenario_id for item in SCENARIO_MANIFEST}:
            raise LookupError(f"Unknown scenario {scenario_id or '<empty>'}.")

        # Serialize restarts for this target. Each completed lifecycle boundary
        # remains durable and recognizable if a later step fails, so retrying the
        # same explicit target resumes rather than fabricating another archive.
        with self.harness.connection() as restart_lock:
            restart_lock.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                (f"session5-scenario-restart:{scenario_id}",),
            )
            with self.harness.connection() as connection:
                other = connection.execute("""SELECT scenario_id FROM certification_scenario_runs
                    WHERE state=ANY(%s) AND scenario_id<>%s LIMIT 1""", (
                        list(EXECUTION_STATES), scenario_id,
                    )).fetchone()
            if other is not None:
                raise RuntimeError(
                    f"Active scenario {other['scenario_id']} blocks restart of {scenario_id}."
                )

            row = self._run(scenario_id)
            if row is None:
                raise LookupError(f"Scenario {scenario_id} has no runtime state.")
            state = str(row["state"])
            if state == "RUNNING":
                attempt = int(row["scenario_attempt"] or 1)
                try:
                    evidence = self.operator_snapshot()
                except RuntimeError as error:
                    if "no unambiguous evidence projection" not in str(error):
                        raise
                    evidence = {
                        "mode": "SESSION_5_SCENARIO_LAB",
                        "scenario": scenario_id,
                        "scenarioAttempt": attempt,
                        "restartEvidenceStatus": "INCOMPLETE_TURN_ARCHIVED",
                        "restartEvidenceReason": str(error),
                        "transport": "TEST_TRANSPORT_NO_WAIT",
                    }
                evidence["execution"] = self.recovery.execution_status(
                    scenario_id, attempt,
                    int(self.harness.definition(scenario_id).maximum_turn_count or 0),
                )
                self.recovery.archive_scenario_attempt(
                    scenario_id, attempt, evidence, reason,
                )
                with self.harness.connection() as connection:
                    connection.execute("""UPDATE certification_scenario_runs
                        SET state='COMPLETED',updated_at=NOW()
                        WHERE scenario_id=%s AND state='RUNNING'""", (scenario_id,))
                state = "COMPLETED"

            try:
                if state == "COMPLETED":
                    self.snapshot(scenario_id)
                    state = "SNAPSHOTTED"
                if state == "SNAPSHOTTED":
                    self.reset(scenario_id)
                    state = "VERIFIED_CLEAN"
                if state != "VERIFIED_CLEAN":
                    raise RuntimeError(
                        f"Scenario {scenario_id} cannot restart from lifecycle {state}."
                    )
                clean = self.verify_clean(scenario_id)
                if clean["result"] != "VERIFIED_CLEAN":
                    raise RuntimeError("VERIFY_CLEAN returned an incomplete reset.")
            except Exception as error:
                raise RuntimeError(
                    f"SCENARIO RESTART FAILED during reset/verification: {error}"
                ) from error

            try:
                prepared = self.prepare(scenario_id)
            except Exception as error:
                # VERIFIED_CLEAN is an intentional retryable boundary. Historical
                # attempt evidence is already durable and no fresh attempt exists.
                raise RuntimeError(
                    f"SCENARIO RESTART FAILED during prepare: {error}"
                ) from error
            prepared["scenarioAttempt"] = self.recovery.scenario_attempt(scenario_id)
            return prepared

    def recover_duplicate_retry_advance(self) -> dict[str, Any]:
        """Restore the latest proven duplicate turn from its PRE_TURN checkpoint."""
        active = self._active(required_state="RUNNING")
        scenario_id = active["scenario_id"]
        scenario_attempt = self.recovery.scenario_attempt(scenario_id)
        rows = self.recovery.turn_attempt_rows(scenario_id, scenario_attempt)
        current = [row for row in rows if row["status"] == "CURRENT"]
        if len(current) < 2:
            raise RuntimeError("DUPLICATE ADVANCE PROOF FAILED: insufficient current turns")
        duplicate, previous = current[-1], current[-2]
        if int(duplicate["logical_turn"]) != int(previous["logical_turn"]) + 1:
            raise RuntimeError("DUPLICATE ADVANCE PROOF FAILED: turns are not adjacent")
        if duplicate["inbound"] != previous["inbound"] or duplicate["outbound"] != previous["outbound"]:
            raise RuntimeError("DUPLICATE ADVANCE PROOF FAILED: replay content differs")
        checkpoint = self.recovery.latest_current_turn(scenario_id, scenario_attempt)
        if checkpoint is None or checkpoint["attempt_id"] != duplicate["attempt_id"]:
            raise RuntimeError("DUPLICATE ADVANCE PROOF FAILED: latest checkpoint mismatch")
        if json.dumps(checkpoint["checkpoint_state"], sort_keys=True, default=str) != json.dumps(
                previous["final_state"], sort_keys=True, default=str):
            raise RuntimeError("DUPLICATE ADVANCE PROOF FAILED: PRE_TURN state differs from prior final state")
        schema_name = checkpoint["schema_name"]
        with self.harness.connection() as connection:
            archived_turns = connection.execute(sql.SQL("""SELECT logical_turn,turn_attempt,status
                FROM {}.certification_scenario_turn_attempts WHERE scenario_id=%s
                AND scenario_attempt=%s ORDER BY logical_turn,turn_attempt""").format(
                    sql.Identifier(schema_name)), (scenario_id, scenario_attempt)).fetchall()
            archived_inbound = connection.execute(sql.SQL("""SELECT COUNT(*) AS count
                FROM {}.certification_scenario_behavior_events
                WHERE scenario_id=%s AND event_type='INBOUND'""").format(
                    sql.Identifier(schema_name)), (scenario_id,)).fetchone()["count"]
        if any(int(row["logical_turn"]) >= int(duplicate["logical_turn"]) for row in archived_turns):
            raise RuntimeError("DUPLICATE ADVANCE PROOF FAILED: checkpoint contains duplicate turn")
        if int(archived_inbound) != int(duplicate["logical_turn"]) - 1:
            raise RuntimeError("DUPLICATE ADVANCE PROOF FAILED: behavior count does not reconcile")
        self.recovery.restore(checkpoint)
        self.recovery.preserve_checkpoint_record(checkpoint)
        self.recovery.preserve_archived_turn_attempt(
            duplicate, status="ABORTED_DUPLICATE_RETRY_ADVANCE",
            reason="Exact duplicate normal-turn advance rolled back to its certified PRE_TURN checkpoint.",
        )
        latest = self.recovery.latest_current_turn(scenario_id, scenario_attempt)
        behavior = self.harness.behavior_summary(scenario_id)
        if latest is None or int(latest["logical_turn"]) != int(previous["logical_turn"]):
            raise RuntimeError("DUPLICATE ADVANCE RECOVERY VERIFICATION FAILED")
        if int(behavior["inbound_message_count"]) != int(previous["logical_turn"]):
            raise RuntimeError("DUPLICATE ADVANCE BEHAVIOR VERIFICATION FAILED")
        return {
            "scenario": scenario_id,
            "scenarioAttempt": scenario_attempt,
            "restoredLogicalTurn": int(previous["logical_turn"]),
            "archivedDuplicateLogicalTurn": int(duplicate["logical_turn"]),
            "archivedDuplicateAttemptId": str(duplicate["attempt_id"]),
            "archivedStatus": "ABORTED_DUPLICATE_RETRY_ADVANCE",
            "inboundMessageCount": int(behavior["inbound_message_count"]),
        }

    def operator_snapshot(self) -> dict[str, Any]:
        """Return UI state without reimplementing any scenario behavior."""
        active = self._active(optional=True)
        body: dict[str, Any] = {
            "mode": "SESSION_5_SCENARIO_LAB",
            "badges": ["SYNTHETIC SCENARIO TEST", "OPERATOR SCENARIO DB",
                       "AUTOMATED TESTS ISOLATED", "NO EXTERNAL SENDS"],
            "databaseEnvironment": {
                "databaseName": self.harness.database_name,
                "purpose": self.harness.database_purpose.value,
            },
            "scenarios": self.list(), "activeScenario": None,
            "transcript": [], "turns": [], "latestAnalysis": None,
            "simulatePurchaseEligible": False,
            "transport": "TEST_TRANSPORT_NO_WAIT",
            "languageModes": [REAL_AVA_LANGUAGE, DETERMINISTIC_CERTIFICATION],
            "defaultLanguageMode": REAL_AVA_LANGUAGE,
            "languageCertification": "EXPLICIT_PER_TURN_LANGUAGE_MODE",
        }
        if active is None:
            return body
        scenario_id = active["scenario_id"]
        rows = self._turns(scenario_id)
        turns = []
        transcript = []
        for row in rows:
            evidence = dict(row["full_analysis"] or {})
            result = dict(evidence.get("operatorResult") or {})
            if result:
                turns.append(result)
            customer = str(evidence.get("inboundText") or row.get("inbound") or "")
            ava = str(evidence.get("finalResponseText") or row.get("outbound") or "")
            if customer: transcript.append({"role": "user", "content": customer})
            if ava: transcript.append({"role": "assistant", "content": ava})
        customer = self.harness.customer_for(self.harness.definition(scenario_id))
        with self.harness.connection() as connection:
            presented = int(connection.execute("""SELECT COUNT(*) AS count FROM purchase_intents
                WHERE telegram_user_id=%s AND status='PRESENTED'
                  AND presented_at IS NOT NULL""",
                (customer.telegram_user_id,)).fetchone()["count"])
            simulated_purchase = connection.execute("""SELECT provenance,result,provider_timestamp
                FROM certification_simulated_provider_events WHERE scenario_id=%s
                ORDER BY created_at DESC LIMIT 1""", (scenario_id,)).fetchone()
            grade = connection.execute(
                "SELECT grade FROM certification_scenario_assessments WHERE scenario_id=%s",
                (scenario_id,),
            ).fetchone()
        body["activeScenario"] = {
            "scenario": scenario_id,
            "name": self.harness.definition(scenario_id).name,
            "canonicalScenarioName": self.harness.definition(scenario_id).name,
            "lifecycle": active["state"], "economicState": active["economic_state"],
            "syntheticTelegramId": int(active["telegram_user_id"]),
            "state": self.builder.derived_state(scenario_id),
            "defects": self._defects(scenario_id),
            "grade": grade["grade"] if grade else None,
        }
        scenario_attempt = self.recovery.scenario_attempt(scenario_id)
        history = self.recovery.attempt_history(
            scenario_id, scenario_attempt=scenario_attempt,
        )
        historical = self.recovery.historical_attempt_history(
            scenario_id, exclude_attempt=scenario_attempt,
        )
        retry_allowed, retry_blocker, retry_latest = self.recovery.retry_boundary(
            scenario_id, scenario_attempt,
        )
        body["activeScenario"]["scenarioAttempt"] = scenario_attempt
        body["recovery"] = {
            "retryEligible": retry_allowed and active["state"] == "RUNNING",
            "retryBlocker": retry_blocker,
            "retryTurn": int(retry_latest["logical_turn"]) if retry_latest else None,
            "retryCustomerMessage": retry_latest["inbound"] if retry_latest else None,
            "history": history,
            "historicalScenarioAttempts": historical,
        }
        body["transcript"] = transcript
        body["turns"] = turns
        body["latestAnalysis"] = (
            dict(rows[-1]["full_analysis"] or {}).get("SalesBrainFullAnalysis")
            if rows else None
        )
        body["simulatePurchaseEligible"] = (
            presented == 1 and active["state"] == "RUNNING"
        )
        body["simulatedProviderPurchase"] = (
            {"provenance": simulated_purchase["provenance"],
             "result": simulated_purchase["result"],
             "providerTimestamp": simulated_purchase["provider_timestamp"].isoformat()}
            if simulated_purchase else None
        )
        return body

    def full_attempt_analysis(self, scenario_id: str | None = None) -> dict[str, Any]:
        """Project one selected attempt's canonical turns without mutating state."""
        active = self._inspectable(scenario_id) if scenario_id else (
            self._active(optional=True) or self._latest_terminal()
        )
        if active is None:
            raise RuntimeError("No inspectable scenario attempt exists.")
        if active["state"] not in {"RUNNING", "COMPLETED", "SNAPSHOTTED"}:
            raise RuntimeError(
                f"Scenario analysis is unavailable in lifecycle {active['state']}."
            )
        scenario_id = active["scenario_id"]
        scenario_attempt = self.recovery.scenario_attempt(scenario_id)
        customer = self.harness.customer_for(self.harness.definition(scenario_id))
        projections = self._current_attempt_turn_projections(
            scenario_id, scenario_attempt,
        )
        with self.harness.connection() as connection:
            prospect = connection.execute("""SELECT relationship_state,preference_state,
                inbound_message_count,first_observed_at,last_observed_at
                FROM telegram_sales_prospects WHERE telegram_user_id=%s
                ORDER BY last_observed_at DESC LIMIT 1""", (
                    customer.telegram_user_id,
                )).fetchone()
            intents = connection.execute("""SELECT purchase_intent_id,status,
                commercial_offering_id,expected_price_minor,expected_currency,
                created_at,presented_at,clicked_at,purchased_at
                FROM purchase_intents WHERE telegram_user_id=%s
                ORDER BY created_at,purchase_intent_id""", (
                    customer.telegram_user_id,
                )).fetchall()
            sessions = connection.execute("""SELECT sales_session_id,state,
                progression_stage,objective,commercial_context,outcome,
                started_at,last_activity_at,ended_at
                FROM sales_sessions WHERE external_fanvue_user_uuid=%s
                ORDER BY created_at,sales_session_id""", (
                    customer.synthetic_buyer_uuid,
                )).fetchall()
            simulated = connection.execute("""SELECT provenance,result,provider_timestamp
                FROM certification_simulated_provider_events WHERE scenario_id=%s
                ORDER BY created_at,event_id""", (scenario_id,)).fetchall()
        accumulated = {
            "derivedState": self.builder.derived_state(scenario_id),
            "relationshipState": dict(prospect["relationship_state"] or {}) if prospect else {},
            "durableConversationalMemory": dict(prospect["preference_state"] or {}) if prospect else {},
            "inboundMessageCount": int(prospect["inbound_message_count"] or 0) if prospect else 0,
            "behavior": self.harness.behavior_summary(scenario_id),
            "purchaseIntents": [dict(row) for row in intents],
            "sessions": [dict(row) for row in sessions],
            "simulatedProviderEvents": [dict(row) for row in simulated],
        }
        history = self.recovery.attempt_history(
            scenario_id, scenario_attempt=scenario_attempt,
        )
        historical = self.recovery.historical_attempt_history(
            scenario_id, exclude_attempt=scenario_attempt,
        )
        def audit_only(value):
            return {
                "scenarioAttempts": list(value.get("scenarioAttempts") or []),
                "turnAttempts": [{
                    key: row.get(key) for key in (
                        "scenario_attempt", "logical_turn", "turn_attempt",
                        "status", "reason",
                    )
                } for row in value.get("turnAttempts") or []],
            }
        return {
            "mode": "SESSION_5_FULL_SCENARIO_ANALYSIS",
            "databaseEnvironment": {
                "databaseName": self.harness.database_name,
                "purpose": self.harness.database_purpose.value,
            },
            "scenario": {
                "scenarioId": scenario_id,
                "name": self.harness.definition(scenario_id).name,
                "canonicalScenarioName": self.harness.definition(scenario_id).name,
                "scenarioAttempt": scenario_attempt,
                "lifecycle": active["state"],
                "economicState": active["economic_state"],
                "syntheticTelegramId": int(active["telegram_user_id"]),
                "transport": "TEST_TRANSPORT_NO_WAIT",
                "canonicalTurnCount": len(projections),
            },
            "currentAccumulatedState": accumulated,
            "turns": [
                {key: value for key, value in turn.items() if not key.startswith("_")}
                for turn in projections
            ],
            "finalAccumulatedState": accumulated,
            "attemptAudit": {
                "currentAttempt": audit_only(history),
                "previousAttempts": audit_only(historical),
            },
        }

    def analysis(self) -> dict[str, Any]:
        active = self._active()
        turns = self._turns(active["scenario_id"])
        if not turns:
            raise RuntimeError("No turn evidence exists for the active scenario.")
        evidence = dict(turns[-1]["full_analysis"] or {})
        return dict(evidence.get("SalesBrainFullAnalysis") or {})

    def defect(self, severity: str, note: str) -> dict[str, Any]:
        severity = severity.upper()
        if severity not in SEVERITIES:
            raise ValueError("Severity must be CRITICAL, MAJOR, or QUALITY.")
        active = self._active()
        turn_number = len(self._turns(active["scenario_id"]))
        defect_id = uuid4()
        with self.harness.connection() as connection:
            connection.execute("""INSERT INTO certification_scenario_defects(
                defect_id,scenario_id,turn_number,severity,note)
                VALUES (%s,%s,%s,%s,%s)""", (
                    defect_id, active["scenario_id"], turn_number, severity, note,
                ))
        return {"defectId": str(defect_id), "scenario": active["scenario_id"],
                "turn": turn_number, "severity": severity, "note": note}

    def complete(self, grade: str) -> dict[str, Any]:
        grade = grade.upper()
        if grade not in GRADES:
            raise ValueError("Grade must be PASS, PASS_WITH_NOTES, or FAIL.")
        active = self._active(required_state="RUNNING")
        self.harness.transition(active["scenario_id"], ScenarioState.COMPLETED)
        with self.harness.connection() as connection:
            connection.execute("""INSERT INTO certification_scenario_assessments(
                scenario_id,grade,completed_at) VALUES (%s,%s,NOW())
                ON CONFLICT(scenario_id) DO UPDATE SET grade=EXCLUDED.grade,
                completed_at=EXCLUDED.completed_at""", (active["scenario_id"], grade))
        return {"scenario": active["scenario_id"], "grade": grade,
                "lifecycle": "COMPLETED", "next": "SNAPSHOT"}

    def snapshot(self, scenario_id: str) -> dict[str, Any]:
        scenario_id = self._target_scenario(scenario_id, required_state="COMPLETED")
        with self.harness.connection() as connection:
            assessment = connection.execute(
                "SELECT grade,completed_at FROM certification_scenario_assessments WHERE scenario_id=%s",
                (scenario_id,),
            ).fetchone()
        try:
            turn_evidence = [dict(row["full_analysis"] or {})
                             for row in self._turns(scenario_id)]
            evidence_status = "COMPLETE"
        except RuntimeError as error:
            if "no unambiguous evidence projection" not in str(error):
                raise
            turn_evidence = []
            evidence_status = "INCOMPLETE_TURN_ARCHIVED"
        evidence = {
            "scenario": scenario_id,
            "startingDefinition": self.harness.definition(scenario_id).name,
            "turns": turn_evidence,
            "evidenceStatus": evidence_status,
            "finalState": self.builder.derived_state(scenario_id),
            "defects": self._defects(scenario_id),
            "assessment": dict(assessment) if assessment else None,
            "transport": "TEST_TRANSPORT_NO_WAIT",
        }
        snapshot_id = self.harness.snapshot(scenario_id, evidence)
        return {"scenario": scenario_id, "snapshotId": str(snapshot_id),
                "lifecycle": "SNAPSHOTTED", "next": "RESET"}

    def reset(self, scenario_id: str) -> dict[str, Any]:
        scenario_id = self._target_scenario(scenario_id, required_state="SNAPSHOTTED")
        return self.harness.reset(scenario_id)

    def verify_clean(self, scenario_id: str | None = None) -> dict[str, Any]:
        row = self._run(scenario_id.upper()) if scenario_id else self._latest_clean()
        if row is None or row["state"] != "VERIFIED_CLEAN":
            raise RuntimeError("No VERIFIED_CLEAN scenario is available.")
        state = self.builder.derived_state(row["scenario_id"])
        inventory = self.harness.starting_state_inventory(row["scenario_id"])
        counts = inventory["counts"]
        clean = all(value == 0 for value in counts.values()) and (
            not inventory["prospect"]["exists"]
            and state["buyerStatus"] == "NONBUYER"
            and state["buyerStage"] == "PROSPECT"
            and state["purchaseCount"] == 0
            and state["lifetimeSpendMinor"] == 0
            and state["ownershipCount"] == 0
            and state["activePurchaseIntent"] is None
            and state["activeSession"] is None
            and state["presentedOpportunityCount"] == 0
            and state["convertedOpportunityCount"] == 0
            and state["failedNonconvertedOpportunityCount"] == 0
        )
        return {"scenario": row["scenario_id"],
                "result": "VERIFIED_CLEAN" if clean else "RESET_INCOMPLETE",
                "state": state, "runtimeInventory": inventory}

    @staticmethod
    def purchase_emulator_eligibility(*, scenario_id: str, turns,
                                      purchase_intent_id,
                                      purchase_intent_state: str,
                                      telegram_commerce: bool = True) -> dict[str, Any]:
        """Require exact presentation plus explicit customer acceptance evidence."""
        target = str(purchase_intent_id)
        turns = list(turns or ())
        matching = next((dict(turn.get("syntheticPpvPresentation") or {})
                         for turn in reversed(turns)
                         if str(dict(dict(turn.get("syntheticPpvPresentation") or {}).get(
                             "purchaseIntent") or {}).get("id") or "") == target), {})
        latest = dict(turns[-1] if turns else {})
        adaptive = dict(latest.get("adaptiveCustomer") or {})
        derived = dict(dict(adaptive.get("validation_result") or {}).get(
            "derivedSignals") or {})
        accepted = bool(
            adaptive.get("behavioral_phase") == "OFFER_REACTION"
            and derived.get("offerAcceptance") is True
        )
        offer_context = dict(adaptive.get("authoritative_offer_context") or {})
        accepted_target = str(
            offer_context.get("purchaseIntentId")
            or dict(offer_context.get("purchaseIntent") or {}).get("id") or ""
        )
        exact_acceptance = bool(accepted and accepted_target == target)
        c04_direct_acceptance = False
        if str(scenario_id).upper() == "C04" and matching:
            from app.services.conversational_sales_progression_service import (
                ConversationalSalesProgressionService,
            )
            customer_text = str(latest.get("customer") or "")
            c04_direct_acceptance = bool(
                ConversationalSalesProgressionService().has_direct_purchase_intent(
                    customer_text
                )
            )
        if not telegram_commerce:
            eligible, reason, source = True, "NON_TELEGRAM_COMMERCE_EXISTING_CONTRACT", "EXISTING_PROVIDER_EMULATOR_CONTRACT"
        elif str(purchase_intent_state).upper() != "PRESENTED":
            eligible, reason, source = False, "TARGET_PURCHASE_INTENT_NOT_PRESENTED", None
        elif not matching:
            eligible, reason, source = False, "AUTHORITATIVE_STRUCTURED_PRESENTATION_MISSING", None
        elif c04_direct_acceptance:
            eligible, reason, source = True, "EXACT_PRESENTED_INTENT_ACCEPTED", "C04_CANONICAL_DIRECT_BUYER_ACCEPTANCE"
        elif not accepted:
            eligible, reason, source = False, "CANONICAL_CUSTOMER_ACCEPTANCE_REQUIRED", None
        elif not exact_acceptance:
            eligible, reason, source = False, "ACCEPTANCE_TARGETS_DIFFERENT_PURCHASE_INTENT", None
        else:
            eligible, reason, source = True, "EXACT_PRESENTED_INTENT_ACCEPTED", "ADAPTIVE_OFFER_REACTION_ACCEPT"
        return {
            "scenarioPurchaseAcceptanceRequired": bool(telegram_commerce),
            "scenarioPurchaseAcceptanceObserved": accepted,
            "scenarioPurchaseAcceptanceSource": source,
            "simulatePurchaseEligible": eligible,
            "simulatePurchaseEligibilityReason": reason,
            "authoritativePresentedPurchaseIntent": (
                target if matching and str(purchase_intent_state).upper() == "PRESENTED" else None
            ),
            "purchaseEmulatorTargetIntent": target,
        }

    def simulate_purchase(self) -> dict[str, Any]:
        active = self._active(required_state="RUNNING")
        scenario_id = active["scenario_id"]
        customer = self.harness.customer_for(self.harness.definition(scenario_id))
        with self.harness.connection() as connection:
            intents = connection.execute("""SELECT purchase_intent_id,
                expected_price_minor,expected_currency,created_metadata
                FROM purchase_intents
                WHERE telegram_user_id=%s AND status='PRESENTED'
                  AND presented_at IS NOT NULL
                  AND EXISTS (
                    SELECT 1 FROM certification_scenario_runs run
                    JOIN telegram_sales_prospects prospect
                      ON prospect.telegram_user_id=run.telegram_user_id
                    WHERE run.scenario_id=%s
                      AND run.telegram_user_id=purchase_intents.telegram_user_id
                      AND prospect.creator_profile_id=
                          purchase_intents.creator_profile_id
                      AND prospect.fanvue_account_id=
                          purchase_intents.fanvue_account_id
                  )
                ORDER BY created_at DESC""", (
                    customer.telegram_user_id, scenario_id,
                )).fetchall()
        if len(intents) != 1:
            raise RuntimeError(
                "SIMULATE_PURCHASE requires exactly one scenario-owned "
                "PRESENTED PurchaseIntent."
            )
        intent = intents[0]
        attempt = self.recovery.scenario_attempt(scenario_id)
        turns = self._current_attempt_turn_projections(scenario_id, attempt)
        matching_ppv = next((
            dict(turn.get("syntheticPpvPresentation") or {})
            for turn in reversed(turns)
            if str(dict(
                dict(turn.get("syntheticPpvPresentation") or {}).get(
                    "purchaseIntent"
                ) or {}
            ).get("id") or "") == str(intent["purchase_intent_id"])
        ), {})
        if not matching_ppv:
            raise RuntimeError(
                "SIMULATE_PURCHASE requires a canonically presented structured PPV."
            )
        eligibility = self.purchase_emulator_eligibility(
            scenario_id=scenario_id, turns=turns,
            purchase_intent_id=intent["purchase_intent_id"],
            purchase_intent_state="PRESENTED",
            telegram_commerce=(
                dict(intent.get("created_metadata") or {}).get("source")
                == "TELEGRAM_COMMERCE"
            ),
        )
        if not eligibility["simulatePurchaseEligible"]:
            raise RuntimeError(
                "SIMULATE_PURCHASE blocked: "
                + eligibility["simulatePurchaseEligibilityReason"]
            )
        before = self.builder.derived_state(scenario_id)
        result = SimulatedProviderPurchaseHarness(self.harness).confirm(
            scenario_id=scenario_id, purchase_intent_id=intent["purchase_intent_id"],
            amount_minor=int(intent["expected_price_minor"]),
            currency=str(intent["expected_currency"]),
        )
        after = self.builder.derived_state(scenario_id)
        return {"scenario": scenario_id, "provenance": result["provenance"],
                "purchaseIntentId": str(intent["purchase_intent_id"]),
                "before": before, "after": after, "fanvueCalled": False,
                "purchaseEmulatorAuthority": eligibility}

    def _turn_projection(self, evidence, changes):
        analysis = dict(evidence.get("SalesBrainFullAnalysis") or {})
        value = dict(evidence.get("customerValueAttention") or {})
        persona = dict(evidence.get("avaPersonaRuntime") or {})
        style = dict(evidence.get("styleDiagnostics") or {})
        return {
            "scenario": evidence["scenarioId"], "turnNumber": evidence["turnNumber"],
            "customer": evidence["inboundText"], "ava": evidence["finalResponseText"],
            "earlyInterestType": (
                self._early_interest_type(evidence["inboundText"])
                if evidence["scenarioId"] == "C06" else None
            ),
            "languageCertification": str(
                (evidence.get("syntheticProvider") or {}).get("syntheticProviderMode")
                or DETERMINISTIC_CERTIFICATION
            ),
            "systemLogic": {
                "decision": dict(analysis.get("finalSalesDecision") or {}).get("decision"),
                "reason": dict(analysis.get("finalSalesDecision") or {}).get("reasonCode"),
                "objection": analysis.get("objection"), "progression": analysis.get("salesProgression"),
                "receptiveness": analysis.get("commercialReceptiveness"),
                "offeringSelected": dict(analysis.get("inventorySelection") or {}).get("selectedOfferingId"),
                "purchaseIntent": evidence.get("PurchaseIntent"),
                "verifiedPurchase": dict(analysis.get("purchaseCommerceState") or {}).get("verifiedPurchase"),
                "activeSession": analysis.get("activeSession"),
            },
            "customerValue": value,
            "avaDiagnostics": {"persona": persona, "style": style,
                "responseWords": len(evidence["finalResponseText"].split()),
                "responseChars": len(evidence["finalResponseText"]),
                "memory": evidence.get("memoryDiagnostics")},
            "temporal": {"time": evidence.get("temporalContext"),
                "sleep": evidence.get("sleep")},
            "stateChangesThisTurn": changes,
            "testTransport": "TEST_TRANSPORT_NO_WAIT", "telegramSent": False,
            "syntheticPpvPresentation": evidence.get("syntheticPpvPresentation"),
            "syntheticProvider": evidence.get("syntheticProvider"),
            "fullAnalysis": analysis,
        }

    @staticmethod
    def _changes(before, after, evidence):
        changes = []
        for key in ("buyerStatus", "buyerStage", "valueTier", "retentionLifecycle",
                    "timeWasterRisk", "attentionTier", "effortMode", "commercialMomentum",
                    "purchaseCount", "ownershipCount", "activePurchaseIntent", "activeSession"):
            if before.get(key) != after.get(key):
                changes.append({"field": key, "before": before.get(key), "after": after.get(key)})
        progression = dict(evidence.get("SalesBrainFullAnalysis") or {}).get("salesProgression")
        if progression:
            changes.append({"field": "salesProgression", "after": progression})
        return changes or [{"field": "materialState", "after": "NO_MATERIAL_STATE_CHANGE"}]

    def _active(self, optional=False, required_state=None):
        terminal_lookup = required_state in TERMINAL_STATES
        states = [required_state] if terminal_lookup else list(EXECUTION_STATES)
        with self.harness.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM certification_scenario_runs WHERE state=ANY(%s) ORDER BY updated_at DESC",
                (states,),
            ).fetchall()
        if not rows:
            if optional: return None
            raise RuntimeError("No active scenario. Use PREPARE first.")
        if len(rows) != 1 and not terminal_lookup:
            raise RuntimeError("Multiple active scenarios exist; reset them before continuing.")
        row = rows[0]
        if required_state and row["state"] != required_state:
            raise RuntimeError(f"Scenario must be {required_state}; current state is {row['state']}.")
        return row

    def _inspectable(self, scenario_id: str):
        selected = str(scenario_id or "").strip().upper()
        if selected not in {item.scenario_id for item in SCENARIO_MANIFEST}:
            raise LookupError(f"Unknown scenario {selected or scenario_id}.")
        with self.harness.connection() as connection:
            row = connection.execute("""SELECT * FROM certification_scenario_runs
                WHERE scenario_id=%s AND state=ANY(%s)
                ORDER BY updated_at DESC LIMIT 1""", (
                selected, list(INSPECTABLE_STATES),
            )).fetchone()
        if row is None:
            raise LookupError(
                f"No inspectable RUNNING, COMPLETED, or SNAPSHOTTED attempt exists for {selected}."
            )
        return row

    def _target_scenario(self, scenario_id: str, *, required_state: str) -> str:
        """Resolve mutation authority only from an explicit scenario identity."""
        selected = str(scenario_id or "").strip().upper()
        if selected not in {item.scenario_id for item in SCENARIO_MANIFEST}:
            raise LookupError(f"Unknown scenario {selected or scenario_id}.")
        with self.harness.connection() as connection:
            row = connection.execute(
                "SELECT scenario_id,state FROM certification_scenario_runs "
                "WHERE scenario_id=%s FOR UPDATE",
                (selected,),
            ).fetchone()
        if row is None:
            raise LookupError(f"Scenario {selected} has no runtime state.")
        if row["state"] != required_state:
            raise RuntimeError(
                f"Scenario {selected} must be {required_state}; "
                f"current state is {row['state']}."
            )
        return selected

    def _latest_terminal(self):
        """Return historical evidence without assigning execution ownership."""
        with self.harness.connection() as connection:
            return connection.execute(
                """SELECT * FROM certification_scenario_runs
                   WHERE state=ANY(%s) ORDER BY updated_at DESC LIMIT 1""",
                (list(TERMINAL_STATES),),
            ).fetchone()

    def _run(self, scenario_id):
        with self.harness.connection() as connection:
            return connection.execute(
                "SELECT * FROM certification_scenario_runs WHERE scenario_id=%s", (scenario_id,)
            ).fetchone()

    def _latest_clean(self):
        with self.harness.connection() as connection:
            return connection.execute("""SELECT * FROM certification_scenario_runs
                WHERE state='VERIFIED_CLEAN' ORDER BY updated_at DESC LIMIT 1""").fetchone()

    def _turns(self, scenario_id):
        run = self._run(scenario_id)
        projections = self._current_attempt_turn_projections(
            scenario_id, int(run["scenario_attempt"] or 1) if run else 1,
        )
        if projections:
            unavailable = [item for item in projections if item["evidenceStatus"] != "MATCHED"]
            if unavailable:
                turn = unavailable[0]["logicalTurn"]
                raise RuntimeError(f"Current scenario Turn {turn} has no unambiguous evidence projection.")
            return [item["_evidenceRow"] for item in projections]
        with self.harness.connection() as connection:
            return connection.execute("""SELECT * FROM certification_scenario_turn_evidence
                WHERE scenario_id=%s ORDER BY created_at,correlation_id""", (scenario_id,)).fetchall()

    def _current_attempt_turn_projections(self, scenario_id: str,
                                          scenario_attempt: int) -> list[dict[str, Any]]:
        with self.harness.connection() as connection:
            attempts = connection.execute("""SELECT logical_turn,inbound,outbound
                ,turn_attempt,status,attempt_id,checkpoint_id,created_at,full_analysis,
                final_state,reason FROM certification_scenario_turn_attempts
                WHERE scenario_id=%s AND scenario_attempt=%s AND status='CURRENT'
                ORDER BY logical_turn""", (
                    scenario_id, scenario_attempt,
                )).fetchall()
            checkpoints = {str(row["checkpoint_id"]): row for row in connection.execute(
                """SELECT checkpoint_id,state,created_at FROM certification_scenario_checkpoints
                WHERE scenario_id=%s AND scenario_attempt=%s""",
                (scenario_id, scenario_attempt),
            ).fetchall()}
            evidence = connection.execute("""SELECT * FROM certification_scenario_turn_evidence
                WHERE scenario_id=%s ORDER BY created_at,correlation_id""", (scenario_id,)).fetchall()
        projections = []
        for attempt in attempts:
            logical_turn = int(attempt["logical_turn"])
            matches = []
            for row in evidence:
                rich = dict(row.get("full_analysis") or {})
                identity = dict(rich.get("scenarioTurnIdentity") or {})
                if identity:
                    matched_identity = (
                        identity.get("scenarioId") == scenario_id
                        and int(identity.get("scenarioAttempt") or -1) == scenario_attempt
                        and int(identity.get("logicalTurn") or -1) == logical_turn
                        and int(identity.get("turnAttempt") or -1)
                            == int(attempt["turn_attempt"])
                        and str(identity.get("correlationId") or "")
                            == str(row.get("correlation_id") or "")
                    )
                else:
                    # Historical attempts created before immutable turn identity
                    # remain inspectable through their original strict matcher.
                    matched_identity = int(dict(
                        rich.get("operatorResult") or {}
                    ).get("turnNumber", -1)) == logical_turn
                if (
                    matched_identity
                    and str(row.get("inbound") or "")
                        == str(attempt.get("inbound") or "")
                    and str(row.get("outbound") or "")
                        == str(attempt.get("outbound") or "")
                ):
                    matches.append(row)
            evidence_status = "MATCHED" if len(matches) == 1 else (
                "UNAVAILABLE" if not matches else "AMBIGUOUS"
            )
            matched = matches[0] if len(matches) == 1 else None
            rich = dict(matched["full_analysis"] or {}) if matched else {}
            checkpoint = checkpoints.get(str(attempt["checkpoint_id"]))
            projection = {
                "logicalTurn": logical_turn,
                "turnAttempt": int(attempt["turn_attempt"]),
                "status": attempt["status"],
                "attemptId": str(attempt["attempt_id"]),
                "checkpointId": str(attempt["checkpoint_id"]),
                "persistenceTimestamp": attempt["created_at"],
                "evidenceTimestamp": matched["created_at"] if matched else None,
                "evidenceStatus": evidence_status,
                "evidenceUnavailableReason": (
                    None if matched else
                    "No exact rich-evidence match for the canonical CURRENT ledger turn."
                    if not matches else
                    "Multiple exact rich-evidence matches; none attached."
                ),
                "customer": attempt["inbound"],
                "ava": attempt["outbound"],
                "canonicalScenarioName": self.harness.definition(scenario_id).name,
                "earlyInterestType": (
                    self._early_interest_type(attempt["inbound"])
                    if scenario_id == "C06" else None
                ),
                "preTurnState": dict(checkpoint["state"] or {}) if checkpoint else None,
                "finalState": dict(attempt["final_state"] or {}),
                "stateChanges": dict(rich.get("operatorResult") or {}).get(
                    "stateChangesThisTurn", []
                ),
                "salesBrainFullAnalysis": (
                    rich.get("SalesBrainFullAnalysis")
                    if matched else dict(attempt["full_analysis"] or {})
                ),
                "customerValueAttention": rich.get("customerValueAttention") if matched else None,
                "conversationInvestment": rich.get("conversationInvestment") if matched else None,
                "conversationalMemory": rich.get("conversationalMemory") if matched else None,
                "memoryDiagnostics": rich.get("memoryDiagnostics") if matched else None,
                "temporalContext": rich.get("temporalContext") if matched else None,
                "sleep": rich.get("sleep") if matched else None,
                "avaPersonaRuntime": rich.get("avaPersonaRuntime") if matched else None,
                "styleDiagnostics": rich.get("styleDiagnostics") if matched else None,
                "pacingCalculation": rich.get("pacingCalculation") if matched else None,
                "providerDraft": rich.get("providerDraft") if matched else None,
                "rewriteHistory": rich.get("rewriteHistory") if matched else None,
                "gatewayDiagnostics": rich.get("gatewayDiagnostics") if matched else None,
                "commerceAuthority": rich.get("commercialAuthority") if matched else None,
                "commerceDiagnostics": rich.get("commerceDiagnostics") if matched else None,
                "purchaseIntent": rich.get("PurchaseIntent") if matched else None,
                "syntheticPpvPresentation": (
                    rich.get("syntheticPpvPresentation") if matched else None
                ),
                "ownership": rich.get("ownership") if matched else None,
                "session": rich.get("Session") if matched else None,
                "syntheticProvider": rich.get("syntheticProvider") if matched else None,
                "behavior": rich.get("behavior") if matched else None,
                "adaptiveCustomer": (
                    rich.get("adaptiveCustomer")
                    if matched else dict(attempt["full_analysis"] or {}).get("adaptiveCustomer")
                ),
                "testTransportResult": rich.get("testTransportResult") if matched else None,
                "_evidenceRow": matched,
            }
            projections.append(projection)
        return projections

    def _defects(self, scenario_id):
        with self.harness.connection() as connection:
            return [dict(row) for row in connection.execute("""SELECT defect_id,turn_number,
                severity,note,created_at FROM certification_scenario_defects
                WHERE scenario_id=%s ORDER BY created_at,defect_id""", (scenario_id,)).fetchall()]

    def _bootstrap_ledger(self):
        with self.harness.connection() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS certification_scenario_defects(
                defect_id UUID PRIMARY KEY,scenario_id TEXT NOT NULL,turn_number INTEGER NOT NULL,
                severity TEXT NOT NULL CHECK(severity IN ('CRITICAL','MAJOR','QUALITY')),
                note TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
            connection.execute("""CREATE TABLE IF NOT EXISTS certification_scenario_assessments(
                scenario_id TEXT PRIMARY KEY,grade TEXT NOT NULL
                CHECK(grade IN ('PASS','PASS_WITH_NOTES','FAIL')),
                completed_at TIMESTAMPTZ NOT NULL)""")


def _parser():
    parser = argparse.ArgumentParser(prog="session5-scenario")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("LIST", "STATUS", "ANALYSIS",
                    "VERIFY_CLEAN", "SIMULATE_PURCHASE", "RUN_CANONICAL",
                    "RECOVER_STALE_EXECUTION"):
        sub.add_parser(command)
    for command in ("SNAPSHOT", "RESET"):
        targeted = sub.add_parser(command)
        targeted.add_argument("scenario")
    prepare = sub.add_parser("PREPARE"); prepare.add_argument("scenario")
    turn = sub.add_parser("TURN"); turn.add_argument("message", nargs="+")
    complete = sub.add_parser("COMPLETE"); complete.add_argument("grade")
    defect = sub.add_parser("DEFECT"); defect.add_argument("severity"); defect.add_argument("note", nargs="+")
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    runner = Session5ScenarioRunner()
    command = args.command
    result = {
        "LIST": runner.list, "STATUS": runner.status, "ANALYSIS": runner.analysis,
        "SNAPSHOT": lambda: runner.snapshot(args.scenario),
        "RESET": lambda: runner.reset(args.scenario),
        "VERIFY_CLEAN": runner.verify_clean, "SIMULATE_PURCHASE": runner.simulate_purchase,
        "RUN_CANONICAL": runner.execute_canonical,
        "RECOVER_STALE_EXECUTION": runner.recover_stale_execution,
        "PREPARE": lambda: runner.prepare(args.scenario),
        "TURN": lambda: runner.turn(" ".join(args.message)),
        "COMPLETE": lambda: runner.complete(args.grade),
        "DEFECT": lambda: runner.defect(args.severity, " ".join(args.note)),
    }[command]()
    print(json.dumps(result, indent=2, default=str, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({"error": type(error).__name__, "message": str(error)}), file=sys.stderr)
        raise SystemExit(2)
