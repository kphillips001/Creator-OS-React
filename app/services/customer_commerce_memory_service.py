"""Compose durable ownership, chronology, financial evidence, and affinities."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from math import exp
from uuid import UUID

from app.models.customer_commerce_memory import (
    CustomerCommerceAffinity,
    CustomerCommerceMemory,
    CustomerPurchaseEvent,
)
from app.repositories.customer_commerce_memory_repository import (
    CustomerCommerceMemoryRepository,
)
from app.services.ownership_intelligence_service import OwnershipIntelligenceService


class CustomerCommerceMemoryService:
    """One read-oriented customer commerce view; never infers ownership."""

    def __init__(self, repository=None, ownership_service=None, clock=None) -> None:
        self.repository = repository or CustomerCommerceMemoryRepository()
        self.ownership = ownership_service or OwnershipIntelligenceService()
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def build(self, *, identity, customer_profile=None, active_purchase_intent=None):
        ownership = self.ownership.answer(identity)
        events = self._dedupe_events([
            *(self._intent_event(row) for row in self.repository.verified_purchase_intents(identity)),
            *(self._entitlement_event(row, identity) for row in self.repository.valid_entitlements(identity)),
            *(self._legacy_event(row, identity) for row in self.repository.legacy_asset_purchases(identity)),
        ])
        events.sort(key=lambda item: (self._aware(item.purchased_at), item.source_type, item.source_record_id))
        profile_id = getattr(customer_profile, "customer_commerce_profile_id", None)
        unmatched_rows = self.repository.unmatched_transactions(profile_id)
        unmatched = tuple({
            "sourceType": "UNMATCHED_PROVIDER_TRANSACTION",
            "sourceRecordId": str(row["customer_commerce_transaction_id"]),
            "paymentTimestamp": self._iso(row.get("payment_timestamp")),
            "grossMinor": int(row.get("gross_minor") or 0),
            "netMinor": int(row.get("net_minor") or 0),
            "paymentStatus": row.get("payment_status"),
            "purchaseSource": row.get("purchase_source"),
            "ownershipCreated": False,
        } for row in unmatched_rows)
        profile_count = int(getattr(customer_profile, "purchase_count", 0) or 0)
        first = getattr(customer_profile, "first_purchase_at", None) or (events[0].purchased_at if events else None)
        last = getattr(customer_profile, "last_purchase_at", None) or (events[-1].purchased_at if events else None)
        insufficiencies = tuple(dict.fromkeys((
            *ownership.insufficiencies,
            *("UNMATCHED_PROVIDER_TRANSACTION:" + item["sourceRecordId"] for item in unmatched),
        )))
        return CustomerCommerceMemory(
            identity=identity, ownership=ownership, purchase_events=tuple(events),
            unmatched_financial_evidence=unmatched,
            purchase_count=max(profile_count, len(events)),
            first_purchase_at=first, last_purchase_at=last,
            lifetime_gross_minor=int(getattr(customer_profile, "lifetime_gross_minor", 0) or 0),
            lifetime_net_minor=int(getattr(customer_profile, "lifetime_net_minor", 0) or 0),
            average_order_value_minor=int(getattr(customer_profile, "average_order_value_minor", 0) or 0),
            largest_order_minor=int(getattr(customer_profile, "largest_purchase_minor", 0) or 0),
            channels_purchased_through=tuple(dict.fromkeys(item.channel for item in events if item.channel)),
            purchase_type_history=tuple(item.sale_type for item in events if item.sale_type),
            affinity=self._affinity(events),
            active_purchase_state=self._active_state(active_purchase_intent),
            attribution_insufficiencies=insufficiencies, conflicts=ownership.conflicts,
        )

    @staticmethod
    def _dedupe_events(events):
        """Prefer the richer Purchase Intent when sources share a transaction."""
        priority = {"PURCHASE_INTENT": 0, "ENTITLEMENT": 1,
                    "VAULT_UNLOCK": 2, "LEGACY_ASSET_OWNERSHIP": 3}
        ordered = sorted(events, key=lambda item: priority.get(item.source_type, 9))
        result, provider_refs = [], set()
        for event in ordered:
            reference = event.provider_transaction_reference
            if reference and reference in provider_refs:
                continue
            result.append(event)
            if reference:
                provider_refs.add(reference)
        return result

    def _affinity(self, events):
        now = self.clock()
        types, tags, channels, prices = defaultdict(float), defaultdict(float), defaultdict(float), []
        recent = 0
        for event in events:
            age_days = max(0.0, (now - self._aware(event.purchased_at)).total_seconds() / 86400)
            weight = max(0.20, exp(-age_days / 180.0))
            recent += int(age_days <= 30)
            if event.sale_type:
                types[event.sale_type] += weight
            if event.channel:
                channels[event.channel] += weight
            for tag in event.intelligence_tags:
                tags[tag] += weight
            if event.gross_minor is not None:
                prices.append(event.gross_minor)
        normalize = lambda values: {
            key: round(value / max(values.values()), 6)
            for key, value in sorted(values.items(), key=lambda item: (-item[1], item[0]))
        } if values else {}
        return CustomerCommerceAffinity(
            offering_type_weights=normalize(types), tag_weights=normalize(tags),
            channel_weights=normalize(channels),
            typical_price_min_minor=min(prices) if prices else None,
            typical_price_max_minor=max(prices) if prices else None,
            recent_purchase_count=recent, historical_purchase_count=len(events),
        )

    @classmethod
    def _intent_event(cls, row):
        return CustomerPurchaseEvent(
            source_type="PURCHASE_INTENT", source_record_id=str(row["purchase_intent_id"]),
            creator_profile_id=int(row["creator_profile_id"]), fanvue_account_id=int(row["fanvue_account_id"]),
            purchased_at=row["purchased_at"], channel=row.get("primary_sales_channel"),
            sale_type=row.get("offering_type"), offering_id=UUID(str(row["commercial_offering_id"])),
            sales_session_id=UUID(str(row["sales_session_id"])) if row.get("sales_session_id") else None,
            asset_ids=tuple(int(value) for value in row.get("asset_ids") or ()),
            gross_minor=int(row["expected_price_minor"]), currency=row.get("expected_currency"),
            provider_transaction_reference=row.get("provider_transaction_order_id"),
            completion_state="PURCHASED_ATTRIBUTED",
            intelligence_tags=cls._tags(row.get("intelligence_profiles") or ()),
            provenance={"status": row.get("status"), "attributionResult": row.get("attribution_result")},
        )

    @staticmethod
    def _entitlement_event(row, identity):
        return CustomerPurchaseEvent(
            source_type="ENTITLEMENT", source_record_id=str(row["id"]),
            creator_profile_id=identity.creator_profile_id, fanvue_account_id=identity.fanvue_account_id,
            purchased_at=row.get("fulfilled_at") or row["granted_at"], channel=row.get("source_type"),
            sale_type=row.get("product_type"), product_id=UUID(str(row["product_id"])),
            asset_ids=tuple(int(value) for value in row.get("asset_ids") or ()),
            provider_transaction_reference=row.get("provider_transaction_id"),
            completion_state=str(row.get("status") or "").upper(),
            provenance={"commerceProvider": row.get("commerce_provider")},
        )

    @staticmethod
    def _legacy_event(row, identity):
        return CustomerPurchaseEvent(
            source_type="VAULT_UNLOCK" if row.get("usage_type") == "content_unlocked" else "LEGACY_ASSET_OWNERSHIP",
            source_record_id=str(row["id"]), creator_profile_id=identity.creator_profile_id,
            fanvue_account_id=identity.fanvue_account_id, purchased_at=row["purchased_at"],
            channel="TELEGRAM_WALL" if row.get("usage_type") == "content_unlocked" else "LEGACY",
            sale_type="SINGLE_IMAGE", asset_ids=(int(row["content_item_id"]),),
            completion_state="EXACT_ASSET_RESOLVED",
            provenance={"usageType": row.get("usage_type"), "contentTag": row.get("content_tag"),
                        "fanvueMediaUuidPresent": bool(row.get("fanvue_media_uuid"))},
        )

    @staticmethod
    def _tags(profiles):
        values = []
        for profile in profiles or ():
            if not isinstance(profile, dict):
                continue
            for key, item in profile.items():
                if key in {"keywords", "themes", "activity", "setting", "mood", "wardrobe"}:
                    values.extend(item if isinstance(item, list) else (item,))
        return tuple(dict.fromkeys(str(item).strip().lower() for item in values if str(item).strip()))

    @staticmethod
    def _active_state(intent):
        if intent is None:
            return {}
        return {"purchaseIntentId": str(intent.purchase_intent_id), "status": intent.status.value,
                "offeringId": str(intent.commercial_offering_id),
                "attributionResult": intent.attribution_result.value}

    @staticmethod
    def _aware(value):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

    @staticmethod
    def _iso(value):
        return value.isoformat() if value else None
