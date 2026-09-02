from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

from app.services.grid_thumbnail_service import GridThumbnailService
from app.services.local_vault_service import LocalVaultService


def _image(path: Path, size=(1200, 800), color=(180, 40, 90)) -> None:
    Image.new("RGB", size, color).save(path, format="PNG")


def test_thumbnail_is_webp_bounded_and_cached(tmp_path):
    source = tmp_path / "original.png"
    _image(source)
    service = GridThumbnailService(
        local_vault_service=LocalVaultService(tmp_path / "cms")
    )

    first = service.get_or_create(source, identity="asset-42")
    first_mtime = first.stat().st_mtime_ns
    second = service.get_or_create(source, identity="asset-42")

    assert first == second
    assert first_mtime == second.stat().st_mtime_ns
    assert first.parent == tmp_path / "cms" / "vault" / "thumbnails" / "asset_library"
    with Image.open(first) as thumbnail:
        assert thumbnail.format == "WEBP"
        assert thumbnail.size == (512, 341)


def test_thumbnail_never_upscales_and_source_change_invalidates(tmp_path):
    source = tmp_path / "small.png"
    _image(source, size=(200, 100))
    service = GridThumbnailService(
        local_vault_service=LocalVaultService(tmp_path / "cms")
    )
    first = service.get_or_create(source, identity="generation-1")
    with Image.open(first) as thumbnail:
        assert thumbnail.size == (200, 100)

    _image(source, size=(300, 150), color=(10, 20, 30))
    second = service.get_or_create(source, identity="generation-1")

    assert second != first
    with Image.open(second) as thumbnail:
        assert thumbnail.size == (300, 150)


def test_concurrent_thumbnail_requests_share_complete_cache_file(tmp_path):
    source = tmp_path / "original.png"
    _image(source)
    service = GridThumbnailService(
        local_vault_service=LocalVaultService(tmp_path / "cms")
    )

    with ThreadPoolExecutor(max_workers=6) as executor:
        paths = tuple(executor.map(
            lambda _value: service.get_or_create(source, identity="asset-42"),
            range(6),
        ))

    assert len(set(paths)) == 1
    assert not tuple(paths[0].parent.glob("*.tmp.webp"))
    with Image.open(paths[0]) as thumbnail:
        thumbnail.verify()


def test_missing_source_fails_without_creating_cache(tmp_path):
    service = GridThumbnailService(
        local_vault_service=LocalVaultService(tmp_path / "cms")
    )

    try:
        service.get_or_create(tmp_path / "missing.png", identity="asset-42")
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("missing source should fail")

    assert not service.cache_directory.exists()


def test_preview_is_aspect_preserving_bounded_cached_and_non_destructive(tmp_path):
    source = tmp_path / "portrait.png"
    _image(source, size=(2400, 3600))
    original = source.read_bytes()
    service = GridThumbnailService(local_vault_service=LocalVaultService(tmp_path / "cms"))

    first = service.get_or_create_preview(source, identity="asset-42")
    second = service.get_or_create_preview(source, identity="asset-42")

    assert first == second
    assert source.read_bytes() == original
    assert first.parent.name == "preview"
    with Image.open(first) as preview:
        assert preview.format == "WEBP"
        assert preview.size == (1067, 1600)


def test_preview_does_not_upscale_and_is_concurrency_safe(tmp_path):
    source = tmp_path / "small.png"
    _image(source, size=(800, 600))
    service = GridThumbnailService(local_vault_service=LocalVaultService(tmp_path / "cms"))

    with ThreadPoolExecutor(max_workers=6) as executor:
        paths = tuple(executor.map(
            lambda _value: service.get_or_create_preview(source, identity="generation-1"),
            range(6),
        ))

    assert len(set(paths)) == 1
    with Image.open(paths[0]) as preview:
        assert preview.size == (800, 600)
        preview.verify()
