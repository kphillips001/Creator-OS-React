"""Persistence for ordered product-to-asset composition."""

from collections.abc import Callable, Iterable
from contextlib import contextmanager
from uuid import UUID

from app.database import get_db_connection
from app.models.product_asset import ProductAsset


class ProductAssetRepositoryError(Exception):
    pass


class ProductAssetRepository:
    def __init__(self, connection_factory: Callable = get_db_connection):
        self._connection_factory = connection_factory

    @contextmanager
    def _connection(self, connection=None):
        if connection is not None:
            yield connection
            return
        with self._connection_factory() as managed:
            yield managed

    def attach_primary(
        self,
        product_id: UUID,
        asset_id: int,
    ) -> tuple[ProductAsset, bool]:
        query = """
            INSERT INTO public.product_assets (
                product_id, asset_id, position, role, is_required,
                delivery_mode
            )
            VALUES (%s, %s, 0, 'primary', TRUE, 'protected')
            ON CONFLICT DO NOTHING
            RETURNING *;
        """
        with self._connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, (product_id, asset_id))
                row = cursor.fetchone()
                created = row is not None
                if not row:
                    cursor.execute(
                        """
                        SELECT * FROM public.product_assets
                        WHERE product_id = %s AND asset_id = %s
                          AND role = 'primary'
                        """,
                        (product_id, asset_id),
                    )
                    row = cursor.fetchone()
        if not row:
            raise ProductAssetRepositoryError(
                f"Product {product_id} has a conflicting position-zero asset"
            )
        return ProductAsset.from_row(row), created

    def replace_product_assets(
        self,
        product_id: UUID,
        asset_ids: Iterable[int],
        *,
        connection=None,
    ) -> list[ProductAsset]:
        ordered_ids = list(asset_ids)
        with self._connection(connection) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM public.product_assets WHERE product_id = %s",
                    (product_id,),
                )
                rows = []
                for position, asset_id in enumerate(ordered_ids):
                    cursor.execute(
                        """
                        INSERT INTO public.product_assets (
                            product_id, asset_id, position, role,
                            is_required, delivery_mode
                        )
                        VALUES (%s, %s, %s, 'primary', TRUE, 'protected')
                        RETURNING *
                        """,
                        (product_id, asset_id, position),
                    )
                    rows.append(cursor.fetchone())
        return [ProductAsset.from_row(row) for row in rows]

    def list_for_product(
        self,
        product_id: UUID,
        *,
        connection=None,
    ) -> list[ProductAsset]:
        with self._connection(connection) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT * FROM public.product_assets
                    WHERE product_id = %s
                    ORDER BY position
                    """,
                    (product_id,),
                )
                rows = cursor.fetchall()
        return [ProductAsset.from_row(row) for row in rows]

    def count_for_product(self, product_id: UUID) -> int:
        with self._connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(*) AS count FROM public.product_assets
                    WHERE product_id = %s
                    """,
                    (product_id,),
                )
                return cursor.fetchone()["count"]

    def count_products_for_asset(self, asset_id: int) -> int:
        with self._connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(DISTINCT product_id) AS count
                    FROM public.product_assets
                    WHERE asset_id = %s
                    """,
                    (asset_id,),
                )
                return cursor.fetchone()["count"]

    def list_product_ids_for_asset(self, asset_id: int) -> tuple[UUID, ...]:
        with self._connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT DISTINCT product_id
                    FROM public.product_assets
                    WHERE asset_id = %s
                    ORDER BY product_id
                    """,
                    (asset_id,),
                )
                rows = cursor.fetchall()
        return tuple(row["product_id"] for row in rows)

    def delete_for_product(
        self,
        product_id: UUID,
        *,
        connection=None,
    ) -> int:
        with self._connection(connection) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM public.product_assets
                    WHERE product_id = %s
                    """,
                    (product_id,),
                )
                return cursor.rowcount
