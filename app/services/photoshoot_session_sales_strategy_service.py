"""Derive one Photoshoot Session Sales playbook from persisted intelligence only."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Callable

from app.repositories.photoshoot_commerce_repository import PhotoshootCommerceRepository
from app.repositories.photoshoot_session_sales_strategy_repository import (
    PhotoshootSessionSalesStrategyRepository,
)
from app.services.llm_json_parser import parse_llm_json


SESSION_SALES_STRATEGY_VERSION = "photoshoot_session_sales_v1"
SALES_ROLES = {"FREE_TEASER", "FIRST_UNLOCK", "ESCALATION", "PREMIUM", "FINALE"}
ACCESS_RECOMMENDATIONS = {"FREE", "PAID"}


class PhotoshootSessionSalesStrategyService:
    """The sole generator for Photoshoot Session Selling strategy."""

    def __init__(self, *, repository=None, photoshoots=None,
                 strategy_runner: Callable[[dict], dict] | None = None):
        self.repository = repository or PhotoshootSessionSalesStrategyRepository()
        self.photoshoots = photoshoots or PhotoshootCommerceRepository()
        self.strategy_runner = strategy_runner or self._run_strategy

    def generate(self, deliverable_id: str, *, creator_profile_id: int,
                 strategy_version: str = SESSION_SALES_STRATEGY_VERSION):
        deliverable = self.photoshoots.get(str(deliverable_id))
        if deliverable is None or int(deliverable["creator_profile_id"]) != int(creator_profile_id):
            raise KeyError("Completed Photoshoot not found.")
        if deliverable["is_archived"]:
            raise ValueError("Archived Photoshoots cannot generate a Session Sales Strategy.")
        session_id = str(deliverable["photoshoot_session_id"])
        existing = self.repository.get(session_id, strategy_version)
        if existing is not None:
            return existing

        canonical = self.photoshoots.get_intelligence(session_id)
        if not canonical or canonical.get("status") != "READY":
            raise ValueError("Canonical Photoshoot Intelligence must be READY.")
        intelligence_version = str(canonical.get("intelligence_version") or "")
        production = dict(canonical.get("production_analysis") or {})
        cross_validation = dict(canonical.get("cross_validation") or {})
        shots = tuple(self.photoshoots.shot_intelligence(session_id, intelligence_version))
        members = tuple(self.photoshoots.members(session_id))
        if not production or not shots or len(shots) != len(members):
            raise ValueError("Complete persisted Production and Shot Intelligence is required.")

        shots_by_asset = {int(row["asset_id"]): dict(row.get("profile_data") or {}) for row in shots}
        ordered_shots = tuple({
            "asset_id": int(member["asset_id"]),
            "shot_order": int(member["shot_order"]),
            "shot_intelligence": shots_by_asset.get(int(member["asset_id"]), {}),
        } for member in members)
        if any(not item["shot_intelligence"] for item in ordered_shots):
            raise ValueError("Every approved shot requires persisted Shot Intelligence.")

        source = {
            "photoshoot_session_id": session_id,
            "intelligence_version": intelligence_version,
            "production_intelligence": production,
            "cross_validation": cross_validation,
            "ordered_shots": ordered_shots,
        }
        result = dict(self.strategy_runner(source) or {})
        normalized = self._validate(result, ordered_shots)
        generated_at = datetime.now(timezone.utc)
        model = os.getenv(
            "SESSION_SALES_STRATEGY_MODEL",
            os.getenv("GROK_MODEL", "grok-4-1-fast-non-reasoning"),
        )
        normalized["metadata"] = {
            "purpose": "PHOTOSHOOT_SESSION_SELLING",
            "source_intelligence_version": intelligence_version,
        }
        return self.repository.save(
            photoshoot_session_id=session_id,
            deliverable_id=deliverable["deliverable_id"],
            creator_profile_id=creator_profile_id,
            strategy_version=strategy_version,
            intelligence_version=intelligence_version,
            strategy_data=normalized,
            model=model,
            generated_at=generated_at,
        )

    def latest(self, photoshoot_session_id: str):
        return self.repository.latest(photoshoot_session_id)

    @classmethod
    def _validate(cls, result: dict, ordered_shots: tuple[dict, ...]) -> dict:
        required = (
            "best_teaser_asset_id", "recommended_customer_entry_point",
            "suggested_sales_progression", "recommended_stopping_points",
            "session_completion_strategy", "customer_engagement_strategy",
            "escalation_pacing", "overall_selling_approach", "shots",
        )
        missing = [key for key in required if result.get(key) in (None, "", [], {})]
        if missing:
            raise ValueError(f"Session Sales Strategy omitted required fields: {', '.join(missing)}")
        canonical_ids = tuple(int(item["asset_id"]) for item in ordered_shots)
        valid_ids = set(canonical_ids)
        progression = tuple(int(value) for value in result["suggested_sales_progression"])
        if len(progression) != len(canonical_ids) or set(progression) != valid_ids:
            raise ValueError("Suggested sales progression must contain every approved Asset exactly once.")
        if int(result["best_teaser_asset_id"]) not in valid_ids:
            raise ValueError("Best teaser must reference an approved Asset.")
        stopping_points = tuple(dict(item) for item in result["recommended_stopping_points"])
        if any(
            item.get("after_asset_id") is not None
            and int(item["after_asset_id"]) not in valid_ids
            for item in stopping_points
        ):
            raise ValueError("Stopping points must reference approved Assets.")
        recommendations = tuple(dict(item) for item in result["shots"])
        if len(recommendations) != len(canonical_ids):
            raise ValueError("Every approved shot requires one sales recommendation.")
        by_id = {int(item.get("asset_id", 0)): item for item in recommendations}
        if set(by_id) != valid_ids or len(by_id) != len(recommendations):
            raise ValueError("Shot recommendations must map uniquely to approved Assets.")
        positions = {int(item.get("sales_position", 0)) for item in recommendations}
        if positions != set(range(1, len(canonical_ids) + 1)):
            raise ValueError("Sales positions must be contiguous and unique.")
        canonical_orders = {int(item["asset_id"]): int(item["shot_order"]) for item in ordered_shots}
        shot_required = (
            "sales_role", "teaser_recommended", "access_recommendation",
            "recommended_progression", "customer_journey_purpose", "escalation_role",
            "psychological_objective", "conversation_goal",
        )
        normalized_shots = []
        for asset_id in canonical_ids:
            item = by_id[asset_id]
            absent = [key for key in shot_required if item.get(key) is None or item.get(key) == ""]
            if absent:
                raise ValueError(f"Asset {asset_id} omitted: {', '.join(absent)}")
            role = str(item["sales_role"]).upper().replace(" ", "_")
            access = str(item["access_recommendation"]).upper()
            if role not in SALES_ROLES or access not in ACCESS_RECOMMENDATIONS:
                raise ValueError(f"Asset {asset_id} has an unsupported sales role or access recommendation.")
            if not isinstance(item["teaser_recommended"], bool):
                raise ValueError(f"Asset {asset_id} teaser recommendation must be boolean.")
            next_id = item.get("suggested_next_asset_id")
            if next_id is not None and int(next_id) not in valid_ids:
                raise ValueError(f"Asset {asset_id} suggests an unknown next shot.")
            normalized_shots.append({
                **item, "asset_id": asset_id, "shot_order": canonical_orders[asset_id],
                "sales_position": int(item["sales_position"]), "sales_role": role,
                "teaser_recommended": bool(item["teaser_recommended"]),
                "access_recommendation": access,
                "suggested_next_asset_id": int(next_id) if next_id is not None else None,
            })
        return {
            **{key: result[key] for key in required if key != "shots"},
            "best_teaser_asset_id": int(result["best_teaser_asset_id"]),
            "suggested_sales_progression": progression,
            "recommended_stopping_points": stopping_points,
            "shots": tuple(normalized_shots),
        }

    @classmethod
    def _run_strategy(cls, source: dict) -> dict:
        from openai import OpenAI
        api_key = os.getenv("GROK_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("GROK_API_KEY is not configured for Session Sales Strategy.")
        prompt = (
            "You are generating a Photoshoot Session Sales Strategy, not creative analysis and not catalog copy. "
            "Use only the persisted Production Intelligence, Shot Intelligence, cross-validation, and canonical "
            "shot order supplied below. Do not assume Shot 1 is free. Recommend the most effective guided customer "
            "sequence based on the actual progression. Do not produce prices, channels, Products, Offers, Bundles, "
            "or Publications. Return JSON only with: best_teaser_asset_id; recommended_customer_entry_point; "
            "suggested_sales_progression (every asset ID exactly once); recommended_stopping_points (array of "
            "structured checkpoints); session_completion_strategy; customer_engagement_strategy; escalation_pacing; "
            "overall_selling_approach; and shots. Each shots item must contain asset_id, sales_position, sales_role "
            "(FREE_TEASER, FIRST_UNLOCK, ESCALATION, PREMIUM, or FINALE), teaser_recommended boolean, "
            "access_recommendation (FREE or PAID), recommended_progression, suggested_next_asset_id or null, "
            "customer_journey_purpose, escalation_role, psychological_objective, and conversation_goal. "
            "These are editable recommendations for the Session Sales Brain. Persisted input: "
            + json.dumps(source, default=str)
        )
        model = os.getenv(
            "SESSION_SALES_STRATEGY_MODEL",
            os.getenv("GROK_MODEL", "grok-4-1-fast-non-reasoning"),
        )
        response = OpenAI(
            api_key=api_key,
            base_url=os.getenv("GROK_BASE_URL", "https://api.x.ai/v1"),
        ).responses.create(
            model=model,
            input=[{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
            temperature=0.2,
        )
        return parse_llm_json(
            response.output_text, model_name=model,
            caller="PhotoshootSessionSalesStrategyService",
        )
