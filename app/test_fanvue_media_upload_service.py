import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.fanvue_media_upload_service import FanvueMediaUploadService


class FanvueMediaUploadRuntimePathTests(unittest.TestCase):
    def service(self):
        return FanvueMediaUploadService(fanvue_account_id=7)

    def test_upload_resolution_prefers_media_metadata_local_vault_path(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            legacy_path = root / "legacy.jpg"
            direct_path = root / "direct.jpg"
            vault_path = root / "vault.jpg"
            legacy_path.write_bytes(b"legacy")
            direct_path.write_bytes(b"direct")
            vault_path.write_bytes(b"vault")

            resolved = self.service()._resolve_upload_file_path(
                {
                    "file_path": str(legacy_path),
                    "local_vault_path": str(direct_path),
                    "media_metadata": {
                        "local_vault_path": str(vault_path),
                    },
                }
            )

        self.assertEqual(resolved, vault_path)

    def test_upload_resolution_falls_back_to_direct_local_vault_path(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            legacy_path = root / "legacy.webp"
            direct_path = root / "direct.webp"
            legacy_path.write_bytes(b"legacy")
            direct_path.write_bytes(b"direct")

            resolved = self.service()._resolve_upload_file_path(
                {
                    "file_path": str(legacy_path),
                    "local_vault_path": str(direct_path),
                    "media_metadata": {},
                }
            )

        self.assertEqual(resolved, direct_path)

    def test_upload_resolution_falls_back_to_legacy_file_path(self):
        with TemporaryDirectory() as temp_dir:
            legacy_path = Path(temp_dir) / "legacy.mp4"
            legacy_path.write_bytes(b"legacy")

            resolved = self.service()._resolve_upload_file_path(
                {
                    "file_path": str(legacy_path),
                    "media_metadata": {},
                }
            )

        self.assertEqual(resolved, legacy_path)

    def test_upload_item_reports_missing_legacy_path_without_network(self):
        result = self.service().upload_media_item(
            {
                "id": 123,
                "file_path": "missing.jpg",
                "classification": "VIP_IMAGE",
            }
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["media_uuid"], None)
        self.assertIn("File not found", result["error"])


if __name__ == "__main__":
    unittest.main()
