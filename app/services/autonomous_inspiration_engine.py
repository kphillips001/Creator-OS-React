"""Private creative-direction ideation for one-click social image generation."""

from __future__ import annotations

import calendar
import re
from collections.abc import Callable
from datetime import datetime
from typing import Any

from app.repositories.creator_profile_repository import get_active_creator_profile
from app.repositories.creator_world_model_repository import CreatorWorldModelRepository
from app.services.creator_intelligence_service import CreatorIntelligenceService
from app.services.creative_intelligence_learning_service import (
    CreativeIntelligenceLearningService,
)
from app.services.editorial_quality_guidance import (
    UNSUPPORTED_CREATOR_FACT_GUARD,
    editorial_quality_guidance,
)
from app.services.grok_anything_service import ask_grok_anything


class AutonomousInspirationEngine:
    """Create private image directions; callers must not expose them in UI."""

    IMAGE_COUNT = 6

    def __init__(
        self,
        *,
        creator_intelligence: Any | None = None,
        creative_intelligence: Any | None = None,
        world_model_repository: Any | None = None,
        creator_profile_loader: Callable[[str], dict] | None = None,
        text_generator: Callable[[str], str] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.creator_intelligence = (
            creator_intelligence or CreatorIntelligenceService()
        )
        self.creative_intelligence = (
            creative_intelligence or CreativeIntelligenceLearningService()
        )
        self.world_model_repository = (
            world_model_repository or CreatorWorldModelRepository()
        )
        self.creator_profile_loader = (
            creator_profile_loader or get_active_creator_profile
        )
        self.text_generator = text_generator or ask_grok_anything
        self.now = now or datetime.now

    def create_directions(
        self,
        *,
        fanvue_account_id: int | str,
        diagnostic_trace_id: str | None = None,
    ) -> tuple[str, ...]:
        account_id = str(fanvue_account_id)
        intelligence = self.creator_intelligence.get_for_account(
            fanvue_account_id=account_id,
        )
        profile = self.creator_profile_loader(account_id)
        if not profile:
            raise LookupError(
                f"No active creator profile exists for account {account_id}."
            )
        world_model = self.world_model_repository.get(
            creator_profile_id=int(profile["id"]),
            fanvue_account_id=account_id,
        )
        if world_model is None:
            raise LookupError(
                f"No World Model exists for creator profile {profile['id']} "
                f"in account {account_id}."
            )
        creative_profile = self.creative_intelligence.get_aggregated_profile(
            creator_profile_id=int(profile["id"]),
            fanvue_account_id=account_id,
        )
        current = self.now()
        brief = self._build_brief(
            personality=dict(intelligence.personality),
            lifestyle=dict(intelligence.lifestyle),
            social_creative_direction=dict(
                intelligence.social_creative_direction
            ),
            world_model=world_model,
            creative_intelligence_profile=dict(creative_profile),
            month=calendar.month_name[current.month],
            season=self._season(current.month),
        )
        from app.services.generation_request_diagnostic_service import GenerationRequestDiagnosticService
        diagnostic = GenerationRequestDiagnosticService()
        diagnostic.record(trace_id=diagnostic_trace_id,
                          workflow_origin="autonomous_inspiration",
                          stage="1_workflow_origin", value="autonomous_inspiration")
        diagnostic.record(
            trace_id=diagnostic_trace_id, workflow_origin="autonomous_inspiration",
            stage="2_initial_creative_input",
            value="Autonomous selection from Creator Intelligence and Creative Intelligence",
        )
        diagnostic.record(trace_id=diagnostic_trace_id,
                          workflow_origin="autonomous_inspiration",
                          stage="3_ava_creator_context_supplied", value=brief)
        directions = self._parse(self.text_generator(brief))
        if len(directions) < self.IMAGE_COUNT:
            raise ValueError(
                "Autonomous Inspiration Engine returned fewer than six "
                "usable image directions."
            )
        selected = directions[:self.IMAGE_COUNT]
        diagnostic.record(trace_id=diagnostic_trace_id,
                          workflow_origin="autonomous_inspiration",
                          stage="4_enhanced_creative_intent", value=selected)
        return selected

    @classmethod
    def _build_brief(
        cls,
        *,
        personality: dict,
        lifestyle: dict,
        social_creative_direction: dict,
        world_model: dict,
        creative_intelligence_profile: dict,
        month: str,
        season: str,
    ) -> str:
        def section(name: str, values: dict) -> str:
            body = "\n".join(
                f"{key}: {value}"
                for key, value in values.items()
                if value not in (None, "")
                and key not in {
                    "id", "creator_profile_id", "fanvue_account_id",
                    "created_at", "updated_at",
                }
            )
            return f"{name}:\n{body}"

        editorial_memory = cls._editorial_memory_guidance(
            creative_intelligence_profile
        )

        return f"""You are the private Creator_OS Autonomous Inspiration Engine.

Answer internally:
"What six images is Kevin most likely to keep and eventually publish while still giving him fresh ideas?"

Create exactly {cls.IMAGE_COUNT} distinct production-ready creative directions for {month} ({season}).
These directions are private inputs to the canonical prompt planner. The operator will see only generated images.

CREATIVE PRIORITY:
1. Social Creative Direction is the primary influence.
2. Creative Intelligence influences selection and balancing, but never overrides Social Creative Direction.
3. Prioritize scroll-stopping imagery and strong social-media appeal.
4. Keep the creator as the unmistakable visual subject; environment supports her.
5. Preserve authentic personality and believable lifestyle context.
6. Maintain seasonal appropriateness and strong visual variety.
7. Let Social Creative Direction guide scene-appropriate styling; do not hardcode a fixed outfit formula.

EDITORIAL EVOLUTION:
- Treat frequently retained patterns as familiar brand anchors, not templates to repeat.
- Use lower-frequency learned patterns as variety opportunities when they fit the canonical creator documents.
- Introduce fresh, canonically plausible execution beyond the observed categories.
- Do not infer that an absent category is disliked; absence may simply mean it has not been tried.
- Never copy an old image. Evolve the recognizable brand through new scenes, actions, moods, and visual hooks.

BATCH VARIETY:
- Span at least four distinct environment families across the six directions.
- Balance indoor and outdoor, public and private, and the creator's established geographic and lifestyle contexts.
- Deliberately vary close, mid, and full-body composition opportunities.
- Do not let any dominant learned setting, pose, composition, mood, or visual hook take over the batch.
- Vary the activity, social context, energy, and visual story—not merely the location or styling.

{editorial_quality_guidance(workflow="autonomous")}

AUTONOMOUS COLLECTION CINEMATOGRAPHY:
- Review the complete batch for static, centered, symmetrical portrait repetition. When an equally authentic execution would create a more lived-in moment, revise the scene toward movement or environmental interaction.
- Optimize for the kind of image an editorial photographer would naturally capture while following Ava through her day, not another posed portrait.
- Do not use assigned cinematography slots.

WARDROBE COLOR — EDITORIAL REASONING:
- Internally ask: "What wardrobe color palette best complements this scene while remaining consistent with Ava's brand and maintaining visual diversity across the batch?"
- Choose wardrobe color as part of the complete editorial composition. Consider the current season, environment, lighting, mood, Ava's Social Creative Direction, Creative Intelligence observations, and the other five directions together.
- Review the six directions as one collection before finalizing them. Avoid allowing an implicit default color to dominate merely because it is broadly appropriate.
- During that collection review, notice repeated colors across every wardrobe piece, including basics, layers, and secondary garments. Do not treat a neutral basic as exempt from visual repetition.
- If a recurring color makes the collection feel repetitive and equally authentic alternatives would complement those scenes, revise the appropriate palettes before returning the batch.
- White remains an authentic, available brand element. Do not eliminate it or treat frequent historical use as a negative signal.
- When more than one palette is equally authentic and visually appropriate, prefer the choice that improves variety across the current batch.
- Let Creative Intelligence reinforce successful tendencies without turning them into repetition requirements.
- Infer appropriate palettes through creative-director judgment. Do not use seasonal color lists, fixed season-to-color mappings, lookup tables, random selection, weighted color lists, or explicit probabilities.
- Carry the resulting wardrobe palette naturally into each private creative direction so the existing canonical planner can preserve the editorial choice. Do not expose the internal comparison or reasoning.

WARDROBE SILHOUETTE — EDITORIAL REASONING:
- Internally ask what scene-appropriate styling best expresses Ava's confident, feminine, stylish, figure-flattering public brand while helping the six images feel like a deliberately varied editorial collection.
- Infer styling from the season, setting, activity, mood, Social Creative Direction, and Creative Intelligence rather than from a fixed garment rotation.
- Review the complete batch for repeated necklines, silhouettes, garment structures, layering approaches, and coverage levels. When equally authentic styling alternatives exist, choose the option that prevents the collection from feeling repetitive.
- Avoid drifting toward uniformly conservative commercial fashion. Treat confident figure-flattering styling and scene-appropriate midriff visibility as normal parts of Ava's established public brand, while preserving meaningful variation across the batch.
- Use Ava's canonical wardrobe examples as evidence of brand range, never as a required rotation, slot assignment, or exhaustive list.
- Preserve natural variation without forcing more or less exposure. Coverage should emerge from the scene and established brand, never from a target, percentage, quota, or escalation rule.
- Do not use wardrobe templates, required garment sequences, fixed category mappings, or deterministic outfit formulas.
- Carry the resulting styling direction naturally into each private creative direction without exposing the internal comparison or reasoning.

AUTONOMOUS SWIMWEAR:
- When an autonomously chosen scene naturally calls for swimwear, select a bikini consistent with the scene and Ava's public brand.
- Do not select a one-piece swimsuit, monokini, swim dress, or one-piece athletic swimwear in Autonomous Inspiration.
- This is scoped only to Autonomous Inspiration. Explicit manual wardrobe requests belong to Creative Studio and must remain unchanged.

AVOID:
- books, reading, laptops, paperwork, presentations, email, notebooks, office administration, and generic work tasks
- detached documentary treatment, ordinary daily schedules, scenery-first images, or concepts where the creator is incidental
- six variations of one location, activity, emotional beat, or composition
- invented pets, partners, possessions, properties, or personal facts not supported by the canonical knowledge
- camera specifications, provider syntax, technical prompt language, or reference-image instructions
- prompts, prompt previews, captions, hashtags, or generation syntax from prior work

Each direction must clearly state one compelling scene, what the creator is doing, and the social energy that makes the image worth stopping for.
Do not write captions, post copy, hashtags, explanations, or numbered lists.

{UNSUPPORTED_CREATOR_FACT_GUARD}

{section("PERSONALITY", personality)}

{section("LIFESTYLE", lifestyle)}

{section("SOCIAL CREATIVE DIRECTION — PRIMARY", social_creative_direction)}

{section("WORLD MODEL", world_model)}

CREATIVE INTELLIGENCE — AGGREGATED IMAGE PATTERNS ONLY:
{editorial_memory}

OUTPUT:
Exactly {cls.IMAGE_COUNT} lines, one private creative direction per line.
No numbering, bullets, headings, markdown, or explanation.
""".strip()

    @staticmethod
    def _editorial_memory_guidance(profile: dict) -> str:
        raw_attributes = profile.get("learned_attributes")
        try:
            attributes = dict(raw_attributes or {})
        except (TypeError, ValueError):
            attributes = {}
        analyzed = max(0, int(profile.get("analyzed_image_count") or 0))
        if not analyzed or not any(dict(values or {}) for values in attributes.values()):
            return (
                "No analyzed retained-image patterns are available yet. Use the "
                "canonical creator documents and maximize balanced novelty."
            )

        labels = {
            "environment": "Environment",
            "visual_style": "Visual style",
            "composition": "Composition",
            "pose": "Pose",
            "season": "Season",
            "lighting": "Lighting",
            "wardrobe_category": "Wardrobe category",
        }
        lines = [
            f"Evidence base: {analyzed} analyzed intentionally retained images."
        ]
        for dimension, label in labels.items():
            counts = dict(attributes.get(dimension) or {})
            ranked = sorted(
                (
                    (str(value).strip(), max(0, int(count)))
                    for value, count in counts.items()
                    if str(value).strip()
                ),
                key=lambda item: (-item[1], item[0]),
            )
            if not ranked:
                continue
            anchors = ", ".join(
                f"{value} (evidence {count})" for value, count in ranked[:3]
            )
            minimum = min(count for _, count in ranked)
            opportunities = ", ".join(
                value for value, count in ranked if count == minimum
            )
            lines.append(f"{label} brand anchors: {anchors}.")
            if len(ranked) > 1:
                lines.append(
                    f"{label} observed variety opportunities: {opportunities}."
                )
        lines.append(
            "Counts express observed editorial tendencies only; they are not "
            "instructions to reproduce prior images."
        )
        return "\n".join(lines)

    @staticmethod
    def _season(month: int) -> str:
        if month in {12, 1, 2}:
            return "winter"
        if month in {3, 4, 5}:
            return "spring"
        if month in {6, 7, 8}:
            return "summer"
        return "fall"

    @staticmethod
    def _parse(value: str) -> tuple[str, ...]:
        directions: list[str] = []
        for raw_line in str(value or "").splitlines():
            line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", raw_line).strip()
            if line and line not in directions:
                directions.append(line)
        return tuple(directions)
