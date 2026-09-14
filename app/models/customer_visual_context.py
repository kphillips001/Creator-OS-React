"""Ephemeral current-turn visual evidence; never customer identity authority."""
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AttachmentVisualObservation:
    attachment_id: str
    analysis_status: str
    person_visible: bool = False
    person_count: int | None = None
    animals: tuple[str, ...] = ()
    objects: tuple[str, ...] = ()
    activity: str | None = None
    setting: str | None = None
    clothing_style: str | None = None
    facial_expression: str | None = None
    media_type: str | None = None
    visible_text: str | None = None
    scene_summary: str | None = None
    confidence: float = 0.0
    provider: str = ""
    model: str = ""


@dataclass(frozen=True)
class CurrentTurnVisualContext:
    operation_id: str
    safety_state: str
    response_policy: str
    solicitation_state: str
    attachment_paths: tuple[str, ...] = ()
    partial_failure: bool = False
    customer_presented_self_image: bool = False
    observations: tuple[AttachmentVisualObservation, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
