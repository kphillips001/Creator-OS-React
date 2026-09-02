"""Compact, durable session memory for Photoshoot Creative Director context."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from app.services.photoshoot_queue_service import PhotoshootQueueService


class PhotoshootSummaryService:
    """Synthesizes approved Photoshoot state without replaying prompt history."""

    LOCATION_TERMS = ("studio", "bedroom", "bathroom", "shower", "hotel", "kitchen", "beach", "outdoor", "window", "mirror", "sofa", "bed")
    WARDROBE_TERMS = ("dress", "lingerie", "bra", "panties", "topless", "nude", "robe", "shirt", "skirt", "bodysuit", "bikini")
    LIGHTING_TERMS = ("soft light", "window light", "golden hour", "natural light", "warm light", "neon", "backlight", "low light", "studio light")
    STYLE_TERMS = ("editorial", "cinematic", "candid", "glamour", "boudoir", "lifestyle", "selfie", "fashion", "intimate")
    POSE_TERMS = ("standing", "seated", "kneeling", "reclining", "lying", "over shoulder", "arched", "leaning", "close-up")
    CAMERA_TERMS = ("close-up", "medium shot", "full body", "wide shot", "low angle", "high angle", "profile", "overhead", "mirror", "three-quarter")
    NEGATION_PATTERN = re.compile(
        r"\b(?:do\s+not|don't|dont|never|avoid|without|must\s+not|no|not)\b",
        flags=re.IGNORECASE,
    )
    STRUCTURED_KEYS = {
        "location": ("current_location", "location", "setting"),
        "wardrobe": ("current_wardrobe", "wardrobe", "clothing_state", "nudity"),
        "environment": ("environment", "scene", "setting"),
        "wetness": ("wetness", "wetness_state"),
        "hairstyle": ("hairstyle", "hair", "hair_state"),
        "props": ("props", "persistent_props"),
    }

    def __init__(self, *, queue=None):
        self.queue = queue or PhotoshootQueueService()

    def build(self, session_id: str) -> dict[str, Any]:
        session = self.queue.get_session(session_id)
        continuity = dict(session.creative_continuity or {})
        approved = tuple(
            request for request in self.queue.requests_for_session(session_id)
            if request.status == "approved"
        )
        directions = tuple(
            dict((request.metadata or {}).get("creative_direction") or {})
            for request in approved
            if isinstance((request.metadata or {}).get("creative_direction"), Mapping)
        )
        latest_prompt = str(approved[-1].prompt_text or "").strip() if approved else ""
        fallback_text = self._positive_text(latest_prompt)
        latest_direction_text = self._positive_text(self._latest_direction_text(directions))
        seed = continuity.get("canonical_seed_summary")
        seed = dict(seed) if isinstance(seed, Mapping) else {}
        poses = self._unique(
            (*self._direction_values(directions, "pose_composition"), *self._terms(fallback_text, self.POSE_TERMS))
        )
        cameras = self._unique(
            (*self._direction_values(directions, "camera_framing"), *self._terms(fallback_text, self.CAMERA_TERMS))
        )
        lighting = self._unique((*self._direction_values(directions, "lighting"), *self._terms(fallback_text, self.LIGHTING_TERMS)))
        themes = self._unique((*self._direction_values(directions, "title"), *self._terms(fallback_text, self.STYLE_TERMS)))
        location = self._state_value(directions, "location") or self._last_term(
            latest_direction_text, self.LOCATION_TERMS
        ) or self._last_term(
            self._positive_text(str(seed.get("scene") or "")), self.LOCATION_TERMS
        ) or self._last_term(fallback_text, self.LOCATION_TERMS)
        wardrobe = self._state_value(directions, "wardrobe") or self._last_term(
            latest_direction_text, self.WARDROBE_TERMS
        ) or str(seed.get("wardrobe") or "").strip() or self._last_term(
            fallback_text, self.WARDROBE_TERMS
        )
        original = str(
            seed.get("mood_and_editorial_intent")
            or seed.get("scene")
            or continuity.get("original_photoshoot_direction")
            or session.creator_notes
            or "Continue the selected seed as one cohesive photoshoot."
        ).strip()
        opportunities = self._opportunities(poses=poses, cameras=cameras)
        summary = {
            "approved_shot_count": len(approved),
            "overall_theme": self._compact(themes, fallback=original, limit=3),
            "current_location": location or "Preserve the established location.",
            "current_wardrobe": wardrobe or "Preserve the established wardrobe.",
            "environment": self._state_value(directions, "environment") or str(seed.get("scene") or "").strip(),
            "wetness": self._state_value(directions, "wetness"),
            "hairstyle": self._state_value(directions, "hairstyle"),
            "props": self._state_value(directions, "props"),
            "lighting": lighting[-1] if lighting else "Preserve the established lighting.",
            "visual_style": self._compact(self._terms(fallback_text, self.STYLE_TERMS), fallback="Maintain the established visual style.", limit=2),
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
        matches = []
        for term in terms:
            matches.extend(
                (match.start(), term)
                for match in re.finditer(rf"(?<!\w){re.escape(term)}(?!\w)", text, flags=re.IGNORECASE)
            )
        return cls._unique(term for _, term in sorted(matches))

    @classmethod
    def _positive_text(cls, text: str) -> str:
        """Exclude negative/provider-lock clauses from legacy state inference."""
        clauses = re.split(r"(?<=[.!?;])\s+|\n+", str(text or ""))
        return " ".join(clause for clause in clauses if clause.strip() and not cls.NEGATION_PATTERN.search(clause))

    @classmethod
    def _last_term(cls, text: str, terms: Iterable[str]) -> str:
        matches = cls._terms(text, terms)
        return matches[-1] if matches else ""

    @classmethod
    def _state_value(cls, directions: Iterable[Mapping[str, Any]], state: str) -> str:
        keys = cls.STRUCTURED_KEYS[state]
        for direction in reversed(tuple(directions)):
            for key in keys:
                value = direction.get(key)
                if isinstance(value, (list, tuple, set)):
                    value = ", ".join(str(item).strip() for item in value if str(item or "").strip())
                clean = re.sub(r"\s+", " ", str(value or "").strip())
                if clean:
                    return clean
        return ""

    @staticmethod
    def _latest_direction_text(directions: Iterable[Mapping[str, Any]]) -> str:
        values = tuple(directions)
        if not values:
            return ""
        latest = values[-1]
        return "\n".join(
            str(latest.get(key) or "").strip()
            for key in ("title", "creative_direction", "continuity_notes", "session_direction")
            if str(latest.get(key) or "").strip()
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
        return [
            "Continue from the latest approved frame with one subtle change in expression, pose, or hand placement; "
            "preserve its scene and camera setup unless the operator directs otherwise."
        ]

    @staticmethod
    def _avoid_repetition(*, poses: tuple[str, ...], cameras: tuple[str, ...]) -> str:
        explored = tuple((*poses[-3:], *cameras[-3:]))
        return (
            "Avoid an exact duplicate while staying adjacent to the latest approved composition: " + "; ".join(explored)
            if explored
            else "Avoid an exact duplicate through one subtle natural change; preserve the latest scene and camera setup."
        )

    @staticmethod
    def _summary_text(summary: Mapping[str, Any]) -> str:
        stable_state = "; ".join(
            f"{label}: {summary.get(key)}"
            for label, key in (("Environment", "environment"), ("Wetness", "wetness"), ("Hair", "hairstyle"), ("Props", "props"))
            if str(summary.get(key) or "").strip()
        )
        lines = [
            f"Theme: {summary['overall_theme']}",
            f"Setting: {summary['current_location']} | Wardrobe: {summary['current_wardrobe']} | Lighting: {summary['lighting']}",
            f"Progression: {summary['current_progression']}",
            f"Poses explored: {', '.join(summary['major_poses_explored']) or 'seed composition only'}",
            f"Compositions explored: {', '.join(summary['camera_compositions_explored']) or 'seed composition only'}",
            f"Open opportunities: {' '.join(summary['creative_opportunities'])}",
            str(summary['avoid_repetition']),
        ]
        if stable_state:
            lines.insert(2, stable_state)
        return "\n".join(lines)
