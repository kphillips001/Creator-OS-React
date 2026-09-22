from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.services.generation_library_publishing_service import GenerationLibraryPublishingService


def make_service(*, publish_status="posted"):
    library = Mock()
    library.get.return_value = SimpleNamespace(
        image_id="generated-1", creative_mode="premium_teaser", prompt_text="Studio portrait",
        prompt_metadata={}, generation_metadata={})
    library.resolve_publishable_image_reference.return_value = "C:/images/generated-1.png"
    social = Mock()
    social.create_queue_item.return_value = SimpleNamespace(queue_item_id="queue-1")
    social.publish_now.return_value = SimpleNamespace(status=publish_status)
    item = SimpleNamespace(queue_item_id="queue-1", platform="telegram", status="posted",
        metadata={"provider_post_id":"88", "provider_metadata":{
            "response":{"result":{"message_id":88,"chat":{"id":-1007}}}}})
    social.list_publish_items.return_value = (item,)
    social.list_history.return_value = ()
    memory = Mock()
    memory.record_confirmed_telegram_broadcast.return_value = SimpleNamespace(
        publication_id="00000000-0000-4000-8000-000000000001", creator_profile_id=7)
    attribution = Mock()
    service = GenerationLibraryPublishingService(
        generation_library=library, caption_studio=Mock(), social_publishing=social,
        publication_memory=memory, content_entry_attribution=attribution)
    return service, library, memory, attribution


@patch("app.services.generation_library_publishing_service.TelegramPublishingProvider.load_telegram_env",
       return_value={"chat_url":"https://t.me/avablackthorne", "content_vault_url":"https://t.me/+vault"})
def test_chat_broadcast_establishes_memory_before_one_attribution(_config):
    service, library, memory, attribution = make_service()
    service.publish(generated_image_id="generated-1", destination="telegram_wall",
        caption="Caption", cta_enabled=True, selected_ctas=("CHAT", "VAULT"))
    memory.record_confirmed_telegram_broadcast.assert_called_once()
    attribution.ensure_and_attach.assert_called_once()
    assert memory.record_confirmed_telegram_broadcast.call_args is not None
    library.mark_published.assert_called_once()


@patch("app.services.generation_library_publishing_service.TelegramPublishingProvider.load_telegram_env",
       return_value={"content_vault_url":"https://t.me/+vault"})
def test_non_chat_broadcast_keeps_memory_without_attribution(_config):
    service, _library, memory, attribution = make_service()
    service.publish(generated_image_id="generated-1", destination="telegram_wall",
        caption="Caption", cta_enabled=True, selected_ctas=("VAULT",))
    memory.record_confirmed_telegram_broadcast.assert_called_once()
    attribution.ensure_and_attach.assert_not_called()


@patch("app.services.generation_library_publishing_service.TelegramPublishingProvider.load_telegram_env",
       return_value={"chat_url":"https://t.me/avablackthorne"})
def test_attribution_failure_cannot_undo_publication_memory_or_republish(_config):
    service, library, memory, attribution = make_service()
    attribution.ensure_and_attach.side_effect = RuntimeError("optional attribution unavailable")
    result = service.publish(generated_image_id="generated-1", destination="telegram_wall",
        caption="Caption", cta_enabled=True, selected_ctas=("CHAT",))
    assert result["message"] == "Published to Telegram."
    memory.record_confirmed_telegram_broadcast.assert_called_once()
    attribution.ensure_and_attach.assert_called_once()
    library.mark_published.assert_called_once()
    service.social_publishing.publish_now.assert_called_once()