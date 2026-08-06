"""Temporary, provider-neutral analysis for inspiration-only images."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


IDENTITY_TERMS = frozenset({
    "face", "facial identity", "hair", "skin", "skin tone", "body",
    "body shape", "age", "ethnicity", "identity", "recognizable identity",
})


@dataclass(frozen=True)
class InspirationSceneAnalysis:
    scene: str = ""
    pose: str = ""
    camera_angle: str = ""
    camera_framing: str = ""
    lighting: str = ""
    composition: str = ""
    wardrobe_concept: str = ""
    expression: str = ""
    mood: str = ""
    environment: str = ""
    color_palette: str = ""
    styling: str = ""
    elements_to_preserve: tuple[str, ...] = ()
    elements_to_ignore: tuple[str, ...] = ()
    identity_transfer_prohibited: bool = True
    confidence: float = 0.0

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "InspirationSceneAnalysis":
        def text(name: str) -> str:
            return str(values.get(name) or "").strip()

        def items(name: str) -> tuple[str, ...]:
            value = values.get(name) or ()
            if isinstance(value, str):
                value = value.split(",")
            return tuple(dict.fromkeys(
                str(item).strip() for item in value if str(item).strip()
            ))

        preserve = tuple(
            item for item in items("elements_to_preserve")
            if not any(term in item.casefold() for term in IDENTITY_TERMS)
        )
        required_ignores = (
            "uploaded subject face", "uploaded subject hair",
            "uploaded subject skin tone", "uploaded subject body",
            "uploaded subject age", "uploaded subject ethnicity",
            "uploaded subject recognizable identity",
        )
        ignore = tuple(dict.fromkeys((*items("elements_to_ignore"), *required_ignores)))
        try:
            confidence = max(0.0, min(1.0, float(values.get("confidence") or 0.0)))
        except (TypeError, ValueError):
            confidence = 0.0
        return cls(
            scene=text("scene"), pose=text("pose"),
            camera_angle=text("camera_angle"),
            camera_framing=text("camera_framing"), lighting=text("lighting"),
            composition=text("composition"),
            wardrobe_concept=text("wardrobe_concept"),
            expression=text("expression"), mood=text("mood"),
            environment=text("environment"), color_palette=text("color_palette"),
            styling=text("styling"), elements_to_preserve=preserve,
            elements_to_ignore=ignore, identity_transfer_prohibited=True,
            confidence=confidence,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

