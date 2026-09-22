"""Read-only operator projection over canonical PPV and Sales Brain evidence."""
from __future__ import annotations


class PPVEscalationProjectionService:
    """Collapse existing authorities into one display stage without persisting state."""

    COMMERCIAL_SIGNALS = frozenset({
        "COMMERCIAL_CURIOSITY", "OFFERING_AVAILABILITY_INQUIRY", "PRICE_REQUEST",
        "DIRECT_CONTENT_INTENT", "SEND_OR_LINK_REQUEST", "PURCHASE_ACCEPTANCE",
    })
    ACTIVE_INTENT_STATES = frozenset({"PRESENTED", "CLICKED"})
    PROACTIVE_REQUIREMENTS = (
        ("SUSTAINED_VOLUNTARY_CONVERSATION", "Sustained Conversation"),
        ("MEANINGFUL_ENGAGEMENT", "Meaningful Engagement"),
        ("VOLUNTARY_SELF_DISCLOSURE", "Voluntary Self-Disclosure"),
        ("RECIPROCAL_RELATIONAL_WARMING", "Reciprocal Warming"),
        ("NO_OFFER_EXPOSURE", "No Prior Offer Exposure"),
    )

    @staticmethod
    def _mapping(value):
        return dict(value) if isinstance(value, dict) else {}

    @staticmethod
    def _upper(value, default="NONE"):
        text = str(value or default).strip().upper()
        return text or default

    def project(self, *, mapped: bool, verified_purchase_count: int | None,
                intents=(), latest_diagnostics=None, messages_since_last_offer=None,
                follow_through=None, commercial_reentry: bool = False,
                sexual_receptiveness_threshold: int = 4):
        diagnostics = self._mapping(latest_diagnostics)
        value = self._mapping(diagnostics.get("customer_value_attention"))
        receptiveness = self._mapping(
            diagnostics.get("commercial_receptiveness")
            or diagnostics.get("commercialReceptiveness"))
        commerce = self._mapping(diagnostics.get("commerce_decision"))
        proactive = self._mapping(
            commerce.get("proactiveProgression")
            or commerce.get("proactive_progression")
            or diagnostics.get("proactive_progression"))
        hot = self._mapping(
            commerce.get("proactiveHotOpportunity")
            or commerce.get("proactive_hot_opportunity")
            or diagnostics.get("proactiveHotOpportunity")
            or diagnostics.get("proactive_hot_opportunity"))
        sexual = self._mapping(
            diagnostics.get("sexual_commercial_progression")
            or diagnostics.get("sexualCommercialProgression"))
        commercial_summary = self._mapping(diagnostics.get("commercial_summary"))
        summary_sexual = self._mapping(
            commercial_summary.get("sexualCommercialProgression"))

        signal = self._upper(
            receptiveness.get("commercialInterestType")
            or value.get("commercialInterestType"))
        fresh_intent = bool(
            receptiveness.get("freshCommercialIntentDetected")
            or receptiveness.get("freshDirectIntentDetected")
            or receptiveness.get("freshDirectIntent")
            or value.get("freshCommercialIntentDetected"))
        sales_decision = self._upper(
            commerce.get("decision") or diagnostics.get("sales_brain_decision"), "UNKNOWN")
        sales_reason = self._upper(
            commerce.get("reason") or commerce.get("reason_code")
            or diagnostics.get("customer_sales_reason_code")
            or diagnostics.get("sales_brain_reason"), "UNKNOWN")
        recommendation = self._mapping(
            commerce.get("recommendation") or commerce.get("offeringSelectorResult")
            or diagnostics.get("offering_selection"))
        selected = bool(
            recommendation.get("selected") or recommendation.get("offeringId")
            or recommendation.get("offering_id") or commerce.get("recommended_offering_id")
            or diagnostics.get("offering_selected")
            or diagnostics.get("authoritative_offering_selected"))

        intent_rows = tuple(self._mapping(item) for item in (intents or ()))
        active = next((item for item in intent_rows if self._upper(item.get("status"))
                       in {"CREATED", "PRESENTED", "CLICKED"}), None)
        presented = tuple(item for item in intent_rows
                          if item.get("presented_at") is not None
                          and item.get("confirmed_delivery") is True)
        last_offer = presented[0] if presented else None
        follow = self._mapping(follow_through)
        conversation_policy = self._mapping(follow.get("conversation_policy"))
        follow_available = bool(follow.get("available"))
        nudge_sent = follow_available and bool(follow.get("confirmed_nudge"))
        follow_eligible = follow_available and bool(follow.get("eligible"))
        backoff = follow_available and bool(follow.get("backoff"))
        purchased = bool(mapped and verified_purchase_count is not None
                         and int(verified_purchase_count) > 0)

        if purchased:
            stage, action = "PURCHASED", "RETAIN_BUYER"
        elif backoff and (fresh_intent or commercial_reentry):
            stage, action = "COMMERCIAL_RE_ENTRY", "COMMERCIAL_EVALUATION"
        elif backoff and not fresh_intent and not commercial_reentry:
            stage, action = "BACKOFF", "BACK_OFF"
        elif nudge_sent:
            stage, action = "NUDGE_SENT", "AWAIT_PURCHASE"
        elif follow_eligible:
            stage, action = "FOLLOW_UP_ELIGIBLE", "NUDGE"
        elif active and self._upper(active.get("status")) in self.ACTIVE_INTENT_STATES:
            stage, action = "AWAITING_PURCHASE", "AWAIT_PURCHASE"
        elif last_offer:
            stage, action = "OFFER_PRESENTED", "AWAIT_PURCHASE"
        elif sales_decision == "PRESENT_OFFER" and selected:
            stage, action = "READY_TO_OFFER", "PRESENT_OFFER"
        elif commercial_reentry:
            stage, action = "COMMERCIAL_RE_ENTRY", "COMMERCIAL_EVALUATION"
        elif signal in self.COMMERCIAL_SIGNALS or fresh_intent:
            stage, action = "COMMERCIAL_INTEREST", "COMMERCIAL_EVALUATION"
        elif hot.get("proactiveHotOpportunityAuthorized") is True:
            stage, action = "COMMERCIAL_EVALUATION", "EVALUATE_OFFER"
        else:
            stage, action = "WARMING", "CONTINUE_WARMUP"

        proactive_value = (proactive.get("authorized") if "authorized" in proactive
                           else proactive.get("proactiveProgressionAuthorized"))
        proactive_authorized = proactive_value is True
        warmup = "COMPLETE" if proactive_authorized else (
            "IN_PROGRESS" if proactive_value is False else "UNKNOWN")
        if stage not in {"WARMING", "COMMERCIAL_INTEREST", "COMMERCIAL_EVALUATION"}:
            warmup = "COMPLETE"
        elif stage == "COMMERCIAL_EVALUATION":
            warmup = "ALTERNATE_PATH"

        behavior_counts = self._mapping(value.get("behaviorEvidenceCounts"))
        sexual_detected = bool(
            sexual.get("sexualEngagementDetected")
            or value.get("sexualEngagementOnly")
            or behavior_counts.get("sexual_engagement_only")
            or int(behavior_counts.get("sexual_engagement_count") or 0) > 0)
        sustained_sexual = bool(
            hot.get("sustainedSexualReceptiveness")
            or sexual.get("sustainedSexualReceptiveness")
            or summary_sexual.get("sustainedSexualReceptiveness")
        )
        current_offer = active if active and active.get("presented_at") else None
        eligibility = (
            "AUTHORIZED" if stage == "READY_TO_OFFER" else
            "EVALUATION_READY" if stage == "COMMERCIAL_EVALUATION" else
            "NOT_ELIGIBLE" if sales_decision in {"CONTINUE_CONVERSATION", "WAIT"} else
            "UNKNOWN")

        if stage == "WARMING" and sexual_detected and not fresh_intent and signal == "NONE":
            why = ("Flirtatious and sexual engagement is established, but no current "
                   "commercial intent or eligible offer exists. Deterministic warming "
                   "requirements remain incomplete." if warmup == "IN_PROGRESS" else
                   "Flirtatious or sexual engagement exists, but it is not canonical buying intent.")
        else:
            why = {
                "WARMING": "No canonical commercial signal or eligible offer currently exists.",
                "COMMERCIAL_INTEREST": "Canonical current commercial interest is established; offer evaluation remains authoritative.",
                "COMMERCIAL_EVALUATION": "Sustained current sexual receptiveness authorizes canonical commercial evaluation; it does not authorize an offer or delivery.",
                "READY_TO_OFFER": "Sales Brain authorized offer presentation and selected an eligible offering.",
                "OFFER_PRESENTED": "A paid offer has confirmed presentation evidence.",
                "AWAITING_PURCHASE": "An unresolved presented PurchaseIntent is awaiting customer action.",
                "FOLLOW_UP_ELIGIBLE": "The active offer is canonically eligible for bounded follow-through.",
                "NUDGE_SENT": "A follow-through nudge has confirmed delivery evidence.",
                "BACKOFF": "Post-nudge nonconversion authority requires commercial backoff.",
                "PURCHASED": "Verified settlement evidence establishes a buyer relationship.",
                "COMMERCIAL_RE_ENTRY": "Canonical re-entry evidence authorizes renewed commercial evaluation.",
            }[stage]

        readiness = self._offer_readiness(
            stage=stage, signal=signal, fresh_intent=fresh_intent,
            proactive=proactive, behavior_counts=behavior_counts,
            sustained_sexual=sustained_sexual,
            sexual_threshold=max(1, int(sexual_receptiveness_threshold)),
            selected=selected, eligibility=eligibility, hot=hot,
        )
        return {
            "stage": stage, "warmupStatus": warmup,
            "commercialSignal": signal,
            "commercialIntent": "DIRECT" if fresh_intent else "NONE",
            "currentOffer": self._offer(current_offer),
            "lastOffer": self._offer(last_offer),
            "offerEligibility": eligibility,
            "purchaseIntentState": self._upper(active.get("status")) if active else "NONE",
            "paidOffersPresented": len(presented),
            "verifiedPurchases": int(verified_purchase_count) if mapped and verified_purchase_count is not None else None,
            "messagesSinceLastOffer": messages_since_last_offer if last_offer else None,
            "followUpStatus": ("ELIGIBLE" if follow_eligible else "NONE") if follow_available else "UNAVAILABLE",
            "nudgeStatus": ("SENT_CONFIRMED" if nudge_sent else "NONE") if follow_available else "UNAVAILABLE",
            "backoffStatus": ("ACTIVE" if backoff else "NONE") if follow_available else "UNAVAILABLE",
            "conversationPolicy": ({
                "responsePurpose": conversation_policy.get("responsePurpose"),
                "supporterBoundaryCommunicated": conversation_policy.get(
                    "supporterBoundaryConfirmed") is True,
                "timeWaster": conversation_policy.get("timeWaster") is True,
                "timeWasterReason": (
                    "Repeated sexual boundary-pushing after a confirmed supporter boundary."
                    if conversation_policy.get("timeWaster") is True else None),
                "optionalReplyAllowance": conversation_policy.get("dailyOptionalReplyLimit"),
                "optionalRepliesUsedToday": conversation_policy.get("optionalRepliesUsedToday"),
                "nextResetAt": conversation_policy.get("nextResetAt"),
                "sexualAccessGated": conversation_policy.get("sexualAccessGated") is True,
                "relationshipActive": conversation_policy.get("relationshipRemainsActive") is True,
                "commercialReentry": conversation_policy.get("commercialReentry") is True,
            } if conversation_policy else None),
            "nextAction": action, "why": why,
            "offerReadiness": readiness,
            "evidence": {
                "salesBrainDecision": sales_decision,
                "salesBrainReason": sales_reason,
                "freshCommercialIntentDetected": fresh_intent,
                "sexualEngagementDetected": sexual_detected,
                "sustainedSexualReceptiveness": sustained_sexual,
                "proactiveProgressionAuthorized": proactive_value,
                "proactiveHotOpportunityAuthorized": hot.get(
                    "proactiveHotOpportunityAuthorized"
                ),
                "purchaseIntentPresent": active is not None,
                "confirmedPaidOfferPresent": last_offer is not None,
                "followThroughAuthorityAvailable": follow_available,
            },
        }

    def _offer_readiness(self, *, stage, signal, fresh_intent, proactive,
                         behavior_counts, sustained_sexual, sexual_threshold,
                         selected, eligibility, hot):
        evidence_value = proactive.get("proactiveProgressionEvidence")
        evidence_available = isinstance(evidence_value, (list, tuple, set))
        evidence = {str(item).upper() for item in (evidence_value or ())}
        explanations = {
            "SUSTAINED_VOLUNTARY_CONVERSATION": "At least six persisted inbound/history turns are required.",
            "MEANINGFUL_ENGAGEMENT": "At least five canonically meaningful engagements are required.",
            "VOLUNTARY_SELF_DISCLOSURE": "At least two durable conversational facts are required.",
            "RECIPROCAL_RELATIONAL_WARMING": "Canonical reciprocal warming must be observed.",
            "NO_OFFER_EXPOSURE": "The proactive path requires no prior offer exposure.",
        }
        counts = {
            "SUSTAINED_VOLUNTARY_CONVERSATION": (behavior_counts.get("inbound_message_count"), 6),
            "MEANINGFUL_ENGAGEMENT": (behavior_counts.get("meaningful_engagement_count"), 5),
            "NO_OFFER_EXPOSURE": (behavior_counts.get("offer_exposure_count"), 0),
        }
        requirements = []
        for key, label in self.PROACTIVE_REQUIREMENTS:
            status = ("SATISFIED" if key in evidence else
                      "REMAINING" if evidence_available else "UNAVAILABLE")
            current, required = counts.get(key, (None, None))
            requirements.append({"key": key, "label": label, "status": status,
                "current": current, "required": required,
                "blocking": status in {"REMAINING", "UNAVAILABLE"},
                "explanation": explanations[key]})
        sexual_count = behavior_counts.get("sexual_engagement_count")
        requirements.append({
            "key": "SUSTAINED_SEXUAL_RECEPTIVENESS", "label": "Sexual Receptiveness",
            "status": ("SATISFIED" if sustained_sexual else
                       "REMAINING" if sexual_count is not None else "UNAVAILABLE"),
            "current": sexual_count, "required": sexual_threshold, "blocking": False,
            "explanation": ("A canonical qualifying signal that can support progression; "
                            "it does not independently authorize a paid offer."),
        })
        bypass = signal in self.COMMERCIAL_SIGNALS or fresh_intent
        remaining = sum(item["blocking"] for item in requirements)
        unavailable = any(item["status"] == "UNAVAILABLE" and item["blocking"]
                          for item in requirements)
        hot_authorized = hot.get("proactiveHotOpportunityAuthorized") is True
        if stage == "READY_TO_OFFER" or (selected and eligibility == "AUTHORIZED"):
            status, distance = "READY_TO_OFFER", "Ready to offer"
        elif hot_authorized:
            status, distance = "EVALUATION_READY", "Ready for commercial evaluation"
        elif (proactive.get("proactiveProgressionAuthorized") is True
              or proactive.get("authorized") is True):
            status, distance = "EVALUATION_READY", "Ready for commercial evaluation"
        elif bypass:
            status, distance = "BYPASS_AVAILABLE", "Ready for commercial evaluation"
        elif unavailable:
            status, distance = "UNKNOWN", "Additional warming required"
        elif remaining == 1:
            status, distance = "WARMING", "1 condition remaining"
        elif remaining == 2:
            status, distance = "WARMING", "2 conditions remaining"
        else:
            status, distance = "WARMING", "Additional warming required"
        return {"status": status, "distance": distance,
                "qualifyingSignals": {"sexualEngagementCount": sexual_count,
                    "sexualReceptivenessThreshold": sexual_threshold,
                    "sustainedSexualReceptiveness": sustained_sexual},
                "requirements": requirements,
                "hotPath": {
                    "label": "Hot Conversation Path",
                    "status": "SATISFIED" if hot_authorized else (
                        "BLOCKED" if hot else "UNAVAILABLE"
                    ),
                    "authorized": hot_authorized,
                    "sustainedConversationSatisfied": hot.get(
                        "sustainedConversationSatisfied"
                    ),
                    "sustainedConversationCount": hot.get(
                        "sustainedConversationCount"
                    ),
                    "sustainedConversationRequired": hot.get(
                        "sustainedConversationRequired"
                    ),
                    "sustainedSexualReceptiveness": hot.get(
                        "sustainedSexualReceptiveness"
                    ),
                    "sexualEngagementCount": hot.get("sexualEngagementCount"),
                    "sexualEngagementRequired": hot.get(
                        "sexualEngagementRequired"
                    ),
                    "currentHotToneQualified": hot.get(
                        "currentHotToneQualified"
                    ),
                    "noPriorPaidOfferExposure": hot.get(
                        "noPriorPaidOfferExposure"
                    ),
                    "commercialSafeguardsPassed": hot.get(
                        "commercialSafeguardsPassed"
                    ),
                    "blockers": list(hot.get("hotOpportunityBlockers") or ()),
                    "reason": hot.get("commercialEvaluationReason"),
                    "note": "Evaluation only; offering and delivery remain downstream authority.",
                },
                "bypass": {"available": bypass,
                    "note": "Direct commercial intent may bypass remaining warming requirements."},
                "summary": distance}

    @staticmethod
    def _offer(item):
        if not item:
            return None
        return {
            "purchaseIntentId": str(item.get("purchase_intent_id")) if item.get("purchase_intent_id") else None,
            "status": str(item.get("status") or "UNKNOWN").upper(),
            "title": item.get("title"), "type": item.get("offering_type"),
            "priceMinor": item.get("expected_price_minor"),
            "presentedAt": item.get("presented_at").isoformat()
                if hasattr(item.get("presented_at"), "isoformat") else item.get("presented_at"),
        }
