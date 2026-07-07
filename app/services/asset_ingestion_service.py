import shutil
from pathlib import Path

from app.services.local_vault_service import LocalVaultService


class AssetIngestionService:
    """
    Copies imported media into the Local Vault.

    The original source path remains legacy compatibility metadata today;
    future runtime media reads should prefer local_vault_path.
    """

    IMAGE_SUFFIXES = {".gif", ".jpeg", ".jpg", ".png", ".webp"}
    VIDEO_SUFFIXES = {".m4v", ".mov", ".mp4", ".webm"}

    def __init__(self, local_vault_service: LocalVaultService | None = None):
        self.local_vault_service = local_vault_service or LocalVaultService()
        self.local_vault_service.initialize()

    def copy_to_local_vault(
        self,
        *,
        content_item_id: int,
        source_path: str | Path,
    ) -> dict:
        source = Path(source_path)

        if not source.exists():
            raise FileNotFoundError(f"Uploaded asset file not found: {source}")

        suffix = source.suffix
        destination_dir = self._destination_dir(suffix.lower())
        destination_dir.mkdir(parents=True, exist_ok=True)

        destination = destination_dir / f"{content_item_id}{suffix}"
        shutil.copy2(source, destination)

        if not destination.exists():
            raise FileNotFoundError(
                f"Local Vault copy was not created: {destination}"
            )

        return {
            "local_vault_path": str(destination),
            "local_vault_filename": destination.name,
            "local_vault_relative_path": str(
                destination.relative_to(self.local_vault_service.cms_root)
            ),
            "local_vault_cms_root": str(self.local_vault_service.cms_root),
            "original_upload_path": str(source),
        }

    def _destination_dir(self, suffix: str) -> Path:
        if suffix in self.VIDEO_SUFFIXES:
            return self.local_vault_service.path("vault/originals/videos")

        return self.local_vault_service.path("vault/originals/images")
