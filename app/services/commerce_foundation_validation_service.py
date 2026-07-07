"""Read-only validation for the Phase 1C commerce foundation."""

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass

from app.database import get_db_connection


@dataclass(frozen=True)
class CommerceValidationResult:
    valid: bool
    content_item_count: int
    legacy_product_count: int
    product_asset_count: int
    correctly_linked_product_count: int
    customer_entitlement_count: int
    missing_product_asset_ids: tuple[int, ...]
    non_draft_asset_ids: tuple[int, ...]
    invalid_product_asset_pairs: tuple[str, ...]
    orphan_product_asset_pairs: tuple[str, ...]


class CommerceFoundationValidationService:
    def __init__(self, connection_factory: Callable = get_db_connection):
        self._connection_factory = connection_factory

    def validate(self) -> CommerceValidationResult:
        with self._connection_factory() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS count FROM public.content_items")
                content_count = cursor.fetchone()["count"]

                cursor.execute(
                    """
                    SELECT COUNT(*) AS count FROM public.products
                    WHERE legacy_content_item_id IS NOT NULL
                    """
                )
                product_count = cursor.fetchone()["count"]

                cursor.execute(
                    "SELECT COUNT(*) AS count FROM public.product_assets"
                )
                product_asset_count = cursor.fetchone()["count"]

                cursor.execute(
                    "SELECT COUNT(*) AS count FROM public.customer_entitlements"
                )
                entitlement_count = cursor.fetchone()["count"]

                cursor.execute(
                    """
                    SELECT ci.id
                    FROM public.content_items ci
                    LEFT JOIN public.products p
                      ON p.legacy_content_item_id = ci.id
                    WHERE p.id IS NULL
                    ORDER BY ci.id
                    """
                )
                missing = tuple(row["id"] for row in cursor.fetchall())

                cursor.execute(
                    """
                    SELECT legacy_content_item_id AS id
                    FROM public.products
                    WHERE legacy_content_item_id IS NOT NULL
                      AND status <> 'DRAFT'
                    ORDER BY legacy_content_item_id
                    """
                )
                non_draft = tuple(row["id"] for row in cursor.fetchall())

                cursor.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM public.products p
                    INNER JOIN public.product_assets pa
                      ON pa.product_id = p.id
                     AND pa.asset_id = p.legacy_content_item_id
                     AND pa.position = 0
                     AND pa.role = 'primary'
                    WHERE p.legacy_content_item_id IS NOT NULL
                    """
                )
                linked_count = cursor.fetchone()["count"]

                cursor.execute(
                    """
                    SELECT p.id::text AS product_id, p.legacy_content_item_id,
                           pa.asset_id
                    FROM public.products p
                    LEFT JOIN public.product_assets pa
                      ON pa.product_id = p.id
                     AND pa.position = 0
                     AND pa.role = 'primary'
                    WHERE p.legacy_content_item_id IS NOT NULL
                      AND (
                        pa.asset_id IS NULL
                        OR pa.asset_id <> p.legacy_content_item_id
                      )
                    ORDER BY p.legacy_content_item_id
                    """
                )
                invalid = tuple(
                    f"{row['product_id']}:{row['legacy_content_item_id']}:{row['asset_id']}"
                    for row in cursor.fetchall()
                )

                cursor.execute(
                    """
                    SELECT pa.product_id::text AS product_id, pa.asset_id
                    FROM public.product_assets pa
                    LEFT JOIN public.products p ON p.id = pa.product_id
                    LEFT JOIN public.content_items ci ON ci.id = pa.asset_id
                    WHERE p.id IS NULL OR ci.id IS NULL
                    ORDER BY pa.product_id, pa.asset_id
                    """
                )
                orphaned = tuple(
                    f"{row['product_id']}:{row['asset_id']}"
                    for row in cursor.fetchall()
                )

        valid = (
            content_count == product_count == product_asset_count == linked_count
            and not missing
            and not invalid
            and not orphaned
        )
        return CommerceValidationResult(
            valid=valid,
            content_item_count=content_count,
            legacy_product_count=product_count,
            product_asset_count=product_asset_count,
            correctly_linked_product_count=linked_count,
            customer_entitlement_count=entitlement_count,
            missing_product_asset_ids=missing,
            non_draft_asset_ids=non_draft,
            invalid_product_asset_pairs=invalid,
            orphan_product_asset_pairs=orphaned,
        )


def main() -> None:
    result = CommerceFoundationValidationService().validate()
    print(json.dumps(asdict(result), indent=2, sort_keys=True))
    if not result.valid:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
