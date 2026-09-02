"""Unify provider-backed economic truth with bounded attention intelligence."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
import re
from typing import Any, Mapping

from app.models.customer_value_attention import CustomerValueAttention


class CustomerValueAttentionService:
    """Pure projection. It never authorizes commerce or persists customer state."""

    HIGH_VALUE_GROSS_MINOR = 15_000
    WHALE_GROSS_MINOR = 50_000
    ACTIVE_PURCHASE_DAYS = 30
    COOLING_PURCHASE_DAYS = 90

    _DISCOVERY_DOMAINS = (
        ("pet", r"\b(?:dog|cat|pet|puppy|kitten|vet)\b"),
        ("music", r"\b(?:music|song|band|artist|concert|listening to)\b"),
        ("hobby_interest", r"\b(?:hobby|hiking|camping|fishing|guitar|outdoors?|trail|gaming|reading)\b"),
        ("event", r"\b(?:plans?|appointment|weekend|tomorrow|tonight|trip|going to)\b"),
        ("routine", r"\b(?:work|shift|finally home|long day|most nights|routine)\b"),
        ("location", r"\b(?:moved|live in|from|here in|city|town)\b"),
        ("personality_social_style", r"\b(?:quiet|shy|outgoing|introvert|extrovert|warm up)\b"),
        ("preferences", r"\b(?:favorite|i like|i love|i enjoy|i'm into|i am into|prefer)\b"),
    )

    def __init__(self):
        self.minimum_failed_paid_opportunities = self._configured_positive_int(
            "CUSTOMER_VALUE_MIN_FAILED_PAID_OPPORTUNITIES", 2
        )
        self.minimum_post_offer_sexual_turns = self._configured_positive_int(
            "CUSTOMER_VALUE_MIN_POST_OFFER_SEXUAL_TURNS", 2
        )

    def project(self, *, commerce_memory: Mapping[str, Any] | None = None,
                behavior: Mapping[str, Any] | None = None,
                legacy: Mapping[str, Any] | None = None,
                now: datetime | None = None) -> CustomerValueAttention:
        commerce = dict(commerce_memory or {})
        behavior = dict(behavior or {})
        legacy = dict(legacy or {})
        current = now or datetime.now(timezone.utc)

        canonical_available = any(key in commerce for key in (
            "verifiedPurchaseCount", "lifetimePurchaseCount", "purchaseCount",
            "lifetimeGrossMinor", "lifetimeSpendMinor", "lifetimeNetMinor",
            "schemaVersion", "activePurchaseState", "ownership",
        ))

        purchase_count = self._int(commerce.get(
            "verifiedPurchaseCount", commerce.get(
                "lifetimePurchaseCount", commerce.get("purchaseCount", 0)
            )
        ))
        gross = self._int(commerce.get(
            "lifetimeGrossMinor", commerce.get("lifetimeSpendMinor")
        ))
        net = self._int(commerce.get("lifetimeNetMinor"))
        average_order = self._int(commerce.get("averageOrderValueMinor"))
        largest_order = self._int(commerce.get("largestOrderMinor"))
        affinity = dict(commerce.get("affinity") or {})
        last_purchase = commerce.get("lastPurchaseAt")
        recency = (
            float(commerce["purchaseRecencyDays"])
            if commerce.get("purchaseRecencyDays") is not None
            else self._days_since(last_purchase, current)
        )
        active_intent = bool(
            behavior.get("active_purchase_intent")
            or dict(commerce.get("activePurchaseState") or {}).get("purchaseIntentId")
        )
        active_session = bool(behavior.get("active_session") or behavior.get("sales_session_id"))
        commercial_interest_type = str(
            behavior.get("commercial_interest_type") or "NONE"
        ).upper()
        meaningful_commercial_interest = commercial_interest_type != "NONE"
        direct = bool(behavior.get("direct_buying_intent") or behavior.get("fresh_direct_intent"))
        sexual_only = bool(behavior.get("sexual_engagement_only")) and not direct
        progression = str(behavior.get("sales_progression_phase") or "CONVERSATIONAL").upper()
        backoff = bool(behavior.get("back_off")) or progression == "BACK_OFF"
        message_count = self._int(behavior.get("inbound_message_count", behavior.get("message_count")))
        offer_count = self._int(behavior.get("offer_exposure_count", behavior.get("offers_shown_count")))
        proactive_tease_count = self._int(behavior.get("proactive_tease_delivered_count"))
        commercial_tease_count = self._int(
            behavior.get("commercial_tease_exposure_count", proactive_tease_count)
        )
        build_interest_count = self._int(behavior.get("build_interest_exposure_count"))
        customer_commercial_response_count = self._int(
            behavior.get("customer_commercial_response_count")
        )
        presented_count = self._int(
            behavior.get("presented_opportunity_count", offer_count)
        )
        failed_count = self._int(
            behavior.get("failed_nonconverted_opportunity_count", 0)
        )
        converted_opportunity_count = self._int(
            behavior.get("converted_opportunity_count", purchase_count)
        )
        active_unresolved_opportunity = bool(
            behavior.get("active_unresolved_opportunity")
        )
        nurture_budget = 1
        nurture_used = self._int(behavior.get("nurture_response_count_rolling_day"))
        last_nurture_response = behavior.get("last_nurture_response_at")
        opportunity_count = (
            commercial_tease_count + build_interest_count + presented_count
        )
        rejection_count = self._int(behavior.get("rejection_count", behavior.get("recovery_attempt_count")))
        low_information_count = self._int(behavior.get("low_information_response_count"))
        idle_browsing_count = self._int(behavior.get("idle_browsing_signal_count"))
        explicit_nonpayment = bool(behavior.get("explicit_nonpayment_detected"))
        browsing_only = bool(behavior.get("browsing_only_detected"))
        meaningful_engagement_count = self._int(behavior.get("meaningful_engagement_count"))
        low_return_count = self._int(
            behavior.get("low_conversational_return_count")
        )
        post_offer_sexual_count = self._int(
            behavior.get("post_offer_sexual_engagement_count")
        )
        hostility_level = str(behavior.get("hostility_level") or "NONE").upper()
        repeated_hostility = bool(behavior.get("repeated_hostility"))
        explicit_disengagement = bool(behavior.get("explicit_disengagement"))
        historical_commercial_interest = bool(
            behavior.get("commercial_movement")
            or self._int(behavior.get("commercial_movement_count")) > 0
        )
        current_commercial_interest = bool(
            direct or meaningful_commercial_interest
            or behavior.get("price_question") or behavior.get("content_request")
        ) and not explicit_nonpayment and not browsing_only
        meaningful = current_commercial_interest
        trajectory_decay = bool(
            failed_count >= self.minimum_failed_paid_opportunities
            and (explicit_nonpayment or browsing_only)
            and (rejection_count >= 2 or idle_browsing_count >= 2)
            and not active_unresolved_opportunity
        )
        opportunity_basis = presented_count > 0
        conversational_low_return = bool(
            purchase_count == 0
            and message_count >= 6
            and low_return_count >= 4
            and meaningful_engagement_count <= 1
            and not direct
            and not active_session
            and not sexual_only
            and not behavior.get("commercial_movement")
            and not behavior.get("price_question")
            and not behavior.get("content_request")
        )

        canonical = ["PROVIDER_PURCHASE_COUNT", "PROVIDER_LIFETIME_SPEND",
                     "PROVIDER_PURCHASE_RECENCY", "CANONICAL_OWNERSHIP_AFFINITY"]
        conflicts, legacy_used = [], []
        legacy_buyer = str(legacy.get("user_value_tier") or legacy.get("valueTier") or "").lower()
        legacy_whale = bool(legacy.get("is_whale")) or legacy_buyer == "whale"
        if not canonical_available:
            canonical = []
            legacy_used.append("LEGACY_FALLBACK_NO_CANONICAL_COMMERCE")
            purchase_count = self._int(behavior.get(
                "purchase_count", legacy.get("purchase_count")
            ))
            gross = self._int(behavior.get(
                "total_spend_cents", behavior.get(
                    "lifetime_spend_minor", legacy.get("lifetime_spend_minor")
                )
            ))
            if purchase_count == 0 and legacy_buyer in {"buyer", "high", "whale"}:
                purchase_count = 1
            if legacy_whale and gross < self.WHALE_GROSS_MINOR:
                gross = self.WHALE_GROSS_MINOR
            elif legacy_buyer == "high" and gross < self.HIGH_VALUE_GROSS_MINOR:
                gross = self.HIGH_VALUE_GROSS_MINOR
        if canonical_available and purchase_count == 0 and legacy_buyer in {"buyer", "high", "whale"}:
            conflicts.append("LEGACY_BUYER_STATUS_REJECTED_WITHOUT_PROVIDER_PURCHASE")
        if canonical_available and purchase_count > 0 and legacy_buyer in {"", "cold", "warm"}:
            conflicts.append("PROVIDER_BUYER_STATUS_OVERRIDES_LEGACY_NONBUYER")
        if canonical_available and legacy_whale and gross < self.WHALE_GROSS_MINOR:
            conflicts.append("PROVIDER_SPEND_OVERRIDES_LEGACY_WHALE_FLAG")

        if purchase_count <= 0:
            buyer_status, buyer_stage = "NONBUYER", "PROSPECT"
        elif purchase_count == 1:
            buyer_status, buyer_stage = (
                "VERIFIED_BUYER" if canonical_available else "LEGACY_BUYER_UNVERIFIED",
                "FIRST_TIME_BUYER",
            )
        else:
            buyer_status, buyer_stage = (
                "VERIFIED_BUYER" if canonical_available else "LEGACY_BUYER_UNVERIFIED",
                "REPEAT_BUYER",
            )

        if purchase_count and gross >= self.WHALE_GROSS_MINOR:
            value_tier, buyer_stage = "WHALE", "HIGH_VALUE_BUYER"
        elif purchase_count and gross >= self.HIGH_VALUE_GROSS_MINOR:
            value_tier, buyer_stage = "HIGH_VALUE", "HIGH_VALUE_BUYER"
        elif purchase_count >= 2:
            value_tier = "REPEAT_BUYER"
        elif purchase_count == 1:
            value_tier = "BUYER"
        else:
            value_tier = "ENGAGED_PROSPECT" if (
                meaningful or historical_commercial_interest
                or meaningful_engagement_count >= 2
                or sexual_only or active_session
            ) else "PROSPECT"

        if not purchase_count:
            lifecycle = "NOT_A_BUYER"
        elif recency is None or recency <= self.ACTIVE_PURCHASE_DAYS:
            lifecycle = "ACTIVE_BUYER"
        elif recency <= self.COOLING_PURCHASE_DAYS:
            lifecycle = "COOLING_BUYER"
        else:
            lifecycle = "DORMANT_BUYER"
        current_inbound_activity = bool(
            behavior.get("current_inbound_activity")
            or behavior.get("reactivation_activity")
        )
        if lifecycle == "DORMANT_BUYER" and current_inbound_activity:
            reactivation_state = "REACTIVATED_BUYER"
        elif lifecycle == "DORMANT_BUYER":
            reactivation_state = "DORMANT"
        elif purchase_count:
            reactivation_state = "ACTIVE_OR_COOLING"
        else:
            reactivation_state = "NOT_APPLICABLE"

        risk_score, evidence = 0, []
        repeated_failure_basis = (
            failed_count >= self.minimum_failed_paid_opportunities
        )
        if purchase_count == 0 and message_count >= 10 and repeated_failure_basis:
            risk_score += 2; evidence.append("HIGH_CHAT_VOLUME_NO_VERIFIED_PURCHASE")
        if purchase_count == 0 and repeated_failure_basis:
            risk_score += 2; evidence.append("MULTIPLE_OFFERS_NO_CONVERSION")
        if (purchase_count == 0
                and repeated_failure_basis
                and post_offer_sexual_count >= self.minimum_post_offer_sexual_turns):
            risk_score += 2
            evidence.append("REPEATED_POST_OFFER_SEXUAL_CONSUMPTION_NO_CONVERSION")
        if rejection_count >= 2 and repeated_failure_basis:
            risk_score += 2; evidence.append("REPEATED_COMMERCIAL_REJECTION")
        if sexual_only and message_count >= 6 and repeated_failure_basis:
            risk_score += 2; evidence.append("SEXUAL_ENGAGEMENT_WITHOUT_BUYING_MOVEMENT")
        if (purchase_count == 0 and message_count >= 8 and not meaningful
                and repeated_failure_basis):
            risk_score += 2; evidence.append("PERSISTENT_CHAT_WITHOUT_COMMERCIAL_MOVEMENT")
        quiet_accumulated = bool(
            purchase_count == 0 and not meaningful
            and low_information_count >= 3
            and meaningful_engagement_count == 0
        )
        if quiet_accumulated and repeated_failure_basis:
            risk_score += 4
            evidence.append("ACCUMULATED_LOW_INFORMATION_LOW_RECIPROCITY")
        if idle_browsing_count >= 2 and not meaningful and repeated_failure_basis:
            risk_score += 2
            evidence.append("REPEATED_IDLE_BROWSING_SIGNAL")
        # Hostility is a conversational-attention signal, not proof of failed
        # commerce. Keep commercial time-waster attribution opportunity-backed.
        legacy_flags = tuple(legacy.get("timewaster_flags") or legacy.get("timeWasterEvidence") or ())
        if legacy_flags:
            legacy_used.append("LEGACY_TIME_WASTER_FLAGS")
            evidence.extend(str(value) for value in legacy_flags)
            risk_score += min(2, len(legacy_flags))
        trajectory_protection = bool(
            meaningful and not trajectory_decay
        )
        if trajectory_protection:
            risk_score -= 3
            evidence.append("CURRENT_MEANINGFUL_COMMERCIAL_TRAJECTORY_PROTECTION")
        elif historical_commercial_interest and trajectory_decay:
            evidence.append("HISTORICAL_COMMERCIAL_TRAJECTORY_DECAYED_BY_CURRENT_NONPAYMENT")
        if active_session:
            risk_score -= 4; evidence.append("ACTIVE_SESSION_PROTECTION")
        if active_unresolved_opportunity:
            risk_score -= 3
            evidence.append("ACTIVE_UNRESOLVED_OPPORTUNITY_PROTECTION")
        if purchase_count:
            risk_score -= 2 if purchase_count == 1 else 3
            evidence.append("VERIFIED_BUYER_PROTECTION")
        risk_score = max(0, risk_score)
        risk = "HIGH" if risk_score >= 6 else "MEDIUM" if risk_score >= 4 else "LOW" if risk_score >= 2 else "NONE"
        if purchase_count and not explicit_disengagement and risk in {"HIGH", "MEDIUM"}:
            risk = "LOW"
            evidence.append("VERIFIED_BUYER_TIME_WASTER_RISK_CAPPED")
        if purchase_count == 0 and risk == "HIGH":
            value_tier = "LOW_VALUE_PROSPECT"

        low_cost_eligible = bool(
            purchase_count == 0
            and repeated_failure_basis
            and (
                risk == "HIGH"
                or (direct and message_count >= 10)
            )
        )
        nurture_bypass = bool(
            low_cost_eligible and (direct or meaningful_commercial_interest)
        )
        low_cost_active = bool(
            low_cost_eligible
            and not nurture_bypass
            and not active_intent
            and not active_session
            and not active_unresolved_opportunity
        )
        optional_reply_suppressed = bool(
            low_cost_active and nurture_used >= nurture_budget
        )
        nurture_next_at = None
        parsed_last_nurture = self._datetime(last_nurture_response)
        if optional_reply_suppressed and parsed_last_nurture is not None:
            nurture_next_at = (
                parsed_last_nurture + timedelta(hours=24)
            ).astimezone(timezone.utc).isoformat()
        nurture_exited_after_purchase = bool(
            purchase_count > 0 and failed_count >= self.minimum_failed_paid_opportunities
        )

        buyer_protection = canonical_available and purchase_count > 0
        if value_tier == "WHALE":
            retention, attention, effort = "VIP", "HIGH", "FULL"
        elif value_tier == "HIGH_VALUE":
            retention, attention, effort = "HIGH", "HIGH", "FULL"
        elif purchase_count >= 2:
            retention, attention, effort = "ELEVATED", "HIGH", "FULL"
        elif purchase_count == 1:
            retention, attention, effort = "NORMAL", "MEDIUM", "BALANCED"
        elif risk == "HIGH":
            retention, attention, effort = "NONE", "LOW", "MINIMAL"
        elif risk == "MEDIUM":
            retention, attention, effort = "NONE", "LOW", "COMPRESSED"
        elif meaningful:
            retention, attention, effort = "NONE", "HIGH", "BALANCED"
        else:
            retention, attention, effort = "NONE", "MEDIUM", "BALANCED"

        # Buyer protection is meaningful, not unlimited. Repeated post-purchase
        # rejection can taper a normal buyer, while high-value history remains protected.
        if purchase_count and rejection_count >= 3 and not direct and not active_session:
            attention = "MEDIUM"
            effort = "BALANCED" if value_tier in {"HIGH_VALUE", "WHALE"} else "COMPRESSED"
            evidence.append("BUYER_REPEATED_NONCONVERSION_TAPER")
        if explicit_disengagement:
            attention = "LOW"
            effort = "MINIMAL"
            evidence.append("HARD_BOUNDARY_OVERRIDES_RELATIONSHIP_VALUE")
        elif purchase_count == 0 and (
            repeated_hostility or hostility_level in {"HIGH", "SEVERE"}
        ):
            attention = "LOW"
            effort = "COMPRESSED"
            evidence.append("CONTEXTUAL_HOSTILITY_REDUCED_CONVERSATIONAL_INVESTMENT")
        elif conversational_low_return and risk == "NONE":
            # Conversational investment is independent of commercial time-waster
            # attribution. Quiet prospects remain welcome and answerable, while
            # sustained low return stops forcing Ava to manufacture momentum.
            attention = "LOW"
            effort = "COMPRESSED"

        if value_tier == "WHALE":
            relationship_investment, memory_priority = "HIGHEST", "HIGHEST"
            sales_pressure, offer_cadence = "LOW", "CAREFUL_PREMIUM"
        elif value_tier == "HIGH_VALUE":
            relationship_investment, memory_priority = "HIGH", "HIGH"
            sales_pressure, offer_cadence = "LOW", "CAREFUL"
        elif purchase_count >= 2:
            relationship_investment, memory_priority = "ELEVATED", "HIGH"
            sales_pressure, offer_cadence = "NORMAL", "RESPONSIVE"
        elif purchase_count == 1:
            relationship_investment, memory_priority = "WARM", "ELEVATED"
            sales_pressure, offer_cadence = "LOW", "POST_PURCHASE_CAREFUL"
        else:
            relationship_investment, memory_priority = "STANDARD", "STANDARD"
            sales_pressure, offer_cadence = "NORMAL", "PROSPECT"
        if lifecycle == "DORMANT_BUYER":
            relationship_investment = max(
                relationship_investment, "WARM",
                key=("STANDARD", "WARM", "ELEVATED", "HIGH", "HIGHEST").index,
            )
            sales_pressure = "LOW"
            offer_cadence = "REENGAGEMENT_CAREFUL"

        taper = effort in {"COMPRESSED", "MINIMAL"}
        hostility_reduced_investment = bool(
            explicit_disengagement
            or (purchase_count == 0 and (
                repeated_hostility or hostility_level in {"HIGH", "SEVERE"}
            ))
        )
        continuation = "HIGH" if active_session or direct or value_tier in {"HIGH_VALUE", "WHALE"} else (
            "LOW" if risk == "HIGH" or conversational_low_return
            or hostility_reduced_investment else "MEDIUM"
        )
        pressure = "LOW" if backoff else "ELEVATED" if direct or (
            sexual_only and risk in {"MEDIUM", "HIGH"}
        ) else "NORMAL"
        momentum = "HOT" if direct or active_session else "WARM" if meaningful else "COOLING" if backoff else "COLD"

        relationship_discovery = self._relationship_discovery(
            behavior=behavior,
            buyer_status=buyer_status,
            buyer_stage=buyer_stage,
            attention_tier=attention,
            effort_mode=effort,
            relationship_investment=relationship_investment,
            memory_priority=memory_priority,
            time_waster_risk=risk,
            conversational_low_return=conversational_low_return,
            repeated_hostility=repeated_hostility,
            explicit_disengagement=explicit_disengagement,
            active_intent=active_intent,
            active_session=active_session,
            backoff=backoff,
            direct=direct,
        )

        if legacy.get("attention_tier") or legacy.get("attentionTier"):
            legacy_used.append("LEGACY_ATTENTION_SCORE")
        compatibility = {
            "attention_tier": attention.lower(),
            "effort_mode": effort.lower(),
            "user_value_tier": value_tier.lower(),
            "is_whale": value_tier == "WHALE",
            "timewaster_flags": list(dict.fromkeys(evidence)),
        }
        return CustomerValueAttention(
            value_authority=(
                "COMMERCE_BACKED_AUTHORITATIVE_VALUE"
                if canonical_available else "LEGACY_COMPATIBILITY_FALLBACK"
            ),
            buyer_status=buyer_status, buyer_stage=buyer_stage, value_tier=value_tier,
            retention_lifecycle=lifecycle, retention_priority=retention,
            lifetime_spend_minor=gross, average_order_value_minor=average_order,
            largest_order_minor=largest_order, purchase_count=purchase_count,
            last_purchase_at=self._iso(last_purchase),
            purchase_recency_days=recency,
            reactivation_state=reactivation_state,
            commercial_momentum=momentum,
            attention_tier=attention, effort_mode=effort, time_waster_risk=risk,
            time_waster_evidence=tuple(dict.fromkeys(evidence)),
            commercial_opportunity_exposure_count=opportunity_count,
            presented_opportunity_count=presented_count,
            failed_nonconverted_opportunity_count=failed_count,
            converted_opportunity_count=converted_opportunity_count,
            active_unresolved_opportunity=active_unresolved_opportunity,
            proactive_tease_delivered_count=proactive_tease_count,
            build_interest_exposure_count=build_interest_count,
            offer_exposure_count=offer_count,
            customer_commercial_response_count=customer_commercial_response_count,
            time_waster_opportunity_basis=opportunity_basis,
            buyer_protection_applied=buyer_protection,
            buyer_protection_reason=("PROVIDER_VERIFIED_PURCHASE_HISTORY" if buyer_protection else None),
            low_cost_nurture_eligible=low_cost_eligible,
            low_cost_nurture_active=low_cost_active,
            low_cost_nurture_reason=(
                "REPEATED_PROVEN_NONCONVERSION"
                if low_cost_eligible else None
            ),
            nurture_response_budget=nurture_budget,
            nurture_responses_used=nurture_used,
            nurture_next_optional_response_at=nurture_next_at,
            optional_ordinary_reply_suppressed=optional_reply_suppressed,
            suppression_reason=(
                "LOW_COST_NURTURE_DAILY_BUDGET_CONSUMED"
                if optional_reply_suppressed else None
            ),
            fresh_commercial_intent_detected=direct,
            nurture_bypassed_for_commercial_intent=nurture_bypass,
            nurture_exited_after_purchase=nurture_exited_after_purchase,
            commercial_interest_type=commercial_interest_type,
            conversation_continuation_value=continuation,
            commercial_progression_pressure=pressure, taper_applied=taper,
            taper_reason=(
                "EXPLICIT_CUSTOMER_DISENGAGEMENT"
                if explicit_disengagement
                else "SUSTAINED_CONTEXTUAL_DISRESPECT"
                if hostility_reduced_investment
                else "SUSTAINED_LOW_CONVERSATIONAL_RETURN"
                if conversational_low_return
                else "PERSISTENT_NONCONVERSION_REDUCED_INVESTMENT" if taper
                else None
            ),
            relationship_investment=relationship_investment,
            memory_priority=memory_priority,
            sales_pressure=sales_pressure,
            offer_cadence=offer_cadence,
            current_commercial_interest=current_commercial_interest,
            historical_commercial_interest=historical_commercial_interest,
            commercial_trajectory_protection_active=trajectory_protection,
            commercial_trajectory_protection_reason=(
                "CURRENT_ACTIONABLE_COMMERCIAL_EVIDENCE"
                if trajectory_protection else None
            ),
            commercial_trajectory_decay_reason=(
                "REPEATED_TERMINAL_NONCONVERSION_AND_CURRENT_NONPAYMENT"
                if trajectory_decay else None
            ),
            explicit_nonpayment_detected=explicit_nonpayment,
            browsing_only_detected=browsing_only,
            time_waster_score=risk_score,
            relationship_discovery=relationship_discovery,
            offering_type_affinity=dict(affinity.get("offeringTypes") or {}),
            content_affinity=dict(affinity.get("tags") or {}),
            price_affinity={
                "typicalPriceMinMinor": affinity.get("typicalPriceMinMinor"),
                "typicalPriceMaxMinor": affinity.get("typicalPriceMaxMinor"),
            },
            canonical_signals_consumed=tuple(canonical),
            legacy_signals_consumed=tuple(dict.fromkeys(legacy_used)),
            conflict_resolution=tuple(conflicts),
            reason=self._reason(value_tier, risk, meaningful, lifecycle),
            compatibility=compatibility,
        )

    @classmethod
    def _relationship_discovery(
        cls, *, behavior, buyer_status, buyer_stage, attention_tier, effort_mode,
        relationship_investment, memory_priority, time_waster_risk,
        conversational_low_return, repeated_hostility, explicit_disengagement,
        active_intent, active_session, backoff, direct,
    ) -> dict[str, Any]:
        """Authorize, but never generate or persist, one contextual question."""
        message = str(behavior.get("latest_message") or "").strip()
        known_domains = {
            str(value).strip().lower()
            for value in behavior.get("known_memory_domains") or () if str(value).strip()
        }
        suggested = next((
            domain for domain, pattern in cls._DISCOVERY_DOMAINS
            if re.search(pattern, message, re.I)
        ), None)
        contextual_opening = bool(suggested and re.search(
            r"\b(?:i|i'm|i am|i've|i have|my|me|finally|just got|been)\b",
            message, re.I,
        ))
        already_known = bool(suggested and suggested in known_domains)
        previous_ava = str(behavior.get("previous_ava_message") or "")
        previous_domain = next((
            domain for domain, pattern in cls._DISCOVERY_DOMAINS
            if "?" in previous_ava and re.search(pattern, previous_ava, re.I)
        ), None)
        written_categories = {
            str(item.get("category") or "").lower()
            for item in behavior.get("memory_written_this_turn") or ()
            if isinstance(item, Mapping)
        }
        category_domains = {
            "pet": "pet", "entity": "pet", "hobby": "hobby_interest",
            "interest": "hobby_interest", "routine": "routine",
            "event": "event", "trait": "personality_social_style",
            "fact": "location", "preference": "preferences",
        }
        learned_domains = {
            category_domains[value] for value in written_categories
            if value in category_domains
        }
        customer_answered_discovery = bool(
            previous_domain and previous_domain in learned_domains
        )
        question_pressure = max(
            cls._int(behavior.get("question_streak")),
            cls._int(behavior.get("recent_question_count")) - 1,
        )
        commercial_action = str(behavior.get("commercial_action") or "").upper()
        acknowledgement = bool(behavior.get("purchase_acknowledgement_pending"))
        safety_action = bool(behavior.get("safety_action"))
        suppression = None
        if safety_action:
            suppression = "SAFETY_ACTION_AUTHORITATIVE"
        elif acknowledgement:
            suppression = "PURCHASE_ACKNOWLEDGEMENT_AUTHORITATIVE"
        elif backoff or commercial_action == "BACK_OFF":
            suppression = "BACK_OFF_AUTHORITATIVE"
        elif direct or commercial_action in {
            "PRESENT_OFFER", "PRESENT_ALTERNATIVE_OFFER", "UPSELL", "CROSS_SELL",
            "DELIVER_PURCHASE", "NUDGE_ACTIVE_OFFER",
        }:
            suppression = "COMMERCIAL_ACTION_AUTHORITATIVE"
        elif active_session:
            suppression = "ACTIVE_SALES_SESSION_AUTHORITATIVE"
        elif active_intent:
            suppression = "ACTIVE_PURCHASE_INTENT_AUTHORITATIVE"
        elif explicit_disengagement:
            suppression = "EXPLICIT_DISENGAGEMENT"
        elif repeated_hostility:
            suppression = "SUSTAINED_DISRESPECT"
        elif time_waster_risk == "HIGH":
            suppression = "GENUINE_COMMERCIAL_TIME_WASTER"
        elif effort_mode in {"MINIMAL", "COMPRESSED"}:
            suppression = f"{effort_mode}_EFFORT"
        elif conversational_low_return:
            suppression = "SUSTAINED_LOW_CONVERSATIONAL_RETURN"
        elif question_pressure >= 2:
            suppression = "QUESTION_PRESSURE"
        elif not contextual_opening:
            suppression = "NO_CONTEXTUAL_OPENING"
        elif already_known:
            suppression = "DOMAIN_ALREADY_KNOWN"

        allowed = suppression is None
        if allowed and buyer_status == "VERIFIED_BUYER":
            reason = "VALUABLE_CONTEXTUAL_BUYER_RELATIONSHIP_DISCOVERY"
        elif allowed:
            reason = "VALUABLE_CONTEXTUAL_RELATIONSHIP_DISCOVERY"
        else:
            reason = "RELATIONSHIP_DISCOVERY_SUPPRESSED"
        value_level = (
            "HIGH" if allowed and (
                buyer_status == "VERIFIED_BUYER"
                or relationship_investment in {"ELEVATED", "HIGH", "HIGHEST"}
                or memory_priority in {"ELEVATED", "HIGH", "HIGHEST"}
            ) else "MEDIUM" if allowed else "NONE"
        )
        return {
            "allowed": allowed,
            "reason": reason,
            "valueLevel": value_level,
            "suggestedDomain": suggested,
            "contextualOpening": contextual_opening,
            "alreadyKnown": already_known,
            "suppressionReason": suppression,
            "buyerStage": buyer_stage,
            "attentionTier": attention_tier,
            "effortMode": effort_mode,
            "questionPressure": question_pressure,
            "knownMemoryDomains": sorted(known_domains),
            "customerAnsweredDiscovery": customer_answered_discovery,
            "memoryLearnedFromAnswer": customer_answered_discovery,
            "authority": "CustomerValueAttentionService",
            "perTurn": True,
        }

    @staticmethod
    def _int(value) -> int:
        try: return max(0, int(value or 0))
        except (TypeError, ValueError): return 0

    @staticmethod
    def _configured_positive_int(name, default):
        try: return max(1, int(os.getenv(name, str(default))))
        except (TypeError, ValueError): return default

    @staticmethod
    def _days_since(value, now) -> float | None:
        if not value: return None
        try:
            parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None: parsed = parsed.replace(tzinfo=timezone.utc)
            return round(max(0.0, (now.astimezone(timezone.utc)-parsed.astimezone(timezone.utc)).total_seconds()/86400), 2)
        except (TypeError, ValueError): return None

    @staticmethod
    def _iso(value) -> str | None:
        if value is None:
            return None
        return value.isoformat() if isinstance(value, datetime) else str(value)

    @staticmethod
    def _datetime(value) -> datetime | None:
        if value is None:
            return None
        try:
            parsed = value if isinstance(value, datetime) else datetime.fromisoformat(
                str(value).replace("Z", "+00:00")
            )
            return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _reason(value_tier, risk, meaningful, lifecycle):
        return f"provider_value={value_tier}; retention={lifecycle}; trajectory={'meaningful' if meaningful else 'limited'}; time_waster_risk={risk}"
