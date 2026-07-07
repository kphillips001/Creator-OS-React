"""Provider-neutral publishing provider contract."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class PublishingProviderCapabilities:
    uploads: bool = True
    upload_status: bool = True
    provider_metadata: bool = True
    provider_media_id: bool = True
    provider_output_url: bool = True
    provider_error: bool = True
    retry: bool = True
    manual_media_link: bool = False
    wall_posts: bool = False


class PublishingProvider(Protocol):
    """Contract implemented by platform-specific publishing providers."""

    provider_name: str

    def publish(
        self,
        *,
        asset_id: int,
        provider_account_id: int,
        preview_path: str,
        full_path: str,
        classification: str,
    ) -> dict[str, Any]:
        """Publish an asset's preview/full media pair to the provider."""

    def publish_media_item(
        self,
        *,
        provider_account_id: int,
        item: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Publish one media item to the provider."""

    def create_wall_post(
        self,
        *,
        provider_account_id: int,
        text: str,
        media_ids: list[str] | None = None,
        audience: str = "followers-and-subscribers",
    ) -> dict[str, Any]:
        """Create a provider wall post."""

    def update(
        self,
        publishing_record: Mapping[str, Any],
        update_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Apply a provider-side update when supported."""

    def delete(
        self,
        publishing_record: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Delete or detach provider-side publishing output when supported."""

    def get_publishing_status(
        self,
        publishing_record: Mapping[str, Any] | None,
    ) -> str | None:
        """Return the provider status from a publishing record."""

    def get_upload_status(
        self,
        publishing_record: Mapping[str, Any] | None,
    ) -> str | None:
        """Return provider upload status from a publishing record."""

    def normalize_provider_response(
        self,
        provider_response: Mapping[str, Any] | None,
        *,
        default_status: str,
        provider_error: Any = None,
        fallback_media_ids: bool = True,
    ) -> dict[str, Any]:
        """Normalize provider response fields for PublishingRecord updates."""

    def retrieve_provider_output(
        self,
        publishing_record: Mapping[str, Any] | None,
    ) -> str | None:
        """Return the provider output URL or equivalent public output."""

    def get_capabilities(self) -> PublishingProviderCapabilities:
        """Return provider feature support without exposing provider internals."""
