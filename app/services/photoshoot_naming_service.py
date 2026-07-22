"""AI naming from normalized Photoshoot Intelligence; never re-analyzes media."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Callable, Mapping

from app.services.llm_json_parser import parse_llm_json


class PhotoshootNamingService:
    FORBIDDEN = re.compile(r"\b(photoshoot|session|studio)\b", re.IGNORECASE)
    LEGACY_TERMS = re.compile(
        r"\b(tease|teasing|explicit|spicy|premium|sexy|nsfw|seductive|suggestive|provocative)\b",
        re.IGNORECASE,
    )

    def __init__(self, runner: Callable[[Mapping[str, Any], int], Mapping[str, Any]] | None = None):
        self.runner = runner or self._run_grok

    def generate(self, intelligence: Mapping[str, Any], shot_count: int) -> tuple[str, str]:
        payload = dict(self.runner(dict(intelligence or {}), int(shot_count)) or {})
        title = " ".join(str(payload.get("title") or "").split()).strip(" .,:;_-\"")
        description = " ".join(str(payload.get("description") or "").split()).strip()
        words = re.findall(r"[A-Za-z0-9&'-]+", title)
        if not 2 <= len(words) <= 5 or self.FORBIDDEN.search(title) or self.LEGACY_TERMS.search(title):
            raise ValueError("AI title must contain 2-5 words and no internal or legacy classification terms.")
        if re.search(r"\d{4}|[_/\\]|\b(id|file|image_?\d+)\b", title, re.IGNORECASE):
            raise ValueError("AI title contains an identifier, filename, or timestamp.")
        if not description or len(re.findall(r"[.!?]", description)) > 2:
            raise ValueError("AI description must contain one or two concise sentences.")
        if self.LEGACY_TERMS.search(description):
            raise ValueError("AI description contains legacy classification terminology.")
        return title, description

    @classmethod
    def needs_refinement(cls, title: str | None, description: str | None) -> bool:
        """Select only missing or legacy-tainted AI copy for idempotent backfill."""
        return not title or not description or bool(cls.LEGACY_TERMS.search(f"{title} {description}"))

    @staticmethod
    def _run_grok(intelligence: Mapping[str, Any], shot_count: int) -> Mapping[str, Any]:
        from openai import OpenAI

        api_key = os.getenv("GROK_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("GROK_API_KEY is not configured for Photoshoot naming.")
        source = {key: intelligence.get(key) for key in (
            "overall_summary", "mood", "theme", "setting", "wardrobe_continuity",
            "lighting_continuity", "lifestyle", "visual_progression", "decision_engine_summary",
        ) if intelligence.get(key) not in (None, "", [], (), {})}
        prompt = (
            "Create tasteful editorial naming for this completed multi-image collection using only its normalized "
            "aggregate intelligence. Return JSON only with title and description. The title must be 2-5 natural, "
            "human-readable words and sound like a curated photo collection. Reflect the setting, mood, lighting, "
            "season, wardrobe, or atmosphere. Styles to prefer include Summer Glow, Golden Meadow, Coastal Escape, "
            "Sunlit Serenity, Blue Horizon, Wildflower Afternoon, Morning Light, and Meadow Moments. Never include "
            "creator names, IDs, filenames, dates, timestamps, Photoshoot, Session, or Studio. Never use tease, "
            "teasing, explicit, spicy, premium, sexy, NSFW, seductive, suggestive, or provocative. The description "
            "must describe the complete set in one concise sentence (two maximum), using tasteful lifestyle or "
            "editorial wording. Mention useful visual details such as setting, lighting, wardrobe, mood, and shot "
            "count when appropriate. Avoid moderation terminology, commercial classifications, marketing hype, and "
            "internal analysis.\n"
            f"Shot count: {shot_count}\nAggregate intelligence: {json.dumps(source, default=str)}"
        )
        client = OpenAI(api_key=api_key, base_url=os.getenv("GROK_BASE_URL", "https://api.x.ai/v1"))
        response = client.responses.create(
            model=os.getenv("GROK_MODEL", "grok-4-1-fast-non-reasoning"),
            input=prompt,
            temperature=0.4,
        )
        return parse_llm_json(
            response.output_text,
            model_name=os.getenv("GROK_MODEL", "grok-4-1-fast-non-reasoning"),
            caller="PhotoshootNamingService",
        )
