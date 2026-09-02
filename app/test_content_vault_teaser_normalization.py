from pathlib import Path

from PIL import Image

from app.services.blur_service import generate_blurred_preview
from app.services.content_vault_teaser_normalization_service import (
    ContentVaultTeaserNormalizationService,
)


def image(path, size, color=(80, 40, 20)):
    Image.new("RGB", size, color).save(path)
    return path


def test_portrait_ratios_normalize_without_changing_active_teaser(tmp_path):
    service = ContentVaultTeaserNormalizationService()
    for size in ((832, 1248), (864, 1152), (832, 1229)):
        source = image(tmp_path / f"safe-{size[1]}.png", size)
        before = source.read_bytes()
        result = service.normalize(source)
        with Image.open(result.path) as normalized:
            assert normalized.size == (960, 1280)
            assert normalized.mode == "RGB"
        assert source.read_bytes() == before
        assert result.metadata["strategy"] == "privacy_safe_cover_crop"
        assert result.metadata["source_teaser_path"] == str(source)


def test_cover_crop_math_and_threshold_are_deterministic():
    service = ContentVaultTeaserNormalizationService()
    box, retained = service._cover_crop((832, 1248))
    assert box == (0, 69, 832, 1178)
    assert retained == 832 * 1109 / (832 * 1248)
    assert retained >= service.MIN_COVER_RETENTION
    _, landscape_retained = service._cover_crop((1600, 900))
    assert landscape_retained < service.MIN_COVER_RETENTION


def test_landscape_and_square_use_only_privacy_safe_canvas_input(tmp_path):
    service = ContentVaultTeaserNormalizationService()
    for size in ((1600, 900), (1000, 1000), (400, 1600)):
        safe = image(tmp_path / f"safe-{size[0]}-{size[1]}.png", size, (12, 90, 140))
        result = service.normalize(safe)
        assert result.metadata["strategy"] == "privacy_safe_background_canvas"
        with Image.open(result.path) as normalized:
            assert normalized.size == (960, 1280)
            # Both fitted foreground and background originated from this one-color
            # privacy-safe input, so no paid-source pixel can be introduced.
            center = normalized.getpixel((480, 640))
            assert abs(center[0] - 12) < 5
            assert abs(center[1] - 90) < 5
            assert abs(center[2] - 140) < 5


def test_idempotency_and_source_change_invalidation(tmp_path):
    source = image(tmp_path / "safe.png", (832, 1248), (10, 20, 30))
    service = ContentVaultTeaserNormalizationService()
    first = service.normalize(source)
    first_mtime = first.path.stat().st_mtime_ns
    reused = service.normalize(source, prior_metadata=first.metadata)
    assert reused.reused is True
    assert reused.path.stat().st_mtime_ns == first_mtime
    image(source, (832, 1248), (200, 30, 40))
    rebuilt = service.normalize(source, prior_metadata=first.metadata)
    assert rebuilt.reused is False
    assert rebuilt.metadata["source_teaser_sha256"] != first.metadata["source_teaser_sha256"]


def test_full_blur_exif_transposes_before_rendering(tmp_path):
    source = tmp_path / "oriented.jpg"
    picture = Image.new("RGB", (30, 60), (180, 90, 20))
    exif = picture.getexif(); exif[274] = 6
    picture.save(source, exif=exif)
    result = Path(generate_blurred_preview(source, output_dir=tmp_path / "blurred"))
    with Image.open(result) as blurred:
        assert blurred.size == (60, 30)
