"""Generation Library to Android Instagram handoff orchestration."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from typing import Callable
from uuid import uuid4

from app.services.android_device_service import AndroidDeviceService
from app.services.generation_library_service import GenerationLibraryService
from app.services.metadata_strip_service import MetadataStripService


class InstagramHandoffService:
    def __init__(self, *, generation_library=None, android_device=None, metadata_strip=None, clipboard_copy: Callable[[str], None] | None = None) -> None:
        self.generation_library = generation_library or GenerationLibraryService()
        self.android_device = android_device or AndroidDeviceService()
        self.metadata_strip = metadata_strip or MetadataStripService()
        self.clipboard_copy = clipboard_copy or self._copy_windows_clipboard
        self._lock = Lock()
        self._active_ids: set[str] = set()

    def handoff(self, *, generated_image_id: str, caption: str) -> dict[str, object]:
        selected_caption = str(caption or "").strip()
        if not selected_caption:
            raise ValueError("Caption is required before sending to Instagram.")
        with self._lock:
            if generated_image_id in self._active_ids:
                raise RuntimeError("An Instagram handoff is already running for this image.")
            self._active_ids.add(generated_image_id)
        try:
            record = self.generation_library.get(generated_image_id)
            reference = self.generation_library.resolve_publishable_image_reference(record.image_id)
            if not reference:
                raise ValueError("The selected Generation Library image is unavailable.")
            filename = f"creator-os-{self._safe_identity(record.image_id)}-{uuid4().hex[:10]}.png"
            with TemporaryDirectory(prefix="creator-os-instagram-") as temporary_dir:
                prepared = Path(temporary_dir) / filename
                self.metadata_strip.strip_to_exact_path(reference, prepared, apply_exif_orientation=True)
                device_result = self.android_device.handoff_instagram_image(prepared, remote_filename=filename)
                self.clipboard_copy(selected_caption)
            return {
                "state": "HANDOFF_READY",
                "message": "Sent to phone — finish your post in Instagram.",
                "generatedImageId": record.image_id,
                "androidPath": device_result.android_path,
                "deviceSerial": device_result.serial,
                "mirrorResult": device_result.mirror_result,
                "captionPrepared": True,
            }
        finally:
            with self._lock:
                self._active_ids.discard(generated_image_id)

    @staticmethod
    def _safe_identity(value: str) -> str:
        safe = "".join(character.lower() if character.isalnum() else "-" for character in str(value))
        return safe.strip("-")[:40] or "image"

    @staticmethod
    def _copy_windows_clipboard(caption: str) -> None:
        try:
            import pyperclip
            pyperclip.copy(caption)
        except Exception as error:
            raise RuntimeError("Unable to prepare the Instagram caption on the Windows clipboard") from error
