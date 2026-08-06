import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from app.services.generation_library_publishing_service import (
    GenerationLibraryPublishingService,
)


def record():
    return SimpleNamespace(
        image_id="generated-1",
        creative_mode="premium_teaser",
        prompt_text="Studio portrait",
        prompt_metadata={"creative_tags": ["gold"]},
        generation_metadata={"workflow_type": "premium_studio"},
    )


class GenerationLibraryPublishingServiceTests(unittest.TestCase):
    def setUp(self):
        self.library = Mock()
        self.library.get.return_value = record()
        self.library.resolve_publishable_image_reference.return_value = "C:/images/generated-1.png"
        self.captions = Mock()
        self.social = Mock()
        self.social.x_account_options.return_value = (
            "AvaBlackthorne", "AvaBlackthorneX",
        )
        self.service = GenerationLibraryPublishingService(
            generation_library=self.library,
            caption_studio=self.captions,
            social_publishing=self.social,
        )

    def test_only_supported_ui_destinations_are_accepted(self):
        self.assertEqual(self.service.validate_destination("x"), ("x", None))
        self.assertEqual(self.service.validate_destination("telegram_wall"), ("telegram", "main"))
        self.assertEqual(self.service.validate_destination("telegram_chat"), ("telegram", "vault"))
        with self.assertRaises(ValueError):
            self.service.validate_destination("fanvue")

    def test_context_exposes_only_marketing_destinations(self):
        context = self.service.context("generated-1")

        self.assertEqual(
            context["destinations"],
            (
                {"value": "x", "label": "X", "available": True},
                {
                    "value": "telegram_wall",
                    "label": "Telegram Broadcast",
                    "available": True,
                },
            ),
        )

    def test_x_and_telegram_use_their_existing_caption_generators(self):
        result = SimpleNamespace(
            caption_result_id="caption-1",
            formatter_metadata={"themes": [{"theme": "One", "captions": ["Caption"]}]},
        )
        self.captions.generate_x_engagement_themes.return_value = result
        self.captions.generate_telegram_vision_themes.return_value = result
        profile = {"id": 12, "display_name": "Ava"}

        x = self.service.generate_captions(
            generated_image_id="generated-1", destination="x", creator_profile=profile, idea_seed=0,
        )
        telegram = self.service.generate_captions(
            generated_image_id="generated-1", destination="telegram_chat", creator_profile=profile, idea_seed=2,
        )

        self.assertEqual(x["captionResultId"], "caption-1")
        self.assertEqual(telegram["themes"][0]["captions"], ("Caption",))
        self.captions.generate_x_engagement_themes.assert_called_once()
        self.captions.generate_telegram_vision_themes.assert_called_once()
        self.assertEqual(self.captions.generate_telegram_vision_themes.call_args.kwargs["idea_seed"], 2)

    def test_publish_uses_existing_x_workflow_and_archives(self):
        queue_item = SimpleNamespace(queue_item_id="queue-1")
        self.social.create_queue_item.return_value = queue_item
        self.social.publish_now.return_value = SimpleNamespace(status="posted")

        result = self.service.publish(
            generated_image_id="generated-1",
            destination="x",
            caption="Edited caption",
            caption_result_id="caption-1",
            selected_generated_caption="Original caption",
        )

        self.assertEqual(result["message"], "Published to X.")
        self.captions.select_caption.assert_called_once_with(
            "caption-1", selected_text="Edited caption"
        )
        self.social.publish_now.assert_called_once_with(
            "queue-1",
            caption_text="Edited caption",
            account_name="AvaBlackthorne",
            caption_id=self.captions.select_caption.return_value.caption_result_id,
            telegram_post_to="main",
            telegram_cta_enabled=False,
            telegram_cta_label="",
            telegram_cta_url="",
        )
        self.library.mark_published.assert_called_once()
        metadata = self.library.mark_published.call_args.kwargs["metadata"]
        self.assertTrue(metadata["caption_was_edited"])
        self.assertEqual(metadata["caption_source"], "edited_generated")

    def test_publish_maps_telegram_destinations_and_cta(self):
        self.social.create_queue_item.return_value = SimpleNamespace(queue_item_id="queue-2")
        self.social.publish_now.return_value = SimpleNamespace(status="posted")

        self.service.publish(
            generated_image_id="generated-1",
            destination="telegram_chat",
            caption="Telegram caption",
            cta_enabled=True,
            cta_label="Open",
            cta_url="https://example.com",
        )

        self.social.publish_now.assert_called_once_with(
            "queue-2",
            caption_text="Telegram caption",
            account_name=None,
            caption_id=None,
            telegram_post_to="vault",
            telegram_cta_enabled=True,
            telegram_cta_label="Open",
            telegram_cta_url="https://example.com",
        )
        metadata = self.library.mark_published.call_args.kwargs["metadata"]
        self.assertEqual(metadata["post_to"], "vault")
        self.assertEqual(metadata["caption_source"], "custom")

    def test_publish_x_targets_succeeds_independently_and_archives_successes(self):
        self.social.create_queue_item.return_value = SimpleNamespace(queue_item_id="queue-x")
        self.social.publish_now.side_effect = (
            SimpleNamespace(status="failed"),
            SimpleNamespace(status="posted"),
        )
        self.social.list_history.return_value = (
            SimpleNamespace(
                queue_item_id="queue-x", status="failed",
                message="First account failed.",
                metadata={"account_name": "AvaBlackthorne"},
            ),
        )

        result = self.service.publish(
            generated_image_id="generated-1",
            destination="x",
            caption="",
            x_targets=(
                {"accountName": "AvaBlackthorne", "caption": "Main"},
                {"accountName": "AvaBlackthorneX", "caption": "Second"},
            ),
        )

        self.assertEqual([item["status"] for item in result["results"]], ["failed", "posted"])
        self.assertEqual(self.social.publish_now.call_count, 2)
        self.assertEqual(
            self.social.publish_now.call_args_list[1].kwargs["account_name"],
            "AvaBlackthorneX",
        )
        self.library.mark_published.assert_called_once()
        metadata = self.library.mark_published.call_args.kwargs["metadata"]
        self.assertEqual(metadata["account_names"], ("AvaBlackthorneX",))

    def test_publish_x_targets_supports_second_account_only(self):
        self.social.create_queue_item.return_value = SimpleNamespace(queue_item_id="queue-second")
        self.social.publish_now.return_value = SimpleNamespace(status="posted")

        result = self.service.publish(
            generated_image_id="generated-1", destination="x", caption="",
            x_targets=({
                "accountName": "AvaBlackthorneX",
                "caption": "Second account caption",
            },),
        )

        self.assertEqual(result["results"], (
            {"accountName": "AvaBlackthorneX", "status": "posted"},
        ))
        self.assertEqual(
            self.social.publish_now.call_args.kwargs["account_name"],
            "AvaBlackthorneX",
        )

    def test_publish_x_targets_rejects_unknown_accounts(self):
        with self.assertRaisesRegex(ValueError, "Unknown X account"):
            self.service.publish(
                generated_image_id="generated-1", destination="x", caption="",
                x_targets=({"accountName": "Unknown", "caption": "Caption"},),
            )
        self.social.publish_now.assert_not_called()

    def test_publish_failure_preserves_library_record(self):
        self.social.create_queue_item.return_value = SimpleNamespace(queue_item_id="queue-3")
        self.social.publish_now.return_value = SimpleNamespace(status="failed")
        self.social.list_history.return_value = (
            SimpleNamespace(queue_item_id="queue-3", message="Provider rejected publish."),
        )

        with self.assertRaisesRegex(RuntimeError, "Provider rejected publish"):
            self.service.publish(
                generated_image_id="generated-1",
                destination="telegram_wall",
                caption="Caption",
            )
        self.library.mark_published.assert_not_called()

if __name__ == "__main__":
    unittest.main()
