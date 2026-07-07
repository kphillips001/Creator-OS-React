import unittest

from app.services.asset_lifecycle_service import AssetLifecycleService


class FakeCursor:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params=None):
        self.calls.append((query, params))


class FakeConnection:
    def __init__(self):
        self.cursor_obj = FakeCursor()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return self.cursor_obj


class FakeMediaProcessingService:
    def build_derivative_metadata(self, *, derivative_path, derivative_type):
        return {
            "path": derivative_path,
            "type": derivative_type,
            "storage": "local_vault",
            "generated_at": "2026-07-01T00:00:00+00:00",
            "source": "media_processing_service",
        }


class AssetLifecycleServiceTests(unittest.TestCase):
    def make_service(self):
        connection = FakeConnection()
        return (
            AssetLifecycleService(
                lambda: connection,
                media_processing_service=FakeMediaProcessingService(),
            ),
            connection,
        )

    def test_approve_asset_owns_active_lifecycle_transition(self):
        service, connection = self.make_service()

        service.approve_asset(
            asset_id=10,
            fanvue_account_id=3,
            suggested_tags=["vip"],
            detected_themes=["mirror"],
            classification="PREMIUM",
            blurred_preview_path="data/previews/10_blurred.jpg",
            creator_profile_id=2,
        )

        query, params = connection.cursor_obj.calls[0]
        self.assertIn("status = 'approved'", query)
        self.assertIn("ready_for_rotation = TRUE", query)
        self.assertIn("blurred_preview_path = %s", query)
        self.assertIn("media_metadata = jsonb_set", query)
        self.assertIn("COALESCE(media_metadata->'derivatives'", query)
        self.assertEqual(params[0], '["vip"]')
        self.assertEqual(params[1], '["mirror"]')
        self.assertEqual(params[2], "PREMIUM")
        self.assertEqual(params[3], "data/previews/10_blurred.jpg")
        derivative_updates = params[4]
        self.assertIn('"blur"', derivative_updates)
        self.assertIn('"blurred_preview"', derivative_updates)
        self.assertIn('"path": "data/previews/10_blurred.jpg"', derivative_updates)
        self.assertEqual(params[5], 2)
        self.assertEqual(params[6], 10)
        self.assertEqual(params[7], 3)

    def test_reject_asset_owns_rejected_lifecycle_transition(self):
        service, connection = self.make_service()

        service.reject_asset(asset_id=11, fanvue_account_id=4)

        query, params = connection.cursor_obj.calls[0]
        self.assertIn("status = 'rejected'", query)
        self.assertEqual(params, (11, 4, 4))

    def test_save_review_edits_keeps_metadata_updates_in_asset_service(self):
        service, connection = self.make_service()

        service.save_review_edits(
            asset_id=12,
            suggested_tags=["tease"],
            detected_themes=["warm"],
            classification="TEASE",
        )

        query, params = connection.cursor_obj.calls[0]
        self.assertIn("suggested_tags = %s::jsonb", query)
        self.assertIn("detected_themes = %s::jsonb", query)
        self.assertNotIn("ready_for_rotation = TRUE", query)
        self.assertEqual(params[0], '["tease"]')
        self.assertEqual(params[1], '["warm"]')
        self.assertEqual(params[2], "TEASE")
        self.assertEqual(params[3], 12)
        self.assertIsNone(params[4])

    def test_legacy_review_approval_does_not_create_rotation_readiness(self):
        service, connection = self.make_service()

        service.approve_review_only(
            asset_id=13,
            suggested_tags=["legacy"],
            detected_themes=["review"],
            classification="VIP",
        )

        query, _ = connection.cursor_obj.calls[0]
        self.assertIn("status = 'approved'", query)
        self.assertNotIn("ready_for_rotation = TRUE", query)
        self.assertNotIn("blurred_preview_path", query)


if __name__ == "__main__":
    unittest.main()
