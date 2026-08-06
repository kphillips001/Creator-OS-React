"""Prompt-safe projection of canonical Photoshoot Session selling state."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from app.repositories.photoshoot_commerce_repository import PhotoshootCommerceRepository
from app.repositories.photoshoot_session_sales_strategy_repository import (
    PhotoshootSessionSalesStrategyRepository,
)


ROLE_OBJECTIVES = {
    "FREE_TEASER": {
        "message_objective": "Introduce the Photoshoot and create curiosity with the current free teaser.",
        "reveal_boundary": "Reveal only enough about the current teaser to create interest.",
        "hidden_progression": "Do not describe later shots or spoil how the Photoshoot escalates.",
        "transition_intent": "End with natural anticipation for the first paid unlock without prematurely presenting it.",
    },
    "FIRST_UNLOCK": {
        "message_objective": "Frame why the first paid unlock matters, what emotional transition it represents, and why that current step is worth purchasing.",
        "reveal_boundary": "Describe the value and emotional change of the current unlock without revealing later shots.",
        "hidden_progression": "Keep later escalation, premium material, and the finale undisclosed.",
        "transition_intent": "Connect the teaser to this deeper first unlock and leave room for the next progression step.",
    },
    "ESCALATION": {
        "message_objective": "Deepen desire through the current escalation step while preserving deliberate pacing.",
        "reveal_boundary": "Frame only the current increase in intensity and experience.",
        "hidden_progression": "Do not reveal premium or finale content and do not compress future progression into this turn.",
        "transition_intent": "Make the current step feel consequential while naturally sustaining interest in what follows.",
    },
    "PREMIUM": {
        "message_objective": "Frame the current premium step as a high-value continuation of the earned progression.",
        "reveal_boundary": "Communicate the current premium value without describing the finale or future unrevealed details.",
        "hidden_progression": "Preserve the finale and any remaining progression as undisclosed.",
        "transition_intent": "Maintain exclusivity and anticipation while preparing a natural path toward completion.",
    },
    "FINALE": {
        "message_objective": "Frame the current finale as the culmination of the completed session progression.",
        "reveal_boundary": "Focus on the value of completing the experience without inventing content beyond the Photoshoot.",
        "hidden_progression": "Do not promise additional unrevealed Photoshoot steps after the finale.",
        "transition_intent": "Bring the guided session to a satisfying close according to the completion strategy.",
    },
}


class PhotoshootSessionConversationContextBuilder:
    """Read persisted intelligence and render one non-decision-making prompt block."""

    SCHEMA_VERSION = "photoshoot_session_conversation_v1"

    def __init__(self, *, strategies=None, photoshoots=None):
        self.strategies = strategies or PhotoshootSessionSalesStrategyRepository()
        self.photoshoots = photoshoots or PhotoshootCommerceRepository()

    def build(self, decision: Any) -> dict[str, Any] | None:
        action = getattr(decision, "next_sales_action", None)
        if action is None:
            return None
        runtime = dict((getattr(action, "metadata", {}) or {}).get("sessionRuntime") or {})
        session_id = str(runtime.get("photoshootSessionId") or action.current_photoshoot_id or "").strip()
        if not runtime or not session_id:
            return None

        intelligence = self._safe_call(self.photoshoots.get_intelligence, session_id) or {}
        deliverable = self._safe_call(self.photoshoots.get_by_session, session_id) or {}
        profile = dict(intelligence.get("profile_data") or {})
        production = dict(intelligence.get("production_analysis") or profile.get("production_analysis") or profile)
        strategy = self._safe_call(self.strategies.latest, session_id)
        shots = tuple(getattr(strategy, "shots", ()) or ())
        current_asset_id = self._integer(runtime.get("currentAssetId"))
        next_asset_id = self._integer(runtime.get("nextAssetId"))
        current_strategy = next((shot for shot in shots if shot.asset_id == current_asset_id), None)
        next_strategy = next((shot for shot in shots if shot.asset_id == next_asset_id), None)
        shot_rows = self._safe_call(self.photoshoots.latest_shot_intelligence, session_id) or ()
        current_shot = next(
            (dict(row.get("profile_data") or {}) for row in shot_rows
             if self._integer(row.get("asset_id")) == current_asset_id),
            {},
        )

        role = str(runtime.get("currentSalesRole") or getattr(current_strategy, "sales_role", "") or "").upper()
        role_objectives = dict(ROLE_OBJECTIVES.get(role) or {
            "message_objective": "Execute only the current deterministic Photoshoot strategy step.",
            "reveal_boundary": "Discuss only the current step using the supplied persisted context.",
            "hidden_progression": "Do not reveal future shots or invent additional progression.",
            "transition_intent": "Transition only toward the supplied next role without selecting or revealing another Asset.",
        })
        title = self._first_text(
            deliverable.get("display_name"), intelligence.get("commercial_title"),
            profile.get("commercial_title"), production.get("commercial_title"), "Photoshoot",
        )
        theme = self._first_text(intelligence.get("theme"), profile.get("theme"), production.get("theme"))
        story = self._first_text(
            intelligence.get("story"), profile.get("story"), production.get("story"),
            production.get("production_summary"), production.get("commercial_summary"),
        )
        current_purpose = self._first_text(
            getattr(current_strategy, "customer_journey_purpose", None),
            current_shot.get("sequence_role"),
        )
        context = {
            "schemaVersion": self.SCHEMA_VERSION,
            "authority": {
                "decisionOwner": "PhotoshootSessionRuntimeService",
                "languageOwner": "GPTService",
                "rules": [
                    "Execute the supplied current step; never choose a different Asset, price, position, or sales order.",
                    "Do not claim that a recommendation, draft, purchase, ownership, or delivery occurred unless supplied canonical state confirms it.",
                ],
            },
            "currentSession": {
                "photoshootSessionId": session_id,
                "title": title,
                "theme": theme,
                "storySummary": story,
                "currentPosition": runtime.get("currentPosition"),
                "totalPositions": runtime.get("totalPositions"),
            },
            "currentStep": {
                "assetId": current_asset_id,
                "salesRole": role or None,
                "accessRecommendation": getattr(current_strategy, "access_recommendation", None),
                "shotSummary": self._shot_summary(current_shot),
                "purpose": current_purpose,
                "recommendedProgression": getattr(current_strategy, "recommended_progression", None),
            },
            "customer": {
                "ownedAssetIds": list(runtime.get("ownedAssetIds") or ()),
                "currentProgression": f"{runtime.get('currentPosition') or 0} of {runtime.get('totalPositions') or 0}",
                "currentLifecycleStage": (
                    (runtime.get("metadata") or {}).get("lifecycleStatus")
                    or runtime.get("sessionStatus")
                ),
            },
            "conversation": {
                "conversationGoal": runtime.get("conversationGoal"),
                "psychologicalObjective": runtime.get("psychologicalObjective"),
                "engagementStrategy": runtime.get("customerEngagementStrategy"),
                "escalationPacing": runtime.get("escalationPacing"),
                "sessionCompletionStrategy": runtime.get("sessionCompletionStrategy"),
            },
            "boundaries": role_objectives,
            "nextStep": {
                "salesRole": runtime.get("nextSalesRole"),
                "recommendation": getattr(next_strategy, "recommended_progression", None),
                "transitionIntent": role_objectives["transition_intent"],
                "instruction": "Use this only to shape the transition. Do not reveal its Asset, content details, or present it early.",
            },
        }
        context["promptBlock"] = self.render_prompt_block(context)
        return context

    @staticmethod
    def render_prompt_block(context: Mapping[str, Any]) -> str:
        safe = {key: value for key, value in context.items() if key != "promptBlock"}
        return (
            "SESSION CONVERSATION CONTEXT\n"
            "The following structured context is authoritative for language execution only. "
            "Do not make progression, Asset, pricing, ownership, or delivery decisions.\n"
            + json.dumps(safe, indent=2, ensure_ascii=False, default=str)
        )

    @staticmethod
    def _shot_summary(profile: Mapping[str, Any]) -> dict[str, Any]:
        keys = (
            "sequence_role", "scene_environment", "pose_action", "camera_framing_angle",
            "facial_expression", "eye_contact", "wardrobe_state", "nudity_explicitness",
            "emotional_tone", "visual_focus", "continuity_observations",
        )
        return {key: profile[key] for key in keys if profile.get(key) not in (None, "", [], {})}

    @staticmethod
    def _safe_call(function, *arguments):
        try:
            return function(*arguments)
        except Exception:
            return None

    @staticmethod
    def _integer(value):
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _first_text(*values):
        return next((str(value).strip() for value in values if value is not None and str(value).strip()), None)
