from pathlib import Path
from types import SimpleNamespace
from threading import Event, Thread

import pytest

from PIL import Image, PngImagePlugin

from app.services.android_device_service import InstagramHandoffDeviceResult
from app.services.instagram_handoff_service import InstagramHandoffService


class FakeGenerationLibrary:
    def __init__(self, source: Path):
        self.source = source

    def get(self, image_id):
        return SimpleNamespace(image_id=image_id)

    def resolve_publishable_image_reference(self, _image_id):
        return str(self.source) if self.source.exists() else None


class InspectingAndroid:
    def __init__(self):
        self.prepared_path = None
        self.info = None

    def handoff_instagram_image(self, local_path, *, remote_filename):
        self.prepared_path = Path(local_path)
        with Image.open(local_path) as image:
            self.info = dict(image.info)
            assert image.format == "PNG"
        return InstagramHandoffDeviceResult(
            serial="SERIAL",
            android_path=f"/sdcard/Pictures/Creator-OS/{remote_filename}",
            mirror_result="STARTED",
        )


class BlockingAndroid(InspectingAndroid):
    def __init__(self):
        super().__init__()
        self.started = Event()
        self.release = Event()

    def handoff_instagram_image(self, local_path, *, remote_filename):
        self.started.set()
        self.release.wait(timeout=2)
        return super().handoff_instagram_image(local_path, remote_filename=remote_filename)


def test_handoff_uses_clean_temporary_png_preserves_source_and_prepares_caption(tmp_path):
    source = tmp_path / "original.png"
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("prompt", "private metadata")
    Image.new("RGB", (4, 3), "red").save(source, pnginfo=metadata)
    original_bytes = source.read_bytes()
    android = InspectingAndroid()
    copied = []
    service = InstagramHandoffService(
        generation_library=FakeGenerationLibrary(source),
        android_device=android,
        clipboard_copy=copied.append,
    )

    result = service.handoff(generated_image_id="generated-1", caption="My caption")

    assert result["state"] == "HANDOFF_READY"
    assert result["message"] == "Sent to phone — finish your post in Instagram."
    assert result["captionPrepared"] is True
    assert copied == ["My caption"]
    assert android.info is not None and "prompt" not in android.info
    assert android.prepared_path is not None and not android.prepared_path.exists()
    assert source.exists() and source.read_bytes() == original_bytes


def test_duplicate_handoff_is_rejected_while_first_request_is_running(tmp_path):
    source = tmp_path / "original.png"
    Image.new("RGB", (2, 2), "blue").save(source)
    android = BlockingAndroid()
    service = InstagramHandoffService(
        generation_library=FakeGenerationLibrary(source),
        android_device=android,
        clipboard_copy=lambda _caption: None,
    )
    first = Thread(target=service.handoff, kwargs={
        "generated_image_id": "generated-1", "caption": "First",
    })
    first.start()
    assert android.started.wait(timeout=1)
    with pytest.raises(RuntimeError, match="already running"):
        service.handoff(generated_image_id="generated-1", caption="Second")
    android.release.set()
    first.join(timeout=2)
    assert not first.is_alive()


def test_unavailable_canonical_image_fails_without_device_or_library_mutation(tmp_path):
    library = FakeGenerationLibrary(tmp_path / "missing.png")
    android = InspectingAndroid()
    service = InstagramHandoffService(
        generation_library=library,
        android_device=android,
        clipboard_copy=lambda _caption: None,
    )
    with pytest.raises(ValueError, match="unavailable"):
        service.handoff(generated_image_id="generated-1", caption="Caption")
    assert android.prepared_path is None
