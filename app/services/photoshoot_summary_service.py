"""Compact, durable session memory for Photoshoot Creative Director context."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from app.services.photoshoot_queue_service import PhotoshootQueueService


class PhotoshootSummaryService:
    """Synthesizes approved Photoshoot state without replaying prompt history."""

    LOCATION_TERMS = ("studio", "bedroom", "bathroom", "hotel", "kitchen", "beach", "outdoor", "window", "mirror", "sofa", "bed")
    WARDROBE_TERMS = ("dress", "lingerie", "bra", "panties", "topless", "nude", "robe", "shirt", "skirt", "bodysuit", "bikini")
    LIGHTING_TERMS = ("soft light", "window light", "golden hour", "natural light", "warm light", "neon", "backlight", "low light", "studio light")
    STYLE_TERMS = ("editorial", "cinematic", "candid", "glamour", "boudoir", "lifestyle", "selfie", "fashion", "intimate")
    POSE_TERMS = ("standing", "seated", "kneeling", "reclining", "lying", "over shoulder", "arched", "leaning", "close-up")
    CAMERA_TERMS = ("close-up", "medium shot", "full body", "wide shot", "low angle", "high angle", "profile", "overhead", "mirror", "three-quarter")

    def __init__(self, *, queue=None):
        self.queue = queue or PhotoshootQueueService()

    def build(self, session_id: str) -> dict[str, Any]:
        session = self.queue.get_session(session_id)
        continuity = dict(session.creative_continuity or {})
        approved = tuple(
            request for request in self.queue.requests_for_session(session_id)
            if request.status == "approved"
        )
        prompts = self._unique(request.prompt_text for request in approved)
        directions = tuple(
            dict((request.metadata or {}).get("creative_direction") or {})
            for request in approved
            if isinstance((request.metadata or {}).get("creative_direction"), Mapping)
        )
        combined = " ".join(prompts).lower()
        poses = self._unique(
            (*self._direction_values(directions, "pose_composition"), *self._terms(combined, self.POSE_TERMS))
        )
        cameras = self._unique(
            (*self._direction_values(directions, "camera_framing"), *self._terms(combined, self.CAMERA_TERMS))
        )
        lighting = self._unique((*self._direction_values(directions, "lighting"), *self._terms(combined, self.LIGHTING_TERMS)))
        themes = self._unique((*self._direction_values(directions, "title"), *self._direction_values(directions, "creative_direction"), *self._terms(combined, self.STYLE_TERMS)))
        locations = self._terms(combined, self.LOCATION_TERMS)
        wardrobe = self._terms(combined, self.WARDROBE_TERMS)
        original = str(
            continuity.get("seed_prompt_text")
            or continuity.get("original_photoshoot_direction")
            or session.creator_notes
            or "Continue the selected seed as one cohesive photoshoot."
        ).strip()
        opportunities = self._opportunities(poses=poses, cameras=cameras)
        summary = {
            "approved_shot_count": len(approved),
            "overall_theme": self._compact(themes, fallback=original, limit=3),
            "current_location": locations[-1] if locations else "Preserve the established location.",
            "current_wardrobe": wardrobe[-1] if wardrobe else "Preserve the established wardrobe.",
            "lighting": lighting[-1] if lighting else "Preserve the established lighting.",
            "visual_style": self._compact(self._terms(combined, self.STYLE_TERMS), fallback="Maintain the established visual style.", limit=2),
            "current_progression": f"{len(approved)} approved shot{'s' if len(approved) != 1 else ''}; continue from the latest approved frame.",
            "major_poses_explored": list(poses[-6:]),
            "camera_compositions_explored": list(cameras[-6:]),
            "creative_opportunities": opportunities,
            "avoid_repetition": self._avoid_repetition(poses=poses, cameras=cameras),
        }
        summary["summary_text"] = self._summary_text(summary)
        return summary

    def refresh(self, session_id: str) -> dict[str, Any]:
        summary = self.build(session_id)
        self.queue.record_photoshoot_summary(session_id=session_id, summary=summary)
        return summary

    @staticmethod
    def _unique(values: Iterable[Any]) -> tuple[str, ...]:
        result = []
        seen = set()
        for value in values:
            clean = re.sub(r"\s+", " ", str(value or "").strip())
            key = clean.lower()
            if clean and key not in seen:
                seen.add(key)
                result.append(clean)
        return tuple(result)

    @classmethod
    def _terms(cls, text: str, terms: Iterable[str]) -> tuple[str, ...]:
        return cls._unique(
            term for term in terms
            if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text, flags=re.IGNORECASE)
        )

    @classmethod
    def _direction_values(cls, directions: Iterable[Mapping[str, Any]], key: str) -> tuple[str, ...]:
        return cls._unique(direction.get(key) for direction in directions)

    @staticmethod
    def _compact(values: Iterable[str], *, fallback: str, limit: int) -> str:
        selected = tuple(values)[-limit:]
        return "; ".join(selected) if selected else fallback

    @staticmethod
    def _opportunities(*, poses: tuple[str, ...], cameras: tuple[str, ...]) -> list[str]:
        opportunities = []
        if not any("profile" in value.lower() for value in cameras):
            opportunities.append("Explore a profile or three-quarter composition.")
        if not any("close-up" in value.lower() for value in cameras):
            opportunities.append("Use a closer expression-led frame.")
        if not any("reclining" in value.lower() or "lying" in value.lower() for value in poses):
            opportunities.append("Introduce a grounded or reclining pose if it fits the direction.")
        return opportunities[:3] or ["Advance expression, hand placement, and framing without repeating an approved composition."]

    @staticmethod
    def _avoid_repetition(*, poses: tuple[str, ...], cameras: tuple[str, ...]) -> str:
        explored = tuple((*poses[-3:], *cameras[-3:]))
        return "Avoid repeating: " + "; ".join(explored) if explored else "Avoid repeating the seed composition; vary pose, framing, expression, and hand placement."

    @staticmethod
    def _summary_text(summary: Mapping[str, Any]) -> str:
        return "\n".join((
            f"Theme: {summary['overall_theme']}",
            f"Setting: {summary['current_location']} | Wardrobe: {summary['current_wardrobe']} | Lighting: {summary['lighting']}",
            f"Progression: {summary['current_progression']}",
            f"Poses explored: {', '.join(summary['major_poses_explored']) or 'seed composition only'}",
            f"Compositions explored: {', '.join(summary['camera_compositions_explored']) or 'seed composition only'}",
            f"Open opportunities: {' '.join(summary['creative_opportunities'])}",
            str(summary['avoid_repetition']),
        ))
