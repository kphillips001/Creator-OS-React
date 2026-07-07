"""Persistence for account-scoped product catalog records."""

import json
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4

from app.database import get_db_connection
from app.models.asset import Asset
from app.models.product import (
    Product,
    ProductApprovalStatus,
    ProductDeliveryType,
    ProductStatus,
    ProductType,
    default_fulfillment_strategy,
    fulfillment_status_for_media_link,
    normalize_product_delivery_type,
    product_metadata_with_delivery_type,
    product_metadata_with_approval,
)


class ProductRepositoryError(Exception):
    pass


class ProductRepository:
    def __init__(self, connection_factory: Callable = get_db_connection):
        self._connection_factory = connection_factory

    @contextmanager
    def _connection(self, connection=None):
        if connection is not None:
            yield connection
            return
        with self._connection_factory() as managed:
            yield managed

    @staticmethod
    def _draft_values(asset: Asset) -> dict:
        # Legacy backfill path: creates a Product Draft from a source Asset.
        # The Product should own commerce fields; Asset analysis is copied only
        # as draft input until the lifecycles are split more cleanly.
        product_type = {
            "image": ProductType.SINGLE_IMAGE,
            "video": ProductType.SINGLE_VIDEO,
        }.get(asset.media_type, ProductType.CUSTOM)
        fallback_name = Path(asset.file_path).name or f"Content {asset.id}"
        return {
            "id": uuid4(),
            "legacy_content_item_id": asset.id,
            "internal_name": f"legacy-content-{asset.id}",
            "product_type": product_type.value,
            "fulfillment_strategy": default_fulfillment_strategy(product_type).value,
            "fulfillment_status": fulfillment_status_for_media_link(None).value,
            "display_name": asset.file_name or fallback_name,
            "metadata": json.dumps(
                product_metadata_with_delivery_type({
                    "backfill_source": "content_items",
                    "legacy_content_item_id": asset.id,
                })
            ),
        }

    def create_draft_for_asset(self, asset: Asset) -> tuple[Product, bool]:
        values = self._draft_values(asset)
        query = """
            INSERT INTO public.products (
                id, legacy_content_item_id, internal_name, product_type,
                fulfillment_strategy, fulfillment_status, display_name, status,
                price_cents, currency, access_type, metadata
            )
            VALUES (
                %(id)s, %(legacy_content_item_id)s, %(internal_name)s,
                %(product_type)s, %(fulfillment_strategy)s,
                %(fulfillment_status)s, %(display_name)s, 'DRAFT', NULL,
                'USD', 'permanent', %(metadata)s::jsonb
            )
            ON CONFLICT DO NOTHING
            RETURNING *;
        """
        with self._connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, values)
                row = cursor.fetchone()
                created = row is not None
                if not row:
                    cursor.execute(
                        """
                        SELECT * FROM public.products
                        WHERE legacy_content_item_id = %s
                        LIMIT 1
                        """,
                        (asset.id,),
                    )
                    row = cursor.fetchone()
        if not row:
            raise ProductRepositoryError(
                f"Product conflict for legacy content item {asset.id}"
            )
        return Product.from_row(row), created

    def create_product(
        self,
        *,
        creator_profile_id: int,
        internal_name: str,
        display_name: str,
        description: str | None,
        product_type: ProductType,
        status: ProductStatus,
        price_cents: int | None,
        currency: str,
        media_link: str | None,
        tags: tuple[str, ...],
        themes: tuple[str, ...],
        delivery_type: ProductDeliveryType | str | None = None,
        connection=None,
    ) -> Product:
        metadata = product_metadata_with_delivery_type(
            {
                "creation_source": "manual",
                "manual_product": True,
            },
            delivery_type,
        )
        metadata = product_metadata_with_approval(
            metadata,
            ProductApprovalStatus.NEEDS_REVIEW,
        )
        query = """
            INSERT INTO public.products (
                id, creator_profile_id, internal_name, display_name,
                description, product_type, fulfillment_strategy, status,
                price_cents, currency, media_link, fulfillment_status, tags,
                themes, access_type, metadata
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, 'permanent', %s::jsonb
            )
            RETURNING *;
        """
        with self._connection(connection) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    query,
                    (
                        uuid4(), creator_profile_id, internal_name,
                        display_name, description, product_type.value,
                        default_fulfillment_strategy(product_type).value,
                        status.value, price_cents, currency, media_link,
                        fulfillment_status_for_media_link(media_link).value,
                        list(tags), list(themes), json.dumps(metadata),
                    ),
                )
                row = cursor.fetchone()
        return Product.from_row(row)

    def create_ai_draft_product(
        self,
        *,
        asset: Asset,
        creator_profile_id: int,
        internal_name: str,
        display_name: str,
        description: str | None,
        product_type: ProductType,
        tags: tuple[str, ...],
        themes: tuple[str, ...],
        metadata: dict,
        delivery_type: ProductDeliveryType | str | None = None,
        connection=None,
    ) -> tuple[Product, bool]:
        # Compatibility boundary: persistence remains keyed by the legacy
        # source Asset/content_items row. Product-facing draft interpretation
        # happens in AIProductDraftingService via ProductDraftSource.
        query = """
            INSERT INTO public.products (
                id, creator_profile_id, legacy_content_item_id, internal_name,
                display_name, description, product_type, fulfillment_strategy,
                status, price_cents, currency, media_link, fulfillment_status,
                tags, themes, access_type, metadata
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, 'DRAFT', NULL, 'USD', NULL,
                %s, %s, %s, 'permanent', %s::jsonb
            )
            ON CONFLICT DO NOTHING
            RETURNING *;
        """
        with self._connection(connection) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    query,
                    (
                        uuid4(), creator_profile_id, asset.id, internal_name,
                        display_name, description, product_type.value,
                        default_fulfillment_strategy(product_type).value,
                        fulfillment_status_for_media_link(None).value,
                        list(tags), list(themes), json.dumps(
                            product_metadata_with_delivery_type(
                                metadata,
                                delivery_type,
                            )
                        ),
                    ),
                )
                row = cursor.fetchone()
                created = row is not None
                if not row:
                    cursor.execute(
                        """
                        SELECT * FROM public.products
                        WHERE legacy_content_item_id = %s
                        LIMIT 1
                        """,
                        (asset.id,),
                    )
                    row = cursor.fetchone()
        if not row:
            raise ProductRepositoryError(
                f"Product conflict for legacy content item {asset.id}"
            )
        return Product.from_row(row), created

    def apply_ai_draft_fields(
        self,
        *,
        product_id: UUID,
        creator_profile_id: int,
        display_name: str,
        description: str | None,
        product_type: ProductType,
        tags: tuple[str, ...],
        themes: tuple[str, ...],
        metadata: dict,
        delivery_type: ProductDeliveryType | str | None = None,
        connection=None,
    ) -> Product | None:
        query = """
            UPDATE public.products
            SET display_name = %s,
                description = %s,
                product_type = %s,
                fulfillment_strategy = %s,
                tags = %s,
                themes = %s,
                metadata = %s::jsonb,
                updated_at = NOW()
            WHERE id = %s
              AND creator_profile_id = %s
              AND status = 'DRAFT'
            RETURNING *;
        """
        with self._connection(connection) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    query,
                    (
                        display_name, description, product_type.value,
                        default_fulfillment_strategy(product_type).value,
                        list(tags), list(themes), json.dumps(
                            product_metadata_with_delivery_type(
                                metadata,
                                delivery_type,
                            )
                        ),
                        product_id, creator_profile_id,
                    ),
                )
                row = cursor.fetchone()
        return Product.from_row(row) if row else None

    def activate_ai_product(
        self,
        *,
        product_id: UUID,
        creator_profile_id: int,
        base_price_cents: int,
        min_price_cents: int,
        max_price_cents: int,
        media_link: str,
        activation_source: str,
        activation_reason: str,
        metadata: dict,
        delivery_type: ProductDeliveryType | str | None = None,
        connection=None,
    ) -> Product | None:
        query = """
            UPDATE public.products
            SET status = 'ACTIVE',
                price_cents = %s,
                base_price_cents = %s,
                min_price_cents = %s,
                max_price_cents = %s,
                media_link = %s,
                fulfillment_status = %s,
                activation_source = %s,
                activation_reason = %s,
                activated_at = COALESCE(activated_at, NOW()),
                metadata = %s::jsonb,
                updated_at = NOW()
            WHERE id = %s
              AND creator_profile_id = %s
              AND status = 'DRAFT'
            RETURNING *;
        """
        with self._connection(connection) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    query,
                    (
                        base_price_cents,
                        base_price_cents,
                        min_price_cents,
                        max_price_cents,
                        media_link,
                        fulfillment_status_for_media_link(media_link).value,
                        activation_source,
                        activation_reason,
                        json.dumps(
                            product_metadata_with_delivery_type(
                                metadata,
                                delivery_type,
                            )
                        ),
                        product_id,
                        creator_profile_id,
                    ),
                )
                row = cursor.fetchone()
        return Product.from_row(row) if row else None

    def update_product(
        self,
        *,
        product_id: UUID,
        creator_profile_id: int,
        internal_name: str,
        display_name: str,
        description: str | None,
        product_type: ProductType,
        status: ProductStatus,
        price_cents: int | None,
        currency: str,
        media_link: str | None,
        tags: tuple[str, ...],
        themes: tuple[str, ...],
        delivery_type: ProductDeliveryType | str | None = None,
        connection=None,
    ) -> Product | None:
        normalized_delivery_type = normalize_product_delivery_type(
            delivery_type
        )
        query = """
            UPDATE public.products
            SET internal_name = %s,
                display_name = %s,
                description = %s,
                product_type = %s,
                fulfillment_strategy = %s,
                status = %s,
                price_cents = %s,
                currency = %s,
                media_link = %s,
                fulfillment_status = %s,
                tags = %s,
                themes = %s,
                metadata = jsonb_set(
                    COALESCE(metadata, '{}'::jsonb),
                    '{delivery_type}',
                    %s::jsonb
                ),
                updated_at = NOW()
            WHERE id = %s
              AND creator_profile_id = %s
            RETURNING *;
        """
        with self._connection(connection) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    query,
                    (
                        internal_name, display_name, description,
                        product_type.value,
                        default_fulfillment_strategy(product_type).value,
                        status.value, price_cents, currency, media_link,
                        fulfillment_status_for_media_link(media_link).value,
                        list(tags), list(themes),
                        json.dumps(normalized_delivery_type.value),
                        product_id,
                        creator_profile_id,
                    ),
                )
                row = cursor.fetchone()
        return Product.from_row(row) if row else None

    def update_media_link(
        self,
        *,
        product_id: UUID,
        creator_profile_id: int,
        media_link: str | None,
        connection=None,
    ) -> Product | None:
        query = """
            UPDATE public.products
            SET media_link = %s,
                fulfillment_status = %s,
                updated_at = NOW()
            WHERE id = %s
              AND creator_profile_id = %s
            RETURNING *;
        """
        with self._connection(connection) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    query,
                    (
                        media_link,
                        fulfillment_status_for_media_link(media_link).value,
                        product_id,
                        creator_profile_id,
                    ),
                )
                row = cursor.fetchone()
        return Product.from_row(row) if row else None

    def get_by_media_link(
        self,
        media_link: str,
        *,
        creator_profile_id: int | None = None,
        connection=None,
    ) -> Product | None:
        filters = ["media_link = %s"]
        params: list[Any] = [media_link]
        if creator_profile_id is not None:
            filters.append("creator_profile_id = %s")
            params.append(creator_profile_id)
        query = f"""
            SELECT *
            FROM public.products
            WHERE {' AND '.join(filters)}
            ORDER BY updated_at DESC
            LIMIT 1;
        """
        with self._connection(connection) as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, tuple(params))
                row = cursor.fetchone()
        return Product.from_row(row) if row else None

    def update_approval_metadata(
        self,
        *,
        product_id: UUID,
        creator_profile_id: int,
        approval_status: ProductApprovalStatus | str,
        reviewed_by: str | None = None,
        notes: str | None = None,
        connection=None,
    ) -> Product | None:
        product = self.get_by_id(
            product_id,
            creator_profile_id=creator_profile_id,
            connection=connection,
        )
        if not product:
            return None
        metadata = product_metadata_with_approval(
            product.metadata,
            approval_status,
            reviewed_by=reviewed_by,
            notes=notes,
        )
        query = """
            UPDATE public.products
            SET metadata = %s::jsonb,
                updated_at = NOW()
            WHERE id = %s
              AND creator_profile_id = %s
            RETURNING *;
        """
        with self._connection(connection) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    query,
                    (
                        json.dumps(metadata),
                        product_id,
                        creator_profile_id,
                    ),
                )
                row = cursor.fetchone()
        return Product.from_row(row) if row else None

    def get_by_id(
        self,
        product_id: UUID,
        *,
        creator_profile_id: int | None = None,
        connection=None,
    ) -> Product | None:
        scope = "" if creator_profile_id is None else "AND creator_profile_id = %s"
        params = (product_id,) if creator_profile_id is None else (
            product_id, creator_profile_id,
        )
        with self._connection(connection) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT * FROM public.products WHERE id = %s {scope}",
                    params,
                )
                row = cursor.fetchone()
        return Product.from_row(row) if row else None

    def get_by_legacy_content_item_id(self, asset_id: int) -> Product | None:
        with self._connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT * FROM public.products
                    WHERE legacy_content_item_id = %s
                    """,
                    (asset_id,),
                )
                row = cursor.fetchone()
        return Product.from_row(row) if row else None

    def list_products(
        self,
        *,
        creator_profile_id: int,
        search: str | None = None,
        status: ProductStatus | None = None,
        product_type: ProductType | None = None,
        tag: str | None = None,
        theme: str | None = None,
        include_archived: bool = False,
        limit: int = 500,
    ) -> list[Product]:
        filters = ["creator_profile_id = %s"]
        params: list = [creator_profile_id]
        if search:
            filters.append(
                "(internal_name ILIKE %s OR display_name ILIKE %s "
                "OR COALESCE(description, '') ILIKE %s)"
            )
            term = f"%{search.strip()}%"
            params.extend((term, term, term))
        if status:
            filters.append("status = %s")
            params.append(status.value)
        elif not include_archived:
            filters.append("status <> 'ARCHIVED'")
        if product_type:
            filters.append("product_type = %s")
            params.append(product_type.value)
        if tag:
            filters.append("%s = ANY(tags)")
            params.append(tag.strip().lower())
        if theme:
            filters.append(
                "LOWER(%s) IN (SELECT LOWER(x) FROM UNNEST(themes) AS x)"
            )
            params.append(theme.strip())
        params.append(limit)
        query = f"""
            SELECT * FROM public.products
            WHERE {' AND '.join(filters)}
            ORDER BY updated_at DESC, display_name ASC
            LIMIT %s
        """
        with self._connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, tuple(params))
                rows = cursor.fetchall()
        return [Product.from_row(row) for row in rows]

    def list_unassigned_drafts(self, limit: int = 500) -> list[Product]:
        with self._connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT * FROM public.products
                    WHERE creator_profile_id IS NULL AND status = 'DRAFT'
                    ORDER BY legacy_content_item_id NULLS LAST, created_at
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = cursor.fetchall()
        return [Product.from_row(row) for row in rows]

    def assign_to_creator(
        self,
        product_id: UUID,
        creator_profile_id: int,
    ) -> Product | None:
        with self._connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE public.products
                    SET creator_profile_id = %s, updated_at = NOW()
                    WHERE id = %s
                      AND creator_profile_id IS NULL
                      AND status = 'DRAFT'
                    RETURNING *
                    """,
                    (creator_profile_id, product_id),
                )
                row = cursor.fetchone()
        return Product.from_row(row) if row else None

    def archive_product(
        self,
        *,
        product_id: UUID,
        creator_profile_id: int,
        connection=None,
    ) -> Product | None:
        query = """
            UPDATE public.products
            SET status = 'ARCHIVED',
                updated_at = NOW()
            WHERE id = %s
              AND creator_profile_id = %s
            RETURNING *
        """
        with self._connection(connection) as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, (product_id, creator_profile_id))
                row = cursor.fetchone()
        return Product.from_row(row) if row else None

    def count_by_status(self, creator_profile_id: int) -> dict[str, int]:
        with self._connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT status, COUNT(*) AS count
                    FROM public.products
                    WHERE creator_profile_id = %s
                    GROUP BY status
                    """,
                    (creator_profile_id,),
                )
                rows = cursor.fetchall()
        counts = {status.value: 0 for status in ProductStatus}
        counts.update({row["status"]: row["count"] for row in rows})
        return counts

    def internal_name_exists(
        self,
        internal_name: str,
        *,
        excluding_product_id: UUID | None = None,
    ) -> bool:
        query = "SELECT 1 FROM public.products WHERE internal_name = %s"
        params: list = [internal_name]
        if excluding_product_id:
            query += " AND id <> %s"
            params.append(excluding_product_id)
        query += " LIMIT 1"
        with self._connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, tuple(params))
                return cursor.fetchone() is not None
