"""Canonical final-boundary presentation derivatives for Telegram still images."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from PIL import Image, ImageFilter, ImageOps


@dataclass(frozen=True)
class TelegramImagePresentation:
    path: Path
    metadata: dict
    reused: bool


class TelegramImageNormalizationService:
    """Guarantee a non-distorted 960x1280 upload artifact for Telegram."""

    VERSION = 1
    WIDTH = 960
    HEIGHT = 1280
    ASPECT_RATIO = "3:4"
    JPEG_QUALITY = 92
    MIN_COVER_RETENTION = 0.80
    SUPPORTED_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp"})

    @classmethod
    def is_supported_image(cls, path) -> bool:
        return Path(path).suffix.lower() in cls.SUPPORTED_SUFFIXES

    def normalize(self, source_path, *, prior_metadata=None) -> TelegramImagePresentation:
        source = Path(source_path)
        if not source.is_file():
            raise FileNotFoundError(f"Telegram source image not found: {source}")
        if not self.is_supported_image(source):
            raise ValueError(f"Unsupported Telegram image format: {source.suffix}")
        digest = self._sha256(source)
        output = source.with_name(f"{source.stem}_telegram_presentation_v{self.VERSION}.jpg")
        prior = dict(prior_metadata or {})
        if self._reusable(prior, digest, output):
            return TelegramImagePresentation(output, prior, True)

        with Image.open(source) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
        crop_box, retention = self._cover_crop(image.size)
        if retention >= self.MIN_COVER_RETENTION:
            rendered = image.crop(crop_box).resize(
                (self.WIDTH, self.HEIGHT), Image.Resampling.LANCZOS
            )
            strategy = "privacy_safe_cover_crop"
        else:
            rendered = self._background_canvas(image)
            strategy = "privacy_safe_background_canvas"

        output.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=output.parent, suffix=".jpg", delete=False) as temp:
            temporary = Path(temp.name)
        try:
            rendered.save(temporary, "JPEG", quality=self.JPEG_QUALITY, optimize=True)
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
            rendered.close()
            image.close()
        metadata = {
            "version": self.VERSION, "aspect_ratio": self.ASPECT_RATIO,
            "width": self.WIDTH, "height": self.HEIGHT, "strategy": strategy,
            "path": str(output), "source_path": str(source),
            "source_sha256": digest, "source_teaser_path": str(source),
            "source_teaser_sha256": digest,
        }
        return TelegramImagePresentation(output, metadata, False)

    @classmethod
    def _cover_crop(cls, size):
        width, height = size
        target = cls.WIDTH / cls.HEIGHT
        current = width / height
        if current > target:
            crop_width = max(1, round(height * target)); left = (width - crop_width) // 2
            box = (left, 0, left + crop_width, height)
        else:
            crop_height = max(1, round(width / target)); top = (height - crop_height) // 2
            box = (0, top, width, top + crop_height)
        retained = ((box[2] - box[0]) * (box[3] - box[1])) / (width * height)
        return box, retained

    @classmethod
    def _background_canvas(cls, image: Image.Image) -> Image.Image:
        box, _ = cls._cover_crop(image.size)
        background = image.crop(box).resize(
            (cls.WIDTH, cls.HEIGHT), Image.Resampling.LANCZOS
        ).filter(ImageFilter.GaussianBlur(radius=36))
        scale = min(cls.WIDTH / image.width, cls.HEIGHT / image.height)
        fitted = image.resize(
            (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
            Image.Resampling.LANCZOS,
        )
        background.paste(fitted, ((cls.WIDTH - fitted.width) // 2, (cls.HEIGHT - fitted.height) // 2))
        fitted.close()
        return background

    @classmethod
    def _reusable(cls, metadata, digest, output):
        metadata_digest = metadata.get("source_sha256") or metadata.get("source_teaser_sha256")
        return bool(
            metadata.get("version") == cls.VERSION
            and metadata.get("width") == cls.WIDTH and metadata.get("height") == cls.HEIGHT
            and metadata_digest == digest
            and Path(str(metadata.get("path") or output)).resolve() == output.resolve()
            and output.is_file()
        )

    @staticmethod
    def _sha256(path):
        value = sha256()
        with Path(path).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""): value.update(chunk)
        return value.hexdigest()
