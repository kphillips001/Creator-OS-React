from pathlib import Path

from PIL import Image, PngImagePlugin

from app.providers.social.x_provider import XPublishingProvider
from app.services.metadata_strip_service import MetadataStripService


def test_strip_metadata_preserves_png_resolution_transparency_and_pixels(tmp_path):
    source = tmp_path / "source.png"
    image = Image.new("RGBA", (17, 13), (10, 20, 30, 120))
    pnginfo = PngImagePlugin.PngInfo()
    pnginfo.add_text("Software", "Creator Tool")
    image.save(source, pnginfo=pnginfo)

    result = MetadataStripService().strip_to_path(
        source,
        output_dir=tmp_path / "output",
    )

    with Image.open(source) as original, Image.open(result.output_path) as stripped:
        assert stripped.size == original.size == (17, 13)
        assert stripped.mode == "RGBA"
        assert list(stripped.getdata()) == list(original.getdata())
        assert "Software" not in stripped.info
        assert "exif" not in stripped.info
        assert "xmp" not in stripped.info


def test_strip_metadata_removes_jpeg_exif_and_preserves_dimensions(tmp_path):
    source = tmp_path / "photo.jpg"
    image = Image.new("RGB", (24, 18), (100, 110, 120))
    exif = Image.Exif()
    exif[271] = "Camera Manufacturer"
    exif[305] = "Editing Software"
    image.save(source, quality=100, exif=exif)

    result = MetadataStripService().strip_to_path(
        source,
        output_dir=tmp_path / "out",
    )

    with Image.open(result.output_path) as stripped:
        assert stripped.size == (24, 18)
        assert len(stripped.getexif()) == 0


def test_output_names_never_overwrite_existing_files(tmp_path):
    source = tmp_path / "image.webp"
    Image.new("RGBA", (10, 10), (1, 2, 3, 4)).save(
        source, "WEBP", lossless=True
    )
    output = tmp_path / "out"
    output.mkdir()
    (output / "image.webp").write_bytes(b"existing")

    result = MetadataStripService().strip_to_path(source, output_dir=output)

    assert Path(result.output_path).name == "image_1.webp"
    assert (output / "image.webp").read_bytes() == b"existing"


class RecordingMetadataStripService:
    def __init__(self):
        self.calls = []

    def strip_to_exact_path(self, source, output, **kwargs):
        self.calls.append((Path(source), Path(output)))
        with Image.open(source) as image:
            image.save(output)


def test_x_preparation_uses_shared_metadata_strip_service(tmp_path):
    source = tmp_path / "source.png"
    Image.new("RGB", (32, 32), "red").save(source)
    shared = RecordingMetadataStripService()
    provider = XPublishingProvider(metadata_strip_service=shared)

    prepared = provider._prepare_image_for_x(source)
    try:
        assert len(shared.calls) == 1
        assert shared.calls[0][0] == source
        assert prepared.is_file()
    finally:
        prepared.unlink(missing_ok=True)


def test_utility_page_uses_shared_service_and_expected_output_directory():
    source = Path("app/dashboard/pages/strip_metadata.py").read_text(
        encoding="utf-8"
    )
    assert "MetadataStripService" in source
    assert 'Path(r"D:\\Strip MetaData")' in source
    assert "accept_multiple_files=True" in source
    assert '"Download All"' in source
    assert '"Open Output Folder"' in source
