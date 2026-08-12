"""Destination-aware teaser preparation for canonical commercial media."""
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
import os

from app.models.asset_lineage import DerivationKind
from app.repositories.asset_repository import AssetRepository
from app.repositories.commercial_teaser_repository import CommercialTeaserRepository
from app.services.asset_lineage_service import AssetLineageService
from app.services.local_vault_service import LocalVaultService
from app.services.media_processing_service import MediaProcessingService
from app.services.runtime_media_resolver import RuntimeMediaResolver
from app.services.selective_blur_mask_validator import SelectiveBlurMaskValidator
from app.services.selective_blur_service import SelectiveBlurService


class CommercialTeaserService:
    CHAT = "CHAT"
    CONTENT_VAULT = "CONTENT_VAULT"

    def __init__(self, *, repository=None, assets=None, lineage=None, renderer=None,
                 validator=None, media=None, vault=None):
        self.repository = repository or CommercialTeaserRepository()
        self.assets = assets or AssetRepository()
        self.lineage = lineage or AssetLineageService(asset_repository=self.assets)
        self.renderer = renderer or SelectiveBlurService()
        self.validator = validator or SelectiveBlurMaskValidator()
        self.media = media or MediaProcessingService()
        self.vault = vault or LocalVaultService()

    def list(self, asset_id: int): return self.repository.list_for_asset(int(asset_id))

    def save_chat(self, asset_id: int, *, creator_profile_id: int, mask_data: str,
                  mask_width: int, mask_height: int, blur_strength: int):
        return self._save_selective(asset_id, creator_profile_id=creator_profile_id,
            distribution_use=self.CHAT, mask_data=mask_data, mask_width=mask_width,
            mask_height=mask_height, blur_strength=blur_strength)

    def save_vault_selective(self, asset_id: int, *, creator_profile_id: int,
                             mask_data: str, mask_width: int, mask_height: int,
                             blur_strength: int):
        return self._save_selective(asset_id, creator_profile_id=creator_profile_id,
            distribution_use=self.CONTENT_VAULT, mask_data=mask_data,
            mask_width=mask_width, mask_height=mask_height,
            blur_strength=blur_strength)

    def _save_selective(self, asset_id: int, *, creator_profile_id: int,
                        distribution_use: str, mask_data: str, mask_width: int,
                        mask_height: int, blur_strength: int):
        source = self._asset(asset_id, creator_profile_id)
        strength = int(blur_strength)
        if not 1 <= strength <= 80: raise ValueError("Blur strength must be between 1 and 80.")
        raw = self.validator.decode(mask_data, mask_width, mask_height)
        root = self.vault.path(f"vault/commercial_teasers/{asset_id}")
        root.mkdir(parents=True, exist_ok=True)
        prefix = "chat" if distribution_use == self.CHAT else "content_vault"
        mask_path, output_path = root / f"{prefix}_mask.png", root / f"{prefix}_selective.png"
        self._atomic_bytes(mask_path, raw)
        source_path = RuntimeMediaResolver().resolve_original_path(source, require_exists=True)
        if source_path is None: raise ValueError("Authoritative teaser source media is unavailable.")
        self.renderer.render(source_path=source_path, mask_path=mask_path,
                             output_path=output_path, blur_strength=strength)
        current = self.repository.get(asset_id, distribution_use)
        commercial_role = ("SINGLE_IMAGE_CHAT_TEASER" if distribution_use == self.CHAT
                           else "SINGLE_IMAGE_CONTENT_VAULT_TEASER")
        metadata = {"media_type": "image", "commercial_role": commercial_role,
                    "source_asset_id": asset_id, "distribution_use": distribution_use,
                    "selective_blur": {"mask_path": str(mask_path), "mask_width": int(mask_width),
                    "mask_height": int(mask_height), "mask_version": self.validator.MASK_VERSION,
                    "blur_strength": strength, "updated_at": datetime.now(timezone.utc).isoformat()}}
        if current and current.get("derived_asset_id"):
            derived_id = int(current["derived_asset_id"])
            self.repository.update_asset(derived_id, path=output_path, metadata=metadata)
        else:
            derived_id = self.repository.create_asset(creator_profile_id=creator_profile_id,
                path=output_path, source_asset_id=asset_id, metadata=metadata)
            self.lineage.relate(source_asset_ids=(asset_id,), derived_asset_id=derived_id,
                creator_profile_id=creator_profile_id, derivation_kind=DerivationKind.SELECTIVE_BLUR,
                provenance={"commercial_role": commercial_role,
                            "distribution_use": distribution_use,
                            "mask_version": self.validator.MASK_VERSION})
        return self.repository.upsert(creator_profile_id=creator_profile_id,
            source_asset_id=asset_id, derived_asset_id=derived_id, derivative_path=output_path,
            teaser_style="SELECTIVE_BLUR", distribution_use=distribution_use, mask_path=mask_path,
            mask_width=int(mask_width), mask_height=int(mask_height),
            mask_version=self.validator.MASK_VERSION, blur_strength=strength, metadata=metadata)

    def ensure_vault(self, asset_id: int, *, creator_profile_id: int):
        asset = self._asset(asset_id, creator_profile_id)
        current = self.repository.get(asset_id, self.CONTENT_VAULT)
        if (current and current.get("teaser_style") == "FULL_BLUR"
                and Path(current["derivative_path"]).is_file()): return current
        path = self.media.resolve_derivative(asset, "blurred_preview")
        if not path or not Path(path).is_file():
            path = self.media.generate_blurred_preview(asset)
            derivative = self.media.build_derivative_metadata(
                derivative_path=path, derivative_type="blurred_preview", source="commercial_teaser")
            merged = self.media.merge_derivative_metadata(asset.media_metadata,
                derivative_type="blurred_preview", derivative_metadata=derivative)
            self.assets.update_blurred_preview(asset.id, path=str(path), media_metadata=merged)
        return self.repository.upsert(creator_profile_id=creator_profile_id,
            source_asset_id=asset_id, derived_asset_id=None, derivative_path=path,
            teaser_style="FULL_BLUR", distribution_use=self.CONTENT_VAULT,
            metadata={"commercial_role": "SINGLE_IMAGE_CONTENT_VAULT_TEASER"})

    def _asset(self, asset_id, creator_profile_id):
        asset = self.assets.get_by_id(int(asset_id))
        if asset is None or int(asset.creator_profile_id or 0) != int(creator_profile_id):
            raise KeyError("Canonical Asset not found.")
        if asset.media_type != "image": raise ValueError("Commercial teasers support image Assets only.")
        return asset

    @staticmethod
    def _atomic_bytes(path, value):
        with NamedTemporaryFile(dir=path.parent, suffix=".png", delete=False) as temp:
            temp.write(value); temporary = Path(temp.name)
        try: os.replace(temporary, path)
        finally: temporary.unlink(missing_ok=True)
