"""Authoritative content-commitment domain for canonical Assets."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping


CONTENT_DESTINATION_SCHEMA_VERSION = "content_destination_v1"


class ContentDestination(str, Enum):
    AVAILABLE_INVENTORY = "AVAILABLE_INVENTORY"
    PHOTOSET = "PHOTOSET"
    VIDEOSET = "VIDEOSET"
    STORY_SET = "STORY_SET"
    TELEGRAM_WALL = "TELEGRAM_WALL"
    TEASER = "TEASER"
    SINGLE_PPV = "SINGLE_PPV"
    BUNDLE = "BUNDLE"


@dataclass(frozen=True)
class AssetContentDestination:
    asset_id: int
    destination: ContentDestination
    creator_profile_id: int | None = None
    assigned_by_profile_id: int | None = None
    source_workflow: str | None = None
    source_reference: str | None = None
    reason: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    assigned_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    schema_version: str = CONTENT_DESTINATION_SCHEMA_VERSION


@dataclass(frozen=True)
class ContentDestinationHistoryEntry:
    history_id: int
    asset_id: int
    event_type: str
    previous_destination: ContentDestination | None
    new_destination: ContentDestination
    assigned_by_profile_id: int | None = None
    source_workflow: str | None = None
    source_reference: str | None = None
    reason: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    schema_version: str = CONTENT_DESTINATION_SCHEMA_VERSION

