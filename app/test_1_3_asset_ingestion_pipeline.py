from pathlib import Path

from app.services.asset_ingestion_service import AssetIngestionService


def test_asset_ingestion_copies_file_to_local_vault_with_asset_id(tmp_path):
    source = tmp_path / "original upload.jpg"
    source.write_bytes(b"asset-bytes")

    service = AssetIngestionService()

    result = service.copy_to_local_vault(
        content_item_id=381,
        source_path=source,
    )

    copied_path = Path(result["local_vault_path"])

    assert copied_path.exists()
    assert copied_path.name == "381.jpg"
    assert copied_path.read_bytes() == b"asset-bytes"
    assert source.exists()
    assert result["local_vault_relative_path"] == (
        "vault\\originals\\images\\381.jpg"
    )


def test_asset_ingestion_routes_videos_to_video_originals(tmp_path):
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"video-bytes")

    service = AssetIngestionService()

    result = service.copy_to_local_vault(
        content_item_id=415,
        source_path=source,
    )

    copied_path = Path(result["local_vault_path"])

    assert copied_path.exists()
    assert copied_path.name == "415.mp4"
    assert copied_path.read_bytes() == b"video-bytes"
    assert source.exists()
    assert result["local_vault_relative_path"] == (
        "vault\\originals\\videos\\415.mp4"
    )
