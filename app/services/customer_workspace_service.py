"""Read-only presentation composition for the React Customer Workspace."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any
from uuid import UUID

from app.repositories.chat_message_repository import get_thread_messages_for_user
from app.repositories.customer_entitlement_repository import CustomerEntitlementRepository
from app.repositories.customer_repository import CustomerRepository
from app.repositories.purchase_intent_repository import PurchaseIntentRepository
from app.repositories.sales_session_repository import SalesSessionRepository
from app.repositories.creator_profile_repository import get_active_creator_profile
from app.models.ownership_intelligence import OwnershipIdentity
from app.services.ownership_intelligence_service import OwnershipIntelligenceService
from app.services.customer_business_service import CustomerBusinessService
from app.services.customer_intelligence_service import (
    CustomerIntelligenceCompatibilityAdapter,
    CustomerIntelligenceService,
)
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
        ownership_intelligence: OwnershipIntelligenceService | None = None,
        creator_profile_resolver: Any = get_active_creator_profile,
        conversation_fetcher: Any = get_thread_messages_for_user,
        purchase_intent_repository: Any | None = None,
        sales_session_repository: Any | None = None,
    ) -> None:
        self.customers = customer_repository or CustomerRepository()
        self.customer_service = customer_service or CustomerService(self.customers)
        self.intelligence = customer_intelligence_service or CustomerIntelligenceService(
            customer_service=self.customer_service,
        )
        self.business = customer_business_service or CustomerBusinessService(
            customer_intelligence_service=CustomerIntelligenceCompatibilityAdapter(
                customer_service=self.customer_service,
            ),
            customer_service=self.customer_service,
        )
        self.entitlements = entitlement_repository or CustomerEntitlementRepository()
        self.ownership_intelligence = (
            ownership_intelligence or OwnershipIntelligenceService()
        )
        self.creator_profile_resolver = creator_profile_resolver
        self.conversation_fetcher = conversation_fetcher
        self.purchase_intents = purchase_intent_repository or PurchaseIntentRepository()
        self.sales_sessions = sales_session_repository or SalesSessionRepository()

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
        canonical_ownership = self._ownership_projection(account_id, user_id)
        messages = tuple(self.conversation_fetcher(account_id, user_id) or ())
        fanvue_identity = customer.identity_for("fanvue")
        telegram_identity = customer.identity_for("telegram")
        source_facts, source_failures = self._canonical_customer_sources(
            creator_profile_id=self._creator_profile_id(account_id),
            account_id=account_id, user_id=user_id,
            external_uuid=(
                fanvue_identity.provider_customer_id if fanvue_identity else None
            ),
        )
        canonical_profile = self.intelligence.build_canonical_profile(
            customer_context={
                "creator_profile_id": self._creator_profile_id(account_id),
                "fanvue_account_id": account_id,
                "canonical_customer_id": customer_id,
                "external_fanvue_user_uuid": (
                    fanvue_identity.provider_customer_id
                    if fanvue_identity else None
                ),
                "telegram_user_id": (
                    telegram_identity.provider_customer_id
                    if telegram_identity else None
                ),
                "identity_path": "fanvue_account:legacy_user",
            },
            entitlements=entitlements,
            ownership=canonical_ownership,
            purchase_intents=source_facts["purchase_intents"],
            sessions=source_facts["sessions"],
            messages=messages,
            recommendations=(self._plain(customer.recommendation),),
            classifications=({
                "label": review.relationship_stage,
                "source": "CustomerIntelligenceReview",
                "confidence": 0.6,
                "evidence": ("relationship_intelligence",),
            },),
            source_failures=source_failures,
        )
        item.update({
            "identity": self._plain(business_snapshot.customer_identity),
            "relationship": self._plain(review.relationship),
            "customerValue": self._plain(business_snapshot.customer_value),
            "journey": self._plain(business_snapshot.current_journey),
            "commerceAndOwnership": {
                "summary": self._plain(commerce),
                "entitlements": self._plain(entitlements),
                "ownershipIntelligence": (
                    self._plain(canonical_ownership)
                ),
            },
            "recommendationHistory": self._plain(customer.recommendation),
            "conversationSummary": {
                **self._plain(customer.conversation),
                "recent_messages": self._plain(messages[-10:]),
            },
            "buyerSession": self._plain(customer.progression),
            "salesSessions": self._plain(source_facts["sessions"]),
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
            "customerIntelligenceProfile": self._plain(canonical_profile),
        })
        return item

    def _ownership_projection(self, account_id: int, user_id):
        creator_profile = self.creator_profile_resolver(str(account_id)) or {}
        if creator_profile.get("id") is None:
            return {
                "insufficiencies": ("CREATOR_SCOPE_UNRESOLVED",),
            }
        answer = self.ownership_intelligence.answer(OwnershipIdentity(
            creator_profile_id=int(creator_profile["id"]),
            fanvue_account_id=int(account_id),
            legacy_fanvue_user_id=str(user_id),
        ))
        return self.ownership_intelligence.workspace_view(answer)

    def _creator_profile_id(self, account_id: int) -> int | None:
        creator_profile = self.creator_profile_resolver(str(account_id)) or {}
        return (
            int(creator_profile["id"])
            if creator_profile.get("id") is not None else None
        )

    def _canonical_customer_sources(
        self, *, creator_profile_id: int | None, account_id: int,
        user_id: int, external_uuid: str | None,
    ) -> tuple[dict[str, tuple[Any, ...]], dict[str, str]]:
        values: dict[str, tuple[Any, ...]] = {
            "purchase_intents": (), "sessions": (),
        }
        failures: dict[str, str] = {}
        if creator_profile_id is None:
            return values, {
                "purchase_intents": "CreatorScopeUnavailable",
                "sessions": "CreatorScopeUnavailable",
            }
        try:
            intents, _total, _page = self.purchase_intents.list_page(
                creator_profile_id=creator_profile_id, search=None,
                status=None, page=1, page_size=100,
            )
            values["purchase_intents"] = tuple(
                item for item in intents
                if int(item.fanvue_account_id) == int(account_id)
                and (
                    external_uuid is None
                    or str(item.external_fanvue_user_uuid) == external_uuid
                )
            )
        except Exception as error:
            failures["purchase_intents"] = type(error).__name__
        try:
            values["sessions"] = tuple(
                item for item in self.sales_sessions.list_for_creator(
                    creator_profile_id=creator_profile_id, limit=500,
                ) if int(item.fanvue_account_id) == int(account_id)
                and int(item.fanvue_user_id) == int(user_id)
            )
        except Exception as error:
            failures["sessions"] = type(error).__name__
        return values, failures

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
        if isinstance(value, UUID):
            return str(value)
        if is_dataclass(value):
            return {
                field.name: cls._plain(getattr(value, field.name))
                for field in fields(value)
            }
        if isinstance(value, dict) or hasattr(value, "items"):
            return {str(key): cls._plain(item) for key, item in value.items()}
        if isinstance(value, (tuple, list, set)):
            return [cls._plain(item) for item in value]
        return value

    @staticmethod
    def _value(value: Any) -> Any:
        return getattr(value, "value", value)
