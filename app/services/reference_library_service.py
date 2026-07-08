"""Reference Library workflow over canonical Creator OS Assets."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from app.models.asset import Asset
from app.models.asset_library import AssetLibraryFilter, AssetLibraryItem
from app.models.creator_intent import CreatorIntent
from app.models.reference_library import (
    ReferenceAsset,
    ReferenceLibraryActionResult,
    ReferenceLibraryFilter,
    ReferenceLibraryResult,
    utc_timestamp,
)
from app.repositories.asset_repository import AssetRepository
from app.services.ai_import_workflow_service import AIImportWorkflowService
from app.services.asset_library_service import AssetLibraryService


REFERENCE_METADATA_KEY = "reference_library"


class ReferenceLibraryService:
    """Owns reference presentation, workflow, and active selection."""

    def __init__(
        self,
        *,
        asset_repository: AssetRepository | None = None,
        asset_library_service: AssetLibraryService | None = None,
        ai_import_workflow: AIImportWorkflowService | None = None,
    ):
        self.assets = asset_repository or AssetRepository()
        self.asset_library = asset_library_service or AssetLibraryService(
            asset_repository=self.assets,
        )
        self.ai_import = ai_import_workflow or AIImportWorkflowService(
            asset_repository=self.assets,
        )

    def add_reference(
        self,
        *,
        media_path: str | Path,
        creator_profile_id: int,
        original_filename: str | None = None,
        fanvue_account_id: int | None = None,
        favorite: bool = False,
        make_active: bool = True,
    ) -> ReferenceLibraryActionResult:
        result = self.ai_import.import_asset(
            media_path=media_path,
            upload_intent="teaser_image",
            creator_profile_id=creator_profile_id,
            creator_intent=CreatorIntent.create(
                "single_asset",
                legacy_upload_intent="teaser_image",
                metadata={
                    "source": "content_studio_reference_library",
                    "reference_image": True,
                },
            ),
            original_filename=original_filename,
            fanvue_account_id=fanvue_account_id,
            create_product_draft=False,
            provider_upload_enabled=False,
            is_test=False,
        )
        if not result.success or not result.content_id:
            return ReferenceLibraryActionResult(
                success=False,
                message=str(result.legacy_result.get("error") or "Reference import failed."),
                data={"import_result": result.to_legacy_result()},
            )

        reference = self.mark_asset_as_reference(
            result.content_id,
            creator_profile_id=creator_profile_id,
            favorite=favorite,
            make_active=make_active,
            original_filename=original_filename,
        )
        if not reference.success:
            return reference
        return ReferenceLibraryActionResult(
            success=True,
            message="Reference image added to Asset Library.",
            asset_id=result.content_id,
            reference=reference.reference,
            data={"import_result": result.to_legacy_result()},
        )

    def mark_asset_as_reference(
        self,
        asset_id: int,
        *,
        creator_profile_id: int,
        favorite: bool = False,
        make_active: bool = False,
        original_filename: str | None = None,
    ) -> ReferenceLibraryActionResult:
        asset = self.assets.get_by_id(asset_id)
        if not asset:
            return ReferenceLibraryActionResult(
                success=False,
                message="Asset was not found.",
                asset_id=asset_id,
            )
        if asset.creator_profile_id not in (None, creator_profile_id):
            return ReferenceLibraryActionResult(
                success=False,
                message="Asset belongs to a different Creator Profile.",
                asset_id=asset_id,
            )

        if make_active:
            self._clear_active_reference(creator_profile_id)

        metadata = self._reference_metadata(asset)
        now = utc_timestamp()
        updated = {
            **metadata,
            "is_reference": True,
            "creator_profile_id": creator_profile_id,
            "favorite": bool(favorite or metadata.get("favorite")),
            "active": bool(make_active or metadata.get("active")),
            "added_at": metadata.get("added_at") or now,
            "removed_at": None,
            "source": "content_studio_reference_library",
        }
        if original_filename:
            updated["original_filename"] = original_filename
        if updated["active"]:
            updated["last_used_at"] = now

        self.assets.update_reference_metadata(asset_id, updated)
        return ReferenceLibraryActionResult(
            success=True,
            message="Asset marked as a Reference Image.",
            asset_id=asset_id,
            reference=self.get_reference(asset_id),
        )

    def remove_reference(
        self,
        asset_id: int,
        *,
        creator_profile_id: int,
    ) -> ReferenceLibraryActionResult:
        asset = self.assets.get_by_id(asset_id)
        if not asset:
            return ReferenceLibraryActionResult(
                success=False,
                message="Asset was not found.",
                asset_id=asset_id,
            )
        metadata = self._reference_metadata(asset)
        if not metadata.get("is_reference"):
            return ReferenceLibraryActionResult(
                success=True,
                message="Asset was not a Reference Image.",
                asset_id=asset_id,
            )
        if self._reference_creator_profile_id(asset) != creator_profile_id:
            return ReferenceLibraryActionResult(
                success=False,
                message="Reference belongs to a different Creator Profile.",
                asset_id=asset_id,
            )
        updated = {
            **metadata,
            "is_reference": False,
            "active": False,
            "removed_at": utc_timestamp(),
        }
        self.assets.update_reference_metadata(asset_id, updated)
        return ReferenceLibraryActionResult(
            success=True,
            message="Reference removed from Reference Library. The Asset remains in Asset Library.",
            asset_id=asset_id,
        )

    def set_active_reference(
        self,
        asset_id: int,
        *,
        creator_profile_id: int,
    ) -> ReferenceLibraryActionResult:
        asset = self.assets.get_by_id(asset_id)
        if not asset:
            return ReferenceLibraryActionResult(
                success=False,
                message="Asset was not found.",
                asset_id=asset_id,
            )
        metadata = self._reference_metadata(asset)
        if not metadata.get("is_reference"):
            return ReferenceLibraryActionResult(
                success=False,
                message="Only Reference Images can become active references.",
                asset_id=asset_id,
            )
        if self._reference_creator_profile_id(asset) != creator_profile_id:
            return ReferenceLibraryActionResult(
                success=False,
                message="Reference belongs to a different Creator Profile.",
                asset_id=asset_id,
            )

        self._clear_active_reference(creator_profile_id)
        updated = {
            **metadata,
            "active": True,
            "last_used_at": utc_timestamp(),
        }
        self.assets.update_reference_metadata(asset_id, updated)
        return ReferenceLibraryActionResult(
            success=True,
            message="Active Reference selected.",
            asset_id=asset_id,
            reference=self.get_reference(asset_id),
        )

    def set_favorite(
        self,
        asset_id: int,
        *,
        creator_profile_id: int,
        favorite: bool,
    ) -> ReferenceLibraryActionResult:
        asset = self.assets.get_by_id(asset_id)
        if not asset:
            return ReferenceLibraryActionResult(False, "Asset was not found.", asset_id)
        if self._reference_creator_profile_id(asset) != creator_profile_id:
            return ReferenceLibraryActionResult(
                False,
                "Reference belongs to a different Creator Profile.",
                asset_id,
            )
        metadata = self._reference_metadata(asset)
        updated = {**metadata, "favorite": bool(favorite)}
        self.assets.update_reference_metadata(asset_id, updated)
        return ReferenceLibraryActionResult(
            True,
            "Favorite updated.",
            asset_id,
            self.get_reference(asset_id),
        )

    def get_active_reference(
        self,
        *,
        creator_profile_id: int | None,
    ) -> ReferenceAsset | None:
        if not creator_profile_id:
            return None
        result = self.list_references(
            ReferenceLibraryFilter(
                creator_profile_id=creator_profile_id,
                active_only=True,
                limit=1,
            )
        )
        return result.active_reference or (result.references[0] if result.references else None)

    def get_reference(self, asset_id: int) -> ReferenceAsset | None:
        asset = self.assets.get_by_id(asset_id)
        if not asset:
            return None
        if not self._reference_metadata(asset).get("is_reference"):
            return None
        item = self.asset_library.build_item(asset)
        return self._build_reference(asset, item)

    def list_references(
        self,
        filters: ReferenceLibraryFilter | None = None,
    ) -> ReferenceLibraryResult:
        filters = filters or ReferenceLibraryFilter()
        query_limit = (
            max(filters.limit, 500)
            if filters.active_only or filters.favorites_only
            else filters.limit
        )
        asset_result = self.asset_library.search_assets(
            AssetLibraryFilter(
                search=filters.search,
                media_type="image",
                eligible_only=False,
                limit=query_limit,
                creator_profile_id=filters.creator_profile_id,
                has_local_vault_original=filters.has_local_vault_original,
            )
        )
        references = []
        for item in asset_result.items:
            asset = self.assets.get_by_id(item.asset_id)
            if not asset:
                continue
            reference = self._build_reference(asset, item)
            if reference is None:
                continue
            if filters.favorites_only and not reference.is_favorite:
                continue
            if filters.active_only and not reference.is_active:
                continue
            references.append(reference)

        sorted_refs = tuple(
            sorted(
                references,
                key=lambda ref: (
                    not ref.is_active,
                    not ref.is_favorite,
                    ref.last_used_at or "",
                    ref.added_at or "",
                    ref.asset_id,
                ),
            )
        )[: filters.limit]
        active = next((ref for ref in sorted_refs if ref.is_active), None)
        return ReferenceLibraryResult(
            references=sorted_refs,
            filters=filters,
            active_reference=active,
        )

    def _clear_active_reference(self, creator_profile_id: int) -> None:
        current = self.list_references(
            ReferenceLibraryFilter(
                creator_profile_id=creator_profile_id,
                active_only=True,
                has_local_vault_original=None,
                limit=500,
            )
        )
        for reference in current.references:
            asset = self.assets.get_by_id(reference.asset_id)
            if not asset:
                continue
            metadata = self._reference_metadata(asset)
            self.assets.update_reference_metadata(
                reference.asset_id,
                {**metadata, "active": False},
            )

    def _build_reference(
        self,
        asset: Asset,
        item: AssetLibraryItem,
    ) -> ReferenceAsset | None:
        metadata = self._reference_metadata(asset)
        if not metadata.get("is_reference"):
            return None
        return ReferenceAsset(
            asset=item,
            creator_profile_id=self._reference_creator_profile_id(asset),
            is_active=bool(metadata.get("active")),
            is_favorite=bool(metadata.get("favorite")),
            added_at=metadata.get("added_at"),
            last_used_at=metadata.get("last_used_at"),
            removed_at=metadata.get("removed_at"),
            metadata=metadata,
        )

    @staticmethod
    def _reference_metadata(asset: Asset | Mapping[str, Any]) -> dict[str, Any]:
        media_metadata = (
            asset.get("media_metadata") if isinstance(asset, Mapping) else asset.media_metadata
        )
        if not isinstance(media_metadata, Mapping):
            return {}
        value = media_metadata.get(REFERENCE_METADATA_KEY)
        return dict(value) if isinstance(value, Mapping) else {}

    @classmethod
    def _reference_creator_profile_id(cls, asset: Asset) -> int | None:
        metadata = cls._reference_metadata(asset)
        value = metadata.get("creator_profile_id") or asset.creator_profile_id
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None
