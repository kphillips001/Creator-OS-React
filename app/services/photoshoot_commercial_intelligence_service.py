"""One canonical, staged understanding of a completed ordered Photoshoot."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from app.services.llm_json_parser import parse_llm_json


PHOTOSHOOT_INTELLIGENCE_VERSION = "completed_photoshoot_v2"


class PhotoshootIntelligenceStageError(RuntimeError):
    def __init__(self, stage: str, cause: Exception, *, asset_id: int | None = None):
        self.stage, self.cause, self.asset_id = stage, cause, asset_id
        suffix = f" for Asset {asset_id}" if asset_id is not None else ""
        super().__init__(f"{stage}{suffix}: {cause}")


class PhotoshootCommercialIntelligenceService:
    """Runs production, sequential shot, and cross-validation analysis once."""

    def __init__(self, *, production_runner: Callable | None = None,
                 shot_runner: Callable | None = None, cross_runner: Callable | None = None):
        self.production_runner = production_runner or self._run_production
        self.shot_runner = shot_runner or self._run_shot
        self.cross_runner = cross_runner or self._run_cross_validation

    def generate(self, *, chapters: Sequence[Mapping[str, Any]], approved_metadata: Mapping[str, Any],
                 intelligence_version: str = PHOTOSHOOT_INTELLIGENCE_VERSION,
                 progress: Callable[[str, Mapping[str, Any]], None] | None = None) -> dict:
        ordered = tuple(sorted((self._meaningful(dict(item)) for item in chapters),
                               key=lambda item: int(item["shot_order"])))
        if not ordered or [int(item["shot_order"]) for item in ordered] != list(range(1, len(ordered) + 1)):
            raise ValueError("Canonical approved shots must have contiguous ordering beginning at one.")
        source = {"approved_metadata": self._meaningful(dict(approved_metadata or {})),
                  "ordered_chapters": ordered, "intelligence_version": intelligence_version}
        if not self._has_evidence(source):
            raise ValueError("Photoshoot Intelligence requires non-empty approved evidence.")
        try:
            production = self._required_mapping(self.production_runner(source), "production analysis")
            if progress: progress("SHOT_ANALYSIS", {"completed_shots": 0, "total_shots": len(ordered)})
        except Exception as error:
            raise PhotoshootIntelligenceStageError("PRODUCTION_ANALYSIS_FAILED", error) from error
        shots = []
        for index, chapter in enumerate(ordered):  # deliberately bounded and sequential; supports 100 shots
            context = {"previous": ordered[index - 1] if index else None,
                       "next": ordered[index + 1] if index + 1 < len(ordered) else None}
            try:
                result = self._required_mapping(self.shot_runner(chapter, production, context), "shot analysis")
            except Exception as error:
                raise PhotoshootIntelligenceStageError(
                    "SHOT_ANALYSIS_FAILED", error, asset_id=int(chapter["asset_id"])) from error
            shots.append({"asset_id": int(chapter["asset_id"]),
                          "shot_order": int(chapter["shot_order"]), **result})
            if progress: progress("SHOT_ANALYSIS", {"completed_shots": len(shots), "total_shots": len(ordered)})
        try:
            if progress: progress("CROSS_VALIDATION", {"completed_shots": len(shots), "total_shots": len(ordered)})
            cross = self._required_mapping(self.cross_runner(production, tuple(shots)), "cross-validation")
        except Exception as error:
            raise PhotoshootIntelligenceStageError("CROSS_VALIDATION_FAILED", error) from error
        roles = dict(cross.get("sequence_roles_by_asset") or {})
        selected = {name: cross.get(f"{name}_asset_id") for name in
                    ("hero", "cover", "thumbnail", "teaser", "opening", "closing")}
        finalized_shots = tuple({**shot,
            "sequence_role": roles.get(str(shot["asset_id"]), roles.get(shot["asset_id"], shot.get("sequence_role"))),
            "relative_rankings": {name: int(asset_id) == int(shot["asset_id"])
                                  for name, asset_id in selected.items() if asset_id is not None},
        } for shot in shots)
        completed = datetime.now(timezone.utc).isoformat()
        return {**production, "production_analysis": production,
                "shot_intelligence": finalized_shots, "cross_validation": cross,
                "input_snapshot": source, "intelligence_version": intelligence_version,
                "model": os.getenv("GROK_MODEL", "grok-4-1-fast-non-reasoning"),
                "generated_at": completed}

    @staticmethod
    def _required_mapping(value, label):
        result = dict(value or {})
        if not result:
            raise ValueError(f"AI returned empty {label}.")
        return result

    @classmethod
    def _has_evidence(cls, value):
        if isinstance(value, Mapping):
            return any(cls._has_evidence(item) for key, item in value.items()
                       if key not in {"shot_order", "asset_id", "is_hero", "intelligence_version", "image_reference"})
        if isinstance(value, (list, tuple)): return any(cls._has_evidence(item) for item in value)
        return bool(str(value or "").strip())

    @classmethod
    def _meaningful(cls, value):
        if isinstance(value, Mapping):
            return {str(key): cls._meaningful(item) for key, item in value.items()
                    if item not in (None, "", (), [], {})}
        if isinstance(value, (list, tuple)):
            return tuple(cls._meaningful(item) for item in value if item not in (None, "", (), [], {}))
        return value

    @classmethod
    def _client_response(cls, prompt: str, image_reference: str | None = None):
        from openai import OpenAI
        api_key = os.getenv("GROK_API_KEY", "").strip()
        if not api_key: raise RuntimeError("GROK_API_KEY is not configured for Photoshoot Intelligence.")
        content = [{"type": "input_text", "text": prompt}]
        if image_reference:
            path = Path(image_reference)
            if not path.is_file(): raise FileNotFoundError(path)
            mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            content.append({"type": "input_image", "image_url": f"data:{mime};base64,{encoded}"})
        model = os.getenv("GROK_MODEL", "grok-4-1-fast-non-reasoning")
        response = OpenAI(api_key=api_key, base_url=os.getenv("GROK_BASE_URL", "https://api.x.ai/v1")).responses.create(
            model=model, input=[{"role": "user", "content": content}], temperature=0.2)
        return parse_llm_json(response.output_text, model_name=model,
                              caller="PhotoshootCommercialIntelligenceService")

    @classmethod
    def _run_production(cls, source):
        prompt = ("Analyze this complete ordered approved Photoshoot as one production. Establish factual story, "
                  "theme, experience, emotional_journey, overall_progression, setting_environment, "
                  "wardrobe_progression, content_escalation, and production_summary. Preserve supported legacy "
                  "commercial_title, subtitle, commercial_summary, buyer_profile, sales_strategy, and "
                  "sales_brain_brief for existing consumers, but prioritize factual production understanding. "
                  "Return JSON only. Input: " + json.dumps(source, default=str))
        return cls._client_response(prompt)

    @classmethod
    def _run_shot(cls, chapter, production, neighbors):
        prompt = ("Analyze this individual approved image in the supplied complete-Photoshoot context. Return JSON "
                  "only with sequence_role, scene_environment, pose_action, camera_framing_angle, facial_expression, "
                  "eye_contact, wardrobe_state, nudity_explicitness, emotional_tone, visual_focus, "
                  "continuity_observations, quality_observations, suggested_content_uses, hero_suitability, "
                  "cover_suitability, thumbnail_suitability, and teaser_suitability. Structured values are required. "
                  f"Shot: {json.dumps({k:v for k,v in chapter.items() if k != 'image_reference'}, default=str)}\n"
                  f"Production: {json.dumps(production, default=str)}\nNeighbors: {json.dumps(neighbors, default=str)}")
        return cls._client_response(prompt, str(chapter.get("image_reference") or ""))

    @classmethod
    def _run_cross_validation(cls, production, shots):
        prompt = ("Cross-validate these ordered shot analyses. Return JSON only with hero_asset_id, cover_asset_id, "
                  "thumbnail_asset_id, teaser_asset_id, opening_asset_id, closing_asset_id, sequence_roles_by_asset, "
                  "escalation_order_asset_ids, continuity_consistency, duplicate_asset_groups, and final_production_summary. "
                  f"Production: {json.dumps(production, default=str)}\nShots: {json.dumps(shots, default=str)}")
        return cls._client_response(prompt)
