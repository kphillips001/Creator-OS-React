import sys
import tempfile
import types
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from app.models.product import Product, ProductFulfillmentStatus, ProductStatus, ProductType


class _FakeStreamlit(types.ModuleType):
    def __getattr__(self, name):
        def _noop(*args, **kwargs):
            return False

        return _noop


@contextmanager
def _unused_db_connection():
    raise AssertionError("Unit tests should not open a database connection.")


fake_database = types.ModuleType("app.database")
fake_database.get_db_connection = _unused_db_connection
sys.modules.setdefault("app.database", fake_database)

fake_psycopg = types.ModuleType("psycopg")
fake_psycopg_errors = types.ModuleType("psycopg.errors")
fake_psycopg_types = types.ModuleType("psycopg.types")
fake_psycopg_types_json = types.ModuleType("psycopg.types.json")
fake_psycopg_errors.UniqueViolation = type("UniqueViolation", (Exception,), {})
fake_psycopg_types_json.Json = lambda value: value
sys.modules.setdefault("psycopg", fake_psycopg)
sys.modules.setdefault("psycopg.errors", fake_psycopg_errors)
sys.modules.setdefault("psycopg.types", fake_psycopg_types)
sys.modules.setdefault("psycopg.types.json", fake_psycopg_types_json)
sys.modules.setdefault("streamlit", _FakeStreamlit("streamlit"))

from app.dashboard.pages import product_catalog


