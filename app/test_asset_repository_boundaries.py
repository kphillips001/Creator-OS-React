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

    def test_asset_library_counts_resolve_current_sales_destinations_exclusively(self):
        class AggregateCursor:
            def __init__(self):
                self.queries = []
                self.index = 0

            def __enter__(self): return self
            def __exit__(self, *_): return False
            def execute(self, query, params=None): self.queries.append(str(query))
            def fetchone(self):
                rows = (
                    {"images": 8, "image_chat": 3, "image_wall": 4, "videos": 2},
                    {"bundles": 4, "photoshoots": 5, "photoshoot_chat": 3,
                     "photoshoot_chat_bundle": 1, "photoshoot_chat_session": 2,
                     "photoshoot_wall": 1},
                    {"teasers": 1},
                )
                row = rows[self.index]
                self.index += 1
                return row

        cursor = AggregateCursor()

        class Connection:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def cursor(self): return cursor

        result = AssetRepository(connection_factory=lambda: Connection()).asset_library_counts(7)

        self.assertEqual(result["destination_breakdown"], {
            "images": {"chat": 3, "wall": 4, "unassigned": 1},
            "photoshoots": {"chat": 3, "wall": 1, "unassigned": 1},
            "chat_commerce_types": {"single": 3, "bundle": 1, "session": 2},
        })
        photoshoot_query = cursor.queries[1]
        self.assertIn("COALESCE(selling_mode,'SESSION')='SESSION'", photoshoot_query)
        self.assertIn("COALESCE(bundle_sales_channel,'CHAT')='CHAT'", photoshoot_query)
        self.assertIn("bundle_sales_channel='CONTENT_WALL'", photoshoot_query)
        image_query = cursor.queries[0]
        self.assertGreaterEqual(image_query.count("acd.destination='TEASER'"), 3)
        self.assertEqual(result["images"], 8)
        self.assertEqual(result["teasers"], 1)


if __name__ == "__main__":
    unittest.main()
