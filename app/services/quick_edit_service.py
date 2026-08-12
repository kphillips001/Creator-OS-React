"""Deterministic Edit Studio tools that never invoke generation providers."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps

from app.models.generation_engine import utc_now
from app.models.generation_library import GeneratedImageRecord
from app.services.generation_library_service import GenerationLibraryService


@dataclass(frozen=True)
class CropBox:
    x: int
    y: int
    width: int
    height: int


class QuickEditService:
    def __init__(self, *, generation_library: GenerationLibraryService | None = None) -> None:
        self.library = generation_library or GenerationLibraryService()

    def crop(self, source_image_id: str, *, creator_profile_id: int, box: CropBox) -> GeneratedImageRecord:
        source = self.library.get(source_image_id)
        if source.creator_profile_id != int(creator_profile_id) or source.status != "pending_edit":
            raise ValueError("Crop source is not available in Edit Studio.")
        source_path = Path(source.output_reference).expanduser()
        if not source_path.is_file():
            raise FileNotFoundError("Crop source image is unavailable.")

        with Image.open(source_path) as opened:
            image = ImageOps.exif_transpose(opened)
            self._validate_box(box, image.width, image.height)
            cropped = image.crop((box.x, box.y, box.x + box.width, box.y + box.height))
            image_id = f"generated_image_{uuid4().hex[:24]}"
            destination_dir = self.library.archive_service.content_paths()["generation_active"]
            destination_dir.mkdir(parents=True, exist_ok=True)
            suffix = source_path.suffix.lower() if source_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"} else ".png"
            destination = destination_dir / f"{image_id}{suffix}"
            save_format = "JPEG" if suffix in {".jpg", ".jpeg"} else suffix.removeprefix(".").upper()
            if save_format == "JPEG" and cropped.mode not in {"RGB", "L"}:
                cropped = cropped.convert("RGB")
            cropped.save(destination, format=save_format, quality=95)

        now = utc_now()
        derived = GeneratedImageRecord(
            image_id=image_id,
            generation_job_id=f"quick_edit_crop_job_{uuid4().hex}",
            generation_request_id=f"quick_edit_crop_request_{uuid4().hex}",
            generation_result_id=f"quick_edit_crop_result_{uuid4().hex}",
            output_reference=str(destination), creator_profile_id=source.creator_profile_id,
            provider_id="deterministic_crop", prompt_plan_id="quick_edit_crop",
            prompt_text="Deterministic crop", creative_mode="quick_edit_crop",
            reference_asset_id=source.reference_asset_id,
            provider_metadata={}, prompt_metadata={},
            generation_metadata={
                "source": "edit_studio_quick_edit", "workflow_type": "quick_edit",
                "quick_edit_tool": "crop", "source_generation_id": source.image_id,
                "source_output_reference": source.output_reference,
                "crop_box": {"x": box.x, "y": box.y, "width": box.width, "height": box.height},
                "source_dimensions": {"width": image.width, "height": image.height},
                "output_dimensions": {"width": box.width, "height": box.height},
                "provider_calls": 0, "asset_intelligence_requested": False,
            },
            created_at=now, updated_at=now,
        )
        original_records = list(self.library.list_records())
        try:
            returned = self.library.return_pending_edit_to_library(source.image_id)
            if not returned.success:
                raise RuntimeError("Original image could not be returned to Generation Library.")
            self.library._write_records([derived, *self.library.list_records()])
        except Exception:
            self.library._write_records(original_records)
            destination.unlink(missing_ok=True)
            raise
        return derived

    @staticmethod
    def dimensions(path: str | Path) -> tuple[int, int]:
        with Image.open(Path(path).expanduser()) as opened:
            image = ImageOps.exif_transpose(opened)
            return image.width, image.height

    @staticmethod
    def _validate_box(box: CropBox, width: int, height: int) -> None:
        if box.x < 0 or box.y < 0 or box.width < 1 or box.height < 1:
            raise ValueError("Crop area must have positive dimensions within the source image.")
        if box.x + box.width > width or box.y + box.height > height:
            raise ValueError("Crop area extends beyond the source image.")
