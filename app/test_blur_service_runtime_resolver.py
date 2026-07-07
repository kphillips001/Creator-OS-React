import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from app.services.blur_service import generate_blurred_preview


def create_image(path: Path, color: str) -> None:
    image = Image.new("RGB", (16, 16), color=color)
    image.save(path)


class BlurServiceRuntimeResolverTests(unittest.TestCase):
    def blurred_output_dir(self, root: Path) -> Path:
        output_dir = root / "cms" / "vault" / "blurred"
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def test_blur_prefers_media_metadata_local_vault_path(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            legacy_path = root / f"{root.name}_legacy.jpg"
            vault_path = root / f"{root.name}_vault.jpg"
            output_dir = self.blurred_output_dir(root)
            create_image(legacy_path, "red")
            create_image(vault_path, "blue")

            blurred_path = Path(
                generate_blurred_preview(
                    {
                        "file_path": str(legacy_path),
                        "media_metadata": {
                            "local_vault_path": str(vault_path),
                        },
                    },
                    output_dir=output_dir,
                    overwrite=True,
                )
            )

            self.assertEqual(
                blurred_path,
                output_dir / f"{vault_path.stem}_blurred.jpg",
            )
            self.assertTrue(blurred_path.exists())

    def test_blur_falls_back_to_legacy_file_path(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            legacy_path = root / f"{root.name}_legacy.jpg"
            output_dir = self.blurred_output_dir(root)
            create_image(legacy_path, "green")

            blurred_path = Path(
                generate_blurred_preview(
                    {"file_path": str(legacy_path)},
                    output_dir=output_dir,
                    overwrite=True,
                )
            )

            self.assertEqual(
                blurred_path,
                output_dir / f"{legacy_path.stem}_blurred.jpg",
            )
            self.assertTrue(blurred_path.exists())

    def test_blur_preserves_string_path_compatibility_and_cache(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / f"{root.name}_cached.jpg"
            output_dir = self.blurred_output_dir(root)
            create_image(image_path, "purple")

            first_path = Path(
                generate_blurred_preview(
                    str(image_path),
                    output_dir=output_dir,
                    overwrite=True,
                )
            )
            first_mtime = Path(first_path).stat().st_mtime_ns
            second_path = generate_blurred_preview(
                str(image_path),
                output_dir=output_dir,
            )
            second_mtime = Path(second_path).stat().st_mtime_ns

            self.assertEqual(str(first_path), second_path)
            self.assertEqual(first_mtime, second_mtime)

    def test_blur_reports_missing_path(self):
        with self.assertRaises(FileNotFoundError):
            generate_blurred_preview({"file_path": "missing.jpg"})


if __name__ == "__main__":
    unittest.main()
