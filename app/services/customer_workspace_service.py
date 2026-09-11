"""Verified Customer directory projection for the React business workspace."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.repositories.creator_profile_repository import get_active_creator_profile
from app.repositories.verified_customer_repository import VerifiedCustomerRepository


class CustomerWorkspaceService:
    """Read successful provider commerce; provider identities are enrichment only."""

    CONTENT_SOURCES = frozenset({"medialink", "media_link", "media", "content", "ppv"})

    def __init__(self, *, repository=None, creator_profile_resolver=get_active_creator_profile):
        self.repository = repository or VerifiedCustomerRepository()
        self.creator_profile_resolver = creator_profile_resolver

    def list_customers(self, *, fanvue_account_id: int, limit: int = 5000):
        creator_id = self._creator_profile_id(fanvue_account_id)
        if creator_id is None:
            return ()
        rows = self.repository.customers(creator_profile_id=creator_id, fanvue_account_id=fanvue_account_id)
        return tuple(self._project(row, include_detail=False) for row in rows[:limit])

    def get_customer(self, customer_id: str, *, fanvue_account_id: int):
        profile_id = self._profile_id(customer_id)
        creator_id = self._creator_profile_id(fanvue_account_id)
        if creator_id is None:
            return None
        for row in self.repository.customers(creator_profile_id=creator_id, fanvue_account_id=fanvue_account_id):
            if UUID(str(row["customer_commerce_profile_id"])) == profile_id:
                return self._project(row, include_detail=True)
        return None

    def customer_identity(self, customer_id: str, *, fanvue_account_id: int):
        customer = self.get_customer(customer_id, fanvue_account_id=fanvue_account_id)
        if not customer or customer.get("localFanvueUserId") is None:
            return None
        return int(customer["localFanvueUserId"])

    @staticmethod
    def summarize(customers):
        items = tuple(customers)
        return {"total": len(items), "buyers": sum(bool(i["isBuyer"]) for i in items),
                "activeSubscribers": sum(i["subscriptionStatus"] in {"ACTIVE", "CANCELED_ACCESS_REMAINING"} for i in items),
                "formerSubscribers": sum(i["subscriptionStatus"] == "FORMER_EXPIRED" for i in items),
                "highValue": sum(bool(i["isHighValue"]) for i in items),
                "activeSessions": sum(bool(i["activeSalesSession"]) for i in items)}

    def _project(self, row, *, include_detail: bool):
        transactions = [self._transaction(i) for i in self.repository.transactions(profile_id=row["customer_commerce_profile_id"])]
        subscription = self._subscription(row)
        is_buyer = any(i["type"] == "CONTENT" for i in transactions)
        value_tier = str(row.get("buyer_tier") or row.get("profile_state") or "CUSTOMER")
        item = {"customerId": f"commerce:{row['customer_commerce_profile_id']}",
                "displayName": row.get("resolved_display_name") or "Verified customer",
                "username": row.get("resolved_handle"),
                "commercialStatuses": [*(["BUYER"] if is_buyer else []), *(["SUBSCRIBER"] if subscription["status"] in {"ACTIVE", "CANCELED_ACCESS_REMAINING"} else []), "CUSTOMER"],
                "totalSpendMinor": sum(i["grossMinor"] for i in transactions), "transactionCount": len(transactions),
                "contentPurchaseCount": sum(i["type"] == "CONTENT" for i in transactions),
                "lastActivityAt": self._iso(row.get("last_purchase_at") or row.get("last_seen_at")),
                "isBuyer": is_buyer,
                "isHighValue": bool(row.get("is_whale") or row.get("is_top_spender")) or value_tier.upper() in {"HIGH_VALUE", "VIP", "WHALE"},
                "valueTier": value_tier, "attentionTier": None, "retentionStatus": self._retention(subscription["status"]),
                "subscriptionStatus": subscription["status"], "subscriptionPeriodEnd": subscription["periodEnd"],
                "activeSalesSession": bool(row.get("active_sales_session")), "activePurchaseIntent": bool(row.get("active_purchase_intent")),
                "relationshipKey": row.get("relationship_key"), "hasTelegramRelationship": bool(row.get("relationship_key")),
                "localFanvueUserId": row.get("local_fanvue_user_id"),
                "identitySearchValues": [str(row["external_fanvue_user_uuid"]), str(row.get("mapped_telegram_user_id") or "")]}
        if include_detail:
            item.update({"transactions": transactions, "subscription": subscription,
                         "customerValue": {"status": "BUYER" if is_buyer else "CUSTOMER", "valueTier": value_tier,
                                           "attentionTier": None, "lifetimeSpendMinor": item["totalSpendMinor"],
                                           "transactionCount": item["transactionCount"], "retentionStatus": item["retentionStatus"]},
                         "commercialState": {"activePurchaseIntent": item["activePurchaseIntent"],
                                             "activeSalesSession": item["activeSalesSession"],
                                             "lastCommercialInteractionAt": item["lastActivityAt"]}, "ownership": []})
        return item

    def _subscription(self, row):
        events = self.repository.subscription_events(fanvue_account_id=int(row["fanvue_account_id"]), external_uuid=row["external_fanvue_user_uuid"])
        status, period_end = "NONE", None
        for event in events:
            payload, kind = event.get("payload") or {}, event.get("event_type")
            if kind in {"subscription_new", "subscription_renewed"}:
                period_end = (payload.get("subscription") or {}).get("currentPeriodEnd"); status = "ACTIVE"
            elif kind == "subscription_cancelled":
                period_end = payload.get("accessEndsAt") or period_end; status = "CANCELED_ACCESS_REMAINING"
            elif kind == "subscription_expired":
                period_end = payload.get("expiredAt") or period_end; status = "FORMER_EXPIRED"
        end = self._datetime(period_end)
        if end and end <= datetime.now(timezone.utc): status = "FORMER_EXPIRED"
        return {"status": status, "periodEnd": self._iso(end), "providerBacked": bool(events)}

    @classmethod
    def _transaction(cls, row):
        source = str(row.get("purchase_source") or "").lower().replace("-", "_")
        compact = source.replace("_", "")
        kind = "CONTENT" if source in cls.CONTENT_SOURCES or compact in cls.CONTENT_SOURCES else "RENEWAL" if source == "renewal" else "SUBSCRIPTION" if source == "subscription" else "TIP" if source == "tip" else "OTHER"
        return {"transactionId": str(row["customer_commerce_transaction_id"]), "type": kind,
                "grossMinor": int(row.get("gross_minor") or 0), "netMinor": int(row.get("net_minor") or 0),
                "occurredAt": cls._iso(row.get("payment_timestamp"))}

    def _creator_profile_id(self, account_id):
        profile = self.creator_profile_resolver(str(account_id)) or {}
        return int(profile["id"]) if profile.get("id") is not None else None

    @staticmethod
    def _profile_id(customer_id):
        prefix, value = str(customer_id).split(":", 1)
        if prefix != "commerce": raise ValueError("Customer ID must be a Commerce profile.")
        return UUID(value)

    @staticmethod
    def _datetime(value):
        if not value or isinstance(value, datetime): return value
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))

    @classmethod
    def _iso(cls, value):
        parsed = cls._datetime(value)
        return parsed.isoformat() if parsed else None

    @staticmethod
    def _retention(status):
        return {"ACTIVE": "ACTIVE_SUBSCRIBER", "CANCELED_ACCESS_REMAINING": "CANCELED_ACCESS_REMAINING", "FORMER_EXPIRED": "FORMER_SUBSCRIBER"}.get(status, "CUSTOMER")
