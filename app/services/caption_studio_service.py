"""Provider-neutral Caption Studio service."""

from __future__ import annotations

import json
import base64
import os
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlparse

import requests

from app.config import GROK_VISION_MODEL
from app.models.caption_studio import (
    CaptionHistory,
    CaptionPlatform,
    CaptionRequest,
    CaptionResult,
    CaptionSession,
    CaptionStyle,
    CaptionTemplate,
)
from app.models.generation_engine import new_generation_id, utc_now
from app.services.caption_prompt_guidance import NATURAL_EMOJI_INSTRUCTION
from app.services.generation_library_service import GenerationLibraryService
from app.services.llm_json_parser import parse_llm_json
from app.services.social_publishing_service import SocialPublishingService


class CaptionStudioService:
    """Owns provider-neutral writing workflow and text history."""

    DEFAULT_STORAGE_DIR = Path("data") / "caption_studio"
    X_CAPTION_COUNT = 10

    def __init__(
        self,
        *,
        storage_dir: str | Path | None = None,
        grok_vision_provider: Callable[..., Mapping[str, Any]] | None = None,
        http_client=None,
    ):
        self.storage_dir = Path(storage_dir or self.DEFAULT_STORAGE_DIR)
        self.grok_vision_provider = grok_vision_provider
        self.http_client = http_client or requests

    @property
    def sessions_path(self) -> Path:
        return self.storage_dir / "caption_sessions.json"

    @property
    def caption_items_path(self) -> Path:
        return self.storage_dir / "caption_items.json"

    @property
    def results_path(self) -> Path:
        return self.storage_dir / "caption_results.json"

    @property
    def history_path(self) -> Path:
        return self.storage_dir / "caption_history.json"

    @property
    def templates_path(self) -> Path:
        return self.storage_dir / "caption_templates.json"

    def create_session(
        self,
        *,
        creator_profile_id: int,
        platform: str,
        style: str,
        tone: str,
        source_generated_image_id: str | None = None,
        social_queue_item_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> CaptionSession:
        session = CaptionSession(
            session_id=new_generation_id("caption_session"),
            creator_profile_id=int(creator_profile_id),
            platform=self.normalize_platform(platform),
            style=self.normalize_style(style),
            tone=str(tone or "confident"),
            source_generated_image_id=source_generated_image_id,
            social_queue_item_id=social_queue_item_id,
            metadata=dict(metadata or {}),
        )
        sessions = list(self.list_sessions())
        sessions.insert(0, session)
        self._write_sessions(sessions)
        return session

    def create_caption_request(
        self,
        *,
        creator_profile_id: int,
        platform: str,
        style: str,
        tone: str,
        source_text: str,
        variation_count: int = 3,
        source_generated_image_id: str | None = None,
        social_queue_item_id: str | None = None,
        template_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> CaptionRequest:
        session = self.create_session(
            creator_profile_id=creator_profile_id,
            platform=platform,
            style=style,
            tone=tone,
            source_generated_image_id=source_generated_image_id,
            social_queue_item_id=social_queue_item_id,
            metadata=metadata,
        )
        item = CaptionRequest(
            caption_request_id=new_generation_id("caption_request"),
            session_id=session.session_id,
            creator_profile_id=int(creator_profile_id),
            platform=session.platform,
            style=session.style,
            tone=session.tone,
            source_text=str(source_text or "").strip(),
            variation_count=max(1, min(int(variation_count or 1), 12)),
            source_generated_image_id=source_generated_image_id,
            social_queue_item_id=social_queue_item_id,
            template_id=template_id,
            metadata=dict(metadata or {}),
        )
        if not item.source_text:
            raise ValueError("Source text is required.")
        items = list(self.list_caption_requests())
        items.insert(0, item)
        self._write_caption_items(items)
        return item

    def generate_caption(
        self,
        caption_request: CaptionRequest,
        *,
        select_first: bool = True,
    ) -> CaptionResult:
        variations = tuple(
            self._format_caption(
                platform=caption_request.platform,
                style=caption_request.style,
                tone=caption_request.tone,
                source_text=caption_request.source_text,
                index=index,
                template=self.get_template(caption_request.template_id) if caption_request.template_id else None,
            )
            for index in range(1, caption_request.variation_count + 1)
        )
        result = CaptionResult(
            caption_result_id=new_generation_id("caption_result"),
            caption_request_id=caption_request.caption_request_id,
            session_id=caption_request.session_id,
            platform=caption_request.platform,
            variations=variations,
            selected_text=variations[0] if select_first and variations else None,
            formatter_metadata={
                "provider_neutral": True,
                "formatter": "CaptionStudioService",
                "style": caption_request.style,
                "tone": caption_request.tone,
            },
        )
        results = list(self.list_results())
        results.insert(0, result)
        self._write_results(results)
        self._append_history(caption_request, result)
        return result

    def regenerate_caption(self, caption_result_id: str) -> CaptionResult:
        result = self.get_result(caption_result_id)
        request = self.get_caption_request(result.caption_request_id)
        return self.generate_caption(request)

    def select_caption(
        self,
        caption_result_id: str,
        *,
        selected_text: str | None = None,
        variation_index: int | None = None,
    ) -> CaptionResult:
        result = self.get_result(caption_result_id)
        if selected_text is None and variation_index is not None:
            index = max(1, int(variation_index)) - 1
            try:
                selected_text = result.variations[index]
            except IndexError as exc:
                raise ValueError("Caption variation index is out of range.") from exc
        selected_text = str(selected_text or "").strip()
        if not selected_text:
            raise ValueError("Selected caption text is required.")
        updated = replace(result, selected_text=selected_text)
        results = [
            updated if candidate.caption_result_id == result.caption_result_id else candidate
            for candidate in self.list_results()
        ]
        self._write_results(results)
        request = self.get_caption_request(result.caption_request_id)
        self._append_history(request, updated)
        return updated

    def generate_from_generation_library(
        self,
        *,
        generated_image_id: str,
        generation_library: GenerationLibraryService,
        platform: str,
        style: str,
        tone: str,
        variation_count: int = 3,
    ) -> CaptionResult:
        record = generation_library.get(generated_image_id)
        source_text = " | ".join(
            value
            for value in (
                record.prompt_text,
                record.creative_mode or "",
                ", ".join(record.prompt_metadata.get("creative_tags") or ()),
            )
            if value
        )
        item = self.create_caption_request(
            creator_profile_id=record.creator_profile_id,
            platform=platform,
            style=style,
            tone=tone,
            source_text=source_text or "Grok Vision X caption set",
            variation_count=variation_count,
            source_generated_image_id=record.image_id,
            metadata={
                "generation_job_id": record.generation_job_id,
                "reference_asset_id": record.reference_asset_id,
                "generation_provider": record.provider_id,
            },
        )
        return self.generate_caption(item)

    def generate_for_social_queue(
        self,
        *,
        queue_item_id: str,
        social_publishing: SocialPublishingService,
        platform: str | None = None,
        style: str = CaptionStyle.SOCIAL_SAFE.value,
        tone: str = "confident",
        variation_count: int = 3,
    ) -> CaptionResult:
        queue_item = social_publishing.get_queue_item(queue_item_id)
        item = self.create_caption_request(
            creator_profile_id=queue_item.creator_profile_id,
            platform=platform or queue_item.platform,
            style=style,
            tone=tone,
            source_text=queue_item.prompt_text or queue_item.generated_image_id,
            variation_count=variation_count,
            source_generated_image_id=queue_item.generated_image_id,
            social_queue_item_id=queue_item.queue_item_id,
            metadata={
                "reference_asset_id": queue_item.reference_asset_id,
                "creative_mode": queue_item.creative_mode,
            },
        )
        result = self.generate_caption(item)
        social_publishing.assign_caption(queue_item.queue_item_id, caption_id=result.caption_result_id)
        return result

    def generate_x_engagement_themes(
        self,
        *,
        generated_image_id: str,
        image_reference: str,
        creator_profile_id: int,
        creator_profile: Mapping[str, Any] | None = None,
        creative_mode: str | None = None,
        prompt_text: str | None = None,
        prompt_metadata: Mapping[str, Any] | None = None,
        generation_metadata: Mapping[str, Any] | None = None,
        theme_count: int = 1,
        captions_per_theme: int = X_CAPTION_COUNT,
        idea_seed: int = 0,
    ) -> CaptionResult:
        """Create Grok Vision-powered X engagement captions for a generated image."""

        grok_response = self._generate_grok_vision_x_captions(
            image_reference=image_reference,
            creator_profile=creator_profile,
            creative_mode=creative_mode,
            prompt_text=prompt_text,
            prompt_metadata=prompt_metadata,
            generation_metadata=generation_metadata,
            idea_seed=idea_seed,
        )
        vision = dict(grok_response.get("image_analysis") or {})
        themes = (
            {
                "theme": "Creator OS Engagement",
                "persona": "creator_os_engagement",
                "captions": tuple(grok_response["captions"]),
            },
        )
        variations = tuple(
            caption
            for theme in themes
            for caption in tuple(theme.get("captions") or ())
        )
        creator_name = str((creator_profile or {}).get("name") or (creator_profile or {}).get("display_name") or "")
        source_text = " | ".join(
            value
            for value in (
                str(vision.get("summary") or ""),
                creator_name,
                str(creative_mode or ""),
                str(prompt_text or ""),
            )
            if value
        )
        item = self.create_caption_request(
            creator_profile_id=creator_profile_id,
            platform=CaptionPlatform.X.value,
            style=CaptionStyle.PLAYFUL.value,
            tone="creator os x engagement",
            source_text=source_text or "Grok Vision X caption set",
            variation_count=len(variations),
            source_generated_image_id=generated_image_id,
            metadata={
                "workflow": "x_engagement_publish",
                "vision_primary": True,
                "vision_provider": "grok",
                "context_priority": (
                    "grok_vision_image_analysis",
                    "creator_profile",
                    "creative_mode",
                    "prompt_context",
                ),
                "image_reference": image_reference,
                "creative_mode": creative_mode,
                "prompt_metadata": dict(prompt_metadata or {}),
                "generation_metadata": dict(generation_metadata or {}),
                "theme_count": 1,
                "captions_per_theme": self.X_CAPTION_COUNT,
                "idea_seed": idea_seed,
            },
        )
        result = CaptionResult(
            caption_result_id=new_generation_id("caption_result"),
            caption_request_id=item.caption_request_id,
            session_id=item.session_id,
            platform=CaptionPlatform.X.value,
            variations=variations,
            selected_text=None,
            formatter_metadata={
                "provider_neutral": True,
                "formatter": "CaptionStudioService",
                "workflow": "x_engagement_publish",
                "vision_primary": True,
                "vision_provider": "grok",
                "vision": vision,
                "themes": themes,
                "personas": {
                    "creator_os_engagement": "Creator OS Engagement",
                },
                "engagement_goals": (
                    "replies",
                    "reposts",
                    "likes",
                    "profile visits",
                    "follows",
                ),
            },
        )
        results = list(self.list_results())
        results.insert(0, result)
        self._write_results(results)
        self._append_history(item, result)
        return result

    def generate_instagram_vision_themes(
        self,
        *,
        generated_image_id: str,
        image_reference: str,
        creator_profile_id: int,
        creator_profile: Mapping[str, Any] | None = None,
        creative_mode: str | None = None,
        prompt_text: str | None = None,
        prompt_metadata: Mapping[str, Any] | None = None,
        generation_metadata: Mapping[str, Any] | None = None,
        idea_seed: int = 0,
    ) -> CaptionResult:
        """Create image-aware Instagram caption choices for a phone handoff."""
        grok_response = self._generate_grok_vision_x_captions(
            image_reference=image_reference,
            creator_profile=creator_profile,
            creative_mode=creative_mode,
            prompt_text=prompt_text,
            prompt_metadata=prompt_metadata,
            generation_metadata=generation_metadata,
            idea_seed=idea_seed,
        )
        vision = dict(grok_response.get("image_analysis") or {})
        themes = ({
            "theme": "Instagram Captions",
            "persona": "instagram_handoff",
            "captions": tuple(grok_response["captions"]),
        },)
        variations = tuple(themes[0]["captions"])
        creator_name = str((creator_profile or {}).get("name") or (creator_profile or {}).get("display_name") or "")
        source_text = " | ".join(value for value in (
            str(vision.get("summary") or ""), creator_name,
            str(creative_mode or ""), str(prompt_text or ""),
        ) if value)
        item = self.create_caption_request(
            creator_profile_id=creator_profile_id,
            platform=CaptionPlatform.INSTAGRAM.value,
            style=CaptionStyle.PLAYFUL.value,
            tone="creator os instagram handoff",
            source_text=source_text or "Grok Vision Instagram caption set",
            variation_count=len(variations),
            source_generated_image_id=generated_image_id,
            metadata={
                "workflow": "instagram_phone_handoff",
                "vision_primary": True,
                "vision_provider": "grok",
                "image_reference": image_reference,
                "creative_mode": creative_mode,
                "prompt_metadata": dict(prompt_metadata or {}),
                "generation_metadata": dict(generation_metadata or {}),
                "idea_seed": idea_seed,
            },
        )
        result = CaptionResult(
            caption_result_id=new_generation_id("caption_result"),
            caption_request_id=item.caption_request_id,
            session_id=item.session_id,
            platform=CaptionPlatform.INSTAGRAM.value,
            variations=variations,
            selected_text=None,
            formatter_metadata={
                "provider_neutral": True,
                "formatter": "CaptionStudioService",
                "workflow": "instagram_phone_handoff",
                "vision_primary": True,
                "vision_provider": "grok",
                "vision": vision,
                "themes": themes,
                "personas": {"instagram_handoff": "Instagram Captions"},
                "engagement_goals": ("caption selection", "manual Instagram posting"),
            },
        )
        results = list(self.list_results())
        results.insert(0, result)
        self._write_results(results)
        self._append_history(item, result)
        return result

    def generate_telegram_vision_themes(
        self,
        *,
        generated_image_id: str,
        image_reference: str,
        creator_profile_id: int,
        creator_profile: Mapping[str, Any] | None = None,
        creative_mode: str | None = None,
        prompt_text: str | None = None,
        prompt_metadata: Mapping[str, Any] | None = None,
        generation_metadata: Mapping[str, Any] | None = None,
        idea_seed: int = 0,
    ) -> CaptionResult:
        """Create Grok Vision-powered Telegram caption personas for a generated image."""

        grok_response = self._generate_grok_vision_telegram_captions(
            image_reference=image_reference,
            creator_profile=creator_profile,
            creative_mode=creative_mode,
            prompt_text=prompt_text,
            prompt_metadata=prompt_metadata,
            generation_metadata=generation_metadata,
            idea_seed=idea_seed,
        )
        vision = dict(grok_response.get("image_analysis") or {})
        themes = (
            {
                "theme": "💛 Romantic",
                "persona": "romantic",
                "captions": tuple(grok_response["romantic"]),
            },
            {
                "theme": "😈 Teasing / Naughty",
                "persona": "teasing_naughty",
                "captions": tuple(grok_response["teasing_naughty"]),
            },
        )
        variations = tuple(
            caption
            for theme in themes
            for caption in tuple(theme.get("captions") or ())
        )
        creator_name = str((creator_profile or {}).get("name") or (creator_profile or {}).get("display_name") or "")
        source_text = " | ".join(
            value
            for value in (
                str(vision.get("summary") or ""),
                creator_name,
                str(creative_mode or ""),
                str(prompt_text or ""),
            )
            if value
        )
        item = self.create_caption_request(
            creator_profile_id=creator_profile_id,
            platform=CaptionPlatform.TELEGRAM.value,
            style=CaptionStyle.DIRECT.value,
            tone="grok vision romantic and teasing naughty",
            source_text=source_text or "Grok Vision Telegram caption set",
            variation_count=len(variations),
            source_generated_image_id=generated_image_id,
            metadata={
                "workflow": "telegram_publish",
                "vision_primary": True,
                "vision_provider": "grok",
                "context_priority": (
                    "grok_vision_image_analysis",
                    "creator_profile",
                    "creative_mode",
                    "prompt_context",
                ),
                "image_reference": image_reference,
                "creative_mode": creative_mode,
                "prompt_metadata": dict(prompt_metadata or {}),
                "generation_metadata": dict(generation_metadata or {}),
                "theme_count": 2,
                "captions_per_theme": 5,
                "idea_seed": idea_seed,
            },
        )
        result = CaptionResult(
            caption_result_id=new_generation_id("caption_result"),
            caption_request_id=item.caption_request_id,
            session_id=item.session_id,
            platform=CaptionPlatform.TELEGRAM.value,
            variations=variations,
            selected_text=None,
            formatter_metadata={
                "provider_neutral": True,
                "formatter": "CaptionStudioService",
                "workflow": "telegram_publish",
                "vision_primary": True,
                "vision_provider": "grok",
                "vision": vision,
                "themes": themes,
                "personas": {
                    "romantic": "💛 Romantic",
                    "teasing_naughty": "😈 Teasing / Naughty",
                },
                "engagement_goals": (
                    "creator selects preferred caption",
                    "telegram publishing",
                ),
            },
        )
        results = list(self.list_results())
        results.insert(0, result)
        self._write_results(results)
        self._append_history(item, result)
        return result

    def save_template(self, template: CaptionTemplate) -> CaptionTemplate:
        templates = [item for item in self.list_templates() if item.template_id != template.template_id]
        templates.insert(0, template)
        self._write_templates(templates)
        return template

    def get_template(self, template_id: str | None) -> CaptionTemplate | None:
        if not template_id:
            return None
        for template in self.list_templates():
            if template.template_id == template_id:
                return template
        return None

    def default_templates(self) -> tuple[CaptionTemplate, ...]:
        return (
            CaptionTemplate("template_x_social", CaptionPlatform.X.value, CaptionStyle.SOCIAL_SAFE.value, "{hook} {detail}"),
            CaptionTemplate("template_telegram_direct", CaptionPlatform.TELEGRAM.value, CaptionStyle.DIRECT.value, "{hook}\n\n{detail}"),
            CaptionTemplate("template_fanvue_premium", CaptionPlatform.FANVUE.value, CaptionStyle.PREMIUM.value, "{hook}. {detail}"),
            CaptionTemplate("template_product_luxury", CaptionPlatform.PRODUCT.value, CaptionStyle.LUXURY.value, "{hook}: {detail}"),
            CaptionTemplate("template_story", CaptionPlatform.STORY.value, CaptionStyle.STORYTELLING.value, "{hook}. {detail}"),
            CaptionTemplate("template_marketing", CaptionPlatform.MARKETING.value, CaptionStyle.PLAYFUL.value, "{hook} - {detail}"),
        )

    def list_sessions(self) -> tuple[CaptionSession, ...]:
        return tuple(self._session_from_dict(item) for item in self._read_json(self.sessions_path, []))

    def list_caption_requests(self) -> tuple[CaptionRequest, ...]:
        return tuple(self._caption_request_from_dict(item) for item in self._read_json(self.caption_items_path, []))

    def list_results(self) -> tuple[CaptionResult, ...]:
        return tuple(self._result_from_dict(item) for item in self._read_json(self.results_path, []))

    def get_result(self, caption_result_id: str) -> CaptionResult:
        for result in self.list_results():
            if result.caption_result_id == caption_result_id:
                return result
        raise KeyError(f"Caption Result not found: {caption_result_id}")

    def get_caption_request(self, caption_request_id: str) -> CaptionRequest:
        for item in self.list_caption_requests():
            if item.caption_request_id == caption_request_id:
                return item
        raise KeyError(f"Caption Request not found: {caption_request_id}")

    def history(self) -> tuple[CaptionHistory, ...]:
        return tuple(self._history_from_dict(item) for item in self._read_json(self.history_path, []))

    def list_templates(self) -> tuple[CaptionTemplate, ...]:
        stored = tuple(self._template_from_dict(item) for item in self._read_json(self.templates_path, []))
        return stored or self.default_templates()

    @staticmethod
    def normalize_platform(platform: str | None) -> str:
        candidate = str(platform or CaptionPlatform.X.value).strip().lower()
        allowed = {item.value for item in CaptionPlatform}
        return candidate if candidate in allowed else CaptionPlatform.MARKETING.value

    @staticmethod
    def normalize_style(style: str | None) -> str:
        candidate = str(style or CaptionStyle.SOCIAL_SAFE.value).strip().lower()
        allowed = {item.value for item in CaptionStyle}
        return candidate if candidate in allowed else CaptionStyle.SOCIAL_SAFE.value

    def _append_history(self, caption_request: CaptionRequest, result: CaptionResult) -> None:
        entries = list(self.history())
        entries.insert(
            0,
            CaptionHistory(
                history_id=new_generation_id("caption_history"),
                session_id=caption_request.session_id,
                caption_request_id=caption_request.caption_request_id,
                caption_result_id=result.caption_result_id,
                platform=result.platform,
                selected_text=result.selected_text,
                metadata={
                    "source_generated_image_id": caption_request.source_generated_image_id,
                    "social_queue_item_id": caption_request.social_queue_item_id,
                },
            ),
        )
        self._write_history(entries)

    @staticmethod
    def _format_caption(
        *,
        platform: str,
        style: str,
        tone: str,
        source_text: str,
        index: int,
        template: CaptionTemplate | None = None,
    ) -> str:
        cleaned = " ".join(str(source_text or "").split())
        detail = cleaned[:220].rstrip(" ,.")
        hook = {
            CaptionPlatform.X.value: "A little moment worth saving.",
            CaptionPlatform.TELEGRAM.value: "New drop for the inner circle.",
            CaptionPlatform.FANVUE.value: "A private set with a little extra pull.",
            CaptionPlatform.PRODUCT.value: "Creator-ready visual set",
            CaptionPlatform.STORY.value: "The scene starts quietly",
            CaptionPlatform.MARKETING.value: "Fresh creative ready for the next campaign",
        }.get(platform, "Fresh creative")
        if index > 1:
            hook = f"{hook} Variation {index}."
        body = template.body if template else "{hook} {detail}"
        text = body.format(hook=hook, detail=detail, tone=tone, style=style).strip()
        if platform == CaptionPlatform.X.value:
            return text[:280]
        if platform == CaptionPlatform.TELEGRAM.value:
            return f"{text}\n\nTone: {tone}"
        if platform == CaptionPlatform.FANVUE.value:
            return f"{text} Crafted in a {tone} tone."
        if platform == CaptionPlatform.PRODUCT.value:
            return f"{text}. Style: {style}. Usage: product description."
        if platform == CaptionPlatform.STORY.value:
            return f"{text}. Built as a story description."
        return f"{text}. Marketing copy direction: {tone}."

    def _generate_grok_vision_x_captions(
        self,
        *,
        image_reference: str,
        creator_profile: Mapping[str, Any] | None,
        creative_mode: str | None,
        prompt_text: str | None,
        prompt_metadata: Mapping[str, Any] | None,
        generation_metadata: Mapping[str, Any] | None,
        idea_seed: int,
    ) -> dict[str, Any]:
        prompt = self._grok_vision_caption_prompt(
            creator_profile=creator_profile,
            creative_mode=creative_mode,
            prompt_text=prompt_text,
            prompt_metadata=prompt_metadata,
            generation_metadata=generation_metadata,
            idea_seed=idea_seed,
        )
        if self.grok_vision_provider is not None:
            raw = self.grok_vision_provider(
                image_reference=image_reference,
                prompt=prompt,
                creator_profile=creator_profile or {},
                creative_mode=creative_mode,
                prompt_text=prompt_text,
                prompt_metadata=dict(prompt_metadata or {}),
                generation_metadata=dict(generation_metadata or {}),
                idea_seed=idea_seed,
            )
            return self._normalize_grok_vision_x_engagement_response(raw)
        return self._call_grok_vision_caption_api(
            image_reference=image_reference,
            prompt=prompt,
            response_kind="x_engagement",
        )

    def _generate_grok_vision_telegram_captions(
        self,
        *,
        image_reference: str,
        creator_profile: Mapping[str, Any] | None,
        creative_mode: str | None,
        prompt_text: str | None,
        prompt_metadata: Mapping[str, Any] | None,
        generation_metadata: Mapping[str, Any] | None,
        idea_seed: int,
    ) -> dict[str, Any]:
        prompt = self._grok_vision_telegram_caption_prompt(
            creator_profile=creator_profile,
            creative_mode=creative_mode,
            prompt_text=prompt_text,
            prompt_metadata=prompt_metadata,
            generation_metadata=generation_metadata,
            idea_seed=idea_seed,
        )
        if self.grok_vision_provider is not None:
            raw = self.grok_vision_provider(
                image_reference=image_reference,
                prompt=prompt,
                creator_profile=creator_profile or {},
                creative_mode=creative_mode,
                prompt_text=prompt_text,
                prompt_metadata=dict(prompt_metadata or {}),
                generation_metadata=dict(generation_metadata or {}),
                idea_seed=idea_seed,
                platform=CaptionPlatform.TELEGRAM.value,
            )
            return self._normalize_grok_vision_caption_response(raw)
        return self._call_grok_vision_caption_api(
            image_reference=image_reference,
            prompt=prompt,
        )

    @staticmethod
    def _grok_vision_caption_prompt(
        *,
        creator_profile: Mapping[str, Any] | None,
        creative_mode: str | None,
        prompt_text: str | None,
        prompt_metadata: Mapping[str, Any] | None,
        generation_metadata: Mapping[str, Any] | None,
        idea_seed: int,
    ) -> str:
        creator_name = str(
            (creator_profile or {}).get("name")
            or (creator_profile or {}).get("display_name")
            or "Ava"
        )
        return f"""
You are Grok Vision writing X captions for {creator_name}.

First analyze the attached image. The image is context, not the caption goal.
Identify only what is actually visible:
- setting
- activity
- time of day
- location
- wardrobe
- expression
- body language
- lighting
- mood
- environment
- activity

Do not hallucinate. Prompt metadata is secondary context only.

Secondary context:
Creative mode: {creative_mode or ""}
Prompt text: {prompt_text or ""}
Prompt metadata: {json.dumps(dict(prompt_metadata or {}), default=str)}
Generation metadata: {json.dumps(dict(generation_metadata or {}), default=str)}
Idea seed: {int(idea_seed or 0)}

Return exactly valid JSON with this shape:
{{
  "image_analysis": {{
    "setting": "",
    "activity": "",
    "time_of_day": "",
    "location": "",
    "wardrobe": "",
    "expression": "",
    "body_language": "",
    "lighting": "",
    "mood": "",
    "environment": ""
  }},
  "captions": ["", "", "", "", "", "", "", "", "", ""]
}}

Primary objective:
- generate exactly 10 X captions
- maximize replies, reposts, likes, profile visits, and follows
- think like a successful organic X creator
- make someone want to reply

Creator OS voice:
- playful
- flirty
- teasing
- approachable
- feminine
- confident
- conversational

Writing strategy:
- write TO the audience, not ABOUT the image
- use the image as the setting for a conversation
- ask engaging questions
- create curiosity
- invite opinions
- make the audience imagine themselves there
- create "what would you do?" moments
- create "choose one" moments
- create "be honest..." moments
- create "help me decide..." moments
- use the image to decide whether the caption naturally leans sweeter or more teasing

Variation requirements:
- the 10 captions must feel substantially different
- include a mix of questions, playful polls, help-me-decide prompts, be-honest prompts, finish-the-sentence prompts, hypotheticals, choose-one prompts, short storytelling, and playful teasing
- do not generate 10 versions of the same caption

All captions:
- must be short enough for X
- must encourage replies
- must be specific to the image setting without simply describing it
- no hashtags
- no mention of AI or generated images
- no labels inside the caption text
- do not list clothing
- do not repeatedly mention bikinis, body parts, or generic thirst hooks
- avoid repetitive openings such as "Golden light", "Warm light", "Soft smile", "This bikini", "My shirt", or "This view"
- {NATURAL_EMOJI_INSTRUCTION}
""".strip()

    @staticmethod
    def _grok_vision_telegram_caption_prompt(
        *,
        creator_profile: Mapping[str, Any] | None,
        creative_mode: str | None,
        prompt_text: str | None,
        prompt_metadata: Mapping[str, Any] | None,
        generation_metadata: Mapping[str, Any] | None,
        idea_seed: int,
    ) -> str:
        creator_name = str(
            (creator_profile or {}).get("name")
            or (creator_profile or {}).get("display_name")
            or "Ava"
        )
        return f"""
You are Grok Vision writing Telegram captions for {creator_name}.

First analyze the attached image. The image is the primary source of truth.
Identify only what is actually visible:
- location
- wardrobe
- expression
- body language
- lighting
- mood
- environment
- activity

Do not hallucinate. Prompt metadata is secondary context only.

Secondary context:
Creative mode: {creative_mode or ""}
Prompt text: {prompt_text or ""}
Prompt metadata: {json.dumps(dict(prompt_metadata or {}), default=str)}
Generation metadata: {json.dumps(dict(generation_metadata or {}), default=str)}
Idea seed: {int(idea_seed or 0)}

Return exactly valid JSON with this shape:
{{
  "image_analysis": {{
    "location": "",
    "wardrobe": "",
    "expression": "",
    "body_language": "",
    "lighting": "",
    "mood": "",
    "environment": "",
    "activity": ""
  }},
  "romantic": ["", "", "", "", ""],
  "teasing_naughty": ["", "", "", "", ""]
}}

💛 Romantic rules:
- exactly 5 captions
- affectionate, warm, playful, intimate, emotionally engaging
- short and natural
- not explicit
- not open-ended
- not engagement bait

😈 Teasing / Naughty rules:
- exactly 5 captions
- teasing, confident, suggestive, sexy, playful, direct
- intended to be consumed, not replied to
- short and natural
- not graphic
- not pornographic
- not open-ended
- not engagement bait

All captions:
- must be based on what you see in the image
- no hashtags
- no mention of AI or generated images
- no labels inside the caption text
- {NATURAL_EMOJI_INSTRUCTION}
""".strip()

    def _call_grok_vision_caption_api(
        self,
        *,
        image_reference: str,
        prompt: str,
        second_key: str = "teasing_naughty",
        second_label: str = "Teasing / Naughty",
        response_kind: str = "themed",
    ) -> dict[str, Any]:
        api_key = os.getenv("GROK_API_KEY", "").strip()
        if not api_key:
            raise ValueError("GROK_API_KEY is required for Grok Vision caption generation.")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ValueError("openai package is required for Grok Vision caption generation.") from exc
        client = OpenAI(
            api_key=api_key,
            base_url=os.getenv("GROK_BASE_URL", "https://api.x.ai/v1"),
        )
        response = client.responses.create(
            model=GROK_VISION_MODEL,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {
                            "type": "input_image",
                            "image_url": self._image_reference_for_grok(image_reference),
                        },
                    ],
                }
            ],
            temperature=0.85,
        )
        raw_text = getattr(response, "output_text", "") or ""
        payload = parse_llm_json(
            raw_text,
            model_name=GROK_VISION_MODEL,
            caller="CaptionStudioService._call_grok_vision_caption_api",
        )
        if response_kind == "x_engagement":
            return self._normalize_grok_vision_x_engagement_response(payload)
        return self._normalize_grok_vision_caption_response(
            payload,
            second_key=second_key,
            second_label=second_label,
        )

    def _image_reference_for_grok(self, image_reference: str) -> str:
        reference = str(image_reference or "").strip()
        if not reference:
            raise ValueError("Image reference is required for Grok Vision caption generation.")
        parsed = urlparse(reference)
        if parsed.scheme in {"http", "https", "data"}:
            return reference
        path = Path(reference).expanduser()
        if not path.exists():
            raise ValueError(f"Image file was not found for Grok Vision caption generation: {reference}")
        suffix = path.suffix.lower()
        mime_type = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }.get(suffix, "image/jpeg")
        return f"data:{mime_type};base64,{base64.b64encode(path.read_bytes()).decode('utf-8')}"

    @staticmethod
    def _normalize_grok_vision_x_engagement_response(raw: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(raw, Mapping):
            raise ValueError("Grok Vision caption response must be a mapping.")
        captions = CaptionStudioService._clean_caption_bucket(raw.get("captions"))
        if len(captions) != CaptionStudioService.X_CAPTION_COUNT:
            raise ValueError("Grok Vision must return exactly 10 X engagement captions.")
        analysis = raw.get("image_analysis") if isinstance(raw.get("image_analysis"), Mapping) else {}
        return {
            "image_analysis": dict(analysis or {}),
            "captions": tuple(captions),
        }

    @staticmethod
    def _normalize_grok_vision_caption_response(
        raw: Mapping[str, Any],
        *,
        second_key: str = "teasing_naughty",
        second_label: str = "Teasing / Naughty",
    ) -> dict[str, Any]:
        if not isinstance(raw, Mapping):
            raise ValueError("Grok Vision caption response must be a mapping.")
        romantic = CaptionStudioService._clean_caption_bucket(raw.get("romantic"))
        teasing = CaptionStudioService._clean_caption_bucket(raw.get(second_key))
        if len(romantic) != 5:
            raise ValueError("Grok Vision must return exactly 5 Romantic captions.")
        if len(teasing) != 5:
            raise ValueError(f"Grok Vision must return exactly 5 {second_label} captions.")
        analysis = raw.get("image_analysis") if isinstance(raw.get("image_analysis"), Mapping) else {}
        return {
            "image_analysis": dict(analysis or {}),
            "romantic": tuple(romantic),
            second_key: tuple(teasing),
        }

    @staticmethod
    def _clean_caption_bucket(value: Any) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)):
            return ()
        cleaned = []
        for caption in value:
            text = " ".join(str(caption or "").split()).strip()
            if not text:
                continue
            if text not in cleaned:
                cleaned.append(text[:280])
        return tuple(cleaned)

    @staticmethod
    def _infer_x_image_vision(
        *,
        image_reference: str,
        creative_mode: str | None,
        prompt_text: str | None,
        prompt_metadata: Mapping[str, Any] | None,
        generation_metadata: Mapping[str, Any] | None,
        idea_seed: int,
    ) -> dict[str, Any]:
        reference_text = Path(str(image_reference or "")).stem.replace("_", " ").replace("-", " ")
        prompt_hint = " ".join(
            str(value)
            for value in (
                prompt_text or "",
                " ".join(str(tag) for tag in (prompt_metadata or {}).get("creative_tags") or ()),
                str((generation_metadata or {}).get("workflow_type") or ""),
                str(creative_mode or ""),
            )
            if value
        )
        searchable = f"{reference_text} {prompt_hint}".lower()
        scene_signals = (
            ("mirror", "mirror selfie energy", "the kind of look that makes him answer too fast"),
            ("window", "soft window light", "a quiet moment with a little trouble in it"),
            ("door", "doorway moment", "walking in right when the room gets interesting"),
            ("bed", "bedroom softness", "lazy confidence with a teasing edge"),
            ("couch", "cozy lounge scene", "comfortable enough to stay awhile"),
            ("kitchen", "kitchen-at-home moment", "casual enough to feel real"),
            ("coffee", "coffee-date warmth", "morning banter made personal"),
            ("beach", "sunny outdoor glow", "vacation confidence with a wink"),
            ("lake", "lake-day glow", "sunlight and playful eye contact"),
            ("boat", "boat-day glow", "sunlight and playful eye contact"),
            ("pool", "poolside glow", "sunlight and playful eye contact"),
            ("car", "car-shot spontaneity", "caught-between-plans energy"),
            ("truck", "truck-shot spontaneity", "caught-between-plans energy"),
            ("hotel", "hotel-room polish", "a getaway scene with a secret-smile mood"),
            ("balcony", "balcony view", "fresh-air flirtation"),
            ("camera", "camera-ready moment", "playful photographer energy"),
        )
        scene = "photo moment"
        mood = "confident, feminine, teasing, approachable"
        scene_key = "default"
        for key, candidate_scene, candidate_mood in scene_signals:
            if key in searchable:
                scene_key = key
                scene = candidate_scene
                mood = candidate_mood
                break
        focus = "her expression, pose, setting, and the visible little story in the image"
        return {
            "summary": f"{scene}; {mood}",
            "scene": scene,
            "scene_key": scene_key,
            "mood": mood,
            "focus": focus,
            "image_reference": image_reference,
            "vision_primary": True,
            "idea_seed": int(idea_seed or 0),
        }

    @staticmethod
    def _build_x_engagement_themes(
        *,
        vision: Mapping[str, Any],
        theme_count: int,
        captions_per_theme: int,
        idea_seed: int,
    ) -> tuple[dict[str, Any], ...]:
        scene = str(vision.get("scene") or "photo moment")
        mood = str(vision.get("mood") or "confident and teasing")
        scene_key = str(vision.get("scene_key") or "default")
        pools = (
            {
                "theme": "Make Him Answer",
                "captions": (
                    f"Be honest... what would you say if you walked into this {scene}?",
                    "You get one sentence to impress me. What is it?",
                    "I feel like you have something clever to say here. Prove me right.",
                    "First thought, no overthinking.",
                ),
            },
            {
                "theme": "Playful Challenge",
                "captions": (
                    "Caption this like you are trying to make me laugh.",
                    "Wrong answers only... what is happening here?",
                    "You can look, but can you keep up?",
                    "Tell me the move. Smooth or dangerous?",
                ),
            },
            {
                "theme": "One-on-One Tease",
                "captions": (
                    f"This feels like I caught you staring at the {mood} part.",
                    "I know exactly what you noticed first.",
                    "Careful. I might ask what you are thinking.",
                    "This is me pretending I do not know you paused.",
                ),
            },
            {
                "theme": "Conversation Starter",
                "captions": (
                    "Pick the vibe: sweet, trouble, or both?",
                    "Would you stay quiet here or say something bold?",
                    "Tell me what this moment needs next.",
                    "What song is playing in this scene?",
                ),
            },
            {
                "theme": "Bookmark Energy",
                "captions": (
                    "Saving this mood for later feels reasonable.",
                    "This is your reminder to enjoy the view.",
                    "A little confidence, a little softness, and a very good reason to linger.",
                    "Keep this one where you can find it again.",
                ),
            },
            {
                "theme": "Quote Post Bait",
                "captions": (
                    "Quote this with the line you would use.",
                    "Quote this with the most honest thought you had.",
                    "Quote this like you are trying not to flirt.",
                    "Quote this with your best excuse for being distracted.",
                ),
            },
        )
        start = int(idea_seed or 0) % len(pools)
        ordered = pools[start:] + pools[:start]
        selected = []
        for theme in ordered[:theme_count]:
            captions = tuple(
                CaptionStudioService._decorate_x_engagement_caption(
                    caption=str(caption),
                    theme=str(theme["theme"]),
                    scene_key=scene_key,
                    scene=scene,
                )
                for caption in theme["captions"][:captions_per_theme]
            )
            selected.append(
                {
                    "theme": theme["theme"],
                    "vision_signal": scene,
                    "emoji_context": scene_key,
                    "captions": captions,
                }
            )
        return tuple(selected)

    @staticmethod
    def _decorate_x_engagement_caption(
        *,
        caption: str,
        theme: str,
        scene_key: str,
        scene: str,
    ) -> str:
        clean = " ".join(str(caption or "").split()).strip()
        if not clean:
            return ""
        emojis = CaptionStudioService._x_engagement_emojis(
            caption=clean,
            theme=theme,
            scene_key=scene_key,
            scene=scene,
        )
        if not emojis:
            return clean[:280]
        text = f"{clean} {''.join(emojis)}"
        return text[:280].rstrip()

    @staticmethod
    def _x_engagement_emojis(
        *,
        caption: str,
        theme: str,
        scene_key: str,
        scene: str,
    ) -> tuple[str, ...]:
        text = f"{caption} {theme} {scene} {scene_key}".lower()
        setting = {
            "beach": "🌊",
            "lake": "🌊",
            "boat": "🚤",
            "pool": "☀️",
            "coffee": "☕",
            "kitchen": "☕",
            "couch": "🛋️",
            "bed": "🌙",
            "mirror": "🫣",
            "window": "☀️",
            "door": "😏",
            "balcony": "🌅",
            "car": "🛻",
            "truck": "🛻",
            "camera": "📸",
            "hotel": "🌙",
        }.get(scene_key)
        selected: list[str] = []
        if setting:
            selected.append(setting)
        if any(word in text for word in ("photographer", "camera", "shot", "smile")) and "📸" not in selected:
            selected.append("📸")
        if any(word in text for word in ("laugh", "wrong answers", "caption this", "snacks")):
            selected.append("😂" if "😂" not in selected else "🤭")
        elif any(word in text for word in ("be honest", "staring", "paused", "careful", "come in", "walked into")):
            selected.append("👀" if "👀" not in selected else "😏")
        elif any(word in text for word in ("impress", "bold", "say", "thinking", "flirt")):
            selected.append("😉" if "😉" not in selected else "😏")
        elif any(word in text for word in ("sweet", "softness", "saving", "view")):
            selected.append("☺️" if "☺️" not in selected else "💕")
        if CaptionStudioService._should_add_reply_cue(caption=caption, theme=theme):
            cue = "👇"
            if any(emoji in selected for emoji in ("👀", "😏", "😂")):
                cue = "👇"
            if cue not in selected:
                selected.append(cue)
        deduped = []
        for emoji in selected:
            if emoji and emoji not in deduped:
                deduped.append(emoji)
            if len(deduped) == 3:
                break
        if not deduped:
            deduped = ["👀", "👇"]
        return tuple(deduped[:3])

    @staticmethod
    def _should_add_reply_cue(*, caption: str, theme: str) -> bool:
        text = f"{caption} {theme}".lower()
        return (
            "?" in caption
            or any(
                phrase in text
                for phrase in (
                    "make him answer",
                    "playful challenge",
                    "one-on-one tease",
                    "conversation starter",
                    "quote post bait",
                    "be honest",
                    "tell me",
                    "pick",
                    "quote this",
                    "caption this",
                    "first thought",
                    "one sentence",
                    "wrong answers",
                )
            )
        )

    @staticmethod
    def _session_from_dict(data: Mapping[str, Any]) -> CaptionSession:
        return CaptionSession(
            session_id=str(data.get("session_id") or ""),
            creator_profile_id=int(data.get("creator_profile_id") or 0),
            platform=str(data.get("platform") or CaptionPlatform.X.value),
            style=str(data.get("style") or CaptionStyle.SOCIAL_SAFE.value),
            tone=str(data.get("tone") or "confident"),
            source_generated_image_id=data.get("source_generated_image_id"),
            social_queue_item_id=data.get("social_queue_item_id"),
            status=str(data.get("status") or "draft"),
            created_at=str(data.get("created_at") or ""),
            updated_at=data.get("updated_at"),
            metadata=data.get("metadata") or {},
        )

    @staticmethod
    def _caption_request_from_dict(data: Mapping[str, Any]) -> CaptionRequest:
        return CaptionRequest(
            caption_request_id=str(data.get("caption_request_id") or ""),
            session_id=str(data.get("session_id") or ""),
            creator_profile_id=int(data.get("creator_profile_id") or 0),
            platform=str(data.get("platform") or CaptionPlatform.X.value),
            style=str(data.get("style") or CaptionStyle.SOCIAL_SAFE.value),
            tone=str(data.get("tone") or "confident"),
            source_text=str(data.get("source_text") or ""),
            variation_count=max(1, int(data.get("variation_count") or 1)),
            source_generated_image_id=data.get("source_generated_image_id"),
            social_queue_item_id=data.get("social_queue_item_id"),
            template_id=data.get("template_id"),
            metadata=data.get("metadata") or {},
            created_at=str(data.get("created_at") or ""),
        )

    @staticmethod
    def _result_from_dict(data: Mapping[str, Any]) -> CaptionResult:
        return CaptionResult(
            caption_result_id=str(data.get("caption_result_id") or ""),
            caption_request_id=str(data.get("caption_request_id") or ""),
            session_id=str(data.get("session_id") or ""),
            platform=str(data.get("platform") or CaptionPlatform.X.value),
            variations=tuple(data.get("variations") or ()),
            selected_text=data.get("selected_text"),
            formatter_metadata=data.get("formatter_metadata") or {},
            created_at=str(data.get("created_at") or ""),
        )

    @staticmethod
    def _history_from_dict(data: Mapping[str, Any]) -> CaptionHistory:
        return CaptionHistory(
            history_id=str(data.get("history_id") or ""),
            session_id=str(data.get("session_id") or ""),
            caption_request_id=str(data.get("caption_request_id") or ""),
            caption_result_id=str(data.get("caption_result_id") or ""),
            platform=str(data.get("platform") or CaptionPlatform.X.value),
            selected_text=data.get("selected_text"),
            created_at=str(data.get("created_at") or ""),
            metadata=data.get("metadata") or {},
        )

    @staticmethod
    def _template_from_dict(data: Mapping[str, Any]) -> CaptionTemplate:
        return CaptionTemplate(
            template_id=str(data.get("template_id") or ""),
            platform=str(data.get("platform") or CaptionPlatform.X.value),
            style=str(data.get("style") or CaptionStyle.SOCIAL_SAFE.value),
            body=str(data.get("body") or "{hook} {detail}"),
            tone=str(data.get("tone") or "confident"),
            metadata=data.get("metadata") or {},
        )

    def _write_sessions(self, sessions: list[CaptionSession]) -> None:
        self._write_json(self.sessions_path, [asdict(item) for item in sessions])

    def _write_caption_items(self, items: list[CaptionRequest]) -> None:
        self._write_json(self.caption_items_path, [asdict(item) for item in items])

    def _write_results(self, results: list[CaptionResult]) -> None:
        self._write_json(self.results_path, [asdict(item) for item in results])

    def _write_history(self, history: list[CaptionHistory]) -> None:
        self._write_json(self.history_path, [asdict(item) for item in history])

    def _write_templates(self, templates: list[CaptionTemplate]) -> None:
        self._write_json(self.templates_path, [asdict(item) for item in templates])

    @staticmethod
    def _read_json(path: Path, default):
        try:
            if not path.exists():
                return default
            with open(path, "r", encoding="utf-8") as file:
                return json.load(file)
        except (OSError, json.JSONDecodeError):
            return default

    @staticmethod
    def _write_json(path: Path, data) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, default=str)
