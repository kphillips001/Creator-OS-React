from pathlib import Path
from unittest.mock import patch

from app.models.generation_library import GeneratedImageRecord
from app.services.content_archive_service import ContentArchiveService
from app.services.generation_library_service import GenerationLibraryService
from app.services.posted_content_service import PostedContentService


def _record(image_id: str, path: Path, provider: str = "seedream_5_0_pro"):
    return GeneratedImageRecord(
        image_id=image_id,
        generation_job_id=f"job-{image_id}",
        generation_request_id=f"request-{image_id}",
        generation_result_id=f"result-{image_id}",
        output_reference=str(path),
        creator_profile_id=7,
        provider_id=provider,
        prompt_plan_id=f"plan-{image_id}",
        prompt_text=f"Prompt for {image_id}",
        creative_mode="premium_teaser",
        reference_asset_id=None,
    )


def test_discovers_x_and_telegram_files_with_existing_archive_metadata(tmp_path):
    archive = ContentArchiveService(storage_dir=tmp_path / "archive", content_root=tmp_path / "Content")
    x_source = tmp_path / "x.png"
    telegram_source = tmp_path / "telegram.jpg"
    x_source.write_bytes(b"x image")
    telegram_source.write_bytes(b"telegram image")
    archive.archive_published(_record("x-1", x_source), platform="x", caption="X caption", metadata={"creator_name": "Ava"})
    archive.archive_published(_record("telegram-1", telegram_source), platform="telegram", caption="Telegram caption", metadata={"post_to": "vault"})

    items = PostedContentService(archive).list_items()

    assert {item.platform for item in items} == {"X", "Telegram"}
    x_item = next(item for item in items if item.platform == "X")
    telegram_item = next(item for item in items if item.platform == "Telegram")
    assert x_item.caption == "X caption"
    assert x_item.creator == "Ava"
    assert x_item.generation_library_id == "x-1"
    assert x_item.provider == "seedream_5_0_pro"
    assert x_item.prompt == "Prompt for x-1"
    assert Path(telegram_item.file_location).parent.name == "Vault"
    assert telegram_item.media_url.endswith(f"/{telegram_item.content_id}/media")


def test_main_x_publish_archives_and_stages_identical_copy(tmp_path):
    archive = ContentArchiveService(storage_dir=tmp_path / "archive", content_root=tmp_path / "Content")
    source = tmp_path / "main-publish.png"
    source.write_bytes(b"exact published image bytes")

    result = archive.archive_published(
        _record("x-main", source), platform="x",
        metadata={"account_name": "AvaBlackthorne"},
    )

    main = Path(result.current_file_path)
    staged = archive.content_paths()["posted_x_slaves_staged"] / main.name
    assert main.is_file()
    assert staged.is_file()
    assert main.read_bytes() == staged.read_bytes() == b"exact published image bytes"


def test_x_slave_staging_is_idempotent(tmp_path):
    archive = ContentArchiveService(storage_dir=tmp_path / "archive", content_root=tmp_path / "Content")
    main = archive.content_paths()["posted_x_main"] / "same-image.png"
    main.parent.mkdir(parents=True)
    main.write_bytes(b"same image")

    first = archive._stage_main_x_publish_for_slaves(main)
    second = archive._stage_main_x_publish_for_slaves(main)

    assert first == second
    assert [path.name for path in first.parent.iterdir()] == ["same-image.png"]


def test_secondary_x_and_non_x_archives_do_not_stage_slave_copy(tmp_path):
    archive = ContentArchiveService(storage_dir=tmp_path / "archive", content_root=tmp_path / "Content")
    secondary = tmp_path / "secondary.png"
    telegram = tmp_path / "telegram.png"
    secondary.write_bytes(b"secondary")
    telegram.write_bytes(b"telegram")

    archive.archive_published(
        _record("x-secondary", secondary), platform="x",
        metadata={"account_names": ("AvaBlackthorneX",)},
    )
    archive.archive_published(
        _record("telegram", telegram), platform="telegram", metadata={"post_to": "main"},
    )

    assert not any(archive.content_paths()["posted_x_slaves_staged"].iterdir())


def test_slave_copy_failure_does_not_fail_successful_main_archive(tmp_path, caplog):
    archive = ContentArchiveService(storage_dir=tmp_path / "archive", content_root=tmp_path / "Content")
    source = tmp_path / "copy-failure.png"
    source.write_bytes(b"published")

    with patch.object(
        archive, "_stage_main_x_publish_for_slaves", side_effect=OSError("disk unavailable")
    ):
        result = archive.archive_published(
            _record("x-copy-failure", source), platform="x",
            metadata={"account_name": "AvaBlackthorne"},
        )

    assert Path(result.current_file_path).is_file()
    assert "X publish succeeded but slave staging copy failed" in caplog.text


def test_discovers_legacy_file_without_creating_persistence(tmp_path):
    archive = ContentArchiveService(storage_dir=tmp_path / "archive", content_root=tmp_path / "Content")
    legacy = archive.content_paths()["posted_x_main"] / "legacy-image.png"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"legacy")

    item = PostedContentService(archive).list_items()[0]

    assert item.generation_library_id == "legacy-image"
    assert item.caption == ""
    assert not archive.records_path.exists()


