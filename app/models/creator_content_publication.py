"""Permanent memory of successfully published creator-owned content."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


CREATOR_CONTENT_PUBLICATION_SCHEMA_VERSION = "creator_content_publication_v1"


@dataclass(frozen=True)
class CreatorContentPublication:
    publication_id: str
    creator_profile_id: int
    platform: str
    destination: str
    telegram_channel_id: int
    telegram_message_id: int
    published_at: datetime
    generated_image_id: str
    publication_status: str = "PUBLISHED"
    published_asset_id: int | None = None
    caption_result_id: str | None = None
    photoshoot_id: str | None = None
    generation_lineage: Mapping[str, Any] = field(default_factory=dict)
    media_identity: Mapping[str, Any] = field(default_factory=dict)
    published_caption: str = ""
    cta_snapshot: Mapping[str, Any] = field(default_factory=dict)
    provider_identifiers: Mapping[str, Any] = field(default_factory=dict)
    factual_visual_summary: str | None = None
    setting: str | None = None
    clothing: str | None = None
    pose: str | None = None
    activity: str | None = None
    expression: str | None = None
    useful_objects: tuple[str, ...] = ()
    mood: str | None = None
    themes: tuple[str, ...] = ()
    safety_snapshot: Mapping[str, Any] = field(default_factory=dict)
    intelligence_source: str = "GENERATION_METADATA"
    intelligence_version: str = CREATOR_CONTENT_PUBLICATION_SCHEMA_VERSION
    intelligence_provenance: Mapping[str, Any] = field(default_factory=dict)
    search_document: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None
