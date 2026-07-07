from app.repositories.content_usage_repository import (
    has_user_seen_content,
    has_user_seen_content_tag,
    log_content_usage,
)


class ContentUsageService:
    def has_seen_content(
        self,
        fanvue_account_id: int,
        fanvue_user_id: int,
        content_item_id: int,
    ) -> bool:
        return has_user_seen_content(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_id,
            content_item_id=content_item_id,
        )

    def has_seen_content_tag(
        self,
        fanvue_account_id: int,
        fanvue_user_id: int,
        content_tag: str,
    ) -> bool:
        return has_user_seen_content_tag(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_id,
            content_tag=content_tag,
        )

    def mark_content_seen(
        self,
        fanvue_account_id: int,
        fanvue_user_id: int,
        content_item_id: int,
        send_source: str,
        fanvue_message_id: str | None = None,
        caption_used: str | None = None,
        price: float | None = None,
        usage_type: str = "send",
        pipeline: str | None = None,
        classification: str | None = None,
    ) -> dict:
        return log_content_usage(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_id,
            content_item_id=content_item_id,
            send_source=send_source,
            fanvue_message_id=fanvue_message_id,
            caption_used=caption_used,
            price=price,
            usage_type=usage_type,
            pipeline=pipeline,
            classification=classification,
        )