"""Canonical, commerce-neutral Bundle Studio workspace models."""
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class BundleStudioMember:
    image_id: str
    position: int
    added_at: datetime
    generation_job_id: str
    generation_request_id: str
    generation_recipe_id: str | None
    provider_id: str
    output_reference: str
    prompt_text: str
    creative_mode: str | None
    generation_date: str


@dataclass(frozen=True)
class BundleStudioBundle:
    bundle_id: UUID
    creator_profile_id: int
    name: str
    status: str
    created_at: datetime
    updated_at: datetime
    members: tuple[BundleStudioMember, ...] = ()
    sales_destination: str | None = None
    commercial_offering_id: UUID | None = None
