import unittest

import app.repositories.asset_repository as asset_repository_module
from app.repositories.asset_repository import AssetRepository


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.query = ""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params=None):
        self.query = query
        self.connection.queries.append(query)

    def fetchall(self):
        if "information_schema.columns" in self.query:
            return [
                {"column_name": column}
                for column in self.connection.existing_columns
            ]
        return self.connection.asset_rows

    def fetchone(self):
        if "information_schema.columns" in self.query:
            rows = self.fetchall()
            return rows[0] if rows else None
        return self.connection.asset_rows[0] if self.connection.asset_rows else None


class FakeConnection:
    def __init__(self, *, existing_columns, asset_rows):
        self.existing_columns = existing_columns
        self.asset_rows = asset_rows
        self.queries = []

    def cursor(self):
        return FakeCursor(self)


class AssetRepositoryBoundaryTests(unittest.TestCase):
    def setUp(self):
        asset_repository_module._CONTENT_ITEM_COLUMN_CACHE = None

    def test_get_asset_owned_row_filters_product_and_publishing_fields(self):
        connection = FakeConnection(
            existing_columns={
                "id",
                "file_path",
                "file_name",
                "media_metadata",
                "local_vault_path",
                "ready_for_rotation",
                "fanvue_upload_status",
            },
            asset_rows=[
                {
                    "id": 10,
                    "file_path": "legacy.jpg",
                    "file_name": "legacy.jpg",
                    "media_metadata": {"mime_type": "image/jpeg"},
                    "local_vault_path": "D:\\Ava_CMS\\vault\\originals\\images\\10.jpg",
                }
            ],
        )

        row = AssetRepository().get_asset_owned_row(10, connection=connection)

        self.assertEqual(row["id"], 10)
        self.assertIn("local_vault_path", row)
        select_query = connection.queries[-1]
        self.assertIn("local_vault_path", select_query)
        self.assertNotIn("ready_for_rotation", select_query)
        self.assertNotIn("fanvue_upload_status", select_query)

    def test_list_asset_owned_rows_preserves_requested_order(self):
        connection = FakeConnection(
            existing_columns={"id", "file_path", "file_name"},
            asset_rows=[
                {"id": 2, "file_path": "two.jpg", "file_name": "two.jpg"},
                {"id": 1, "file_path": "one.jpg", "file_name": "one.jpg"},
            ],
        )

        rows = AssetRepository().list_asset_owned_rows(
            [1, 2],
            connection=connection,
        )

        self.assertEqual([row["id"] for row in rows], [1, 2])


if __name__ == "__main__":
    unittest.main()
