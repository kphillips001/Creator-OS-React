"""Generation Library publishing orchestration for HTTP presentation clients."""

from __future__ import annotations

from typing import Any, Mapping

from app.services.caption_studio_service import CaptionStudioService
from app.services.generation_library_service import GenerationLibraryService
from app.services.social_publishing_service import SocialPublishingService


DESTINATION_TARGETS = {
    "x": ("x", None),
    "telegram_wall": ("telegram", "main"),
    "telegram_chat": ("telegram", "vault"),
}


class GenerationLibraryPublishingService:
    """Preserves the Streamlit publish workflow behind a small API boundary."""

    def __init__(
        self,
        *,
        generation_library: GenerationLibraryService | None = None,
        caption_studio: CaptionStudioService | None = None,
        social_publishing: SocialPublishingService | None = None,
    ) -> None:
        self.generation_library = generation_library or GenerationLibraryService()
        self.caption_studio = caption_studio or CaptionStudioService()
        self.social_publishing = social_publishing or SocialPublishingService()

    @staticmethod
    def validate_destination(destination: str) -> tuple[str, str | None]:
        try:
            return DESTINATION_TARGETS[str(destination or "").strip()]
        except KeyError as exc:
            raise ValueError("Destination must be X, Telegram Wall, or Telegram Chat.") from exc

    def context(self, generated_image_id: str) -> dict[str, Any]:
        record = self.generation_library.get(generated_image_id)
        image_reference = self.generation_library.resolve_publishable_image_reference(record.image_id)
        if not image_reference:
            raise ValueError(
                "This image file is no longer available at its recorded location. "
                "Return it to the Generation Library or repair the asset record before publishing."
            )
        return {
            "generatedImageId": record.image_id,
            "defaultDestination": "x",
            "destinations": (
                {"value": "x", "label": "X", "available": True},
                {"value": "telegram_wall", "label": "Telegram Wall", "available": True},
                {"value": "telegram_chat", "label": "Telegram Chat", "available": True},
            ),
        }

    def generate_captions(
        self,
        *,
        generated_image_id: str,
        destination: str,
        creator_profile: Mapping[str, Any],
        idea_seed: int,
    ) -> dict[str, Any]:
        platform, _ = self.validate_destination(destination)
        record = self.generation_library.get(generated_image_id)
        image_reference = self.generation_library.resolve_publishable_image_reference(record.image_id)
        if not image_reference:
            raise ValueError("The selected Generation Library image is unavailable.")
        arguments = {
            "generated_image_id": record.image_id,
            "image_reference": image_reference,
            "creator_profile_id": int(creator_profile.get("id") or 0),
            "creator_profile": creator_profile,
            "creative_mode": str(record.creative_mode or ""),
            "prompt_text": str(record.prompt_text or ""),
            "prompt_metadata": dict(record.prompt_metadata or {}),
            "generation_metadata": dict(record.generation_metadata or {}),
            "idea_seed": max(0, int(idea_seed)),
        }
        result = (
            self.caption_studio.generate_x_engagement_themes(**arguments)
            if platform == "x"
            else self.caption_studio.generate_telegram_vision_themes(**arguments)
        )
        themes = tuple(
            {
                "theme": str(theme.get("theme") or "Captions"),
                "captions": tuple(str(value) for value in theme.get("captions") or ()),
            }
            for theme in result.formatter_metadata.get("themes") or ()
        )
        return {
            "captionResultId": result.caption_result_id,
            "themes": themes,
        }

    def publish(
        self,
        *,
        generated_image_id: str,
        destination: str,
        caption: str,
        caption_result_id: str | None = None,
        selected_generated_caption: str = "",
        cta_enabled: bool = False,
        cta_label: str = "",
        cta_url: str = "",
    ) -> dict[str, Any]:
        platform, telegram_post_to = self.validate_destination(destination)
        selected_caption = str(caption or "").strip()
        if not selected_caption:
            raise ValueError("Caption is required before publishing.")

        record = self.generation_library.get(generated_image_id)
        if not self.generation_library.resolve_publishable_image_reference(record.image_id):
            raise ValueError("The selected Generation Library image is unavailable.")

        selected_generated = str(selected_generated_caption or "").strip()
        caption_id = None
        if caption_result_id and selected_generated:
            selected_result = self.caption_studio.select_caption(
                caption_result_id,
                selected_text=selected_caption,
            )
            caption_id = selected_result.caption_result_id

        item = self.social_publishing.create_queue_item(
            generated_image_id=record.image_id,
            generation_library=self.generation_library,
            platform=platform,
            creator_notes=(
                "Queued from Generation Library X Publish dialog."
                if platform == "x"
                else "Queued from Generation Library Telegram Publish dialog."
            ),
        )
        if caption_id:
            self.social_publishing.assign_caption(item.queue_item_id, caption_id=caption_id)

        updated = self.social_publishing.publish_now(
            item.queue_item_id,
            caption_text=selected_caption,
            account_name="AvaBlackthorne" if platform == "x" else None,
            caption_id=caption_id,
            telegram_post_to=telegram_post_to or "main",
            telegram_cta_enabled=bool(cta_enabled),
            telegram_cta_label=str(cta_label or ""),
            telegram_cta_url=str(cta_url or ""),
        )
        if updated.status != "posted":
            latest_history = next(iter(self.social_publishing.list_history()), None)
            message = (
                latest_history.message
                if latest_history and latest_history.queue_item_id == item.queue_item_id
                else f"{'X' if platform == 'x' else 'Telegram'} publish failed."
            )
            raise RuntimeError(message)

        caption_was_edited = bool(
            selected_generated and selected_caption != selected_generated
        )
        metadata = {
            "social_queue_item_id": item.queue_item_id,
            "caption_id": caption_id,
            "selected_generated_caption": selected_generated,
            "caption_was_edited": caption_was_edited,
            "caption_source": (
                "edited_generated"
                if caption_was_edited
                else "generated"
                if selected_generated
                else "custom"
            ),
        }
        if platform == "x":
            metadata["account_name"] = "AvaBlackthorne"
        else:
            metadata.update(
                {
                    "post_to": telegram_post_to,
                    "cta_enabled": bool(cta_enabled),
                    "cta_label": str(cta_label or ""),
                    "cta_url": str(cta_url or ""),
                }
            )
        self.generation_library.mark_published(
            record.image_id,
            platform=platform,
            caption=selected_caption,
            metadata=metadata,
        )
        return {
            "message": f"Published to {'X' if platform == 'x' else 'Telegram'}.",
            "queueItemId": item.queue_item_id,
        }
