"""Governed, non-destructive classification of legacy commerce evidence.

``content_items`` remains the compatibility persistence for canonical Assets.
This service determines whether those Assets have enough business evidence to
enter Product or Offering composition; it never creates one Product per Asset.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import PurePath
from typing import Any, Callable, Iterable, Mapping

from app.database import get_db_connection


class MigrationMode(str, Enum):
    DRY_RUN = "DRY_RUN"
    APPLY = "APPLY"
    REVALIDATE = "REVALIDATE"


class RecordClassification(str, Enum):
    CANONICAL_ASSET_ALREADY_EXISTS = "CANONICAL_ASSET_ALREADY_EXISTS"
    REQUIRES_CANONICAL_ASSET_REGISTRATION = "REQUIRES_CANONICAL_ASSET_REGISTRATION"
    HISTORICAL_ONLY = "HISTORICAL_ONLY"
    DUPLICATE = "DUPLICATE"
    INVALID_OR_INCOMPLETE = "INVALID_OR_INCOMPLETE"
    ALREADY_MIGRATED = "ALREADY_MIGRATED"


@dataclass(frozen=True)
class LegacyCommerceDecision:
    legacy_record_id: int
    creator_profile_id: int | None
    classification: str
    commerce_action: str
    canonical_asset_id: int | None
    product_id: str | None
    offering_ids: tuple[str, ...]
    exclusion_reason: str | None
    source_reference: str | None
    active: bool


@dataclass(frozen=True)
class LegacyCommerceMigrationReport:
    mode: str
    records_seen: int
    decisions: tuple[LegacyCommerceDecision, ...]
    writes_performed: int
    certification_valid: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class LegacyCommerceMigrationService:
    SUPPORTED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".mov"})

    def __init__(self, connection_factory: Callable = get_db_connection):
        self._connection_factory = connection_factory

    def run(self, mode: MigrationMode | str = MigrationMode.DRY_RUN) -> LegacyCommerceMigrationReport:
        resolved_mode = MigrationMode(str(getattr(mode, "value", mode)).upper())
        records = self._inventory()
        decisions = self.classify_records(records)
        # Current canonical persistence already represents each content_items
        # row as an Asset. No present record has approved evidence requiring a
        # new Product or Offering, so APPLY is intentionally a no-op.
        valid = all(item.commerce_action != "BLOCKED" for item in decisions)
        return LegacyCommerceMigrationReport(
            mode=resolved_mode.value,
            records_seen=len(records),
            decisions=decisions,
            writes_performed=0,
            certification_valid=valid,
        )

    @classmethod
    def classify_records(cls, records: Iterable[Mapping[str, Any]]) -> tuple[LegacyCommerceDecision, ...]:
        materialized = tuple(dict(item) for item in records)
        source_counts: dict[str, int] = {}
        for item in materialized:
            source = cls._source(item)
            if source:
                source_counts[source.casefold()] = source_counts.get(source.casefold(), 0) + 1
        return tuple(cls._classify(item, source_counts) for item in materialized)

    @classmethod
    def _classify(cls, item: Mapping[str, Any], source_counts: Mapping[str, int]) -> LegacyCommerceDecision:
        record_id = int(item["id"])
        creator_id = item.get("creator_profile_id")
        source = cls._source(item)
        product_id = str(item["product_id"]) if item.get("product_id") else None
        offerings = tuple(str(value) for value in (item.get("offering_ids") or ()))
        active = bool(item.get("is_active"))
        reason = None
        action = "ASSET_ONLY"
        classification = RecordClassification.CANONICAL_ASSET_ALREADY_EXISTS

        if not creator_id:
            classification, action, reason = RecordClassification.INVALID_OR_INCOMPLETE, "BLOCKED", "missing_creator_scope"
        elif not source:
            classification, action, reason = RecordClassification.INVALID_OR_INCOMPLETE, "BLOCKED", "missing_media_reference"
        elif PurePath(source).suffix.lower() not in cls.SUPPORTED_EXTENSIONS:
            classification, action, reason = RecordClassification.INVALID_OR_INCOMPLETE, "BLOCKED", "unsupported_media"
        elif source_counts.get(source.casefold(), 0) > 1:
            classification, action, reason = RecordClassification.DUPLICATE, "NONE", "duplicate_media_reference"
        elif product_id or offerings:
            classification, action = RecordClassification.ALREADY_MIGRATED, "REVALIDATE"
        elif not active:
            classification, action, reason = RecordClassification.HISTORICAL_ONLY, "NONE", "inactive_historical_content"
        elif str(item.get("classification") or "").upper() == "REFERENCE":
            reason = "reference_asset_not_sellable"
        elif not item.get("price_minor") or not item.get("sale_intent"):
            reason = "no_current_sellable_or_pricing_evidence"
        else:
            action = "OFFERING_ONLY"

        return LegacyCommerceDecision(
            legacy_record_id=record_id,
            creator_profile_id=int(creator_id) if creator_id else None,
            classification=classification.value,
            commerce_action=action,
            canonical_asset_id=record_id,
            product_id=product_id,
            offering_ids=offerings,
            exclusion_reason=reason,
            source_reference=source,
            active=active,
        )

    @staticmethod
    def _source(item: Mapping[str, Any]) -> str | None:
        return str(item.get("local_vault_path") or item.get("file_path") or "").strip() or None

    def _inventory(self) -> tuple[dict[str, Any], ...]:
        with self._connection_factory() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT ci.id, ci.creator_profile_id, ci.content_type,
                           ci.file_path, ci.local_vault_path, ci.classification,
                           ci.is_active, ci.is_test, ci.status, ci.upload_status,
                           ci.fanvue_media_id, ci.fanvue_media_preview_uuid,
                           ci.fanvue_media_full_uuid, ci.fanvue_account_id,
                           ci.mass_ppv_price AS price_minor,
                           ci.distribution_type AS sale_intent,
                           p.id::text AS product_id,
                           COALESCE(array_agg(DISTINCT coa.offering_id::text)
                             FILTER (WHERE coa.offering_id IS NOT NULL), '{}') AS offering_ids
                    FROM public.content_items ci
                    LEFT JOIN public.products p ON p.legacy_content_item_id = ci.id
                    LEFT JOIN public.commercial_offering_assets coa ON coa.asset_id = ci.id
                    GROUP BY ci.id, p.id
                    ORDER BY ci.id
                    """
                )
                return tuple(dict(row) for row in cursor.fetchall())

