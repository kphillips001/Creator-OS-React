"""Provider-neutral Photoshoot Queue domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Iterable, Mapping

from app.models.generation_engine import utc_now


PHOTOSHOOT_ASSET_METADATA_KEY = "photoshoot_session"


@dataclass(frozen=True)
class CanonicalPhotoshootSeedSummary:
    """Provider-neutral creative foundation extracted from one seed-image prompt."""

    scene: str
    wardrobe: str = ""
    mood_and_editorial_intent: str = ""
    creator_identity: str = ""
    artistic_intent: str = ""

    _SECTION_PATTERN = re.compile(
        r"(?m)^(SCENE|EXPLICIT EDITORIAL GUIDANCE|EDITORIAL DIRECTION|WARDROBE|"
        r"CREATOR IDENTITY|VISUAL QUALITY|PROVIDER OPTIMIZATION|"
        r"FINAL REFERENCE BODY LOCK[^\n]*|WAN BUST VISIBILITY LOCK|"
        r"SEEDREAM[^\n]*LOCK)\s*:?[ \t]*$"
    )
    _QUALITY_START = re.compile(
        r"(?i)(?:,?\s+)(?:photorealistic|ultra-realistic|masterpiece|best quality)"
    )

    @classmethod
    def from_provider_prompt(
        cls,
        prompt_text: str,
        *,
        creative_tags: Iterable[str] = (),
    ) -> "CanonicalPhotoshootSeedSummary":
        source = str(prompt_text or "").strip()
        source = re.sub(r"^Prompt\s+\d+\s*:\s*", "", source, count=1, flags=re.IGNORECASE)
        sections = cls._sections(source)
        scene = str(sections.get("SCENE") or cls._leading_scene(source)).strip()
        clean_tags = tuple(
            " ".join(str(tag or "").split())
            for tag in creative_tags
            if str(tag or "").strip()
        )
        if not sections and len(scene) > 4000 and clean_tags:
            scene = "; ".join(clean_tags)
        quality_match = cls._QUALITY_START.search(scene)
        if quality_match:
            scene = scene[:quality_match.start()].rstrip(" ,.;")
        if not scene:
            scene = "Continue the approved seed image as one cohesive Photoshoot."
        return cls(
            scene=scene,
            wardrobe=str(sections.get("WARDROBE") or "").strip(),
            mood_and_editorial_intent=str(sections.get("EDITORIAL DIRECTION") or "").strip(),
            creator_identity=str(sections.get("CREATOR IDENTITY") or "").strip(),
            artistic_intent=str(sections.get("EXPLICIT EDITORIAL GUIDANCE") or "").strip(),
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CanonicalPhotoshootSeedSummary":
        return cls(
            scene=str(value.get("scene") or "").strip(),
            wardrobe=str(value.get("wardrobe") or "").strip(),
            mood_and_editorial_intent=str(value.get("mood_and_editorial_intent") or "").strip(),
            creator_identity=str(value.get("creator_identity") or "").strip(),
            artistic_intent=str(value.get("artistic_intent") or "").strip(),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "scene": self.scene,
            "wardrobe": self.wardrobe,
            "mood_and_editorial_intent": self.mood_and_editorial_intent,
            "creator_identity": self.creator_identity,
            "artistic_intent": self.artistic_intent,
        }

    def to_prompt_text(self) -> str:
        values = (
            ("Original scene", self.scene),
            ("Wardrobe foundation", self.wardrobe),
            ("Mood and editorial intent", self.mood_and_editorial_intent),
            ("Creator identity", self.creator_identity),
            ("Overall artistic intent", self.artistic_intent),
        )
        return " ".join(
            f"{label}: {' '.join(value.split())}"
            for label, value in values
            if value.strip()
        )

    @classmethod
    def _sections(cls, source: str) -> dict[str, str]:
        matches = tuple(cls._SECTION_PATTERN.finditer(source))
        sections: dict[str, str] = {}
        for index, match in enumerate(matches):
            heading = match.group(1)
            end = matches[index + 1].start() if index + 1 < len(matches) else len(source)
            sections.setdefault(heading, source[match.end():end].strip())
        return sections

    @classmethod
    def _leading_scene(cls, source: str) -> str:
        match = cls._SECTION_PATTERN.search(source)
        return source[:match.start()].strip() if match else source.strip()


def normalize_target_shot_count(value, *, default: int = 10) -> int:
    """Return 0 for an open-ended Photoshoot, otherwise the supported fixed target."""
    try:
        count = int(default if value is None or value == "" else value)
    except (TypeError, ValueError):
        count = default
    return 0 if count == 0 else max(2, min(100, count))


@dataclass(frozen=True)
class PhotoshootPlanningContext:
    """Creative-only continuity passed into canonical Photoshoot planning."""

    photoshoot_summary: str
    latest_approved_direction: str
    current_wardrobe: str
    current_location: str
    current_lighting: str
    camera_style: str
    hairstyle: str
    makeup: str
    continuity_locks: Mapping[str, bool]
    progression_stage: int | None
    current_shot: int
    planning_shot: int
    target_shot_count: int
    remaining_shots: int | None
    editorial_stage: str | None
    progression_enabled: bool
    operator_guidance: str
    required_identity_instructions: str
    latest_approved_shot_reference: str
    latest_approved_shot: Mapping[str, Any]
    repetition_avoidance: str

    def to_prompt_text(self) -> str:
        progression_values = (
            ("Progression stage", str(max(0, int(self.progression_stage or 0)))),
            ("Current shot", str(max(1, int(self.current_shot)))),
            ("Planning shot", str(max(2, int(self.planning_shot)))),
            ("Target shots", str(max(2, int(self.target_shot_count)))),
            ("Remaining shots", str(max(0, int(self.remaining_shots or 0)))),
            ("Editorial stage", self.editorial_stage),
        ) if self.progression_enabled else (
            ("Creative structure", "OPEN_ENDED_NON_PROGRESSIVE"),
            ("Session length", "Open-ended; the operator decides when to finish"),
        )
        values = (
            ("Photoshoot summary", self.photoshoot_summary),
            ("Latest approved direction", self.latest_approved_direction),
            ("Current wardrobe", self.current_wardrobe),
            ("Current location", self.current_location),
            ("Current lighting", self.current_lighting),
            ("Camera style", self.camera_style),
            ("Hairstyle", self.hairstyle),
            ("Makeup", self.makeup),
            ("Continuity locks", self._locks_text()),
            *progression_values,
            ("Operator guidance", self.operator_guidance),
            ("Required identity instructions", self.required_identity_instructions),
            ("Latest approved shot reference", self.latest_approved_shot_reference),
            ("Latest approved shot structured continuity", self._latest_shot_text()),
            ("Repetition avoidance", self.repetition_avoidance),
        )
        return " ".join(
            f"{label}: {' '.join(str(value or '').split())}"
            for label, value in values
            if str(value or "").strip()
        )

    def _locks_text(self) -> str:
        return ", ".join(
            f"{str(name).replace('_', ' ')}={'locked' if enabled else 'flexible'}"
            for name, enabled in sorted(self.continuity_locks.items())
        ) or "Use established Photoshoot continuity defaults."

    def _latest_shot_text(self) -> str:
        return "; ".join(
            f"{str(name).replace('_', ' ')}={str(value).strip()}"
            for name, value in self.latest_approved_shot.items()
            if self.progression_enabled or str(name) != "progression_stage"
            if str(value or "").strip()
        )


@dataclass(frozen=True)
class PhotoshootRequest:
    request_id: str
    session_id: str
    prompt_plan_id: str
    prompt_text: str
    sequence_index: int
    creative_mode: str
    reference_asset_id: int | None
    status: str = "queued"
    generation_job_id: str | None = None
    imported_asset_ids: tuple[int, ...] = ()
    review_status: str | None = None
    review_notes: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    updated_at: str | None = None


@dataclass(frozen=True)
class PhotoshootProgress:
    total_prompts: int
    queued_prompts: int
    active_prompts: int
    awaiting_review: int
    approved_images: int
    rejected_images: int
    imported_assets: int
    percent_complete: float


@dataclass(frozen=True)
class PhotoshootResult:
    session_id: str
    approved_asset_ids: tuple[int, ...] = ()
    rejected_asset_ids: tuple[int, ...] = ()
    regenerated_request_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PhotoshootSession:
    session_id: str
    creator_profile_id: int
    title: str
    reference_asset_id: int | None
    creative_mode: str
    target_shot_count: int = 10
    status: str = "queued"
    provider_id: str = "future_provider"
    creator_notes: str | None = None
    creative_continuity: Mapping[str, Any] = field(default_factory=dict)
    request_ids: tuple[str, ...] = ()
    current_request_id: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PhotoshootQueue:
    sessions: tuple[PhotoshootSession, ...] = ()
    requests: tuple[PhotoshootRequest, ...] = ()
