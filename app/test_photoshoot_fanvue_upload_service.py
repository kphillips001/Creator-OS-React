import tempfile
import sys
import types
import unittest
from pathlib import Path

if "psycopg" not in sys.modules:
    psycopg = types.ModuleType("psycopg")
    rows = types.ModuleType("psycopg.rows")
    psycopg_types = types.ModuleType("psycopg.types")
    json_types = types.ModuleType("psycopg.types.json")
    errors = types.ModuleType("psycopg.errors")
    psycopg.connect = lambda *args, **kwargs: None
    rows.dict_row = object()
    json_types.Json = lambda value: value
    errors.UniqueViolation = type("UniqueViolation", (Exception,), {})
    sys.modules["psycopg"] = psycopg
    sys.modules["psycopg.rows"] = rows
    sys.modules["psycopg.types"] = psycopg_types
    sys.modules["psycopg.types.json"] = json_types
    sys.modules["psycopg.errors"] = errors

from app.models.generation_library import GeneratedImageRecord
from app.models.photoshoot_queue import PhotoshootSession
from app.services.photoshoot_fanvue_upload_service import (
    FANVUE_PHOTOSHOOT_FOLDER,
    FANVUE_WALL_FOLDER,
    PhotoshootFanvueUploadService,
)
from app.services.photoshoot_queue_service import PhotoshootQueueService


def session(metadata=None):
    return PhotoshootSession(
        session_id="photoshoot_session_test",
        creator_profile_id=7,
        title="Completed Shoot",
        reference_asset_id=None,
        creative_mode="photoshoot",
        status="completed",
        provider_id="seedream_5_0_pro",
        metadata=metadata or {},
    )


def record(image_id, path, *, imported_asset_id=None):
    return GeneratedImageRecord(
        image_id=image_id,
        generation_job_id=f"job_{image_id}",
        generation_request_id=f"request_{image_id}",
        generation_result_id=f"result_{image_id}",
        output_reference=str(path),
        creator_profile_id=7,
        provider_id="seedream_5_0_pro",
        prompt_plan_id=f"plan_{image_id}",
        prompt_text="Prompt",
        creative_mode="photoshoot",
        reference_asset_id=None,
        photoshoot_session_id="photoshoot_session_test",
        imported_asset_id=imported_asset_id,
    )


class FakeFanvueAPI:
    def __init__(self, *, fanvue_account_id):
        self.fanvue_account_id = fanvue_account_id

    def list_vault_folders(self):
        return {
            "success": True,
            "data": [
                {"name": FANVUE_PHOTOSHOOT_FOLDER, "uuid": "folder-telegram-wall"}
            ],
        }


class MissingFolderFanvueAPI:
    def __init__(self, *, fanvue_account_id):
        self.fanvue_account_id = fanvue_account_id

    def list_vault_folders(self):
        return {"success": True, "data": [{"name": "Other Folder"}]}


class WallFolderFanvueAPI:
    def __init__(self, *, fanvue_account_id):
        self.fanvue_account_id = fanvue_account_id

    def list_vault_folders(self):
        return {
            "success": True,
            "data": [
                {"name": FANVUE_WALL_FOLDER, "uuid": "folder-wall"},
            ],
        }


class FakePublishingService:
    def __init__(self):
        self.calls = []

    def upload_asset_media_item(self, *, fanvue_account_id, item):
        self.calls.append({"fanvue_account_id": fanvue_account_id, "item": item})
        return {
            "success": True,
            "media_uuid": f"media-{item['id']}",
            "preview_uuid": f"media-{item['id']}",
            "full_uuid": f"media-{item['id']}",
            "status": "uploaded",
            "folder_name": item.get("folder_name"),
            "folder_success": True,
        }


class FakeFulfillmentService:
    def __init__(self):
        self.calls = []

    def upload_customer_conversations_asset(self, *, asset_id, fanvue_account_id):
        self.calls.append(
            {"asset_id": asset_id, "fanvue_account_id": fanvue_account_id}
        )
        return types.SimpleNamespace(
            success=True,
            record=None,
            errors=(),
            warnings=(),
        )


