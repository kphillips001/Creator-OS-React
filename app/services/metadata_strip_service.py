"""Canonical image metadata stripping used by publishing and creator utilities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from PIL import Image, ImageOps


SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


@dataclass(frozen=True)
class MetadataStripResult:
    source_path: str
    output_path: str
    width: int
    height: int
    image_format: str
    metadata_removed: tuple[str, ...] = (
        "EXIF",
        "IPTC",
        "XMP",
        "GPS",
        "Camera Metadata",
        "Software Metadata",
    )


class MetadataStripService:
    """Strip non-pixel metadata by cleanly decoding and re-encoding the image."""

    DEFAULT_OUTPUT_DIR = Path(r"D:\Strip MetaData")

    def strip_to_path(
        self,
        source_path: str | Path,
        *,
        output_dir: str | Path | None = None,
        preferred_filename: str | None = None,
    ) -> MetadataStripResult:
        source = Path(source_path)
        self._validate_source(source)
        destination_dir = Path(output_dir or self.DEFAULT_OUTPUT_DIR)
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = self.unique_output_path(
            destination_dir,
            preferred_filename or source.name,
        )
        return self._strip(source, destination)

    def strip_to_exact_path(
        self,
        source_path: str | Path,
        output_path: str | Path,
        *,
        apply_exif_orientation: bool = False,
    ) -> MetadataStripResult:
        source = Path(source_path)
        self._validate_source(source)
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        return self._strip(
            source,
            destination,
            apply_exif_orientation=apply_exif_orientation,
        )

    @staticmethod
    def unique_output_path(directory: Path, filename: str) -> Path:
        safe_name = Path(filename).name
        stem = Path(safe_name).stem or "image"
        suffix = Path(safe_name).suffix.lower()
        if suffix not in SUPPORTED_IMAGE_SUFFIXES:
            suffix = ".png"
        candidate = directory / f"{stem}{suffix}"
        number = 1
        while candidate.exists():
            candidate = directory / f"{stem}_{number}{suffix}"
            number += 1
        return candidate

    def _strip(
        self,
        source: Path,
        destination: Path,
        *,
        apply_exif_orientation: bool = False,
    ) -> MetadataStripResult:
        with Image.open(source) as opened:
            image_format = self._format_for(destination.suffix, opened.format)
            image = (
                ImageOps.exif_transpose(opened)
                if apply_exif_orientation
                else opened
            )
            image.load()
            clean = image.copy()
            if image_format == "JPEG" and clean.mode not in {"RGB", "L", "CMYK"}:
                converted = clean.convert("RGB")
                clean.close()
                clean = converted
            save_options = self._save_options(clean, image_format, opened)
            clean.save(destination, format=image_format, **save_options)
            width, height = clean.size
            clean.close()
        return MetadataStripResult(
            source_path=str(source),
            output_path=str(destination),
            width=width,
            height=height,
            image_format=image_format,
        )

    @staticmethod
    def _save_options(image: Image.Image, image_format: str, source: Image.Image) -> dict:
        options: dict = {}
        # ICC describes color interpretation rather than source/camera identity.
        icc_profile = source.info.get("icc_profile")
        if icc_profile:
            options["icc_profile"] = icc_profile
        if image_format == "JPEG":
            options.update(quality=100, subsampling=0)
        elif image_format == "PNG":
            options.update(optimize=False)
        elif image_format == "WEBP":
            options.update(lossless=True, quality=100, method=6)
        return options

    @staticmethod
    def _format_for(suffix: str, fallback: str | None) -> str:
        return {
            ".jpg": "JPEG",
            ".jpeg": "JPEG",
            ".png": "PNG",
            ".webp": "WEBP",
        }.get(suffix.lower(), str(fallback or "PNG").upper())

    @staticmethod
    def _validate_source(source: Path) -> None:
        if not source.is_file():
            raise FileNotFoundError(f"Image not found: {source}")
        if source.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
            raise ValueError(f"Unsupported image format: {source.suffix}")
