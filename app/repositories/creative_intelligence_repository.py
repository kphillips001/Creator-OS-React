"""PostgreSQL persistence for creator-specific editorial learning."""

from __future__ import annotations

import json
from collections.abc import Callable

from app.database import get_db_connection
from app.models.creative_intelligence import CreativeLearningSignal, LEARNED_DIMENSIONS


class CreativeIntelligenceRepository:
    POSITIVE_EVENT_WEIGHTS = {
        "published": 5,
        "photoshoot_added": 4,
        "generation_library_retained": 4,
        "edit_saved": 3,
    }
    def __init__(self, connection_factory: Callable = get_db_connection) -> None:
        self.connection_factory = connection_factory

    def fanvue_account_id_for_creator(self, creator_profile_id: int) -> str:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT fanvue_account_id FROM public.creator_profiles WHERE id = %s",
                    (int(creator_profile_id),),
                )
                row = cursor.fetchone()
                if not row:
                    raise KeyError(f"Creator Profile not found: {creator_profile_id}")
                return str(row["fanvue_account_id"])

    def has_event(self, event_key: str) -> bool:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM public.creative_intelligence_events WHERE event_key = %s",
                    (str(event_key),),
                )
                return cursor.fetchone() is not None

    def record(self, signal: CreativeLearningSignal) -> dict:
        """Insert an idempotent event and update its creator's aggregate profile."""
        account_id = self.fanvue_account_id_for_creator(signal.creator_profile_id)
        analysis = signal.analysis.as_dict()
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO public.creative_intelligence_events (
                        event_key, creator_profile_id, fanvue_account_id,
                        source_image_id, source_asset_id, image_reference,
                        event_type, source_workflow, signal, analysis,
                        analysis_status, analysis_provider, analysis_error,
                        operational_metadata
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s::jsonb, %s, %s, %s, %s::jsonb
                    )
                    ON CONFLICT (event_key) DO NOTHING
                    RETURNING *
                    """,
                    (
                        signal.event_key,
                        signal.creator_profile_id,
                        account_id,
                        signal.source_image_id,
                        signal.source_asset_id,
                        signal.image_reference,
                        signal.event_type,
                        signal.source_workflow,
                        signal.signal,
                        json.dumps(analysis),
                        signal.analysis_status,
                        signal.analysis_provider,
                        signal.analysis_error,
                        json.dumps(dict(signal.operational_metadata)),
                    ),
                )
                event = cursor.fetchone()
                if event is None:
                    cursor.execute(
                        "SELECT * FROM public.creative_intelligence_events WHERE event_key = %s",
                        (signal.event_key,),
                    )
                    return {**dict(cursor.fetchone()), "already_recorded": True}

                cursor.execute(
                    """
                    INSERT INTO public.creative_intelligence_profiles (
                        creator_profile_id, fanvue_account_id
                    ) VALUES (%s, %s)
                    ON CONFLICT (creator_profile_id) DO NOTHING
                    """,
                    (signal.creator_profile_id, account_id),
                )
                cursor.execute(
                    """
                    SELECT learned_attributes
                    FROM public.creative_intelligence_profiles
                    WHERE creator_profile_id = %s AND fanvue_account_id = %s
                    FOR UPDATE
                    """,
                    (signal.creator_profile_id, account_id),
                )
                profile = cursor.fetchone()
                learned = dict((profile or {}).get("learned_attributes") or {})
                if signal.signal == "positive":
                    weight = self.POSITIVE_EVENT_WEIGHTS.get(signal.event_type, 1)
                    for dimension in LEARNED_DIMENSIONS:
                        value = analysis.get(dimension)
                        if not value:
                            continue
                        counts = dict(learned.get(dimension) or {})
                        counts[value] = int(counts.get(value) or 0) + weight
                        learned[dimension] = counts
                cursor.execute(
                    """
                    UPDATE public.creative_intelligence_profiles
                    SET positive_event_count = positive_event_count + %s,
                        negative_event_count = negative_event_count + %s,
                        analyzed_image_count = analyzed_image_count + %s,
                        learned_attributes = %s::jsonb,
                        updated_at = NOW()
                    WHERE creator_profile_id = %s AND fanvue_account_id = %s
                    """,
                    (
                        1 if signal.signal == "positive" else 0,
                        1 if signal.signal == "negative" else 0,
                        1 if signal.analysis_status == "completed" else 0,
                        json.dumps(learned),
                        signal.creator_profile_id,
                        account_id,
                    ),
                )
                return {**dict(event), "already_recorded": False}

    def get_profile(self, *, creator_profile_id: int, fanvue_account_id: str) -> dict | None:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT * FROM public.creative_intelligence_profiles
                    WHERE creator_profile_id = %s AND fanvue_account_id = %s
                    """,
                    (int(creator_profile_id), str(fanvue_account_id)),
                )
                row = cursor.fetchone()
                return dict(row) if row else None

    def list_events(self, *, creator_profile_id: int) -> tuple[dict, ...]:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT * FROM public.creative_intelligence_events
                    WHERE creator_profile_id = %s ORDER BY created_at, id
                    """,
                    (int(creator_profile_id),),
                )
                return tuple(dict(row) for row in cursor.fetchall())
