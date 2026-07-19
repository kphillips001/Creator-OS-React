"""Read-only observability composition for the React Sales Workspace."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Mapping

from app.repositories.chat_commerce_delivery_repository import ChatCommerceDeliveryRepository
from app.repositories.commerce_outcome_repository import CommerceOutcomeRepository
from app.repositories.content_commerce_learning_repository import ContentCommerceLearningRepository
from app.repositories.send_log_repository import get_decision_activity, list_decision_activities
from app.services.business_learning_service import BusinessLearningService
from app.services.content_commerce_learning_service import ContentCommerceLearningService
from app.services.customer_workspace_service import CustomerWorkspaceService


class SalesWorkspaceService:
    """Explain persisted Sales Agent activity; never execute or recreate a decision."""

    def __init__(
        self,
        *,
        decision_list_reader: Any = list_decision_activities,
        decision_detail_reader: Any = get_decision_activity,
        learning_repository: Any | None = None,
        outcome_repository: Any | None = None,
        delivery_repository: Any | None = None,
        content_learning_service: Any | None = None,
        business_learning_service: Any | None = None,
        customer_workspace_service: Any | None = None,
    ) -> None:
        self._list_decisions = decision_list_reader
        self._get_decision = decision_detail_reader
        self.learning_repository = learning_repository or ContentCommerceLearningRepository()
        self.outcomes = outcome_repository or CommerceOutcomeRepository()
        self.deliveries = delivery_repository or ChatCommerceDeliveryRepository()
        self.content_learning = content_learning_service or ContentCommerceLearningService(repository=self.learning_repository)
        self.business_learning = business_learning_service or BusinessLearningService()
        self.customers = customer_workspace_service or CustomerWorkspaceService()

    def decisions(self, *, account_id: int, limit: int = 5000) -> tuple[dict[str, Any], ...]:
        events = self._scoped_learning_events(account_id)
        outcomes = self._scoped_outcomes(account_id)
        deliveries = self._scoped_deliveries(account_id)
        return tuple(self._decision_item(row, events, outcomes, deliveries) for row in (self._list_decisions(account_id, limit) or ()))

    def decision_detail(self, decision_id: str, *, account_id: int) -> dict[str, Any] | None:
        activity_id = self._activity_id(decision_id)
        row = self._get_decision(account_id, activity_id)
        if not row:
            return None
        events = self._scoped_learning_events(account_id)
        outcomes = self._scoped_outcomes(account_id)
        deliveries = self._scoped_deliveries(account_id)
        item = self._decision_item(row, events, outcomes, deliveries)
        payload, response = self._mapping(row.get("payload")), self._mapping(row.get("response"))
        customer = None
        try:
            customer = self.customers.get_customer(item["customerId"], fanvue_account_id=account_id)
        except Exception:
            item["warnings"].append("Customer context is unavailable.")
            item["partialSections"].append("customerContext")
        linked_events = self._linked_events(item, events)
        linked_outcomes = self._linked_outcomes(item, outcomes)
        linked_deliveries = self._linked_deliveries(item, deliveries)
        offer = self._mapping(payload.get("offer"))
        content = self._mapping(offer.get("content"))
        route = self._mapping(payload.get("route"))
        classifier = self._mapping(route.get("classifier_result"))
        item.update({
            "customerContext": customer or {},
            "classificationAndRouting": {
                "intent": item["intent"], "intent_score": self._deep(payload, "intent", "score"),
                "buying_intent": classifier.get("buying_intent"), "closing_readiness": classifier.get("close_ready"),
                "route": item["route"], "relationship_route": payload.get("relationship_route"),
                "route_confidence": route.get("confidence"), "route_reason": route.get("reason"),
                "objection": payload.get("objection"), "conversation_mode": payload.get("mode"),
            },
            "sellDecision": {
                "brain_chose_to_sell": item["sellDecision"], "gateway_authorized": item["authorizationState"],
                "timing_or_pressure": payload.get("offer_pressure") or payload.get("timing_result"),
                "suppression_or_block_reason": item["reason"], "ownership_block": payload.get("ownership_blocked"),
                "recent_offer_block": payload.get("recent_offer_blocked"), "no_eligible_inventory": item["sellDecision"] and not (item["productId"] or item["assetId"]),
                "fulfillment_readiness": payload.get("delivery_prepared"),
            },
            "recommendation": {
                "product_id": item["productId"], "asset_id": item["assetId"], "recommendation_id": item["recommendationId"],
                "offer_type": item["offerType"], "price": item["price"], "score": content.get("recommendation_score"),
                "confidence": content.get("recommendation_confidence"), "score_components": self._deep(content, "recommendation_metadata", "score") or {},
                "supporting_evidence": content.get("recommendation_evidence") or [],
                "persisted_lifecycle": linked_events,
            },
            "delivery": {
                "delivery_type": payload.get("delivery_type") or content.get("delivery_type"),
                "delivery_mode": payload.get("delivery_permission_mode") or content.get("delivery_permission_mode"),
                "media_link_state": "available" if content.get("media_link") or content.get("fanvue_link") else "unknown",
                "fulfillment_state": content.get("fulfillment_status"), "payload_prepared": payload.get("delivery_prepared"),
                "execution_events": linked_deliveries, "delivery_id": item["deliveryId"], "failure_or_block_reason": item["reason"] if item["deliveryState"] in {"failed", "blocked"} else None,
            },
            "conversation": {
                "customer_message": payload.get("message"), "generated_reply": response.get("text"),
                "provider": payload.get("selected_provider") or payload.get("provider"), "model": payload.get("model"),
                "cta_or_nudge": {"send_nudge": payload.get("send_nudge"), "nudge_type": payload.get("nudge_type")},
            },
            "outcomeAndLearning": {"events": linked_events, "outcomes": linked_outcomes, "learning_status": "recorded" if linked_events else "not_correlated"},
            "rawDiagnostics": {},
        })
        item["partialSections"] = sorted(set(item["partialSections"]))
        item["dataStatus"] = "partial" if item["partialSections"] else "complete"
        return item

    def offers(self, *, account_id: int) -> tuple[dict[str, Any], ...]:
        events = self._scoped_learning_events(account_id)
        grouped: dict[str, list[dict[str, Any]]] = {}
        for event in events:
            key = str(event.get("recommendation_id") or event.get("event_id"))
            grouped.setdefault(key, []).append(event)
        items = []
        for key, lifecycle in grouped.items():
            ordered = sorted(lifecycle, key=lambda value: str(value.get("event_timestamp") or ""))
            states = [str(value.get("event_state") or "UNKNOWN").upper() for value in ordered]
            latest = ordered[-1]
            metadata = self._mapping(latest.get("outcome_metadata"))
            items.append({
                "offerId": key, "decisionId": None, "customerId": latest.get("customer_id"),
                "productId": latest.get("product_id"), "assetId": latest.get("asset_id"), "offerType": self._deep(latest, "metadata", "offer_type"),
                "price": metadata.get("gross_revenue_cents"), "generatedAt": ordered[0].get("event_timestamp"),
                "presentedAt": next((value.get("event_timestamp") for value in ordered if str(value.get("event_state")).upper() in {"PRESENTED", "OFFERED"}), None),
                "state": states[-1], "states": states, "deliveryState": "confirmed" if "DELIVERED" in states else "not_confirmed",
                "purchased": "PURCHASED" in states, "refunded": "REFUNDED" in states,
                "revenueCents": int(metadata.get("net_revenue_cents") or 0), "attributionState": metadata.get("matched_by") or "unknown",
                "attention": bool(set(states) & {"SUPPRESSED", "REJECTED", "DELIVERY_FAILED", "UNMATCHED", "LEARNING_FAILED"}),
                "warnings": [] if latest.get("customer_id") else ["Customer correlation is unavailable."], "dataStatus": "partial" if not latest.get("customer_id") else "complete",
            })
        return tuple(sorted(items, key=lambda value: str(value.get("generatedAt") or ""), reverse=True))

    def learning(self, *, account_id: int) -> dict[str, Any]:
        events = self._scoped_learning_events(account_id)
        outcomes = self._scoped_business_outcomes(account_id)
        asset_ids = {int(event["asset_id"]) for event in events if event.get("asset_id") is not None}
        profiles = tuple(profile for profile in self.content_learning.list_asset_learning_profiles() if int(profile.asset_id) in asset_ids)
        top = sorted(profiles, key=lambda value: value.score, reverse=True)
        under = sorted(profiles, key=lambda value: value.score)
        snapshot = self.business_learning.build_learning_snapshot(outcomes=outcomes, metadata={"read_only_sales_workspace": True})
        unmatched = [event for event in events if str(event.get("event_state")).upper() == "UNMATCHED"]
        failures = list(self.learning_repository.list_failed_learning_events())
        return self._plain({
            "summary": {
                "recommendations": sum(str(event.get("event_state")).upper() == "GENERATED" for event in events),
                "offers": sum(str(event.get("event_state")).upper() in {"OFFERED", "PRESENTED"} for event in events),
                "deliveries": sum(str(event.get("event_state")).upper() == "DELIVERED" for event in events),
                "purchases": sum(str(event.get("event_state")).upper() == "PURCHASED" for event in events),
                "refunds": sum(str(event.get("event_state")).upper() == "REFUNDED" for event in events),
                "grossRevenueCents": sum(profile.gross_revenue_cents for profile in profiles),
                "netRevenueCents": sum(profile.net_revenue_cents for profile in profiles),
                "conversionRate": (sum(profile.purchase_count for profile in profiles) / sum(profile.offer_count for profile in profiles)) if sum(profile.offer_count for profile in profiles) else 0.0,
            },
            "topAssets": top[:10], "underperformingAssets": under[:10], "topProducts": [],
            "suppressionReasons": self._reason_counts(events, "suppression_reasons"), "rejectionReasons": self._reason_counts(events, "rejected_candidate_reasons"),
            "deliveryFailures": [event for event in events if str(event.get("event_state")).upper() == "DELIVERY_FAILED"],
            "unmatchedOutcomes": unmatched, "failedLearningEvents": failures,
            "learningInsights": snapshot.learning_insights, "learningRecommendations": snapshot.learning_recommendations,
            "warnings": (["Product-level learning is not available in the persisted learning ledger."] if not outcomes else []) + (["Some unscoped learning records were excluded."] if self._has_unscoped_learning(account_id) else []),
            "dataStatus": "partial" if self._has_unscoped_learning(account_id) else "complete",
        })

    def overview(self, *, account_id: int) -> dict[str, Any]:
        decisions = self.decisions(account_id=account_id)
        today = date.today()
        today_items = [item for item in decisions if self._date(item.get("timestamp")) == today]
        learning = self.learning(account_id=account_id)
        lsum = learning["summary"]
        active_sessions = 0
        try:
            active_sessions = sum(bool(item.get("activeBuyerSession")) for item in self.customers.list_customers(fanvue_account_id=account_id, limit=5000))
        except Exception:
            pass
        offers = sum(bool(item["sellDecision"]) for item in decisions)
        purchases = int(lsum["purchases"])
        warnings = ["Decision Activity does not prove an external provider send occurred."]
        if learning["dataStatus"] == "partial": warnings.extend(learning["warnings"])
        return {
            "metrics": {
                "decisionActivitiesToday": len(today_items), "sellDecisions": offers, "noSellDecisions": len(decisions) - offers,
                "offersAuthorized": sum(item["authorizationState"] == "authorized" for item in decisions),
                "blockedOrSuppressed": sum(item["authorizationState"] == "blocked" for item in decisions),
                "deliverySuccesses": sum(item["deliveryState"] == "confirmed" for item in decisions),
                "deliveryFailures": len(learning["deliveryFailures"]), "purchases": purchases, "refunds": int(lsum["refunds"]),
                "revenueCents": int(lsum["netRevenueCents"]), "conversionRate": purchases / offers if offers else 0.0,
                "activeBuyerSessions": active_sessions, "highPriorityRecommendations": 0,
                "learningIssues": len(learning["unmatchedOutcomes"]) + len(learning["failedLearningEvents"]),
            },
            "recentActivity": list(decisions[:8]), "topAssets": learning["topAssets"][:5], "underperformingAssets": learning["underperformingAssets"][:5],
            "highPriorityRecommendations": [], "learningWarnings": warnings, "unmatchedOutcomes": learning["unmatchedOutcomes"][:5],
            "dataStatus": "partial", "partialSections": ["externalSendConfirmation", "highPriorityRecommendations"], "warnings": warnings,
        }

    def _decision_item(self, row: Mapping[str, Any], events, outcomes, deliveries) -> dict[str, Any]:
        payload, response = self._mapping(row.get("payload")), self._mapping(row.get("response"))
        offer, route = self._mapping(payload.get("offer")), self._mapping(payload.get("route"))
        content = self._mapping(offer.get("content"))
        customer_id = f"{row.get('fanvue_account_id')}:{row.get('fanvue_user_id')}"
        recommendation_id = content.get("recommendation_id") or self._deep(content, "recommendation_metadata", "recommendation_id")
        asset_id = content.get("asset_id") or content.get("content_item_id") or content.get("id")
        product_id = content.get("product_id") or offer.get("product_id")
        base = {"recommendationId": recommendation_id, "assetId": self._text(asset_id), "productId": self._text(product_id), "customerId": customer_id}
        linked_events, linked_outcomes, linked_deliveries = self._linked_events(base, events), self._linked_outcomes(base, outcomes), self._linked_deliveries(base, deliveries)
        states = {str(event.get("event_state") or "").upper() for event in linked_events}
        sell = bool(payload.get("send_offer"))
        warnings = ["Decision Activity is not confirmation of an external send."]
        partial = ["gatewayAuthorization"]
        if not linked_events: partial.append("recommendationLifecycle")
        if not linked_deliveries: partial.append("delivery")
        if not linked_outcomes: partial.append("outcome")
        delivery_state = "confirmed" if "DELIVERED" in states or any(event.get("event_type") == "delivery_success" for event in linked_deliveries) else "failed" if "DELIVERY_FAILED" in states or any(event.get("event_type") == "delivery_failure" for event in linked_deliveries) else "not_confirmed"
        outcome_state = "refunded" if "REFUNDED" in states else "purchased" if "PURCHASED" in states else "none_confirmed"
        revenue = sum(int(self._deep(event, "outcome_metadata", "net_revenue_cents") or 0) for event in linked_events if str(event.get("event_state")).upper() in {"PURCHASED", "REFUNDED"})
        return {
            "decisionId": f"decision-{row.get('id')}", "timestamp": row.get("created_at"), "activityLabel": "Decision Activity",
            "customerId": customer_id, "customerName": row.get("fanvue_user_uuid") or customer_id, "provider": "fanvue", "accountId": row.get("fanvue_account_id"),
            "messageSummary": str(payload.get("message") or "")[:160], "replySummary": str(response.get("text") or "")[:160],
            "intent": self._deep(payload, "intent", "tier") or self._deep(route, "classifier_result", "intent") or "unknown",
            "route": route.get("route") or row.get("route") or "unknown", "relationshipStage": payload.get("relationship_route"), "buyerTier": payload.get("buyer_tier"),
            "sellDecision": sell, "productId": self._text(product_id), "assetId": self._text(asset_id), "recommendationId": recommendation_id,
            "offerType": offer.get("offer_type") or row.get("offer_type"), "price": offer.get("price") if offer.get("price") is not None else row.get("price"),
            "authorizationState": "blocked" if payload.get("blocked") or payload.get("ownership_blocked") else "unknown",
            "reason": payload.get("delivery_blocking_reason") or route.get("reason") or ("Offer selected" if sell else "The brain chose not to sell"),
            "deliveryState": delivery_state, "outcomeState": outcome_state, "revenueCents": revenue,
            "deliveryId": next((event.get("delivery_id") for event in linked_events if event.get("delivery_id")), None),
            "correlationReferences": {"send_log_id": row.get("id"), "recommendation_id": recommendation_id},
            "correlationConfidence": "high" if recommendation_id and linked_events else "low", "dataStatus": "partial" if partial else "complete",
            "partialSections": partial, "warnings": warnings,
        }

    def _scoped_learning_events(self, account_id: int): return tuple(item for item in self.learning_repository.list_recommendation_events() if self._belongs(item, account_id))
    def _scoped_business_outcomes(self, account_id: int): return tuple(item for item in self.learning_repository.list_business_outcomes() if self._belongs(item, account_id))
    def _scoped_outcomes(self, account_id: int): return tuple(item for item in self.outcomes.list_outcomes() if self._belongs(item, account_id))
    def _scoped_deliveries(self, account_id: int): return tuple(item for item in self.deliveries.list_events() if self._belongs(self._mapping(item.get("payload")), account_id))
    def _has_unscoped_learning(self, account_id): return any(not self._belongs(item, account_id) for item in self.learning_repository.list_recommendation_events())
    @staticmethod
    def _belongs(item, account_id):
        account = item.get("fanvue_account_id") or item.get("provider_account_id") or SalesWorkspaceService._deep(item, "provider_metadata", "provider_account_id") or SalesWorkspaceService._deep(item, "outcome_metadata", "provider_account_id")
        customer = str(item.get("customer_id") or "")
        return str(account) == str(account_id) or customer.startswith(f"{account_id}:")
    @staticmethod
    def _linked_events(item, events): return [event for event in events if (item.get("recommendationId") and str(event.get("recommendation_id")) == str(item["recommendationId"])) or (item.get("assetId") and str(event.get("asset_id")) == str(item["assetId"]) and str(event.get("customer_id")) == str(item.get("customerId")))]
    @staticmethod
    def _linked_outcomes(item, outcomes): return [outcome for outcome in outcomes if str(SalesWorkspaceService._deep(outcome, "attribution", "recommendation_id") or "") == str(item.get("recommendationId") or "") and item.get("recommendationId")]
    @staticmethod
    def _linked_deliveries(item, deliveries): return [event for event in deliveries if str(SalesWorkspaceService._deep(event, "payload", "recommendation_id") or SalesWorkspaceService._deep(event, "payload", "payload", "recommendation_id") or "") == str(item.get("recommendationId") or "") and item.get("recommendationId")]
    @staticmethod
    def _reason_counts(events, key):
        counts = {}
        for event in events:
            for reason in event.get(key) or (): counts[str(reason)] = counts.get(str(reason), 0) + 1
        return counts
    @staticmethod
    def _activity_id(value):
        text = str(value); return int(text[9:] if text.startswith("decision-") else text)
    @staticmethod
    def _mapping(value): return dict(value) if isinstance(value, Mapping) else {}
    @staticmethod
    def _deep(value, *path):
        current = value
        for key in path:
            if not isinstance(current, Mapping): return None
            current = current.get(key)
        return current
    @staticmethod
    def _text(value): return str(value) if value is not None else None
    @staticmethod
    def _date(value):
        if isinstance(value, datetime): return value.date()
        try: return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
        except (TypeError, ValueError): return None
    @classmethod
    def _plain(cls, value):
        if isinstance(value, Enum): return value.value
        if is_dataclass(value): return cls._plain(asdict(value))
        if isinstance(value, Mapping): return {str(k): cls._plain(v) for k, v in value.items()}
        if isinstance(value, (tuple, list, set)): return [cls._plain(v) for v in value]
        if isinstance(value, (datetime, date)): return value.isoformat()
        return value