def asset(**overrides):
    values = {
        "id": 101,
        "file_path": "missing.jpg",
        "file_name": "missing.jpg",
        "classification": "VIP_IMAGE",
        "media_type": "image",
        "status": "approved",
        "fanvue_media_preview_uuid": None,
        "fanvue_media_full_uuid": None,
        "fanvue_upload_status": None,
        "fanvue_upload_error": None,
        "blurred_preview_path": None,
        "media_metadata": {},
        "local_vault_path": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeUploader:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def upload_media_item(self, item):
        self.calls.append(item)
        return dict(self.result)


class FakePublishingService:
    def __init__(self, result):
        self.result = result
        self.calls = []
        self.record_calls = []

    def project_legacy_asset_record(self, asset):
        return {
            "provider_status": getattr(asset, "fanvue_upload_status", None),
            "provider_media_id": (
                getattr(asset, "fanvue_media_full_uuid", None)
                or getattr(asset, "fanvue_media_preview_uuid", None)
            ),
            "provider_error": getattr(asset, "fanvue_upload_error", None),
        }

    def get_provider_status_display(
        self,
        record,
        *,
        provider_name="Provider",
        missing_detail="No local asset is attached.",
        local_detail="Local asset only",
    ):
        if not record:
            return f"Not uploaded to {provider_name}", missing_detail
        if record.get("provider_error"):
            return f"Failed {provider_name} upload", record["provider_error"]
        if record.get("provider_media_id"):
            return f"Uploaded to {provider_name}", record["provider_media_id"]
        return f"Not uploaded to {provider_name}", local_detail

    def upload_asset_media_item(self, *, fanvue_account_id, item):
        self.calls.append(
            {
                "fanvue_account_id": fanvue_account_id,
                "item": item,
            }
        )
        return dict(self.result)

    def build_upload_success_payload(
        self,
        upload_result,
        *,
        default_status="uploaded",
    ):
        media_id = upload_result.get("media_uuid")
        return {
            "provider_status": upload_result.get("status") or default_status,
            "provider_error": None,
            "provider_metadata": upload_result,
            "provider_media_id": media_id,
            "provider_preview_media_id": upload_result.get("preview_uuid")
            or media_id,
            "provider_full_media_id": upload_result.get("full_uuid")
            or media_id,
        }

    def build_upload_failure_payload(self, upload_result=None, *, error=None):
        upload_result = upload_result or {}
        provider_error = (
            error
            if error is not None
            else str(upload_result.get("error"))
            if "error" in upload_result
            else None
        )
        return {
            "provider_status": upload_result.get("status") or "failed",
            "provider_error": None if provider_error is None else str(provider_error),
            "provider_metadata": upload_result,
            "provider_media_id": upload_result.get("media_uuid"),
            "provider_preview_media_id": upload_result.get("preview_uuid"),
            "provider_full_media_id": upload_result.get("full_uuid"),
        }

    def record_asset_upload_payload(self, *, asset_id, upload_payload):
        self.record_calls.append(
            {
                "asset_id": asset_id,
                "upload_payload": upload_payload,
            }
        )


class FakeMediaProcessingService:
    def __init__(self, derivative_path=None):
        self.derivative_path = derivative_path
        self.calls = []

    def resolve_derivative(self, media, derivative_type):
        self.calls.append((media, derivative_type))
        return self.derivative_path


class ProductCatalogFanvueVaultUploadTests(unittest.TestCase):
    def test_upload_button_visible_for_local_only_asset(self):
        with tempfile.NamedTemporaryFile(suffix=".jpg") as local_file:
            visible, enabled, _ = product_catalog._asset_fanvue_upload_action_state(
                asset(file_path=local_file.name)
            )

        self.assertTrue(visible)
        self.assertTrue(enabled)

    def test_upload_button_hidden_for_uploaded_asset(self):
        visible, enabled, _ = product_catalog._asset_fanvue_upload_action_state(
            asset(fanvue_media_full_uuid="fanvue-media-uuid")
        )

        self.assertFalse(visible)
        self.assertFalse(enabled)

    def test_upload_invokes_fanvue_service_and_persists_metadata(self):
        upload_result = {
            "success": True,
            "media_uuid": "media-123",
            "preview_uuid": "preview-123",
            "full_uuid": "full-123",
            "status": "uploaded",
            "raw": {"id": "media-123"},
        }
        publishing = FakePublishingService(upload_result)

        with tempfile.NamedTemporaryFile(suffix=".jpg") as local_file:
            local_asset = asset(id=202, file_path=local_file.name)
            with patch.object(
                product_catalog,
                "_PUBLISHING_SERVICE",
                publishing,
            ):
                result = product_catalog._upload_asset_to_fanvue_vault(
                    fanvue_account_id=7,
                    asset=local_asset,
                )

        self.assertTrue(result["success"])
        self.assertEqual(len(publishing.calls), 1)
        self.assertEqual(publishing.calls[0]["fanvue_account_id"], 7)
        self.assertEqual(publishing.calls[0]["item"]["id"], 202)
        self.assertEqual(len(publishing.record_calls), 1)
        record_call = publishing.record_calls[0]
        self.assertEqual(record_call["asset_id"], 202)
        payload = record_call["upload_payload"]
        self.assertEqual(payload["provider_preview_media_id"], "preview-123")
        self.assertEqual(payload["provider_full_media_id"], "full-123")
        self.assertEqual(payload["provider_status"], "uploaded")
        self.assertIsNone(payload["provider_error"])
        self.assertEqual(payload["provider_metadata"]["media_uuid"], "media-123")

    def test_upload_prefers_local_vault_path_from_media_metadata(self):
        publishing = FakePublishingService(
            {"success": True, "media_uuid": "media-vault"}
        )

        with tempfile.NamedTemporaryFile(suffix=".jpg") as legacy_file:
            with tempfile.NamedTemporaryFile(suffix=".jpg") as vault_file:
                local_asset = asset(
                    id=303,
                    file_path=legacy_file.name,
                    media_metadata={"local_vault_path": vault_file.name},
                )
                with patch.object(
                    product_catalog,
                    "_PUBLISHING_SERVICE",
                    publishing,
                ):
                    result = product_catalog._upload_asset_to_fanvue_vault(
                        fanvue_account_id=7,
                        asset=local_asset,
                    )

        self.assertTrue(result["success"])
        self.assertEqual(publishing.calls[0]["item"]["file_path"], vault_file.name)

    def test_thumbnail_prefers_blurred_preview_over_original(self):
        with tempfile.NamedTemporaryFile(suffix=".jpg") as original_file:
            with tempfile.NamedTemporaryFile(suffix=".jpg") as preview_file:
                media_service = FakeMediaProcessingService(
                    derivative_path=preview_file.name,
                )
                with patch.object(
                    product_catalog,
                    "_MEDIA_PROCESSING_SERVICE",
                    media_service,
                ):
                    preview = product_catalog._asset_preview_path(
                        asset(
                            file_path=original_file.name,
                            media_metadata={"local_vault_path": original_file.name},
                            blurred_preview_path="legacy-preview.jpg",
                        )
                    )

        self.assertEqual(preview, preview_file.name)
        self.assertEqual(len(media_service.calls), 1)
        self.assertEqual(media_service.calls[0][1], "blurred_preview")

    def test_thumbnail_prefers_local_vault_derivative_from_media_service(self):
        with tempfile.NamedTemporaryFile(suffix=".jpg") as original_file:
            with tempfile.NamedTemporaryFile(suffix=".jpg") as vault_preview:
                media_service = FakeMediaProcessingService(
                    derivative_path=vault_preview.name,
                )
                with patch.object(
                    product_catalog,
                    "_MEDIA_PROCESSING_SERVICE",
                    media_service,
                ):
                    preview = product_catalog._asset_preview_path(
                        asset(
                            file_path=original_file.name,
                            media_metadata={"local_vault_path": original_file.name},
                            blurred_preview_path="legacy-preview.jpg",
                        )
                    )

        self.assertEqual(preview, vault_preview.name)

    def test_thumbnail_falls_back_to_original_when_no_derivative_exists(self):
        with tempfile.NamedTemporaryFile(suffix=".jpg") as original_file:
            media_service = FakeMediaProcessingService(derivative_path=None)
            with patch.object(
                product_catalog,
                "_MEDIA_PROCESSING_SERVICE",
                media_service,
            ):
                preview = product_catalog._asset_preview_path(
                    asset(
                        file_path=original_file.name,
                        media_metadata={"local_vault_path": original_file.name},
                        blurred_preview_path=None,
                    )
                )

        self.assertEqual(preview, original_file.name)

    def test_ordered_assets_and_cover_prefer_experience(self):
        assets = [
            asset(id=1, file_name="one.jpg"),
            asset(id=2, file_name="two.jpg"),
            asset(id=3, file_name="three.jpg"),
        ]
        links = [
            types.SimpleNamespace(asset_id=1, position=0),
            types.SimpleNamespace(asset_id=2, position=1),
            types.SimpleNamespace(asset_id=3, position=2),
        ]
        experience = types.SimpleNamespace(
            ordered_asset_ids=(3, 1, 2),
            cover_asset_id=2,
        )

        ordered = product_catalog._ordered_assets(links, assets, experience)
        cover = product_catalog._cover_asset(ordered, experience)

        self.assertEqual([item.id for item in ordered], [3, 1, 2])
        self.assertEqual(cover.id, 2)

    def test_vault_upload_does_not_make_product_ready_without_media_link(self):
        now = datetime.now(timezone.utc)
        product = Product(
            id=uuid4(),
            creator_profile_id=7,
            legacy_content_item_id=None,
            internal_name="local-product",
            display_name="Local Product",
            description=None,
            product_type=ProductType.SINGLE_IMAGE,
            status=ProductStatus.ACTIVE,
            price_cents=1500,
            base_price_cents=1500,
            min_price_cents=1500,
            max_price_cents=1500,
            currency="USD",
            media_link=None,
            tags=(),
            themes=(),
            metadata={},
            activation_source=None,
            activation_reason=None,
            activated_at=now,
            created_at=now,
            updated_at=now,
        )
        publishing = FakePublishingService(
            {
                "success": True,
                "media_uuid": "media-456",
                "status": "uploaded",
            }
        )

        with tempfile.NamedTemporaryFile(suffix=".jpg") as local_file:
            with patch.object(
                product_catalog,
                "_PUBLISHING_SERVICE",
                publishing,
            ):
                product_catalog._upload_asset_to_fanvue_vault(
                    fanvue_account_id=7,
                    asset=asset(file_path=local_file.name),
                )

        self.assertEqual(
            product.fulfillment_status,
            ProductFulfillmentStatus.NOT_READY,
        )


if __name__ == "__main__":
    unittest.main()
