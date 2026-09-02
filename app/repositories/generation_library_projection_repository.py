"""Indexed, derived read model for Generation Library browse and staged cards."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable

from app.database import get_db_connection
from app.models.generation_library import GeneratedImageRecord, GenerationLibraryFilter


class GenerationLibraryProjectionRepository:
    PROJECTION_NAME = "canonical_generation_library_json_v1"
    DISPOSITION_CLAUSE = """NOT EXISTS (
        SELECT 1 FROM public.generation_image_dispositions d
        WHERE d.image_id=generation_library_read_projection.image_id)"""
    EFFECTIVE_CLASSIFICATION_SQL = """COALESCE(
        (SELECT manual.content_classification FROM public.generation_library_content_classifications manual
         WHERE manual.image_id=generation_library_read_projection.image_id),
        (SELECT CASE
           WHEN canonical.record_payload->'generation_metadata'->'request_metadata'->>'workflow_origin'='autonomous_inspiration' THEN 'SFW'
           WHEN canonical.record_payload->'generation_metadata'->'request_metadata'->>'workflow_origin'=ANY(ARRAY['explicit_tags','explicit_inspiration']) THEN 'NSFW'
         END FROM public.generation_library_records canonical
         WHERE canonical.image_id=generation_library_read_projection.image_id)
    )"""
    CLASSIFICATION_SOURCE_SQL = """CASE
        WHEN EXISTS (SELECT 1 FROM public.generation_library_content_classifications manual
                     WHERE manual.image_id=generation_library_read_projection.image_id) THEN 'MANUAL'
        WHEN EXISTS (SELECT 1 FROM public.generation_library_records canonical
                     WHERE canonical.image_id=generation_library_read_projection.image_id
                       AND canonical.record_payload->'generation_metadata'->'request_metadata'->>'workflow_origin'=ANY(ARRAY['autonomous_inspiration','explicit_tags','explicit_inspiration'])) THEN 'WORKFLOW'
        ELSE NULL END"""

    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def source_version(self) -> str | None:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT source_version FROM public.generation_library_projection_state WHERE projection_name=%s", (self.PROJECTION_NAME,))
            row = cursor.fetchone()
        return str(row["source_version"]) if row else None

    def synchronize(self, records: Iterable[GeneratedImageRecord], *, source_version: str) -> int:
        records = tuple(records)
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (self.PROJECTION_NAME,))
            if records:
                cursor.executemany(
                    """INSERT INTO public.generation_library_read_projection(
                         image_id,generation_job_id,output_reference,creator_profile_id,provider_id,
                         prompt_plan_id,prompt_text,creative_mode,reference_asset_id,generation_recipe_id,
                         photoshoot_session_id,generation_date,status,review_state,selected,imported_asset_id,
                         created_at,updated_at,media_available,is_staged,staged_at)
                       VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT(image_id) DO UPDATE SET
                         generation_job_id=EXCLUDED.generation_job_id,output_reference=EXCLUDED.output_reference,
                         creator_profile_id=EXCLUDED.creator_profile_id,provider_id=EXCLUDED.provider_id,
                         prompt_plan_id=EXCLUDED.prompt_plan_id,prompt_text=EXCLUDED.prompt_text,
                         creative_mode=EXCLUDED.creative_mode,reference_asset_id=EXCLUDED.reference_asset_id,
                         generation_recipe_id=EXCLUDED.generation_recipe_id,photoshoot_session_id=EXCLUDED.photoshoot_session_id,
                         generation_date=EXCLUDED.generation_date,status=EXCLUDED.status,review_state=EXCLUDED.review_state,
                         selected=EXCLUDED.selected,imported_asset_id=EXCLUDED.imported_asset_id,
                         created_at=EXCLUDED.created_at,updated_at=EXCLUDED.updated_at,
                         media_available=EXCLUDED.media_available,is_staged=EXCLUDED.is_staged,
                         staged_at=EXCLUDED.staged_at""",
                    [self._values(record) for record in records],
                )
                cursor.execute("DELETE FROM public.generation_library_read_projection WHERE NOT (image_id = ANY(%s))", ([record.image_id for record in records],))
            else:
                cursor.execute("DELETE FROM public.generation_library_read_projection")
            cursor.execute(
                """INSERT INTO public.generation_library_projection_state(projection_name,source_version,projected_count)
                   VALUES(%s,%s,%s) ON CONFLICT(projection_name) DO UPDATE SET
                   source_version=EXCLUDED.source_version,projected_count=EXCLUDED.projected_count,synchronized_at=NOW()""",
                (self.PROJECTION_NAME, source_version, len(records)),
            )
        return len(records)

    def upsert(self, records: Iterable[GeneratedImageRecord], *, source_version: str) -> int:
        records = tuple(records)
        with self.connection_factory() as connection, connection.cursor() as cursor:
            if records:
                cursor.executemany(
                    """INSERT INTO public.generation_library_read_projection(
                         image_id,generation_job_id,output_reference,creator_profile_id,provider_id,prompt_plan_id,
                         prompt_text,creative_mode,reference_asset_id,generation_recipe_id,photoshoot_session_id,
                         generation_date,status,review_state,selected,imported_asset_id,created_at,updated_at,media_available,is_staged,staged_at)
                       VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT(image_id) DO UPDATE SET generation_job_id=EXCLUDED.generation_job_id,
                         output_reference=EXCLUDED.output_reference,creator_profile_id=EXCLUDED.creator_profile_id,
                         provider_id=EXCLUDED.provider_id,prompt_plan_id=EXCLUDED.prompt_plan_id,
                         prompt_text=EXCLUDED.prompt_text,creative_mode=EXCLUDED.creative_mode,
                         reference_asset_id=EXCLUDED.reference_asset_id,generation_recipe_id=EXCLUDED.generation_recipe_id,
                         photoshoot_session_id=EXCLUDED.photoshoot_session_id,generation_date=EXCLUDED.generation_date,
                         status=EXCLUDED.status,review_state=EXCLUDED.review_state,selected=EXCLUDED.selected,
                         imported_asset_id=EXCLUDED.imported_asset_id,created_at=EXCLUDED.created_at,
                         updated_at=EXCLUDED.updated_at,media_available=EXCLUDED.media_available,
                         is_staged=EXCLUDED.is_staged,staged_at=EXCLUDED.staged_at""",
                    [self._values(record) for record in records],
                )
            self._set_state(cursor, source_version, delta=0)
        return len(records)

    def delete(self, image_ids, *, source_version: str) -> None:
        ids = tuple(dict.fromkeys(str(value) for value in image_ids))
        with self.connection_factory() as connection, connection.cursor() as cursor:
            if ids:
                cursor.execute("DELETE FROM generation_library_read_projection WHERE image_id=ANY(%s)", (list(ids),))
            self._set_state(cursor, source_version, delta=0)

    def _set_state(self, cursor, source_version: str, *, delta: int = 0):
        cursor.execute("SELECT COUNT(*) total FROM generation_library_read_projection")
        total = int(cursor.fetchone()["total"])
        cursor.execute(
            """INSERT INTO generation_library_projection_state(projection_name,source_version,projected_count)
               VALUES(%s,%s,%s) ON CONFLICT(projection_name) DO UPDATE SET
               source_version=EXCLUDED.source_version,projected_count=EXCLUDED.projected_count,synchronized_at=NOW()""",
            (self.PROJECTION_NAME, str(source_version), total + int(delta)),
        )

    def browse_page(self, filters: GenerationLibraryFilter, *, page: int, page_size: int):
        clauses, params = self._filters(filters)
        where = " AND ".join(clauses)
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM public.generation_library_read_projection WHERE {where}", tuple(params))
            total = int(cursor.fetchone()["total"])
            # Eligibility is applied first.  Lineage is then resolved in one batched
            # query so search/filtering never pulls an ineligible sibling into view.
            cursor.execute(f"SELECT *, {self.EFFECTIVE_CLASSIFICATION_SQL} AS content_classification, {self.CLASSIFICATION_SOURCE_SQL} AS classification_source FROM public.generation_library_read_projection WHERE {where}", tuple(params))
            rows = list(cursor.fetchall())
            cursor.execute("""SELECT rr.source_generated_image_id parent_image_id,
                       x.generated_image_id child_image_id,x.variation_index,
                       rr.created_at run_created_at,x.created_at result_created_at
                    FROM public.regeneration_results x
                    JOIN public.regeneration_runs rr ON rr.operation_id=x.operation_id
                    WHERE rr.creator_profile_id=%s AND x.generated_image_id IS NOT NULL""",
                    (int(filters.creator_profile_id),))
            edges = list(cursor.fetchall())
            disposition_clause = self.DISPOSITION_CLAUSE
            facet_clauses = ["creator_profile_id=%s", "status='active'", "media_available=TRUE", disposition_clause] if filters.creator_profile_id is not None else ["status='active'", "media_available=TRUE", disposition_clause]
            facet_params = (int(filters.creator_profile_id),) if filters.creator_profile_id is not None else ()
            cursor.execute(f"SELECT ARRAY_REMOVE(ARRAY_AGG(DISTINCT provider_id),NULL) providers,ARRAY_REMOVE(ARRAY_AGG(DISTINCT creative_mode),NULL) modes FROM public.generation_library_read_projection WHERE {' AND '.join(facet_clauses)}", facet_params)
            facets = cursor.fetchone()
        ordered = self._staged_first_order(rows, edges, sort=filters.sort)
        pages = self._family_pages(ordered, page_size=int(page_size))
        current_page = min(max(1, int(page)), len(pages))
        selected = pages[current_page - 1] if pages else []
        return (tuple(self._record(row) for row in selected), total,
                tuple(sorted(facets["providers"] or ())), tuple(sorted(facets["modes"] or ())),
                max(1, len(pages)))

    @staticmethod
    def _staged_first_order(rows, edges, *, sort: str):
        """Pin eligible staged records without changing normal lineage-family order."""
        def epoch(value):
            if isinstance(value, datetime):
                return value.timestamp()
            if value:
                try:
                    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
                except ValueError:
                    pass
            return 0.0

        staged = sorted(
            (row for row in rows if bool(row.get("is_staged"))),
            key=lambda row: (-epoch(row.get("staged_at")), str(row["image_id"])),
        )
        normal = [row for row in rows if not bool(row.get("is_staged"))]
        return [(f"staged:{row['image_id']}", [row]) for row in staged] + \
            GenerationLibraryProjectionRepository._family_order(normal, edges, sort=sort)

    @staticmethod
    def _family_order(rows, edges, *, sort: str):
        """Return eligible rows grouped by their persisted regeneration root."""
        def epoch(value):
            if isinstance(value, datetime):
                return value.timestamp()
            if value:
                try:
                    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
                except ValueError:
                    pass
            return 0.0

        parent = {str(edge["child_image_id"]): str(edge["parent_image_id"]) for edge in edges}
        edge_order = {str(edge["child_image_id"]): (
            epoch(edge.get("run_created_at")),
            int(edge.get("variation_index") or 0),
            epoch(edge.get("result_created_at")),
            str(edge["child_image_id"]),
        ) for edge in edges}

        def root_of(image_id: str) -> str:
            trail, seen, current = [], set(), image_id
            while current in parent and current not in seen:
                seen.add(current); trail.append(current); current = parent[current]
            if current in seen:  # Deterministic protection for malformed cycles.
                cycle = trail[trail.index(current):]
                return min(cycle)
            return current

        families = {}
        for row in rows:
            families.setdefault(root_of(str(row["image_id"])), []).append(row)

        def timestamp(row):
            return epoch(row.get("generation_date") or row.get("created_at"))

        def lineage_key(row):
            image_id, chain, seen = str(row["image_id"]), [], set()
            current = image_id
            while current in parent and current not in seen:
                seen.add(current); chain.append(edge_order.get(current, (0.0, 0, 0.0, current)))
                current = parent[current]
            return (len(chain), tuple(reversed(chain)), timestamp(row), image_id)

        for root, members in families.items():
            members.sort(key=lambda row: ((0,) if str(row["image_id"]) == root else (1,)) + lineage_key(row))

        if sort == "oldest":
            family_key = lambda item: (min(timestamp(row) for row in item[1]), item[0])
        elif sort == "provider":
            family_key = lambda item: (min(str(row.get("provider_id") or "") for row in item[1]),
                                       -max(timestamp(row) for row in item[1]), item[0])
        elif sort == "status":
            family_key = lambda item: (min(str(row.get("status") or "") for row in item[1]),
                                       -max(timestamp(row) for row in item[1]), item[0])
        else:
            family_key = lambda item: (-max(timestamp(row) for row in item[1]), item[0])
        return [(root, members) for root, members in sorted(families.items(), key=family_key)]

    @staticmethod
    def _family_pages(ordered_families, *, page_size: int):
        """Paginate the fully eligible, staged-first, lineage-ordered population."""
        ordered = [row for _root, members in ordered_families for row in members]
        return [ordered[offset:offset + page_size]
                for offset in range(0, len(ordered), page_size)] or [[]]

    def staged(self, *, creator_profile_id: int, search: str | None = None):
        filters = GenerationLibraryFilter(creator_profile_id=creator_profile_id, status="staged_asset_library", search=search, sort="newest")
        clauses, params = self._filters(filters)
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(f"SELECT * FROM public.generation_library_read_projection WHERE {' AND '.join(clauses)} ORDER BY generation_date DESC", tuple(params))
            return tuple(self._record(row) for row in cursor.fetchall())

    def staged_count(self, creator_profile_id: int) -> int:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) total FROM public.generation_library_read_projection WHERE creator_profile_id=%s AND status='staged_asset_library'", (int(creator_profile_id),))
            return int(cursor.fetchone()["total"])

    def get(self, image_id: str):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(f"SELECT *, {self.EFFECTIVE_CLASSIFICATION_SQL} AS content_classification, {self.CLASSIFICATION_SOURCE_SQL} AS classification_source FROM public.generation_library_read_projection WHERE image_id=%s", (str(image_id),))
            row = cursor.fetchone()
        return self._record(row) if row else None

    def eligible_unclassified_ids(self, image_ids, *, creator_profile_id: int) -> set[str]:
        ids = tuple(str(image_id) for image_id in image_ids)
        if not ids:
            return set()
        clauses, params = self._filters(GenerationLibraryFilter(
            creator_profile_id=int(creator_profile_id), content_origin="UNCLASSIFIED",
        ))
        clauses.append("image_id=ANY(%s)")
        params.append(list(ids))
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"SELECT image_id FROM public.generation_library_read_projection WHERE {' AND '.join(clauses)} FOR UPDATE",
                tuple(params),
            )
            return {str(row["image_id"]) for row in cursor.fetchall()}

    def existing_identities(self, *, generation_job_id: str, output_references, image_ids):
        references = tuple(str(value) for value in output_references)
        ids = tuple(str(value) for value in image_ids)
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT image_id,generation_job_id,output_reference
                   FROM generation_library_read_projection
                   WHERE generation_job_id=%s OR output_reference=ANY(%s) OR image_id=ANY(%s)""",
                (str(generation_job_id), list(references), list(ids)),
            )
            rows = cursor.fetchall()
        return ({str(row["image_id"]) for row in rows},
                {(str(row["generation_job_id"]), str(row["output_reference"])) for row in rows})

    @staticmethod
    def _filters(filters):
        clauses = [GenerationLibraryProjectionRepository.DISPOSITION_CLAUSE]
        params = []
        status = filters.status if filters.status is not None else "active"
        for column, value in (("creator_profile_id", filters.creator_profile_id), ("provider_id", filters.provider_id), ("status", status), ("creative_mode", filters.creative_mode), ("photoshoot_session_id", filters.photoshoot_session_id), ("reference_asset_id", filters.reference_asset_id)):
            if value is not None:
                clauses.append(f"{column}=%s"); params.append(value)
        content_origin = str(filters.content_origin or "").upper()
        if content_origin in {"SFW", "NSFW"}:
            clauses.append(f"({GenerationLibraryProjectionRepository.EFFECTIVE_CLASSIFICATION_SQL})=%s")
            params.append(content_origin)
        elif content_origin == "UNCLASSIFIED":
            clauses.append(f"({GenerationLibraryProjectionRepository.EFFECTIVE_CLASSIFICATION_SQL}) IS NULL")
        if filters.selected_only:
            clauses.append("selected=TRUE")
        if filters.search:
            clauses.append("(image_id ILIKE %s OR generation_job_id ILIKE %s OR provider_id ILIKE %s OR prompt_plan_id ILIKE %s OR prompt_text ILIKE %s OR COALESCE(creative_mode,'') ILIKE %s OR COALESCE(photoshoot_session_id,'') ILIKE %s)")
            params.extend([f"%{str(filters.search).strip()}%"] * 7)
        if status == "active":
            clauses.append("media_available=TRUE")
        return clauses, params

    @staticmethod
    def _values(record):
        reference = str(record.output_reference or "").strip()
        available = bool(reference.startswith(("http://", "https://", "data:")) or Path(reference).expanduser().is_file())
        return (record.image_id,record.generation_job_id,record.output_reference,record.creator_profile_id,record.provider_id,record.prompt_plan_id,record.prompt_text,record.creative_mode,record.reference_asset_id,record.generation_recipe_id,record.photoshoot_session_id,record.generation_date,record.status,record.review_state,record.selected,record.imported_asset_id,record.created_at,record.updated_at,available,record.is_staged,record.staged_at)

    @staticmethod
    def _record(row):
        iso = lambda value: value.isoformat() if isinstance(value, datetime) else str(value or "")
        return GeneratedImageRecord(image_id=row["image_id"],generation_job_id=row["generation_job_id"],generation_request_id="",generation_result_id="",output_reference=row["output_reference"],creator_profile_id=int(row["creator_profile_id"]),provider_id=row["provider_id"],prompt_plan_id=row["prompt_plan_id"],prompt_text=row["prompt_text"],creative_mode=row["creative_mode"],reference_asset_id=row["reference_asset_id"],generation_recipe_id=str(row["generation_recipe_id"]) if row["generation_recipe_id"] else None,photoshoot_session_id=row["photoshoot_session_id"],generation_date=iso(row["generation_date"]),status=row["status"],review_state=row["review_state"],selected=bool(row["selected"]),imported_asset_id=row["imported_asset_id"],created_at=iso(row["created_at"]),updated_at=iso(row["updated_at"]) or None,is_staged=bool(row.get("is_staged")),staged_at=iso(row.get("staged_at")) or None,content_classification=row.get("content_classification"),classification_source=row.get("classification_source"))