def test_posted_content_routes_are_read_only_and_registered():
    from app.fanvue_callback_server import app

    routes = {
        route.path: route.methods
        for route in app.routes
        if getattr(route, "path", "").startswith("/api/v1/posted-content")
    }
    assert routes["/api/v1/posted-content"] == {"GET"}
    assert routes["/api/v1/posted-content/{content_id}/media"] == {"GET"}
    assert routes["/api/v1/posted-content/{content_id}/move-to-generation-library"] == {"POST"}
    assert all("DELETE" not in methods for methods in routes.values())


def test_moves_published_image_back_with_history_classification_and_lineage(tmp_path):
    archive = ContentArchiveService(storage_dir=tmp_path / "archive", content_root=tmp_path / "Content")
    source = tmp_path / "published.png"
    source.write_bytes(b"published image")
    original = _record("return-1", source)
    original = original.__class__(
        **{**original.__dict__, "generation_recipe_id": "recipe-1",
           "content_classification": "NSFW", "classification_source": "MANUAL"}
    )
    published = archive.archive_published(
        original, platform="x", caption="Historical caption",
        metadata={"provider_publication_id": "post-123", "publication_url": "https://example.test/post"},
    )
    library = GenerationLibraryService(storage_dir=tmp_path / "library", archive_service=archive)
    service = PostedContentService(archive, generation_library=library)

    restored_item, replay = service.move_to_generation_library(published.archive_id)

    assert replay is False
    restored = library.get("return-1")
    assert restored.status == "active"
    assert restored.review_state == "restored_from_published"
    assert restored.generation_date == original.generation_date
    assert restored.created_at == original.created_at
    assert restored.generation_metadata["library_entry_reason"] == "PUBLISHED_ARCHIVE_RESTORE"
    assert restored.generation_metadata["source_publication_archive_id"] == published.archive_id
    assert restored.generation_metadata["library_entered_at"]
    assert restored.content_classification == "NSFW"
    assert restored.classification_source == "MANUAL"
    assert restored.generation_recipe_id == "recipe-1"
    assert Path(restored.output_reference).is_file()
    assert not Path(published.current_file_path).exists()
    history = next(item for item in archive.list_records() if item.archive_id == published.archive_id)
    assert history.archive_type == "published_x"
    assert history.caption == "Historical caption"
    assert history.metadata["provider_publication_id"] == "post-123"
    assert history.metadata["publication_url"] == "https://example.test/post"
    assert history.metadata["current_disposition"] == "generation_library"
    assert service.list_items() == ()
    assert restored_item.generation_library_id == "return-1"

    _, replay = service.move_to_generation_library(published.archive_id)
    assert replay is True
    assert len(library.list_records()) == 1


def test_move_rejects_legacy_or_duplicate_without_changing_published_file(tmp_path):
    archive = ContentArchiveService(storage_dir=tmp_path / "archive", content_root=tmp_path / "Content")
    legacy = archive.content_paths()["posted_x_main"] / "legacy.png"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"legacy")
    service = PostedContentService(
        archive,
        generation_library=GenerationLibraryService(
            storage_dir=tmp_path / "library", archive_service=archive
        ),
    )
    item = service.list_items()[0]
    assert item.move_eligible is False
    try:
        service.move_to_generation_library(item.content_id)
        assert False, "legacy media must not be movable"
    except KeyError:
        pass
    assert legacy.read_bytes() == b"legacy"


def test_backend_failure_rolls_file_and_library_back(tmp_path):
    archive = ContentArchiveService(storage_dir=tmp_path / "archive", content_root=tmp_path / "Content")
    source = tmp_path / "failure.png"
    source.write_bytes(b"failure bytes")
    published = archive.archive_published(_record("failure-1", source), platform="telegram")
    library = GenerationLibraryService(storage_dir=tmp_path / "library", archive_service=archive)
    service = PostedContentService(archive, generation_library=library)

    with patch.object(archive, "mark_published_returned_to_generation", side_effect=OSError("write failed")):
        try:
            service.move_to_generation_library(published.archive_id)
            assert False, "move must fail"
        except OSError:
            pass

    assert Path(published.current_file_path).read_bytes() == b"failure bytes"
    try:
        library.get("failure-1")
        assert False, "failed move must not leave a Generation Library record"
    except KeyError:
        pass
    assert len(service.list_items()) == 1


def test_duplicate_generation_record_fails_closed_without_moving_publication(tmp_path):
    archive = ContentArchiveService(storage_dir=tmp_path / "archive", content_root=tmp_path / "Content")
    source = tmp_path / "duplicate.png"
    source.write_bytes(b"duplicate bytes")
    original = _record("duplicate-1", source)
    published = archive.archive_published(original, platform="x")
    library = GenerationLibraryService(storage_dir=tmp_path / "library", archive_service=archive)
    library._append_records((original,))

    try:
        PostedContentService(archive, generation_library=library).move_to_generation_library(
            published.archive_id
        )
        assert False, "duplicate active record must fail closed"
    except ValueError as error:
        assert "already active" in str(error)

    assert Path(published.current_file_path).read_bytes() == b"duplicate bytes"
    history = next(item for item in archive.list_records() if item.archive_id == published.archive_id)
    assert "current_disposition" not in history.metadata
