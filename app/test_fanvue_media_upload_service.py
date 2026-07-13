import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import app.services.fanvue_media_upload_service as fanvue_media_upload_module
from app.services.fanvue_media_upload_service import FanvueMediaUploadService


class FakeResponse:
    def __init__(self, status_code=200, body=None, text="", headers=None):
        self.status_code = status_code
        self._body = body
        self.text = text
        self.headers = headers or {}

    def json(self):
        if self._body is None:
            raise ValueError("No JSON body")
        return self._body


class FakeRequests:
    def __init__(self):
        self.calls = []
        self.media_statuses = ["processing", "ready"]

    def post(self, url, **kwargs):
        self.calls.append(("post", url, kwargs.get("json")))
        if url.endswith("/media/uploads"):
            return FakeResponse(
                body={
                    "mediaUuid": "media-ready-123",
                    "uploadId": "upload-123",
                }
            )
        if "/vault/folders/Wall/media" in url:
            return FakeResponse(body={"attached": True})
        return FakeResponse(status_code=404, body={"error": "unexpected post"})

    def get(self, url, **kwargs):
        self.calls.append(("get", url, None))
        if url.endswith("/media/uploads/upload-123/parts/1/url"):
            return FakeResponse(text="https://signed-upload.test/part-1")
        if url.endswith("/media/media-ready-123"):
            status = self.media_statuses.pop(0)
            return FakeResponse(body={"uuid": "media-ready-123", "status": status})
        return FakeResponse(status_code=404, body={"error": "unexpected get"})

    def put(self, url, **kwargs):
        self.calls.append(("put", url, None))
        return FakeResponse(headers={"ETag": '"etag-123"'})

    def patch(self, url, **kwargs):
        self.calls.append(("patch", url, kwargs.get("json")))
        return FakeResponse(body={"status": "processing"})


class FanvueMediaUploadRuntimePathTests(unittest.TestCase):
    def service(self):
        return FanvueMediaUploadService(fanvue_account_id=7)

    def test_upload_resolution_prefers_media_metadata_local_vault_path(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            legacy_path = root / "legacy.jpg"
            direct_path = root / "direct.jpg"
            vault_path = root / "vault.jpg"
            legacy_path.write_bytes(b"legacy")
            direct_path.write_bytes(b"direct")
            vault_path.write_bytes(b"vault")

            resolved = self.service()._resolve_upload_file_path(
                {
                    "file_path": str(legacy_path),
                    "local_vault_path": str(direct_path),
                    "media_metadata": {
                        "local_vault_path": str(vault_path),
                    },
                }
            )

        self.assertEqual(resolved, vault_path)

    def test_upload_resolution_falls_back_to_direct_local_vault_path(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            legacy_path = root / "legacy.webp"
            direct_path = root / "direct.webp"
            legacy_path.write_bytes(b"legacy")
            direct_path.write_bytes(b"direct")

            resolved = self.service()._resolve_upload_file_path(
                {
                    "file_path": str(legacy_path),
                    "local_vault_path": str(direct_path),
                    "media_metadata": {},
                }
            )

        self.assertEqual(resolved, direct_path)

    def test_upload_resolution_falls_back_to_legacy_file_path(self):
        with TemporaryDirectory() as temp_dir:
            legacy_path = Path(temp_dir) / "legacy.mp4"
            legacy_path.write_bytes(b"legacy")

            resolved = self.service()._resolve_upload_file_path(
                {
                    "file_path": str(legacy_path),
                    "media_metadata": {},
                }
            )

        self.assertEqual(resolved, legacy_path)

    def test_upload_item_reports_missing_legacy_path_without_network(self):
        result = self.service().upload_media_item(
            {
                "id": 123,
                "file_path": "missing.jpg",
                "classification": "VIP_IMAGE",
            }
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["media_uuid"], None)
        self.assertIn("File not found", result["error"])

    def test_upload_polls_until_ready_before_attaching_to_wall_folder(self):
        fake_requests = FakeRequests()
        original_requests = fanvue_media_upload_module.requests
        fanvue_media_upload_module.requests = fake_requests
        try:
            service = FanvueMediaUploadService(
                fanvue_account_id=7,
                processing_poll_interval_seconds=0,
                processing_timeout_seconds=5,
            )
            service.oauth.get_valid_access_token = lambda: "token"
            with TemporaryDirectory() as temp_dir:
                image_path = Path(temp_dir) / "ready.png"
                image_path.write_bytes(b"image")

                result = service.upload_media_item(
                    {
                        "id": "shot-ready",
                        "file_path": str(image_path),
                        "classification": "WALL_IMAGE",
                        "folder_name": "Wall",
                    }
                )
        finally:
            fanvue_media_upload_module.requests = original_requests

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["media_uuid"], "media-ready-123")
        self.assertTrue(result["folder_success"])
        poll_calls = [
            call
            for call in fake_requests.calls
            if call[0] == "get" and call[1].endswith("/media/media-ready-123")
        ]
        self.assertEqual(len(poll_calls), 2)
        attach_index = next(
            index
            for index, call in enumerate(fake_requests.calls)
            if call[0] == "post" and "/vault/folders/Wall/media" in call[1]
        )
        last_poll_index = max(
            index
            for index, call in enumerate(fake_requests.calls)
            if call[0] == "get" and call[1].endswith("/media/media-ready-123")
        )
        self.assertGreater(attach_index, last_poll_index)

    def test_upload_fails_without_folder_attach_when_processing_times_out(self):
        fake_requests = FakeRequests()
        fake_requests.media_statuses = ["processing", "processing", "processing"]
        original_requests = fanvue_media_upload_module.requests
        fanvue_media_upload_module.requests = fake_requests
        try:
            service = FanvueMediaUploadService(
                fanvue_account_id=7,
                processing_poll_interval_seconds=0,
                processing_timeout_seconds=0,
            )
            service.oauth.get_valid_access_token = lambda: "token"
            with TemporaryDirectory() as temp_dir:
                image_path = Path(temp_dir) / "stuck.png"
                image_path.write_bytes(b"image")

                result = service.upload_media_item(
                    {
                        "id": "shot-stuck",
                        "file_path": str(image_path),
                        "classification": "WALL_IMAGE",
                        "folder_name": "Wall",
                    }
                )
        finally:
            fanvue_media_upload_module.requests = original_requests

        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "processing")
        self.assertFalse(result["folder_success"])
        self.assertEqual(
            result["error"]["message"],
            "Fanvue accepted the upload but did not finish processing the media.",
        )
        self.assertFalse(
            any(
                call[0] == "post" and "/vault/folders/Wall/media" in call[1]
                for call in fake_requests.calls
            )
        )


if __name__ == "__main__":
    unittest.main()
