"""Reverse standalone Generation Library Asset registration safely."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.database import get_db_connection
from app.models.generation_library import GeneratedImageRecord
from app.services.generation_library_service import GenerationLibraryService


class AssetReturnConflict(ValueError):
    """The Asset has relationships that must not be destructively removed."""


@dataclass(frozen=True)
class AssetReturnResult:
    asset_id: int
    generation_id: str
    intelligence_profiles_removed: int
    provider_results_removed: int
    content_profiles_removed: int


class AssetLibraryReturnService:
    """Return an unprepared Single Image while preserving its source generation."""

    def __init__(self, *, generation_library: GenerationLibraryService | None = None,
                 connection_factory: Callable = get_db_connection) -> None:
        self.generation_library = generation_library or GenerationLibraryService()
        self.connection_factory = connection_factory

    def return_single_image(self, generation_id: str, *, creator_profile_id: int) -> AssetReturnResult:
        record = self.generation_library.get(str(generation_id))
        if int(record.creator_profile_id) != int(creator_profile_id):
            raise KeyError("Generated image not found.")
        if record.status != "business_asset_registered" or record.imported_asset_id is None:
            raise AssetReturnConflict("Only a registered Single Image can be returned.")
        asset_id = int(record.imported_asset_id)
        original: GeneratedImageRecord = record
        moved = False
        try:
            with self.connection_factory() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """SELECT id, creator_profile_id, classification, media_metadata
                           FROM public.content_items WHERE id=%s FOR UPDATE""", (asset_id,))
                    asset = cursor.fetchone()
                    if not asset or int(asset["creator_profile_id"] or 0) != int(creator_profile_id):
                        raise KeyError("Asset not found.")
                    registration = dict((asset.get("media_metadata") or {}).get("asset_registration") or {})
                    if asset.get("classification") != "SINGLE_IMAGE" or registration.get("source") != "generation_library":
                        raise AssetReturnConflict("Only standalone Generation Library images can be returned.")
                    if str(registration.get("generated_image_id") or "") != str(generation_id):
                        raise AssetReturnConflict("Asset registration does not match this generation.")
                    self._assert_no_commercial_or_historical_dependencies(cursor, asset_id)
                    self.generation_library.move_back_to_generation_library(
                        record.image_id, registration_reversed=True)
                    moved = True
                    provider_results = self._delete(cursor, "DELETE FROM public.asset_intelligence_provider_results WHERE asset_id=%s", asset_id)
                    self._delete(cursor, "DELETE FROM public.asset_intelligence_provider_executions WHERE asset_id=%s", asset_id)
                    self._delete(cursor, "DELETE FROM public.asset_intelligence_runs WHERE asset_id=%s", asset_id)
                    content_profiles = self._delete(cursor, "DELETE FROM public.content_intelligence_profiles WHERE asset_id=%s", asset_id)
                    self._delete(cursor, "DELETE FROM public.business_asset_registrations WHERE asset_id=%s", asset_id)
                    intelligence_profiles = self._delete(cursor, "DELETE FROM public.asset_intelligence_profiles WHERE asset_id=%s", asset_id)
                    cursor.execute("DELETE FROM public.content_items WHERE id=%s", (asset_id,))
                    if cursor.rowcount != 1:
                        raise RuntimeError("Canonical Asset registration was not removed.")
            return AssetReturnResult(asset_id, record.image_id, intelligence_profiles,
                                     provider_results, content_profiles)
        except Exception:
            if moved:
                self.generation_library._replace_record(original)
            raise

    @staticmethod
    def _delete(cursor, statement: str, asset_id: int) -> int:
        cursor.execute(statement, (asset_id,))
        return int(cursor.rowcount or 0)

    @staticmethod
    def _assert_no_commercial_or_historical_dependencies(cursor, asset_id: int) -> None:
        checks = (
            ("commercial offering", "SELECT 1 FROM public.commercial_offering_assets WHERE asset_id=%s LIMIT 1"),
            ("commercial offering", "SELECT 1 FROM public.commercial_offerings WHERE hero_asset_id=%s LIMIT 1"),
            ("commercial teaser", "SELECT 1 FROM public.commercial_teasers WHERE source_asset_id=%s OR derived_asset_id=%s LIMIT 1"),
            ("commercial upload", "SELECT 1 FROM public.commercial_publication_uploads WHERE asset_id=%s LIMIT 1"),
            ("completed usage history", "SELECT 1 FROM public.content_usage_log WHERE content_item_id=%s LIMIT 1"),
            ("Photoshoot membership", "SELECT 1 FROM public.photoshoot_asset_memberships WHERE asset_id=%s LIMIT 1"),
            ("hosted media", "SELECT 1 FROM public.hosted_asset_references WHERE asset_id=%s LIMIT 1"),
            ("commercial role history", "SELECT 1 FROM public.commercial_role_history WHERE asset_id=%s LIMIT 1"),
        )
        for label, statement in checks:
            parameters = (asset_id, asset_id) if statement.count("%s") == 2 else (asset_id,)
            cursor.execute(statement, parameters)
            if cursor.fetchone():
                raise AssetReturnConflict(
                    f"This image has {label} records. Withdraw its active commercial preparation before returning it; historical sales and ownership will not be deleted."
                )
