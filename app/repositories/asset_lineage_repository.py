"""PostgreSQL persistence for canonical Asset-to-Asset lineage."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from uuid import UUID

from app.database import get_db_connection
from app.models.asset_lineage import AssetLineageRelationship, DerivationKind


class AssetLineageRepository:
    def __init__(self, connection_factory: Callable = get_db_connection) -> None:
        self._connection_factory = connection_factory

    def create(self, relationship: AssetLineageRelationship) -> AssetLineageRelationship:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                # Serialize lineage graph mutations so the service-level cycle
                # check cannot be invalidated by a concurrent relationship.
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", (52734054,))
                cursor.execute(
                    """SELECT 1 FROM public.asset_lineage_relationships
                       WHERE derived_asset_id=%s LIMIT 1""",
                    (relationship.derived_asset_id,),
                )
                if cursor.fetchone() is not None:
                    raise ValueError(
                        "A Derived Asset already has a canonical derivation relationship."
                    )
                cursor.execute(
                    """WITH RECURSIVE descendants(asset_id,path) AS (
                        SELECT derived_asset_id,
                               ARRAY[%s::bigint,derived_asset_id]
                        FROM public.asset_lineage_relationships
                        WHERE source_asset_id=%s
                        UNION ALL
                        SELECT edge.derived_asset_id,
                               descendants.path||edge.derived_asset_id
                        FROM descendants
                        JOIN public.asset_lineage_relationships edge
                          ON edge.source_asset_id=descendants.asset_id
                        WHERE NOT edge.derived_asset_id=ANY(descendants.path)
                    )
                    SELECT 1 FROM descendants WHERE asset_id=ANY(%s) LIMIT 1""",
                    (
                        relationship.derived_asset_id,
                        relationship.derived_asset_id,
                        list(relationship.source_asset_ids),
                    ),
                )
                if cursor.fetchone() is not None:
                    raise ValueError(
                        "Asset Lineage relationships cannot create cycles."
                    )
                for position, source_asset_id in enumerate(relationship.source_asset_ids):
                    cursor.execute(
                        """INSERT INTO public.asset_lineage_relationships
                           (relationship_id,source_asset_id,derived_asset_id,
                            source_position,derivation_kind,provenance)
                           VALUES (%s,%s,%s,%s,%s,%s::jsonb)""",
                        (
                            relationship.relationship_id, source_asset_id,
                            relationship.derived_asset_id, position,
                            relationship.derivation_kind.value,
                            json.dumps(dict(relationship.provenance), default=str),
                        ),
                    )
        return self.get(relationship.relationship_id)

    def get(self, relationship_id: UUID) -> AssetLineageRelationship | None:
        rows = self._rows(
            """SELECT * FROM public.asset_lineage_relationships
               WHERE relationship_id=%s ORDER BY source_position,source_asset_id""",
            (relationship_id,),
        )
        return self._relationship(rows) if rows else None

    def relationships_for_asset(self, asset_id: int) -> tuple[AssetLineageRelationship, ...]:
        rows = self._rows(
            """SELECT * FROM public.asset_lineage_relationships
               WHERE relationship_id IN (
                   SELECT relationship_id FROM public.asset_lineage_relationships
                   WHERE source_asset_id=%s OR derived_asset_id=%s
               ) ORDER BY created_at,relationship_id,source_position""",
            (int(asset_id), int(asset_id)),
        )
        return self._group(rows)

    def parents(self, asset_id: int) -> tuple[int, ...]:
        return self._asset_ids(
            """SELECT source_asset_id AS asset_id
               FROM public.asset_lineage_relationships
               WHERE derived_asset_id=%s ORDER BY source_position,source_asset_id""",
            (int(asset_id),),
        )

    def children(self, asset_id: int) -> tuple[int, ...]:
        return self._asset_ids(
            """SELECT DISTINCT derived_asset_id AS asset_id
               FROM public.asset_lineage_relationships
               WHERE source_asset_id=%s ORDER BY asset_id""",
            (int(asset_id),),
        )

    def ancestors(self, asset_id: int) -> tuple[tuple[int, int], ...]:
        return self._traversal(asset_id, reverse=True)

    def descendants(self, asset_id: int) -> tuple[tuple[int, int], ...]:
        return self._traversal(asset_id, reverse=False)

    def photoshoot_memberships(
        self, asset_ids: Iterable[int],
    ) -> tuple[dict, ...]:
        ids = tuple(dict.fromkeys(int(value) for value in asset_ids))
        if not ids:
            return ()
        return tuple(self._rows(
            """SELECT photoshoot_session_id,asset_id
               FROM public.photoshoot_asset_memberships
               WHERE approved=TRUE AND asset_id=ANY(%s)
               ORDER BY photoshoot_session_id,asset_id""",
            (list(ids),),
        ))

    def _traversal(self, asset_id: int, *, reverse: bool) -> tuple[tuple[int, int], ...]:
        first = "source_asset_id" if reverse else "derived_asset_id"
        anchor = "derived_asset_id" if reverse else "source_asset_id"
        join_left = "edge.derived_asset_id" if reverse else "edge.source_asset_id"
        sql = f"""WITH RECURSIVE lineage(asset_id,depth,path) AS (
            SELECT {first},1,ARRAY[%s::bigint,{first}]
            FROM public.asset_lineage_relationships WHERE {anchor}=%s
            UNION ALL
            SELECT edge.{first},lineage.depth+1,lineage.path||edge.{first}
            FROM lineage JOIN public.asset_lineage_relationships edge
              ON {join_left}=lineage.asset_id
            WHERE NOT edge.{first}=ANY(lineage.path)
        )
        SELECT asset_id,MIN(depth) AS depth FROM lineage
        GROUP BY asset_id ORDER BY MIN(depth),asset_id"""
        return tuple(
            (int(row["asset_id"]), int(row["depth"]))
            for row in self._rows(sql, (int(asset_id), int(asset_id)))
        )

    def _asset_ids(self, sql: str, params: tuple) -> tuple[int, ...]:
        return tuple(int(row["asset_id"]) for row in self._rows(sql, params))

    def _rows(self, sql: str, params: tuple) -> list[dict]:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                return [dict(row) for row in cursor.fetchall()]

    @classmethod
    def _group(cls, rows: list[dict]) -> tuple[AssetLineageRelationship, ...]:
        grouped: dict[UUID, list[dict]] = {}
        for row in rows:
            grouped.setdefault(UUID(str(row["relationship_id"])), []).append(row)
        return tuple(cls._relationship(values) for values in grouped.values())

    @classmethod
    def _relationship(cls, rows: list[dict]) -> AssetLineageRelationship:
        first = rows[0]
        return AssetLineageRelationship(
            relationship_id=UUID(str(first["relationship_id"])),
            source_asset_ids=tuple(int(row["source_asset_id"]) for row in rows),
            derived_asset_id=int(first["derived_asset_id"]),
            derivation_kind=DerivationKind(first["derivation_kind"]),
            provenance=cls._mapping(first.get("provenance")),
            created_at=first.get("created_at"),
        )

    @staticmethod
    def _mapping(value) -> dict:
        if isinstance(value, Mapping):
            return dict(value)
        if isinstance(value, str):
            parsed = json.loads(value)
            return dict(parsed) if isinstance(parsed, Mapping) else {}
        return {}
