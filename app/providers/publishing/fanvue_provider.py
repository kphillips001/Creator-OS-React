"""Fanvue publishing provider implementation.

C.1.2 establishes the provider boundary only. This provider intentionally wraps
the existing Fanvue upload service and does not change current workflows.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from app.providers.publishing.base import PublishingProviderCapabilities
from app.services.fanvue_api_service import FanvueAPIService
from app.services.fanvue_media_upload_service import FanvueMediaUploadService


class FanvuePublishingProvider:
    """Thin Fanvue adapter for the publishing provider boundary."""

    provider_name = "fanvue"

    def __init__(
        self,
        *,
        media_upload_service_factory: Callable[..., Any] = FanvueMediaUploadService,
        api_service_factory: Callable[..., Any] = FanvueAPIService,
    ):
        self._media_upload_service_factory = media_upload_service_factory
        self._api_service_factory = api_service_factory

    def publish(
        self,
        *,
        asset_id: int,
        provider_account_id: int,
        preview_path: str,
        full_path: str,
        classification: str,
    ) -> dict[str, Any]:
        uploader = self._media_upload_service_factory(
            fanvue_account_id=provider_account_id,
        )
        preview_result = uploader.upload_media_item(
            {
                "id": asset_id,
                "file_path": preview_path,
                "classification": classification,
            }
        )
        full_result = uploader.upload_media_item(
            {
                "id": asset_id,
                "file_path": full_path,
                "classification": classification,
            }
        )
        return {
            "success": bool(
                preview_result.get("success") and full_result.get("success")
            ),
            "preview_result": preview_result,
            "full_result": full_result,
        }

    def publish_media_item(
        self,
        *,
        provider_account_id: int,
        item: Mapping[str, Any],
    ) -> dict[str, Any]:
        uploader = self._media_upload_service_factory(
            fanvue_account_id=provider_account_id,
        )
        return uploader.upload_media_item(dict(item))

    def create_wall_post(
        self,
        *,
        provider_account_id: int,
        text: str,
        media_ids: list[str] | None = None,
        audience: str = "followers-and-subscribers",
    ) -> dict[str, Any]:
        api = self._api_service_factory(fanvue_account_id=provider_account_id)
        return api.create_wall_post(
            text=text,
            media_uuids=media_ids,
            audience=audience,
        )

    def update(
        self,
        publishing_record: Mapping[str, Any],
        update_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "success": False,
            "provider": self.provider_name,
            "reason": "provider_update_not_supported",
            "publishing_record": dict(publishing_record),
            "update_payload": dict(update_payload),
        }

    def delete(
        self,
        publishing_record: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "success": False,
            "provider": self.provider_name,
            "reason": "provider_delete_not_supported",
            "publishing_record": dict(publishing_record),
        }

    def get_publishing_status(
        self,
        publishing_record: Mapping[str, Any] | None,
    ) -> str | None:
        if not publishing_record:
            return None
        return publishing_record.get("provider_status")

    def get_upload_status(
        self,
        publishing_record: Mapping[str, Any] | None,
    ) -> str | None:
        return self.get_publishing_status(publishing_record)

    def normalize_provider_response(
        self,
        provider_response: Mapping[str, Any] | None,
        *,
        default_status: str,
        provider_error: Any = None,
        fallback_media_ids: bool = True,
    ) -> dict[str, Any]:
        provider_response = dict(provider_response or {})
        media_id = provider_response.get("media_uuid")
        preview_id = provider_response.get("preview_uuid")
        full_id = provider_response.get("full_uuid")
        if fallback_media_ids:
            preview_id = preview_id or media_id
            full_id = full_id or media_id
        return {
            "provider_status": provider_response.get("status") or default_status,
            "provider_media_id": (
                media_id or full_id or preview_id
                if fallback_media_ids
                else media_id
            ),
            "provider_preview_media_id": preview_id,
            "provider_full_media_id": full_id,
            "provider_error": None if provider_error is None else str(provider_error),
            "provider_metadata": provider_response,
        }

    def retrieve_provider_output(
        self,
        publishing_record: Mapping[str, Any] | None,
    ) -> str | None:
        if not publishing_record:
            return None
        return publishing_record.get("provider_output_url")

    def get_capabilities(self) -> PublishingProviderCapabilities:
        return PublishingProviderCapabilities(
            uploads=True,
            upload_status=True,
            provider_metadata=True,
            provider_media_id=True,
            provider_output_url=True,
            provider_error=True,
            retry=True,
            manual_media_link=True,
            wall_posts=True,
        )
