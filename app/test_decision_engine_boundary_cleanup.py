import unittest
from pathlib import Path

from app.engine.decision_engine import DecisionEngine


class FakeRuntimeBoundary:
    def __init__(self):
        self.calls = []

    def get_active_creator_profile(self, account_id):
        self.calls.append(("profile", account_id))
        return {"persona_name": "Ava"}

    def get_user_by_account_and_id(self, account_id, user_id):
        self.calls.append(("user", account_id, user_id))
        return {"is_subscriber": True}

    def update_memory_fields(self, account_id, user_id, data):
        self.calls.append(("memory", account_id, user_id, data))
        return {"ok": True}

    def log_send_event(self, **kwargs):
        self.calls.append(("send_log", kwargs))
        return None


class FakeContentUsageService:
    def __init__(self):
        self.calls = []

    def has_seen_content(self, **kwargs):
        self.calls.append(("content", kwargs))
        return False

    def has_seen_content_tag(self, **kwargs):
        self.calls.append(("tag", kwargs))
        return False

    def mark_content_seen(self, **kwargs):
        self.calls.append(("mark", kwargs))
        return {"ok": True}


class DecisionEngineBoundaryCleanupTests(unittest.TestCase):
    def test_decision_engine_does_not_import_repositories_directly(self):
        source = Path("app/engine/decision_engine.py").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("from app.repositories", source)
        self.assertNotIn("import app.repositories", source)
        self.assertIn("DecisionEngineRuntimeBoundary", source)
        self.assertIn("ContentUsageService", source)

    def test_runtime_boundary_is_injectable(self):
        engine = object.__new__(DecisionEngine)
        runtime_boundary = FakeRuntimeBoundary()
        content_usage = FakeContentUsageService()

        engine.decision_runtime_boundary = runtime_boundary
        engine.content_usage_service = content_usage

        self.assertEqual(
            engine.decision_runtime_boundary.get_active_creator_profile(7),
            {"persona_name": "Ava"},
        )
        self.assertFalse(
            engine.content_usage_service.has_seen_content(
                fanvue_account_id=7,
                fanvue_user_id=11,
                content_item_id=4,
            )
        )

        self.assertEqual(runtime_boundary.calls, [("profile", 7)])
        self.assertEqual(
            content_usage.calls,
            [
                (
                    "content",
                    {
                        "fanvue_account_id": 7,
                        "fanvue_user_id": 11,
                        "content_item_id": 4,
                    },
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()