class PhotoshootFanvueUploadServiceTests(unittest.TestCase):
    def test_uploads_completed_session_to_telegram_wall(self):
        with tempfile.TemporaryDirectory() as root:
            first = Path(root) / "shot1.png"
            second = Path(root) / "shot2.png"
            first.write_bytes(b"first")
            second.write_bytes(b"second")
            publishing = FakePublishingService()
            service = PhotoshootFanvueUploadService(
                publishing_service=publishing,
                api_service_factory=FakeFanvueAPI,
            )

            result = service.upload_completed_session(
                session=session(),
                records=(record("shot1", first), record("shot2", second)),
                fanvue_account_id=7,
            )

            self.assertTrue(result["success"])
            self.assertEqual(result["uploaded_folder"], FANVUE_PHOTOSHOOT_FOLDER)
            self.assertEqual(result["uploaded_count"], 2)
            self.assertEqual(result["total_count"], 2)
            self.assertEqual(tuple(result["uploaded_media_ids"]), ("media-shot1", "media-shot2"))
            self.assertEqual(len(publishing.calls), 2)
            self.assertEqual(publishing.calls[0]["item"]["folder_name"], FANVUE_PHOTOSHOOT_FOLDER)

    def test_uploads_completed_session_to_wall_folder_when_configured(self):
        with tempfile.TemporaryDirectory() as root:
            image_path = Path(root) / "shot1.png"
            image_path.write_bytes(b"first")
            publishing = FakePublishingService()
            service = PhotoshootFanvueUploadService(
                publishing_service=publishing,
                api_service_factory=WallFolderFanvueAPI,
                folder_name=FANVUE_WALL_FOLDER,
            )

            result = service.upload_completed_session(
                session=session(),
                records=(record("shot1", image_path),),
                fanvue_account_id=7,
            )

            self.assertTrue(result["success"])
            self.assertEqual(result["uploaded_folder"], FANVUE_WALL_FOLDER)
            self.assertEqual(result["folder"]["uuid"], "folder-wall")
            self.assertEqual(publishing.calls[0]["item"]["folder_name"], FANVUE_WALL_FOLDER)

    def test_retry_uploads_only_remaining_images(self):
        with tempfile.TemporaryDirectory() as root:
            first = Path(root) / "shot1.png"
            second = Path(root) / "shot2.png"
            first.write_bytes(b"first")
            second.write_bytes(b"second")
            publishing = FakePublishingService()
            service = PhotoshootFanvueUploadService(
                publishing_service=publishing,
                api_service_factory=FakeFanvueAPI,
            )
            partial_session = session(
                {
                    "fanvue_photoshoot_upload": {
                        "uploaded_media_ids": ("media-shot1",),
                        "uploaded_media_by_image_id": {"shot1": "media-shot1"},
                        "uploaded_count": 1,
                        "total_count": 2,
                    }
                }
            )

            result = service.upload_completed_session(
                session=partial_session,
                records=(record("shot1", first), record("shot2", second)),
                fanvue_account_id=7,
            )

            self.assertTrue(result["success"])
            self.assertEqual(len(publishing.calls), 1)
            self.assertEqual(publishing.calls[0]["item"]["id"], "shot2")
            self.assertEqual(tuple(result["uploaded_media_ids"]), ("media-shot1", "media-shot2"))

    def test_wall_upload_can_ignore_existing_metadata_and_upload_every_visible_image(self):
        with tempfile.TemporaryDirectory() as root:
            first = Path(root) / "shot1.png"
            second = Path(root) / "shot2.png"
            first.write_bytes(b"first")
            second.write_bytes(b"second")
            publishing = FakePublishingService()
            service = PhotoshootFanvueUploadService(
                publishing_service=publishing,
                api_service_factory=WallFolderFanvueAPI,
                folder_name=FANVUE_WALL_FOLDER,
            )
            previous_upload_session = session(
                {
                    "fanvue_photoshoot_upload": {
                        "uploaded_media_ids": ("stale-media-shot1", "stale-media-shot2"),
                        "uploaded_media_by_image_id": {
                            "shot1": "stale-media-shot1",
                            "shot2": "stale-media-shot2",
                        },
                        "uploaded_count": 2,
                        "total_count": 2,
                    }
                }
            )

            result = service.upload_completed_session(
                session=previous_upload_session,
                records=(record("shot1", first), record("shot2", second)),
                fanvue_account_id=7,
                reuse_existing_upload_metadata=False,
            )

            self.assertTrue(result["success"])
            self.assertEqual(len(publishing.calls), 2)
            self.assertEqual(
                tuple(call["item"]["id"] for call in publishing.calls),
                ("shot1", "shot2"),
            )
            self.assertEqual(tuple(result["uploaded_media_ids"]), ("media-shot1", "media-shot2"))

    def test_missing_local_file_fails_before_upload(self):
        publishing = FakePublishingService()
        service = PhotoshootFanvueUploadService(
            publishing_service=publishing,
            api_service_factory=WallFolderFanvueAPI,
            folder_name=FANVUE_WALL_FOLDER,
        )

        result = service.upload_completed_session(
            session=session(),
            records=(record("shot1", "C:/missing/shot1.png"),),
            fanvue_account_id=7,
            reuse_existing_upload_metadata=False,
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["reason"], "local_file_missing")
        self.assertEqual(publishing.calls, [])

    def test_missing_telegram_wall_folder_does_not_upload(self):
        publishing = FakePublishingService()
        service = PhotoshootFanvueUploadService(
            publishing_service=publishing,
            api_service_factory=MissingFolderFanvueAPI,
        )

        result = service.upload_completed_session(
            session=session(),
            records=(record("shot1", "C:/missing/shot1.png"),),
            fanvue_account_id=7,
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["reason"], "fanvue_folder_not_found")
        self.assertEqual(publishing.calls, [])

    def test_upload_result_persists_on_photoshoot_session(self):
        with tempfile.TemporaryDirectory() as root:
            queue = PhotoshootQueueService(storage_dir=root)
            created = session()
            queue._write_sessions([created])

            updated = queue.record_fanvue_upload_result(
                created.session_id,
                {
                    "uploaded_to_fanvue": True,
                    "uploaded_folder": FANVUE_PHOTOSHOOT_FOLDER,
                    "uploaded_timestamp": "2026-07-10T00:00:00Z",
                    "last_attempted_at": "2026-07-10T00:00:00Z",
                    "uploaded_media_ids": ("media-shot1",),
                    "uploaded_media_by_image_id": {"shot1": "media-shot1"},
                    "uploaded_count": 1,
                    "total_count": 1,
                    "failures": (),
                },
            )

            restored = PhotoshootQueueService(storage_dir=root).get_session(
                created.session_id
            )
            upload = restored.metadata["fanvue_photoshoot_upload"]
            self.assertTrue(upload["uploaded_to_fanvue"])
            self.assertEqual(upload["uploaded_folder"], FANVUE_PHOTOSHOOT_FOLDER)
            self.assertEqual(tuple(upload["uploaded_media_ids"]), ("media-shot1",))
            self.assertEqual(updated.metadata["fanvue_photoshoot_upload"], upload)

    def test_customer_conversations_photoshoot_upload_uses_imported_asset_id(self):
        fulfillment = FakeFulfillmentService()
        service = PhotoshootFanvueUploadService(
            publishing_service=FakePublishingService(),
            api_service_factory=WallFolderFanvueAPI,
            folder_name=FANVUE_WALL_FOLDER,
        )

        result = service.register_customer_conversations_fulfillment(
            session=session(),
            records=(
                record("shot1", "unused.png", imported_asset_id=501),
                record("shot2", "unused.png", imported_asset_id=502),
            ),
            fanvue_account_id=7,
            fulfillment_service=fulfillment,
        )

        self.assertTrue(result["success"])
        self.assertEqual(
            fulfillment.calls,
            [
                {"asset_id": 501, "fanvue_account_id": 7},
                {"asset_id": 502, "fanvue_account_id": 7},
            ],
        )
        self.assertEqual(result["results"][0]["image_id"], "shot1")
        self.assertEqual(result["results"][0]["asset_id"], 501)


if __name__ == "__main__":
    unittest.main()
