from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from app.models.generation_library import GeneratedImageRecord
from app.services.content_archive_service import ContentArchiveService
from app.services.generation_library_service import GenerationLibraryService
from app.services.quick_edit_service import CropBox, QuickEditService


def _library(tmp_path: Path):
    archive = ContentArchiveService(storage_dir=tmp_path / "archive", content_root=tmp_path / "content")
    library = GenerationLibraryService(
        storage_dir=tmp_path / "library", archive_service=archive,
        asset_repository=SimpleNamespace(get_by_id=lambda _id: None),
    )
    source_path = archive.content_paths()["pending_edit"] / "source.png"
    source_path.parent.mkdir(parents=True)
    image = Image.new("RGB", (100, 80), "red")
    image.paste("blue", (0, 60, 100, 80))
    image.save(source_path)
    source = GeneratedImageRecord(
        image_id="source-1", generation_job_id="job", generation_request_id="request",
        generation_result_id="result", output_reference=str(source_path), creator_profile_id=7,
        provider_id="seedream", prompt_plan_id="plan", prompt_text="portrait",
        creative_mode="explicit", reference_asset_id=93, status="pending_edit",
        review_state="pending_edit", generation_metadata={"original_marker": True},
    )
    library._write_records([source])
    return library, source


def test_crop_creates_new_generation_preserves_original_and_uses_no_provider(tmp_path):
    library, source = _library(tmp_path)

    result = QuickEditService(generation_library=library).crop(
        source.image_id, creator_profile_id=7, box=CropBox(0, 0, 100, 60))

    original = library.get(source.image_id)
    assert original.status == "active" and Path(original.output_reference).is_file()
    assert result.image_id != original.image_id and result.status == "active"
    assert result.imported_asset_id is None
    assert result.provider_id == "deterministic_crop"
    assert result.generation_metadata["source_generation_id"] == source.image_id
    assert result.generation_metadata["crop_box"] == {"x": 0, "y": 0, "width": 100, "height": 60}
    assert result.generation_metadata["provider_calls"] == 0
    assert result.generation_metadata["asset_intelligence_requested"] is False
    with Image.open(result.output_reference) as cropped:
        assert cropped.size == (100, 60)
        assert cropped.getpixel((50, 59)) == (255, 0, 0)


def test_crop_rejects_out_of_bounds_without_changing_source(tmp_path):
    library, source = _library(tmp_path)
    try:
        QuickEditService(generation_library=library).crop(
            source.image_id, creator_profile_id=7, box=CropBox(0, 20, 100, 70))
    except ValueError as error:
        assert "beyond" in str(error)
    else:
        raise AssertionError("Expected invalid crop to fail")
    assert library.get(source.image_id) == source
    assert len(library.list_records()) == 1
