from pathlib import Path
from unittest.mock import patch

from app.models.generation_library import GeneratedImageRecord
from app.services.content_archive_service import ContentArchiveService
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
    assert all("POST" not in methods and "DELETE" not in methods for methods in routes.values())
