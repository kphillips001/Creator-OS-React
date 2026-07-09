import importlib
import unittest
from unittest.mock import patch

from app.config import settings


class OpenAILazyInitializationTest(unittest.TestCase):
    def setUp(self):
        self.original_openai_api_key = settings.OPENAI_API_KEY

    def tearDown(self):
        settings.OPENAI_API_KEY = self.original_openai_api_key

        try:
            from app.services import content_caption_service

            content_caption_service._client = None
        except Exception:
            pass

    def test_content_caption_service_import_does_not_require_openai_key(self):
        settings.OPENAI_API_KEY = ""

        module = importlib.import_module("app.services.content_caption_service")
        importlib.reload(module)

        self.assertTrue(hasattr(module, "get_openai_client"))

    def test_dashboard_main_import_does_not_require_openai_key(self):
        settings.OPENAI_API_KEY = ""

        try:
            module = importlib.import_module("app.main")
        except ModuleNotFoundError as error:
            if error.name == "psycopg":
                self.skipTest("psycopg is not installed in this test environment")
            raise

        importlib.reload(module)

        self.assertEqual(
            module.decision_engine.__class__.__name__,
            "LazyDecisionEngine",
        )

    def test_missing_openai_key_raises_clean_configuration_error(self):
        settings.OPENAI_API_KEY = ""
        module = importlib.import_module("app.services.content_caption_service")
        importlib.reload(module)

        with self.assertRaisesRegex(
            RuntimeError,
            "OpenAI API key is not configured.",
        ):
            module.get_openai_client()

    def test_openai_client_is_created_lazily_with_configured_key(self):
        settings.OPENAI_API_KEY = "test-openai-key"
        module = importlib.import_module("app.services.content_caption_service")
        importlib.reload(module)

        class FakeOpenAI:
            def __init__(self, api_key):
                self.api_key = api_key

        with patch.object(module, "OpenAI", FakeOpenAI):
            client = module.get_openai_client()

        self.assertEqual(client.api_key, "test-openai-key")


if __name__ == "__main__":
    unittest.main()
