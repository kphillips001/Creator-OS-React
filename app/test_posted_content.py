from pathlib import Path

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
