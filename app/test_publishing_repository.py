import unittest
from uuid import UUID

import app.repositories.publishing_repository as publishing_repository_module
from app.repositories.publishing_repository import PublishingRepository


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.query = ""
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params=None):
        self.query = query
        self.params = params
        self.connection.queries.append(query)

    def fetchall(self):
        if "information_schema.columns" not in self.query:
            return []
        table_name = self.params[1] if self.params else None
        if table_name == "content_items":
            columns = self.connection.content_columns
        elif table_name == "products":
            columns = self.connection.product_columns
        else:
            columns = set()
        return [{"column_name": column} for column in columns]

    def fetchone(self):
        if "FROM public.content_items" in self.query:
            return self.connection.content_row
        if "FROM public.products" in self.query:
            return self.connection.product_row
        return None


class FakeConnection:
    def __init__(
        self,
        *,
        content_columns=None,
        product_columns=None,
        content_row=None,
        product_row=None,
    ):
        self.content_columns = content_columns or set()
        self.product_columns = product_columns or set()
        self.content_row = content_row
        self.product_row = product_row
        self.queries = []

    def cursor(self):
        return FakeCursor(self)


class PublishingRepositoryTests(unittest.TestCase):
    def setUp(self):
        publishing_repository_module._COLUMN_CACHE = {}

    def test_projects_content_item_to_provider_neutral_record(self):
        repo = PublishingRepository()

        record = repo.project_content_item(
            {
                "id": 12,
                "fanvue_account_id": 3,
                "fanvue_upload_status": "completed",
                "fanvue_preview_upload_status": "completed",
                "fanvue_full_upload_status": "completed",
                "fanvue_media_preview_uuid": "preview-id",
                "fanvue_media_full_uuid": "full-id",
                "fanvue_upload_error": None,
            }
        )

        self.assertEqual(record["asset_id"], 12)
        self.assertEqual(record["provider"], "fanvue")
        self.assertEqual(record["provider_account_id"], 3)
        self.assertEqual(record["provider_status"], "completed")
        self.assertEqual(record["provider_media_id"], "full-id")
        self.assertEqual(record["provider_preview_media_id"], "preview-id")
        self.assertEqual(record["provider_full_media_id"], "full-id")

    def test_projects_product_and_merges_legacy_asset_state(self):
        product_id = UUID("00000000-0000-4000-8000-000000000001")
        connection = FakeConnection(
            product_columns={
                "id",
                "legacy_content_item_id",
                "media_link",
                "fulfillment_status",
                "fulfillment_strategy",
                "metadata",
            },
            content_columns={
                "id",
                "fanvue_upload_status",
                "fanvue_media_preview_uuid",
                "fanvue_media_full_uuid",
            },
            product_row={
                "id": product_id,
                "legacy_content_item_id": 99,
                "media_link": "https://fanvue.example/link",
                "fulfillment_status": "READY",
                "fulfillment_strategy": "FANVUE_PAID_CHAT",
                "metadata": {"delivery_type": "PAID"},
            },
            content_row={
                "id": 99,
                "fanvue_upload_status": "completed",
                "fanvue_media_preview_uuid": "preview-id",
                "fanvue_media_full_uuid": "full-id",
            },
        )

        record = PublishingRepository().get_by_product_id(
            product_id,
            connection=connection,
        )

        self.assertEqual(record["product_id"], product_id)
        self.assertEqual(record["asset_id"], 99)
        self.assertEqual(record["provider_output_url"], "https://fanvue.example/link")
        self.assertEqual(record["delivery_method"], "FANVUE_PAID_CHAT")
        self.assertEqual(record["delivery_type"], "PAID")
        self.assertEqual(record["provider_status"], "READY")
        self.assertEqual(record["provider_media_id"], "full-id")

    def test_projects_product_delivery_type_from_product_metadata(self):
        record = PublishingRepository().project_product(
            {
                "id": UUID("00000000-0000-4000-8000-000000000011"),
                "media_link": "https://fanvue.example/link",
                "fulfillment_status": "READY",
                "fulfillment_strategy": "FANVUE_PAID_CHAT",
                "metadata": {"delivery_type": "FREE"},
            }
        )

        self.assertEqual(record["delivery_type"], "FREE")
        self.assertEqual(record["provider_output_url"], "https://fanvue.example/link")
        self.assertEqual(record["provider_status"], "READY")

    def test_projects_product_delivery_type_defaults_to_paid_without_inference(self):
        record = PublishingRepository().project_product(
            {
                "id": UUID("00000000-0000-4000-8000-000000000012"),
                "media_link": None,
                "fulfillment_status": None,
                "fulfillment_strategy": None,
            }
        )

        self.assertEqual(record["delivery_type"], "PAID")
        self.assertIsNone(record["provider_output_url"])
        self.assertIsNone(record["provider_status"])

    def test_projects_legacy_upload_link_shape(self):
        record = PublishingRepository().project_legacy_upload_link(
            {
                "content_item_id": 8,
                "fanvue_account_id": 4,
                "upload_status": "uploaded",
                "fanvue_media_uuid": "media-id",
                "fanvue_preview_media_uuid": "preview-id",
                "fanvue_full_media_uuid": "full-id",
                "destination": "vip",
                "delivery_method": "chat",
                "vault_folder_id": "folder-id",
                "error_message": None,
            }
        )

        self.assertEqual(record["asset_id"], 8)
        self.assertEqual(record["provider_status"], "uploaded")
        self.assertEqual(record["provider_media_id"], "media-id")
        self.assertEqual(record["provider_folder_id"], "folder-id")
        self.assertEqual(record["destination"], "vip")


if __name__ == "__main__":
    unittest.main()
