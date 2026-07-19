"""Read-only Edit Studio context aggregation for presentation clients."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

from app.models.generation_engine import GenerationType
from app.services.generation_engine_service import GenerationEngineService
from app.services.generation_library_service import GenerationLibraryService
from app.services.reference_library_service import ReferenceLibraryService
from app.models.reference_library import ReferenceLibraryFilter


EDIT_STUDIO_PROVIDER_ORDER = (
    "seedream_5_0_pro",
    "nano_banana_pro",
    "wan_2_7_image_edit",
    "nano_banana",
)


class EditStudioContextService:
    """Aggregates existing Edit Studio state without owning workflow logic."""

    def __init__(
        self,
        *,
        generation_library: GenerationLibraryService | None = None,
        generation_engine: GenerationEngineService | None = None,
        reference_library: ReferenceLibraryService | None = None,
    ) -> None:
        self.generation_library = generation_library or GenerationLibraryService()
        self.generation_engine = generation_engine or GenerationEngineService()
        self.reference_library = reference_library or ReferenceLibraryService()

    def read(self, *, creator_profile: Mapping[str, Any] | None) -> dict[str, Any]:
        creator_profile_id = int((creator_profile or {}).get("id") or 0)
        pending_source = (
            self.generation_library.pending_edit_record(
                creator_profile_id=creator_profile_id,
            )
            if creator_profile_id
            else None
        )
        return {
            "creator_profile_exists": bool(creator_profile_id),
            "pending_source": self._pending_source_payload(pending_source),
            "providers": self._edit_providers(),
        }

    def pending_source_path(self, *, creator_profile: Mapping[str, Any] | None) -> Path:
        creator_profile_id = int((creator_profile or {}).get("id") or 0)
        if not creator_profile_id:
            raise KeyError("Pending Edit Studio source not found.")
        record = self.generation_library.pending_edit_record(
            creator_profile_id=creator_profile_id,
        )
        if record is None:
            raise KeyError("Pending Edit Studio source not found.")
        path = Path(str(record.output_reference or "")).expanduser()
        if not path.is_file():
            raise FileNotFoundError("Pending Edit Studio source image is unavailable.")
        return path

    def creative_references(self, *, creator_profile_id: int) -> tuple[dict[str, Any], ...]:
        references = self.reference_library.list_references(
            ReferenceLibraryFilter(
                creator_profile_id=int(creator_profile_id),
                has_local_vault_original=None,
                limit=100,
            )
        ).references
        result = []
        for reference in references:
            details = self.reference_library.asset_library.get_asset_details(reference.asset_id)
            if self._is_identity_reference(reference, details):
                continue
            result.append({
                "asset_id": reference.asset_id,
                "label": self._reference_label(reference, details),
                "preview_url": f"/api/v1/edit-studio/references/{reference.asset_id}/image",
            })
        return tuple(result)

    def _edit_providers(self) -> tuple[dict[str, str], ...]:
        registry = self.generation_engine.provider_registry
        registered = {
            item.provider_id: item
            for item in registry.metadata()
            if item.enabled
            and item.capabilities.supports_images
            and GenerationType.IMAGE_TO_IMAGE.value
            in item.capabilities.supported_generation_types
        }
        return tuple(
            {"value": provider_id, "label": registered[provider_id].display_name}
            for provider_id in EDIT_STUDIO_PROVIDER_ORDER
            if provider_id in registered
        )

    @staticmethod
    def _pending_source_payload(record) -> dict[str, Any] | None:
        if record is None:
            return None
        payload = asdict(record)
        output_reference = str(record.output_reference or "")
        version = str(record.updated_at or record.generation_date or record.image_id)
        payload["image_url"] = (
            output_reference
            if output_reference.startswith(("http://", "https://", "data:"))
            else f"/api/v1/edit-studio/pending-source/image?image_id={record.image_id}&v={version}"
        )
        return payload

    @staticmethod
    def _is_identity_reference(reference, details) -> bool:
        if reference.is_active:
            return True
        metadata = dict(reference.metadata or {})
        media_metadata = dict(getattr(details, "media_metadata", None) or {})
        canonical = dict(media_metadata.get("canonical_reference") or {})
        truthy_flags = (
            "canonical", "protected", "identity", "identity_reference",
            "identity_lock", "reference_lock", "reference_locked",
            "permanent_identity_asset",
        )
        if any(bool(metadata.get(flag) or media_metadata.get(flag) or canonical.get(flag)) for flag in truthy_flags):
            return True
        tags = {str(tag).strip().lower().replace("_", "-") for tag in reference.asset.tags}
        return bool(tags & {"canonical-reference", "identity", "identity-reference", "identity-lock", "reference-lock"})

    @staticmethod
    def _reference_label(reference, details) -> str:
        metadata = dict(reference.metadata or {})
        media_metadata = dict(getattr(details, "media_metadata", None) or {})
        intelligence = getattr(details, "intelligence_profile", None)
        vision = dict(getattr(details, "gpt_vision_result", None) or {})
        candidates = (
            getattr(intelligence, "title", None),
            media_metadata.get("title"),
            metadata.get("user_defined_name"),
            media_metadata.get("user_defined_name"),
            metadata.get("display_name"),
            media_metadata.get("display_name"),
            metadata.get("name"),
            media_metadata.get("name"),
            metadata.get("prompt_summary"),
            media_metadata.get("prompt_summary"),
            metadata.get("prompt"),
            media_metadata.get("prompt"),
            getattr(intelligence, "short_description", None),
            getattr(intelligence, "detailed_description", None),
            getattr(intelligence, "content_summary", None),
            getattr(details, "summary", None),
            vision.get("description"),
            vision.get("summary"),
            vision.get("caption"),
            reference.asset.file_name,
            f"Reference {reference.asset_id}",
        )
        return next(str(value).strip() for value in candidates if str(value or "").strip())
