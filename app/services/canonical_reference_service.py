"""Permanent creator identity image storage and startup recovery."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from app.services.local_vault_service import LocalVaultService


LOGGER = logging.getLogger(__name__)


class CanonicalReferenceService:
    """Owns permanent media outside normal Asset and vault cleanup roots."""

    IMAGE_NAME = "canonical_reference.png"
    METADATA_NAME = "metadata.json"

    def __init__(self, *, cms_root: str | Path | None = None) -> None:
        self.local_vault = LocalVaultService(cms_root)
        self.root = self.local_vault.cms_root / "Canonical"

    @staticmethod
    def creator_directory_name(display_name: str) -> str:
        clean = re.sub(r"[^A-Za-z0-9]+", "_", str(display_name).strip()).strip("_")
        return clean or "Creator"

    def creator_directory(self, display_name: str) -> Path:
        return self.root / self.creator_directory_name(display_name)

    def image_path(self, display_name: str) -> Path:
        return self.creator_directory(display_name) / self.IMAGE_NAME

    def metadata_path(self, display_name: str) -> Path:
        return self.creator_directory(display_name) / self.METADATA_NAME

    def protect(
        self,
        *,
        source_path: str | Path,
        creator_profile: Mapping[str, Any],
        original_filename: str,
        expected_sha256: str | None = None,
        historical_asset_id: int | None = None,
    ) -> Mapping[str, Any]:
        source = Path(source_path)
        if not source.is_file():
            raise FileNotFoundError(f"Canonical reference source not found: {source}")
        source_hash = self.sha256(source)
        if expected_sha256 and source_hash.upper() != expected_sha256.upper():
            raise ValueError("Canonical reference SHA-256 does not match the expected value.")

        display_name = self._display_name(creator_profile)
        directory = self.creator_directory(display_name)
        directory.mkdir(parents=True, exist_ok=True)
        destination = self.image_path(display_name)
        shutil.copy2(source, destination)
        destination_hash = self.sha256(destination)
        if destination_hash != source_hash:
            destination.unlink(missing_ok=True)
            raise IOError("Canonical reference copy failed integrity verification.")

        metadata = {
            "schema_version": 1,
            "creator_profile_id": int(creator_profile["id"]),
            "creator_display_name": display_name,
            "creator_persona_name": creator_profile.get("persona_name"),
            "creator_fanvue_account_id": creator_profile.get("fanvue_account_id"),
            "original_filename": original_filename,
            "canonical_filename": self.IMAGE_NAME,
            "canonical_path": str(destination),
            "sha256": destination_hash,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "historical_asset_id": historical_asset_id,
            "source_path": str(source),
            "permanent_identity_asset": True,
            "automatic_cleanup_allowed": False,
        }
        self.metadata_path(display_name).write_text(
            json.dumps(metadata, indent=2, default=str),
            encoding="utf-8",
        )
        return metadata

    def load_metadata(self, display_name: str) -> Mapping[str, Any] | None:
        path = self.metadata_path(display_name)
        if not path.is_file():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            LOGGER.warning("Canonical reference metadata is unreadable: %s", exc)
            return None
        return value if isinstance(value, Mapping) else None

    def verify(self, display_name: str) -> tuple[bool, str]:
        metadata = self.load_metadata(display_name)
        image = self.image_path(display_name)
        if metadata is None:
            return False, "Canonical reference metadata is missing."
        if not image.is_file():
            return False, f"Canonical reference image is missing: {image}"
        expected = str(metadata.get("sha256") or "").upper()
        actual = self.sha256(image)
        if not expected or actual != expected:
            return False, "Canonical reference SHA-256 verification failed."
        return True, actual

    def recover_creator(
        self,
        creator_profile: Mapping[str, Any],
        *,
        reference_service=None,
    ):
        from app.services.reference_library_service import ReferenceLibraryService

        service = reference_service or ReferenceLibraryService()
        creator_profile_id = int(creator_profile["id"])
        existing_asset_id = service.get_active_canonical_asset_id(
            creator_profile_id=creator_profile_id
        )
        if existing_asset_id is not None:
            return existing_asset_id

        display_name = self._display_name(creator_profile)
        valid, detail = self.verify(display_name)
        if not valid:
            LOGGER.warning(
                "Canonical reference recovery skipped for %s: %s",
                display_name,
                detail,
            )
            return None
        metadata = self.load_metadata(display_name) or {}
        result = service.restore_canonical_reference(
            media_path=self.image_path(display_name),
            creator_profile_id=creator_profile_id,
            original_filename=str(metadata.get("original_filename") or self.IMAGE_NAME),
            canonical_metadata=metadata,
        )
        if not result.success:
            LOGGER.warning(
                "Canonical reference recovery failed for %s: %s",
                display_name,
                result.message,
            )
            return None
        return result.reference

    @staticmethod
    def sha256(path: str | Path) -> str:
        digest = hashlib.sha256()
        with Path(path).open("rb") as file:
            for block in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest().upper()

    @staticmethod
    def _display_name(creator_profile: Mapping[str, Any]) -> str:
        return str(
            creator_profile.get("display_name")
            or creator_profile.get("persona_name")
            or creator_profile.get("name")
            or f"Creator_{creator_profile.get('id')}"
        )


def recover_all_active_creator_references() -> None:
    """Best-effort database rebuild recovery from permanent role metadata/media."""
    try:
        from app.database import get_db_connection
        from app.services.reference_library_service import ReferenceLibraryService

        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM creator_profiles WHERE COALESCE(is_active, TRUE) = TRUE")
                profiles = tuple(dict(row) for row in cursor.fetchall())
        canonical = CanonicalReferenceService()
        references = ReferenceLibraryService()
        for profile in profiles:
            canonical.recover_creator(profile, reference_service=references)
    except Exception as exc:
        LOGGER.warning("Canonical reference startup recovery was skipped: %s", exc)
