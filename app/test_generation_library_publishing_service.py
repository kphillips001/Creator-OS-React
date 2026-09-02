import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.services.generation_library_publishing_service import (
    GenerationLibraryPublishingService,
)
from app.providers.social.telegram_provider import TelegramPublishingProvider


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
        self.assertEqual(self.service.validate_destination("instagram"), ("instagram", None))
        with self.assertRaises(ValueError):
            self.service.validate_destination("telegram_chat")
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
                {"value": "instagram", "label": "Instagram", "available": True},
            ),
        )

    def test_destinations_use_their_destination_aware_caption_generators(self):
        result = SimpleNamespace(
            caption_result_id="caption-1",
            formatter_metadata={"themes": [{"theme": "One", "captions": ["Caption"]}]},
        )
        self.captions.generate_x_engagement_themes.return_value = result
        self.captions.generate_telegram_vision_themes.return_value = result
        self.captions.generate_instagram_vision_themes.return_value = result
        profile = {"id": 12, "display_name": "Ava"}

        x = self.service.generate_captions(
            generated_image_id="generated-1", destination="x", creator_profile=profile, idea_seed=0,
        )
        telegram = self.service.generate_captions(
            generated_image_id="generated-1", destination="telegram_wall", creator_profile=profile, idea_seed=2,
        )
        instagram = self.service.generate_captions(
            generated_image_id="generated-1", destination="instagram", creator_profile=profile, idea_seed=3,
        )

        self.assertEqual(x["captionResultId"], "caption-1")
        self.assertEqual(telegram["themes"][0]["captions"], ("Caption",))
        self.assertEqual(instagram["captionResultId"], "caption-1")
        self.captions.generate_x_engagement_themes.assert_called_once()
        self.captions.generate_telegram_vision_themes.assert_called_once()
        self.captions.generate_instagram_vision_themes.assert_called_once()
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
            audit_metadata={
                "x_auto_replies_enabled": True,
                "x_auto_callback_status": "pending",
            },
        )
        self.library.mark_published.assert_called_once()
        metadata = self.library.mark_published.call_args.kwargs["metadata"]
        self.assertTrue(metadata["caption_was_edited"])
        self.assertEqual(metadata["caption_source"], "edited_generated")

    def test_instagram_cannot_enter_social_publication_or_archive_path(self):
        with self.assertRaisesRegex(ValueError, "phone handoff endpoint"):
            self.service.publish(
                generated_image_id="generated-1",
                destination="instagram",
                caption="Caption",
            )
        self.social.create_queue_item.assert_not_called()
        self.library.mark_published.assert_not_called()

    def test_publish_maps_telegram_broadcast_and_cta(self):
        self.social.create_queue_item.return_value = SimpleNamespace(queue_item_id="queue-2")
        self.social.publish_now.return_value = SimpleNamespace(status="posted")

        self.service.publish(
            generated_image_id="generated-1",
            destination="telegram_wall",
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
            telegram_post_to="main",
            telegram_cta_enabled=True,
            telegram_cta_label="Open",
            telegram_cta_url="https://example.com",
            audit_metadata=None,
        )
        metadata = self.library.mark_published.call_args.kwargs["metadata"]
        self.assertEqual(metadata["post_to"], "main")
        self.assertEqual(metadata["caption_source"], "custom")

    @patch(
        "app.services.generation_library_publishing_service.TelegramPublishingProvider.load_telegram_env",
        return_value={"content_vault_url": "https://t.me/+canonical-vault"},
    )
    def test_semantic_vault_cta_uses_canonical_config_and_persists_identity(self, _config):
        self.social.create_queue_item.return_value = SimpleNamespace(queue_item_id="queue-vault")
        self.social.publish_now.return_value = SimpleNamespace(status="posted")

        self.service.publish(
            generated_image_id="generated-1",
            destination="telegram_wall",
            caption="Telegram caption",
            cta_enabled=True,
            selected_ctas=("VAULT",),
        )

        self.social.publish_now.assert_called_once_with(
            "queue-vault",
            caption_text="Telegram caption",
            account_name=None,
            caption_id=None,
            telegram_post_to="main",
            telegram_cta_enabled=True,
            telegram_cta_label="🔒 Vault",
            telegram_cta_url="https://t.me/+canonical-vault",
            telegram_cta_buttons=({
                "identity": "VAULT", "url": "https://t.me/+canonical-vault",
            },),
            audit_metadata={"selected_ctas": ["VAULT"]},
        )
        metadata = self.library.mark_published.call_args.kwargs["metadata"]
        self.assertEqual(metadata["selected_ctas"], ["VAULT"])
        self.assertEqual(
            TelegramPublishingProvider.build_inline_keyboard(
                cta_buttons=({
                    "identity": "VAULT", "url": "https://t.me/+canonical-vault",
                },),
            ),
            {"inline_keyboard": [[{
                "text": "🔒 Private Content Vault", "url": "https://t.me/+canonical-vault",
            }]]},
        )

    def test_vault_label_uses_final_outgoing_button_count(self):
        vault = {"identity": "VAULT", "url": "https://t.me/+canonical-vault"}
        chat = {"identity": "CHAT", "text": "💬 Chat", "url": "https://example.test/chat"}
        tip = {"identity": "TIP", "text": "❤️ Tip", "url": "https://example.test/tip"}

        one = TelegramPublishingProvider.build_inline_keyboard(cta_buttons=(vault,))
        two = TelegramPublishingProvider.build_inline_keyboard(cta_buttons=(vault, chat))
        three = TelegramPublishingProvider.build_inline_keyboard(cta_buttons=(vault, chat, tip))

        self.assertEqual(one["inline_keyboard"][0][0]["text"], "🔒 Private Content Vault")
        self.assertEqual(two["inline_keyboard"][0][0]["text"], "🔒 Vault")
        self.assertEqual(three["inline_keyboard"][0][0]["text"], "🔒")
        self.assertEqual(one["inline_keyboard"][0][0]["url"], "https://t.me/+canonical-vault")
        self.assertIsNone(TelegramPublishingProvider.build_inline_keyboard(cta_buttons=()))

    @patch(
        "app.services.generation_library_publishing_service.TelegramPublishingProvider.load_telegram_env",
        return_value={"cashapp_tip_url": "https://cash.app/$AvaBlackthorne"},
    )
    def test_semantic_tip_cta_uses_canonical_config_and_persists_identity(self, _config):
        self.social.create_queue_item.return_value = SimpleNamespace(queue_item_id="queue-tip")
        self.social.publish_now.return_value = SimpleNamespace(status="posted")

        self.service.publish(
            generated_image_id="generated-1", destination="telegram_wall",
            caption="Telegram caption", cta_enabled=True, selected_ctas=("TIP",),
        )

        arguments = self.social.publish_now.call_args.kwargs
        self.assertEqual(arguments["telegram_cta_buttons"], ({
            "identity": "TIP", "url": "https://cash.app/$AvaBlackthorne",
        },))
        self.assertEqual(arguments["audit_metadata"], {"selected_ctas": ["TIP"]})
        self.assertEqual(
            TelegramPublishingProvider.build_inline_keyboard(
                cta_buttons=arguments["telegram_cta_buttons"],
            ),
            {"inline_keyboard": [[{
                "text": "❤️ Show Ava Some Love",
                "url": "https://cash.app/$AvaBlackthorne",
            }]]},
        )
        self.assertEqual(
            self.library.mark_published.call_args.kwargs["metadata"]["selected_ctas"],
            ["TIP"],
        )

    @patch(
        "app.services.generation_library_publishing_service.TelegramPublishingProvider.load_telegram_env",
        return_value={
            "content_vault_url": "https://t.me/+canonical-vault",
            "cashapp_tip_url": "https://cash.app/$AvaBlackthorne",
        },
    )
    def test_vault_and_tip_are_ordered_on_one_row_and_persisted_semantically(self, _config):
        self.social.create_queue_item.return_value = SimpleNamespace(queue_item_id="queue-both")
        self.social.publish_now.return_value = SimpleNamespace(status="posted")

        self.service.publish(
            generated_image_id="generated-1", destination="telegram_wall",
            caption="Telegram caption", cta_enabled=True, selected_ctas=("TIP", "VAULT"),
        )

        arguments = self.social.publish_now.call_args.kwargs
        self.assertEqual(arguments["audit_metadata"], {"selected_ctas": ["VAULT", "TIP"]})
        self.assertEqual(
            TelegramPublishingProvider.build_inline_keyboard(
                cta_buttons=arguments["telegram_cta_buttons"],
            ),
            {"inline_keyboard": [[
                {"text": "🔒 Vault", "url": "https://t.me/+canonical-vault"},
                {"text": "❤️ Tip", "url": "https://cash.app/$AvaBlackthorne"},
            ]]},
        )

    def test_tip_label_uses_final_outgoing_button_count(self):
        vault = {"identity": "VAULT", "url": "https://example.test/vault"}
        chat = {"identity": "CHAT", "text": "Chat", "url": "https://example.test/chat"}
        tip = {"identity": "TIP", "url": "https://example.test/tip"}

        one = TelegramPublishingProvider.build_inline_keyboard(cta_buttons=(tip,))
        two = TelegramPublishingProvider.build_inline_keyboard(cta_buttons=(vault, tip))
        three = TelegramPublishingProvider.build_inline_keyboard(cta_buttons=(vault, chat, tip))
        self.assertEqual(one["inline_keyboard"][0][0]["text"], "❤️ Show Ava Some Love")
        self.assertEqual(two["inline_keyboard"][0][1]["text"], "❤️ Tip")
        self.assertEqual(three["inline_keyboard"][0][0]["text"], "🔒")
        self.assertEqual(three["inline_keyboard"][0][2]["text"], "❤️")

    def test_missing_or_invalid_tip_url_fails_before_publishing(self):
        for value in ("", "https://"):
            self.social.reset_mock()
            with patch(
                "app.services.generation_library_publishing_service.TelegramPublishingProvider.load_telegram_env",
                return_value={"cashapp_tip_url": value},
            ):
                with self.assertRaisesRegex(ValueError, "Tip URL|TIP CTA URL"):
                    self.service.publish(
                        generated_image_id="generated-1", destination="telegram_wall",
                        caption="Telegram caption", cta_enabled=True, selected_ctas=("TIP",),
                    )
            self.social.publish_now.assert_not_called()

    @patch(
        "app.services.generation_library_publishing_service.TelegramPublishingProvider.load_telegram_env",
        return_value={
            "content_vault_url": "https://t.me/+canonical-vault",
            "chat_url": "https://t.me/avablackthorne",
            "cashapp_tip_url": "https://cash.app/$AvaBlackthorne",
        },
    )
    def test_chat_combinations_render_in_canonical_order_and_persist_identities(self, _config):
        cases = (
            (("CHAT",), [
                {"text": "💬 Chat With Me", "url": "https://t.me/avablackthorne"},
            ]),
            (("CHAT", "VAULT"), [
                {"text": "🔒 Vault", "url": "https://t.me/+canonical-vault"},
                {"text": "💬 Chat", "url": "https://t.me/avablackthorne"},
            ]),
            (("TIP", "CHAT"), [
                {"text": "💬 Chat", "url": "https://t.me/avablackthorne"},
                {"text": "❤️ Tip", "url": "https://cash.app/$AvaBlackthorne"},
            ]),
            (("TIP", "VAULT", "CHAT"), [
                {"text": "🔒", "url": "https://t.me/+canonical-vault"},
                {"text": "💬", "url": "https://t.me/avablackthorne"},
                {"text": "❤️", "url": "https://cash.app/$AvaBlackthorne"},
            ]),
        )
        for index, (selection, expected_row) in enumerate(cases):
            with self.subTest(selection=selection):
                self.social.reset_mock()
                self.library.mark_published.reset_mock()
                self.social.create_queue_item.return_value = SimpleNamespace(queue_item_id=f"queue-chat-{index}")
                self.social.publish_now.return_value = SimpleNamespace(status="posted")
                self.service.publish(
                    generated_image_id="generated-1", destination="telegram_wall",
                    caption="Telegram caption", cta_enabled=True, selected_ctas=selection,
                )
                arguments = self.social.publish_now.call_args.kwargs
                keyboard = TelegramPublishingProvider.build_inline_keyboard(
                    cta_buttons=arguments["telegram_cta_buttons"],
                )
                self.assertEqual(keyboard, {"inline_keyboard": [expected_row]})
                expected_identities = [value for value in ("VAULT", "CHAT", "TIP") if value in selection]
                self.assertEqual(arguments["audit_metadata"]["selected_ctas"], expected_identities)
                self.assertEqual(
                    self.library.mark_published.call_args.kwargs["metadata"]["selected_ctas"],
                    expected_identities,
                )

    def test_missing_or_invalid_chat_url_fails_before_publishing(self):
        for value in ("", "https://"):
            self.social.reset_mock()
            with patch(
                "app.services.generation_library_publishing_service.TelegramPublishingProvider.load_telegram_env",
                return_value={"chat_url": value},
            ):
                with self.assertRaisesRegex(ValueError, "Chat URL|CHAT CTA URL"):
                    self.service.publish(
                        generated_image_id="generated-1", destination="telegram_wall",
                        caption="Telegram caption", cta_enabled=True, selected_ctas=("CHAT",),
                    )
            self.social.publish_now.assert_not_called()

    def test_legacy_freeform_keyboard_remains_unchanged(self):
        self.assertEqual(
            TelegramPublishingProvider.build_inline_keyboard(
                cta_enabled=True, cta_label="Legacy", cta_url="https://example.test/legacy",
            ),
            {"inline_keyboard": [[{"text": "Legacy", "url": "https://example.test/legacy"}]]},
        )

    def test_semantic_cta_selection_cannot_publish_placeholders_or_empty_keyboard(self):
        self.social.create_queue_item.return_value = SimpleNamespace(queue_item_id="queue-empty")
        self.social.publish_now.return_value = SimpleNamespace(status="posted")

        self.service.publish(
            generated_image_id="generated-1", destination="telegram_wall",
            caption="Telegram caption", cta_enabled=True, selected_ctas=(),
        )
        self.assertFalse(self.social.publish_now.call_args.kwargs["telegram_cta_enabled"])
        self.assertEqual(self.social.publish_now.call_args.kwargs["telegram_cta_label"], "")
        self.assertEqual(self.social.publish_now.call_args.kwargs["telegram_cta_url"], "")


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
            x_auto_replies_enabled=False,
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
        self.assertEqual(
            self.social.publish_now.call_args.kwargs["audit_metadata"],
            {
                "x_auto_replies_enabled": False,
                "x_auto_callback_status": "pending",
            },
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

    def test_failed_main_x_publish_never_reaches_archive_or_slave_staging(self):
        self.social.create_queue_item.return_value = SimpleNamespace(queue_item_id="queue-x-failed")
        self.social.publish_now.return_value = SimpleNamespace(status="failed")
        self.social.list_history.return_value = (
            SimpleNamespace(queue_item_id="queue-x-failed", message="X provider rejected publish."),
        )

        with self.assertRaisesRegex(RuntimeError, "X provider rejected publish"):
            self.service.publish(
                generated_image_id="generated-1",
                destination="x",
                caption="Caption",
            )

        self.library.mark_published.assert_not_called()

    def test_cancelled_publish_does_not_consume_posting_stage(self):
        self.social.create_queue_item.return_value = SimpleNamespace(queue_item_id="queue-cancelled")
        self.social.publish_now.return_value = SimpleNamespace(status="cancelled")
        self.social.list_history.return_value = (
            SimpleNamespace(queue_item_id="queue-cancelled", message="Publish cancelled."),
        )

        with self.assertRaisesRegex(RuntimeError, "Publish cancelled"):
            self.service.publish(
                generated_image_id="generated-1",
                destination="telegram_wall",
                caption="Caption",
            )

        self.library.mark_published.assert_not_called()

    def test_archive_transition_failure_is_not_reported_as_publish_success(self):
        self.social.create_queue_item.return_value = SimpleNamespace(queue_item_id="queue-archive")
        self.social.publish_now.return_value = SimpleNamespace(status="posted")
        self.library.mark_published.return_value = SimpleNamespace(
            success=False, message="Generated image could not be archived after publish.",
        )

        with self.assertRaisesRegex(RuntimeError, "could not be archived"):
            self.service.publish(
                generated_image_id="generated-1",
                destination="telegram_wall",
                caption="Caption",
            )

if __name__ == "__main__":
    unittest.main()
