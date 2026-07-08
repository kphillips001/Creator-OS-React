"""Provider-neutral Caption Studio service."""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Mapping

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
from app.services.generation_library_service import GenerationLibraryService
from app.services.social_publishing_service import SocialPublishingService


class CaptionStudioService:
    """Owns provider-neutral writing workflow and text history."""

    DEFAULT_STORAGE_DIR = Path("data") / "caption_studio"

    def __init__(self, *, storage_dir: str | Path | None = None):
        self.storage_dir = Path(storage_dir or self.DEFAULT_STORAGE_DIR)

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
            source_text=source_text,
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
