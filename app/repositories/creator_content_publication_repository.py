"""PostgreSQL persistence for permanent creator publication memory."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from app.database import get_db_connection
from app.models.creator_content_publication import CreatorContentPublication


class CreatorContentPublicationRepository:
    MAX_SEARCH_RESULTS = 50

    def __init__(self, *, connection_factory: Callable = get_db_connection) -> None:
        self._connection_factory = connection_factory

    def save_successful(
        self, publication: CreatorContentPublication,
    ) -> CreatorContentPublication:
        """Insert once by confirmed Telegram identity; safe under replay."""
        with self._connection_factory() as connection:
            self._ensure_table(connection)
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO public.creator_content_publications (
                        publication_id, creator_profile_id, platform, destination,
                        telegram_channel_id, telegram_message_id, published_at,
                        publication_status, generated_image_id, published_asset_id,
                        caption_result_id, photoshoot_id, generation_lineage,
                        media_identity, published_caption, cta_snapshot,
                        provider_identifiers, factual_visual_summary, setting,
                        clothing, pose, activity, expression, useful_objects, mood,
                        themes, safety_snapshot, intelligence_source,
                        intelligence_version, intelligence_provenance, search_document,
                        created_at, updated_at
                    ) VALUES (
                        %s::uuid,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                        %s::jsonb,%s::jsonb,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s,
                        %s,%s,%s::jsonb,%s,%s::jsonb,%s::jsonb,%s,%s,%s::jsonb,%s,
                        COALESCE(%s,now()),now()
                    )
                    ON CONFLICT (platform,destination,telegram_channel_id,telegram_message_id)
                    DO UPDATE SET updated_at = public.creator_content_publications.updated_at
                    RETURNING *
                    """,
                    self._params(publication),
                )
                row = cursor.fetchone()
        return self._from_row(row)

    def get_by_id(self, *, creator_profile_id: int, publication_id: str):
        with self._connection_factory() as connection:
            self._ensure_table(connection)
            with connection.cursor() as cursor:
                cursor.execute("""SELECT * FROM public.creator_content_publications
                    WHERE creator_profile_id=%s AND publication_id=%s::uuid
                      AND publication_status='PUBLISHED'""",
                    (int(creator_profile_id), str(publication_id)))
                row = cursor.fetchone()
        return self._from_row(row) if row else None
    def get_by_telegram_message(
        self, *, platform: str, destination: str,
        telegram_channel_id: int, telegram_message_id: int,
    ) -> CreatorContentPublication | None:
        with self._connection_factory() as connection:
            self._ensure_table(connection)
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT * FROM public.creator_content_publications
                       WHERE platform=%s AND destination=%s
                         AND telegram_channel_id=%s AND telegram_message_id=%s""",
                    (platform, destination, telegram_channel_id, telegram_message_id),
                )
                row = cursor.fetchone()
        return self._from_row(row) if row else None

    def search(
        self, *, creator_profile_id: int, query: str | None = None,
        platform: str | None = None, destination: str | None = None,
        limit: int = 20,
    ) -> tuple[CreatorContentPublication, ...]:
        filters = ["creator_profile_id=%s"]
        params: list[Any] = [int(creator_profile_id)]
        if platform:
            filters.append("platform=%s")
            params.append(str(platform))
        if destination:
            filters.append("destination=%s")
            params.append(str(destination))
        normalized_query = " ".join(str(query or "").split())
        rank = "published_at"
        if normalized_query:
            filters.append(
                "to_tsvector('simple',search_document) @@ plainto_tsquery('simple',%s)"
            )
            params.append(normalized_query)
            rank = "ts_rank(to_tsvector('simple',search_document),plainto_tsquery('simple',%s))"
            params.append(normalized_query)
        params.append(max(1, min(int(limit), self.MAX_SEARCH_RESULTS)))
        with self._connection_factory() as connection:
            self._ensure_table(connection)
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""SELECT * FROM public.creator_content_publications
                        WHERE {' AND '.join(filters)}
                        ORDER BY {rank} DESC, published_at DESC
                        LIMIT %s""",
                    tuple(params),
                )
                rows = cursor.fetchall()
        return tuple(self._from_row(row) for row in rows)

    def search_reference_candidates(
        self, *, creator_profile_id: int, terms: tuple[str, ...], limit: int = 20,
    ) -> tuple[CreatorContentPublication, ...]:
        lexemes = tuple(dict.fromkeys(
            "".join(character for character in str(term).lower() if character.isalnum())
            for term in terms if str(term).strip()
        ))[:12]
        lexemes = tuple(value for value in lexemes if value)
        if not lexemes:
            return ()
        query = " | ".join(lexemes)
        bounded_limit = max(1, min(int(limit), self.MAX_SEARCH_RESULTS))
        with self._connection_factory() as connection:
            self._ensure_table(connection)
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT * FROM public.creator_content_publications
                       WHERE creator_profile_id=%s AND platform='telegram'
                         AND destination='main'
                         AND to_tsvector('simple',search_document)
                             @@ to_tsquery('simple',%s)
                       ORDER BY ts_rank(to_tsvector('simple',search_document),
                                        to_tsquery('simple',%s)) DESC,
                                published_at DESC
                       LIMIT %s""",
                    (int(creator_profile_id), query, query, bounded_limit),
                )
                rows = cursor.fetchall()
        return tuple(self._from_row(row) for row in rows)
    @staticmethod
    def _ensure_table(connection) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT to_regclass('public.creator_content_publications') AS table_ref"
            )
            row = cursor.fetchone()
        if not row or not row["table_ref"]:
            raise RuntimeError(
                "Missing creator_content_publications; apply migration 144 first."
            )

    @staticmethod
    def _params(value: CreatorContentPublication) -> tuple[Any, ...]:
        dump = lambda item: json.dumps(item, default=str, ensure_ascii=False)
        return (
            value.publication_id, value.creator_profile_id, value.platform,
            value.destination, value.telegram_channel_id, value.telegram_message_id,
            value.published_at, value.publication_status, value.generated_image_id,
            value.published_asset_id, value.caption_result_id, value.photoshoot_id,
            dump(dict(value.generation_lineage)), dump(dict(value.media_identity)),
            value.published_caption, dump(dict(value.cta_snapshot)),
            dump(dict(value.provider_identifiers)), value.factual_visual_summary,
            value.setting, value.clothing, value.pose, value.activity,
            value.expression, dump(list(value.useful_objects)), value.mood,
            dump(list(value.themes)), dump(dict(value.safety_snapshot)),
            value.intelligence_source, value.intelligence_version,
            dump(dict(value.intelligence_provenance)), value.search_document,
            value.created_at,
        )

    @staticmethod
    def _from_row(row) -> CreatorContentPublication:
        return CreatorContentPublication(
            publication_id=str(row["publication_id"]),
            creator_profile_id=int(row["creator_profile_id"]),
            platform=str(row["platform"]), destination=str(row["destination"]),
            telegram_channel_id=int(row["telegram_channel_id"]),
            telegram_message_id=int(row["telegram_message_id"]),
            published_at=row["published_at"],
            publication_status=str(row["publication_status"]),
            generated_image_id=str(row["generated_image_id"]),
            published_asset_id=row.get("published_asset_id"),
            caption_result_id=row.get("caption_result_id"),
            photoshoot_id=row.get("photoshoot_id"),
            generation_lineage=dict(row.get("generation_lineage") or {}),
            media_identity=dict(row.get("media_identity") or {}),
            published_caption=str(row.get("published_caption") or ""),
            cta_snapshot=dict(row.get("cta_snapshot") or {}),
            provider_identifiers=dict(row.get("provider_identifiers") or {}),
            factual_visual_summary=row.get("factual_visual_summary"),
            setting=row.get("setting"), clothing=row.get("clothing"),
            pose=row.get("pose"), activity=row.get("activity"),
            expression=row.get("expression"),
            useful_objects=tuple(row.get("useful_objects") or ()),
            mood=row.get("mood"), themes=tuple(row.get("themes") or ()),
            safety_snapshot=dict(row.get("safety_snapshot") or {}),
            intelligence_source=str(row["intelligence_source"]),
            intelligence_version=str(row["intelligence_version"]),
            intelligence_provenance=dict(row.get("intelligence_provenance") or {}),
            search_document=str(row.get("search_document") or ""),
            created_at=row.get("created_at"), updated_at=row.get("updated_at"),
        )
