"""Destination-specific presentation derivatives for Telegram Content Vault."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
import os

from PIL import Image, ImageFilter, ImageOps


@dataclass(frozen=True)
class ContentVaultPresentation:
    path: Path
    metadata: dict
    reused: bool


class ContentVaultTeaserNormalizationService:
    """Normalize an already privacy-safe teaser without touching its source."""

    VERSION = 1
    WIDTH = 960
    HEIGHT = 1280
    ASPECT_RATIO = "3:4"
    JPEG_QUALITY = 92
    # Use a cover crop only when it retains at least 80% of the privacy-safe
    # teaser. More destructive crops use a privacy-safe background canvas.
    MIN_COVER_RETENTION = 0.80

    def normalize(self, source_path, *, prior_metadata=None) -> ContentVaultPresentation:
        source = Path(source_path)
        if not source.is_file():
            raise FileNotFoundError(f"Privacy-safe Content Vault teaser not found: {source}")
        digest = self._sha256(source)
        output = source.with_name(f"{source.stem}_content_vault_presentation_v{self.VERSION}.jpg")
        prior = dict(prior_metadata or {})
        if self._reusable(prior, digest, output):
            return ContentVaultPresentation(output, prior, True)

        with Image.open(source) as opened:
            safe = ImageOps.exif_transpose(opened).convert("RGB")
        crop_box, retention = self._cover_crop(safe.size)
        if retention >= self.MIN_COVER_RETENTION:
            rendered = safe.crop(crop_box).resize(
                (self.WIDTH, self.HEIGHT), Image.Resampling.LANCZOS
            )
            strategy = "privacy_safe_cover_crop"
        else:
            rendered = self._background_canvas(safe)
            strategy = "privacy_safe_background_canvas"

        output.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=output.parent, suffix=".jpg", delete=False) as temp:
            temporary = Path(temp.name)
        try:
            rendered.save(temporary, "JPEG", quality=self.JPEG_QUALITY, optimize=True)
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
        metadata = {
            "version": self.VERSION, "aspect_ratio": self.ASPECT_RATIO,
            "width": self.WIDTH, "height": self.HEIGHT, "strategy": strategy,
            "path": str(output), "source_teaser_path": str(source),
            "source_teaser_sha256": digest,
        }
        return ContentVaultPresentation(output, metadata, False)

    @classmethod
    def _cover_crop(cls, size):
        width, height = size
        target = cls.WIDTH / cls.HEIGHT
        current = width / height
        if current > target:
            crop_width = max(1, round(height * target))
            left = (width - crop_width) // 2
            box = (left, 0, left + crop_width, height)
        else:
            crop_height = max(1, round(width / target))
            top = (height - crop_height) // 2
            box = (0, top, width, top + crop_height)
        retained = ((box[2] - box[0]) * (box[3] - box[1])) / (width * height)
        return box, retained

    @classmethod
    def _background_canvas(cls, safe: Image.Image) -> Image.Image:
        box, _ = cls._cover_crop(safe.size)
        background = safe.crop(box).resize(
            (cls.WIDTH, cls.HEIGHT), Image.Resampling.LANCZOS
        ).filter(ImageFilter.GaussianBlur(radius=36))
        scale = min(cls.WIDTH / safe.width, cls.HEIGHT / safe.height)
        fitted = safe.resize(
            (max(1, round(safe.width * scale)), max(1, round(safe.height * scale))),
            Image.Resampling.LANCZOS,
        )
        background.paste(
            fitted, ((cls.WIDTH - fitted.width) // 2, (cls.HEIGHT - fitted.height) // 2)
        )
        return background

    @classmethod
    def _reusable(cls, metadata, digest, output):
        return bool(
            metadata.get("version") == cls.VERSION
            and metadata.get("width") == cls.WIDTH
            and metadata.get("height") == cls.HEIGHT
            and metadata.get("source_teaser_sha256") == digest
            and Path(str(metadata.get("path") or output)).resolve() == output.resolve()
            and output.is_file()
        )

    @staticmethod
    def _sha256(path):
        value = sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                value.update(chunk)
        return value.hexdigest()


# Backward-compatible names now delegate to the single Telegram upload normalizer.
from app.services.telegram_image_normalization_service import (
    TelegramImageNormalizationService,
    TelegramImagePresentation,
)

ContentVaultPresentation = TelegramImagePresentation
ContentVaultTeaserNormalizationService = TelegramImageNormalizationService
