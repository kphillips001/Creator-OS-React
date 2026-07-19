"""Read-only presentation composition for the React Customer Workspace."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any

from app.repositories.chat_message_repository import get_thread_messages_for_user
from app.repositories.customer_entitlement_repository import CustomerEntitlementRepository
from app.repositories.customer_repository import CustomerRepository
from app.services.customer_business_service import CustomerBusinessService
from app.services.customer_intelligence_service import CustomerIntelligenceService
from app.services.customer_service import CustomerService


class CustomerWorkspaceService:
    """Compose certified Customer read models without executing customer actions."""

    def __init__(
        self,
        *,
        customer_repository: CustomerRepository | None = None,
        customer_service: CustomerService | None = None,
        customer_intelligence_service: CustomerIntelligenceService | None = None,
        customer_business_service: CustomerBusinessService | None = None,
        entitlement_repository: CustomerEntitlementRepository | None = None,
        conversation_fetcher: Any = get_thread_messages_for_user,
    ) -> None:
        self.customers = customer_repository or CustomerRepository()
        self.customer_service = customer_service or CustomerService(self.customers)
        self.intelligence = customer_intelligence_service or CustomerIntelligenceService(
            customer_service=self.customer_service,
        )
        self.business = customer_business_service or CustomerBusinessService(
            customer_intelligence_service=self.intelligence,
            customer_service=self.customer_service,
        )
        self.entitlements = entitlement_repository or CustomerEntitlementRepository()
        self.conversation_fetcher = conversation_fetcher

    def list_customers(self, *, fanvue_account_id: int, limit: int = 1000) -> tuple[dict[str, Any], ...]:
        return tuple(
            self._project(customer, include_detail=False)
            for customer in self.customers.list_by_fanvue_account(
                fanvue_account_id=fanvue_account_id,
                limit=limit,
            )
        )

    def get_customer(self, customer_id: str, *, fanvue_account_id: int) -> dict[str, Any] | None:
        account_id, user_id = self._parse_customer_id(customer_id)
        if account_id != int(fanvue_account_id):
            return None
        customer = self.customers.get_by_legacy_fanvue_user(
            fanvue_account_id=account_id,
            fanvue_user_id=user_id,
        )
        return self._project(customer, include_detail=True) if customer else None

    def summarize(self, customers: tuple[dict[str, Any], ...] | list[dict[str, Any]]) -> dict[str, int]:
        items = tuple(customers)
        return {
            "total": len(items),
            "active": sum(item["relationshipStage"] in {"active", "engaged"} for item in items),
            "purchasers": sum(item["purchaseCount"] > 0 for item in items),
            "highValue": sum(str(item["valueTier"]).lower() in {"high", "high_value", "vip_potential", "vip", "whale"} for item in items),
            "atRisk": sum(str(item["retentionRisk"]).lower() in {"at_risk", "high", "critical", "dormant"} for item in items),
            "activeSessions": sum(bool(item["activeBuyerSession"]) for item in items),
        }

    def _project(self, customer: Any, *, include_detail: bool) -> dict[str, Any]:
        customer_id = customer.customer_id
        basic = self.customer_service.get_customer_summary(customer_id) or {}
        commerce = self.customer_service.get_customer_commerce_summary(customer_id) or {}
        intelligence_snapshot = self.intelligence.build_customer_snapshot(
            customer_id=customer_id,
            customer_summary=basic,
            commerce_summary=commerce,
        )
        review = self.intelligence.build_customer_review(intelligence_snapshot)
        business_snapshot = self.business.build_snapshot(
            customer_id=customer_id,
            customer_read_model=customer,
            customer_summary=basic,
            customer_snapshot=intelligence_snapshot,
        )
        business_summary = business_snapshot.summary
        item = {
            "customerId": customer_id,
            "displayName": customer.display_name or customer_id,
            "providerIdentities": self._plain(customer.provider_identities),
            "relationshipStatus": customer.relationship.status.value,
            "relationshipStage": business_summary.relationship_stage or review.relationship_stage,
            "buyerTier": customer.relationship.buyer_tier,
            "valueTier": self._value(business_snapshot.value_tier),
            "customerHealth": self._value(business_summary.health),
            "lifecycleStage": self._value(business_summary.lifecycle_stage),
            "totalSpendCents": int(basic.get("total_spend_cents") or 0),
            "purchaseCount": int(basic.get("purchase_count") or 0),
            "lastActivityAt": basic.get("last_active_at"),
            "retentionRisk": self._value(business_snapshot.retention_risk),
            "activeBuyerSession": bool(basic.get("active_session")),
            "nextRecommendedAction": business_summary.next_recommended_action,
            "isSubscriber": bool(basic.get("is_subscriber")),
            "isFollower": bool(basic.get("is_follower")),
        }
        if not include_detail:
            return item

        account_id, user_id = self._parse_customer_id(customer_id)
        entitlements = self.entitlements.list_for_legacy_user(
            legacy_fanvue_account_id=account_id,
            legacy_fanvue_user_id=user_id,
        )
        messages = tuple(self.conversation_fetcher(account_id, user_id) or ())
        item.update({
            "identity": self._plain(business_snapshot.customer_identity),
            "relationship": self._plain(review.relationship),
            "customerValue": self._plain(business_snapshot.customer_value),
            "journey": self._plain(business_snapshot.current_journey),
            "commerceAndOwnership": {
                "summary": self._plain(commerce),
                "entitlements": self._plain(entitlements),
            },
            "recommendationHistory": self._plain(customer.recommendation),
            "conversationSummary": {
                **self._plain(customer.conversation),
                "recent_messages": self._plain(messages[-10:]),
            },
            "buyerSession": self._plain(customer.progression),
            "retentionAndGrowth": {
                "retention": self._plain(business_snapshot.retention_summary),
                "growth": self._plain(business_snapshot.growth_summary),
            },
            "businessGuidance": {
                "opportunities": self._plain(business_snapshot.opportunities),
                "recommendations": self._plain(business_snapshot.recommendations),
                "next_recommended_action": business_snapshot.next_recommended_action,
            },
            "businessSummary": self._plain(business_summary),
            "businessSnapshot": self._plain(business_snapshot),
            "intelligenceReview": self._plain(review),
        })
        return item

    @staticmethod
    def _parse_customer_id(customer_id: str) -> tuple[int, int]:
        parts = str(customer_id).split(":", 1)
        if len(parts) != 2:
            raise ValueError("Customer ID must use account:user format.")
        return int(parts[0]), int(parts[1])

    @classmethod
    def _plain(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, Enum):
            return value.value
        if is_dataclass(value):
            return cls._plain(asdict(value))
        if isinstance(value, dict):
            return {str(key): cls._plain(item) for key, item in value.items()}
        if isinstance(value, (tuple, list, set)):
            return [cls._plain(item) for item in value]
        return value

    @staticmethod
    def _value(value: Any) -> Any:
        return getattr(value, "value", value)
