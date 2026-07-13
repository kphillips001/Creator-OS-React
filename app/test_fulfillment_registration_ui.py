import unittest
from pathlib import Path


class FulfillmentRegistrationUITests(unittest.TestCase):
    def test_content_studio_exposes_generation_and_photoshoot_fulfillment_workflow(self):
        source = Path("app/dashboard/pages/content_studio.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("FulfillmentRegistrationService", source)
        self.assertIn("_render_fulfillment_registration_panel", source)
        self.assertIn("source_workflow=\"generation_library\"", source)
        self.assertIn("source_workflow=\"photoshoot_gallery\"", source)
        self.assertIn("Waiting For Media Link", source)
        self.assertIn("Paste Media Link", source)
        self.assertIn("Verify Media Link", source)
        self.assertIn("Upload to Fanvue Chat Vault", source)
        self.assertIn("MediaLinkSubmission", source)
        self.assertIn("upload_customer_conversations_asset", source)
        self.assertIn("submit_media_link", source)
        self.assertIn("ChatCommerceRegistrationService", source)
        self.assertIn("_render_chat_commerce_status_panel", source)
        self.assertIn("Chat Commerce Status", source)
        self.assertIn("Chat Ready", source)

    def test_creator_hq_exposes_media_link_attention_queue(self):
        source = Path("app/dashboard/pages/creator_workspace.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("FulfillmentRegistrationService", source)
        self.assertIn("_render_fulfillment_media_link_queue", source)
        self.assertIn("_creator_fulfillment_attention_count", source)
        self.assertIn("Waiting For Media Links", source)
        self.assertIn("Business Assets waiting for Fanvue Media Links", source)
        self.assertIn("creator_hq_fulfillment_media_link", source)
        self.assertIn("Verify Media Link", source)
        self.assertIn("Retry Upload", source)
        self.assertIn("Fulfillment Ready", source)
        self.assertIn("list_waiting_for_media_link", source)
        self.assertIn("list_failed_or_retry_required", source)
        self.assertIn("submit_media_link", source)
        self.assertIn("ChatCommerceRegistrationService", source)
        self.assertIn("_render_chat_commerce_registration_exceptions", source)
        self.assertIn("Chat Commerce Registration", source)
        self.assertIn("Chat Commerce registration exceptions", source)
        self.assertIn("list_blocked_assets", source)
        self.assertIn("list_temporarily_unavailable_assets", source)


if __name__ == "__main__":
    unittest.main()
