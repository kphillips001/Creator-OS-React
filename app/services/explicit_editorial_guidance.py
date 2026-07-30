"""Independent artistic prior for Explicit Content planning workflows."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExplicitEditorialGuidance:
    """Own explicit editorial language without changing scene or wardrobe."""

    system_id: str = "explicit_editorial_guidance"
    version: str = "1"

    def planning_instruction(self) -> str:
        return """
EXPLICIT EDITORIAL GUIDANCE — IMMUTABLE ARTISTIC PRIOR
Treat the selected scene as a sophisticated premium creator editorial image.
Derive the execution naturally from that scene while reinforcing private
moments, intimate atmosphere, teasing energy, sensual body language, quiet
confidence, luxury editorial styling, intentional posing, cinematic intimacy,
magnetic presence, emotional tension, natural seduction, and sophisticated
premium creator photography when supported by the scene.

This layer owns artistic language only. It must not add, remove, cover,
reinterpret, or weaken the Scene, Editorial Direction, Wardrobe, Creator
Identity, Visual Quality, or Provider Optimization layers.

Do not impose influencer lifestyle, cheerful creator portraiture, commercial
catalog photography, creator camera-roll energy, generic fashion-campaign
styling, travel/editorial blogging, observed day-in-the-life activity, casual
environmental interaction, walking into locations, carrying everyday objects,
creator lifestyle storytelling, premium fashion as the dominant objective, or
candid influencer photography.
""".strip()

    def provider_section(self) -> str:
        return """
Private premium creator editorial language; intimate atmosphere; intentional,
scene-faithful body language; quiet confidence; cinematic intimacy; magnetic
presence; emotional tension; natural seduction; sophisticated luxury finish.
Avoid influencer lifestyle, cheerful commercial portraiture, catalog energy,
camera-roll casualness, generic fashion campaigns, and travel-blog aesthetics.
Do not rewrite any concrete scene, wardrobe, expression, gaze, or pose detail.
""".strip()

    def metadata(self) -> dict[str, str]:
        return {
            "system_id": self.system_id,
            "version": self.version,
            "artistic_language": "private_premium_creator_editorial",
            "scope": "explicit_only",
        }
