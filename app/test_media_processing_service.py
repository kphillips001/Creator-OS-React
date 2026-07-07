import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from PIL import Image

from app.services.local_vault_service import LocalVaultService
from app.services.media_processing_service import MediaProcessingService


def create_image(path: Path, color: str = "blue") -> None:
    image = Image.new("RGB", (16, 16), color=color)
    image.save(path)


class MediaProcessingServiceTests(unittest.TestCase):
    def test_blur_generation_delegates_to_media_processing_dependency(self):
        calls = []

        def fake_blur_generator(media, **kwargs):
            calls.append((media, kwargs))
            return "data/previews/asset_blurred.jpg"

        service = MediaProcessingService(blur_generator=fake_blur_generator)

        result = service.generate_blurred_preview(
            "data/uploads/asset.jpg",
            overwrite=True,
        )

        self.assertEqual(result, "data/previews/asset_blurred.jpg")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "data/uploads/asset.jpg")
        self.assertTrue(calls[0][1]["overwrite"])
        self.assertTrue(str(calls[0][1]["output_dir"]).endswith("vault\\blurred"))

    def test_generate_derivative_supports_blur_alias(self):
        calls = []

        def fake_blur_generator(media, **kwargs):
            calls.append((media, kwargs))
            return "data/previews/asset_blurred.jpg"

        service = MediaProcessingService(blur_generator=fake_blur_generator)

        result = service.generate_derivative(
            "data/uploads/asset.jpg",
            "blur",
            blur_strength=20,
        )

        self.assertEqual(result, "data/previews/asset_blurred.jpg")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "data/uploads/asset.jpg")
        self.assertEqual(calls[0][1]["blur_strength"], 20)
        self.assertTrue(str(calls[0][1]["output_dir"]).endswith("vault\\blurred"))

    def test_new_blurred_preview_is_written_into_local_vault(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "asset.jpg"
            create_image(source)
            local_vault = LocalVaultService(root / "cms")
            service = MediaProcessingService(local_vault_service=local_vault)

            result = Path(
                service.generate_derivative(
                    str(source),
                    "blur",
                    overwrite=True,
                )
            )

            self.assertEqual(result.parent, local_vault.path("vault/blurred"))
            self.assertEqual(result.name, "asset_blurred.jpg")
            self.assertTrue(result.exists())

    def test_existing_data_previews_derivative_still_resolves(self):
        legacy_dir = Path("data/previews")
        legacy_dir.mkdir(parents=True, exist_ok=True)
        legacy_path = legacy_dir / "legacy_b2_3_blurred.jpg"
        legacy_path.write_bytes(b"legacy")
        self.addCleanup(lambda: legacy_path.unlink(missing_ok=True))

        result = MediaProcessingService().resolve_derivative(
            {"blurred_preview_path": legacy_path.name},
            "blurred_preview",
        )

        self.assertEqual(Path(result), legacy_path)

    def test_resolve_derivative_prefers_local_vault_over_legacy_path(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original = root / "asset.jpg"
            create_image(original)
            legacy = root / "asset_legacy_blurred.jpg"
            legacy.write_bytes(b"legacy")
            local_vault = LocalVaultService(root / "cms")
            local_vault.initialize()
            vault_preview = local_vault.path("vault/blurred") / "asset_blurred.jpg"
            vault_preview.write_bytes(b"vault")
            service = MediaProcessingService(local_vault_service=local_vault)
            asset = {
                "file_path": str(original),
                "blurred_preview_path": str(legacy),
            }

            result = service.resolve_derivative(
                asset,
                "blurred_preview",
            )

        self.assertEqual(result, str(vault_preview))

    def test_media_metadata_derivative_still_has_highest_precedence(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original = root / "asset.jpg"
            create_image(original)
            metadata_preview = root / "metadata_blurred.jpg"
            metadata_preview.write_bytes(b"metadata")
            local_vault = LocalVaultService(root / "cms")
            local_vault.initialize()
            vault_preview = local_vault.path("vault/blurred") / "asset_blurred.jpg"
            vault_preview.write_bytes(b"vault")
            service = MediaProcessingService(local_vault_service=local_vault)
            asset = {
                "file_path": str(original),
                "media_metadata": {
                    "derivatives": {
                        "blurred_preview": str(metadata_preview),
                    },
                },
            }

            result = service.resolve_derivative(
                asset,
                "blurred_preview",
            )

        self.assertEqual(result, str(metadata_preview))

    def test_build_derivative_metadata_uses_provider_neutral_shape(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            local_vault = LocalVaultService(root / "cms")
            local_vault.initialize()
            service = MediaProcessingService(local_vault_service=local_vault)
            derivative_path = local_vault.path("vault/blurred") / "asset_blurred.jpg"

            metadata = service.build_derivative_metadata(
                derivative_path=derivative_path,
                derivative_type="blurred_preview",
                generated_at="2026-07-01T00:00:00+00:00",
            )

        self.assertEqual(metadata["path"], str(derivative_path))
        self.assertEqual(metadata["type"], "blur")
        self.assertEqual(metadata["storage"], "local_vault")
        self.assertEqual(metadata["generated_at"], "2026-07-01T00:00:00+00:00")
        self.assertEqual(metadata["source"], "media_processing_service")

    def test_generate_derivative_metadata_generates_and_describes_derivative(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "asset.jpg"
            create_image(source)
            local_vault = LocalVaultService(root / "cms")
            service = MediaProcessingService(local_vault_service=local_vault)

            metadata = service.generate_derivative_metadata(
                str(source),
                "blur",
                overwrite=True,
            )

            derivative_path = Path(metadata["path"])
            self.assertTrue(derivative_path.exists())
            self.assertEqual(derivative_path.parent, local_vault.path("vault/blurred"))
            self.assertEqual(metadata["type"], "blur")
            self.assertEqual(metadata["storage"], "local_vault")

    def test_merge_derivative_metadata_preserves_existing_media_metadata(self):
        service = MediaProcessingService()
        original_metadata = {
            "local_vault_path": "vault/originals/images/10.jpg",
            "original_filename": "source.jpg",
            "derivatives": {
                "thumbnail": {
                    "path": "vault/thumbnails/10.jpg",
                    "type": "thumbnail",
                },
            },
        }

        merged = service.merge_derivative_metadata(
            original_metadata,
            derivative_type="blur",
            derivative_metadata={
                "path": "vault/blurred/10_blurred.jpg",
                "type": "blur",
                "storage": "local_vault",
                "generated_at": "2026-07-01T00:00:00+00:00",
                "source": "media_processing_service",
            },
        )

        self.assertEqual(
            merged["local_vault_path"],
            "vault/originals/images/10.jpg",
        )
        self.assertEqual(merged["original_filename"], "source.jpg")
        self.assertIn("thumbnail", merged["derivatives"])
        self.assertEqual(
            merged["derivatives"]["blur"]["path"],
            "vault/blurred/10_blurred.jpg",
        )
        self.assertEqual(
            merged["derivatives"]["blurred_preview"],
            merged["derivatives"]["blur"],
        )

    def test_resolve_derivative_finds_legacy_blurred_preview_path(self):
        with TemporaryDirectory() as temp_dir:
            preview_path = Path(temp_dir) / "asset_blurred.jpg"
            preview_path.write_bytes(b"preview")
            asset = SimpleNamespace(
                blurred_preview_path=str(preview_path),
                media_metadata={},
            )

            result = MediaProcessingService().resolve_derivative(
                asset,
                "blurred_preview",
            )

        self.assertEqual(result, str(preview_path))

    def test_resolve_derivative_finds_media_metadata_derivative_path(self):
        with TemporaryDirectory() as temp_dir:
            preview_path = Path(temp_dir) / "asset_blurred.jpg"
            preview_path.write_bytes(b"preview")
            asset = {
                "media_metadata": {
                    "derivatives": {
                        "blur": {
                            "path": str(preview_path),
                        },
                    },
                },
            }

            result = MediaProcessingService().resolve_derivative(
                asset,
                "blur",
            )

        self.assertEqual(result, str(preview_path))

    def test_resolve_derivative_finds_json_metadata_blurred_preview(self):
        with TemporaryDirectory() as temp_dir:
            preview_path = Path(temp_dir) / "asset_blurred.jpg"
            preview_path.write_bytes(b"preview")
            asset = {
                "media_metadata": (
                    '{"derivatives": {"blurred_preview": "'
                    + str(preview_path).replace("\\", "\\\\")
                    + '"}}'
                ),
            }

            result = MediaProcessingService().resolve_derivative(
                asset,
                "blurred_preview",
            )

        self.assertEqual(result, str(preview_path))

    def test_unsupported_derivative_type_behavior_is_controlled(self):
        service = MediaProcessingService()

        self.assertIsNone(
            service.resolve_derivative(
                {},
                "watermark",
            )
        )
        with self.assertRaises(ValueError):
            service.generate_derivative(
                "data/uploads/asset.jpg",
                "watermark",
            )
        with self.assertRaises(ValueError):
            service.get_or_create_derivative(
                "data/uploads/asset.jpg",
                "watermark",
            )

    def test_get_or_create_derivative_uses_existing_before_generating(self):
        calls = []

        def fake_blur_generator(media, **kwargs):
            calls.append((media, kwargs))
            return "data/previews/generated_blurred.jpg"

        with TemporaryDirectory() as temp_dir:
            preview_path = Path(temp_dir) / "asset_blurred.jpg"
            preview_path.write_bytes(b"preview")
            asset = {"blurred_preview_path": str(preview_path)}
            service = MediaProcessingService(blur_generator=fake_blur_generator)

            result = service.get_or_create_derivative(
                asset,
                "blurred_preview",
            )

        self.assertEqual(result, str(preview_path))
        self.assertEqual(calls, [])

    def test_get_or_create_derivative_generates_when_missing(self):
        calls = []

        def fake_blur_generator(media, **kwargs):
            calls.append((media, kwargs))
            return "data/previews/generated_blurred.jpg"

        service = MediaProcessingService(blur_generator=fake_blur_generator)

        result = service.get_or_create_derivative(
            "data/uploads/asset.jpg",
            "blurred_preview",
            overwrite=True,
        )

        self.assertEqual(result, "data/previews/generated_blurred.jpg")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "data/uploads/asset.jpg")
        self.assertTrue(calls[0][1]["overwrite"])
        self.assertTrue(str(calls[0][1]["output_dir"]).endswith("vault\\blurred"))

    def test_regenerate_and_delete_derivatives_use_public_contract(self):
        generated_paths = []

        def fake_blur_generator(media, **kwargs):
            generated_path = Path(media)
            generated_path.write_bytes(b"generated")
            generated_paths.append((str(generated_path), kwargs))
            return str(generated_path)

        with TemporaryDirectory() as temp_dir:
            preview_path = Path(temp_dir) / "asset_blurred.jpg"
            service = MediaProcessingService(blur_generator=fake_blur_generator)

            regenerate_result = service.regenerate_derivatives(
                str(preview_path),
                derivative_types=["blur"],
                overwrite=False,
            )
            delete_result = service.delete_derivatives(
                {"blurred_preview_path": str(preview_path)},
                derivative_types=["blurred_preview"],
            )

        self.assertEqual(
            regenerate_result,
            {"blurred_preview": str(preview_path)},
        )
        self.assertEqual(
            generated_paths,
            [
                (
                    str(preview_path),
                    {
                        "overwrite": True,
                        "output_dir": service.derivative_directory("blur"),
                    },
                )
            ],
        )
        self.assertEqual(delete_result, {"blurred_preview": True})


if __name__ == "__main__":
    unittest.main()
