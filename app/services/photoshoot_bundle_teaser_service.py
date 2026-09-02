"""Canonical selective-blur promotional teaser workflow for Bundle Photoshoots."""

import base64
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile
import os

from PIL import Image, UnidentifiedImageError

from app.models.asset_lineage import DerivationKind
from app.repositories.asset_repository import AssetRepository
from app.repositories.photoshoot_bundle_teaser_repository import PhotoshootBundleTeaserRepository
from app.repositories.photoshoot_commerce_repository import PhotoshootCommerceRepository
from app.services.asset_lineage_service import AssetLineageService
from app.services.local_vault_service import LocalVaultService
from app.services.runtime_media_resolver import RuntimeMediaResolver
from app.services.selective_blur_service import SelectiveBlurService
from app.services.selective_blur_mask_validator import SelectiveBlurMaskValidator
from app.services.blur_service import FULL_BLUR_STRENGTH


class PhotoshootBundleTeaserService:
    MASK_VERSION = "selective_blur_mask_v1"
    MAX_MASK_BYTES = 8 * 1024 * 1024

    def __init__(self, *, photoshoots=None, repository=None, assets=None, lineage=None,
                 renderer=None, vault=None):
        self.photoshoots = photoshoots or PhotoshootCommerceRepository()
        self.repository = repository or PhotoshootBundleTeaserRepository()
        self.assets = assets or AssetRepository()
        self.lineage = lineage or AssetLineageService(asset_repository=self.assets)
        self.renderer = renderer or SelectiveBlurService()
        self.vault = vault or LocalVaultService()
        self.mask_validator = SelectiveBlurMaskValidator()

    def inspect(self, deliverable_id, *, creator_profile_id: int):
        row, members = self._context(deliverable_id, creator_profile_id)
        current = self.repository.get(str(row["deliverable_id"]))
        candidates = [{"assetId": int(item["asset_id"]), "shotOrder": int(item["shot_order"]),
                       "imageUrl": f'/api/v1/assets/{int(item["asset_id"])}/media'} for item in members]
        if not current:
            return {"status": "NOT_CONFIGURED", "statusLabel": "Teaser Not Configured",
                    "commercialRole": "BUNDLE_PROMOTIONAL_TEASER", "candidates": candidates,
                    "sourceAssetId": None, "teaserAssetId": None, "blurStrength": 24,
                    "maskWidth": None, "maskHeight": None, "maskVersion": self.MASK_VERSION,
                    "maskUrl": None, "previewUrl": None, "teaserStyle": None, "error": None}
        mask = Path(current["mask_path"])
        asset = self.assets.get_by_id(int(current["teaser_asset_id"]))
        member_ids = {int(item["asset_id"]) for item in members}
        source_id = int(current["source_asset_id"])
        teaser_id = int(current["teaser_asset_id"])
        lineage_repository = getattr(self.lineage, "repository", self.lineage)
        relationships = tuple(
            item for item in lineage_repository.relationships_for_asset(teaser_id)
            if item.derived_asset_id == teaser_id
        )
        valid_lineage = bool(
            len(relationships) == 1
            and relationships[0].source_asset_ids == (source_id,)
            and relationships[0].derivation_kind is DerivationKind.SELECTIVE_BLUR
        )
        conflicts = self.repository.integrity_conflicts(
            deliverable_id=str(row["deliverable_id"]),
            teaser_asset_id=teaser_id,
        )
        integrity_errors = []
        if source_id not in member_ids:
            integrity_errors.append("Teaser source is no longer an approved original.")
        if asset is None or int(asset.creator_profile_id or 0) != int(creator_profile_id):
            integrity_errors.append("Teaser Asset creator ownership is invalid.")
        if not valid_lineage:
            integrity_errors.append("Teaser selective-blur lineage is invalid.")
        if conflicts.get("photoshoot_member"):
            integrity_errors.append("Promotional teaser cannot be a Photoshoot original member.")
        if conflicts.get("paid_bundle_member"):
            integrity_errors.append("Promotional teaser cannot be paid Bundle content.")
        ready = bool(
            not integrity_errors and asset
            and Path(asset.local_vault_path or asset.file_path).is_file()
            and mask.is_file()
        )
        asset_metadata = dict(getattr(asset, "media_metadata", None) or {}) if asset else {}
        teaser_style = str(asset_metadata.get("teaser_style") or "SELECTIVE_BLUR")
        return {"status": "READY" if ready else "NEEDS_ATTENTION",
                "statusLabel": "Promotional Teaser Ready" if ready else "Teaser Needs Attention",
                "commercialRole": current["commercial_role"], "candidates": candidates,
                "sourceAssetId": int(current["source_asset_id"]),
                "teaserAssetId": int(current["teaser_asset_id"]),
                "blurStrength": int(current["blur_strength"]),
                "maskWidth": int(current["mask_width"]), "maskHeight": int(current["mask_height"]),
                "maskVersion": current["mask_version"],
                "teaserStyle": teaser_style,
                "maskUrl": f'/api/v1/assets/photoshoots/{row["deliverable_id"]}/bundle-teaser/mask',
                "previewUrl": f'/api/v1/assets/{current["teaser_asset_id"]}/media',
                "error": None if ready else (
                    " ".join(integrity_errors)
                    or "Teaser media or edit mask is unavailable."
                )}

    def save(self, deliverable_id, *, creator_profile_id: int, source_asset_id: int,
             mask_data: str, mask_width: int, mask_height: int, blur_strength: int):
        row, members = self._context(deliverable_id, creator_profile_id)
        member_ids = {int(item["asset_id"]) for item in members}
        source_id = int(source_asset_id)
        if source_id not in member_ids:
            raise ValueError("Teaser source must be an approved original member of this Photoshoot.")
        source = self.assets.get_by_id(source_id)
        if source is None or int(source.creator_profile_id or 0) != int(creator_profile_id):
            raise ValueError("Teaser source is unavailable for this creator.")
        current = self.repository.get(str(row["deliverable_id"]))
        if current and int(current["source_asset_id"]) != source_id and self.photoshoots.has_protected_commercial_evidence(
            str(row["deliverable_id"]), creator_profile_id):
            raise ValueError("Teaser source cannot change after a live publication or confirmed purchase.")
        width, height = int(mask_width), int(mask_height)
        if not 1 <= width <= 2048 or not 1 <= height <= 2048:
            raise ValueError("Mask dimensions must be between 1 and 2048 pixels.")
        strength = int(blur_strength)
        if not 1 <= strength <= 80:
            raise ValueError("Blur strength must be between 1 and 80.")
        mask_bytes = self._decode_mask(mask_data, width, height)
        teaser_style = (
            "FULL_BLUR" if self.mask_validator.is_full_blur(mask_bytes)
            else "SELECTIVE_BLUR"
        )
        if teaser_style == "FULL_BLUR":
            strength = FULL_BLUR_STRENGTH
        root = self.vault.path(f"vault/bundle_teasers/{row['deliverable_id']}")
        root.mkdir(parents=True, exist_ok=True)
        mask_path = root / f"mask_source_{source_id}.png"
        self._atomic_bytes(mask_path, mask_bytes)
        source_path = RuntimeMediaResolver().resolve_original_path(source, require_exists=True)
        if source_path is None:
            raise ValueError("Authoritative teaser source media is unavailable.")
        output_path = root / f"promotional_teaser_source_{source_id}.png"
        self.renderer.render(source_path=source_path, mask_path=mask_path,
                             output_path=output_path, blur_strength=strength)
        now = datetime.now(timezone.utc).isoformat()
        metadata = {"media_type": "image", "commercial_role": "BUNDLE_PROMOTIONAL_TEASER",
                    "teaser_style": teaser_style,
                    "source_asset_id": source_id, "source_photoshoot_deliverable_id": str(row["deliverable_id"]),
                    "selective_blur": {"mask_path": str(mask_path), "mask_width": width,
                    "mask_height": height, "mask_version": self.MASK_VERSION,
                    "blur_strength": strength, "updated_at": now}}
        reuse = current and int(current["source_asset_id"]) == source_id
        if reuse:
            teaser_id = int(current["teaser_asset_id"])
            self.repository.update_asset(teaser_id, path=output_path, metadata=metadata)
        else:
            teaser_id = self.repository.create_asset(creator_profile_id=creator_profile_id,
                path=output_path, source_asset_id=source_id, metadata=metadata)
            self.lineage.relate(source_asset_ids=(source_id,), derived_asset_id=teaser_id,
                creator_profile_id=creator_profile_id, derivation_kind=DerivationKind.SELECTIVE_BLUR,
                provenance={"commercial_role": "BUNDLE_PROMOTIONAL_TEASER",
                            "photoshoot_deliverable_id": str(row["deliverable_id"]),
                            "mask_version": self.MASK_VERSION})
        self.repository.upsert(deliverable_id=str(row["deliverable_id"]),
            creator_profile_id=creator_profile_id, source_asset_id=source_id,
            teaser_asset_id=teaser_id, mask_path=str(mask_path), mask_width=width,
            mask_height=height, blur_strength=strength)
        return self.inspect(deliverable_id, creator_profile_id=creator_profile_id)

    def mask_path(self, deliverable_id, *, creator_profile_id):
        row, _ = self._context(deliverable_id, creator_profile_id)
        current = self.repository.get(str(row["deliverable_id"]))
        path = Path(current["mask_path"]) if current else None
        if path is None or not path.is_file(): raise KeyError("Bundle teaser mask not found.")
        return path

    def preview_source(self, deliverable_id, *, creator_profile_id: int, source_asset_id: int):
        """Resolve an approved source for non-persistent teaser editing previews."""
        _, members = self._context(deliverable_id, creator_profile_id)
        source_id = int(source_asset_id)
        if source_id not in {int(item["asset_id"]) for item in members}:
            raise ValueError("Teaser source must be an approved original member of this Photoshoot.")
        source = self.assets.get_by_id(source_id)
        if source is None or int(source.creator_profile_id or 0) != int(creator_profile_id):
            raise KeyError("Teaser source is unavailable for this creator.")
        return source

    def _context(self, deliverable_id, creator_profile_id):
        row = self.photoshoots.get(str(deliverable_id))
        if row is None or int(row["creator_profile_id"]) != int(creator_profile_id): raise KeyError("Photoshoot not found.")
        if str(row.get("selling_mode") or "SESSION") != "BUNDLE": raise ValueError("Promotional teaser editing requires BUNDLE selling mode.")
        members = tuple(self.photoshoots.members(str(row["photoshoot_session_id"])))
        return row, tuple(sorted(members, key=lambda item: int(item["shot_order"])))

    def _decode_mask(self, value, width, height):
        return self.mask_validator.decode(value, width, height)

    @staticmethod
    def _atomic_bytes(path, value):
        with NamedTemporaryFile(dir=path.parent, suffix=".png", delete=False) as temp:
            temp.write(value); temporary = Path(temp.name)
        try: os.replace(temporary, path)
        finally: temporary.unlink(missing_ok=True)
