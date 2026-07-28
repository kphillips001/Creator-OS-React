"""Image-only learning pipeline for creator editorial memory.

This service is deliberately downstream of generation. It records operator
retention/rejection decisions and never exposes its profile to prompt builders.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import mimetypes
import os
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping

from app.models.creative_intelligence import CreativeImageAnalysis, CreativeLearningSignal
from app.repositories.creative_intelligence_repository import CreativeIntelligenceRepository
from app.services.llm_json_parser import parse_llm_json


logger = logging.getLogger(__name__)
_SAFE_OPERATIONAL_KEYS = frozenset(
    {"platform", "photoshoot_session_id", "publish_id", "archive_reason", "version"}
)


class CreativeImageAnalyzer:
    """Extract only coarse editorial categories from the actual image."""

    provider_name = "openai-vision"

    def __init__(self, runner: Callable[[Path], Mapping[str, Any]] | None = None) -> None:
        self._runner = runner

    def analyze(self, image_reference: str) -> CreativeImageAnalysis:
        path = Path(str(image_reference)).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"Creative Intelligence image is unavailable: {path}")
        raw = dict(self._runner(path) if self._runner else self._analyze_with_vision(path))
        return CreativeImageAnalysis(
            **{
                field: self._category(raw.get(field))
                for field in CreativeImageAnalysis.__dataclass_fields__
            }
        )

    @staticmethod
    def _category(value: object) -> str | None:
        normalized = " ".join(str(value or "").strip().lower().split())
        return normalized[:80] or None

    @staticmethod
    def _analyze_with_vision(path: Path) -> Mapping[str, Any]:
        from app.services.content_classification_service import get_openai_client

        mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        image_url = f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"
        response = get_openai_client().responses.create(
            model=os.getenv("CREATIVE_INTELLIGENCE_VISION_MODEL", "gpt-4.1-mini"),
            input=[{
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Analyze only the attached image. Return coarse editorial categories, "
                            "not exact garment descriptions and not a caption or prompt. Use null "
                            "when a category cannot be inferred."
                        ),
                    },
                    {"type": "input_image", "image_url": image_url},
                ],
            }],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "creative_intelligence_image_analysis",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "environment": {"type": ["string", "null"]},
                            "visual_style": {"type": ["string", "null"]},
                            "composition": {"type": ["string", "null"]},
                            "pose": {"type": ["string", "null"]},
                            "season": {"type": ["string", "null"]},
                            "lighting": {"type": ["string", "null"]},
                            "wardrobe_category": {"type": ["string", "null"]},
                        },
                        "required": [
                            "environment", "visual_style", "composition", "pose",
                            "season", "lighting", "wardrobe_category",
                        ],
                    },
                }
            },
        )
        return parse_llm_json(
            response.output_text,
            model_name=os.getenv("CREATIVE_INTELLIGENCE_VISION_MODEL", "gpt-4.1-mini"),
            caller="CreativeImageAnalyzer",
        )


class CreativeIntelligenceLearningService:
    POSITIVE_EVENTS = frozenset(
        {"published", "photoshoot_added", "generation_library_retained", "edit_saved"}
    )
    NEGATIVE_EVENTS = frozenset({"archived", "deleted", "inspire_discarded"})

    def __init__(
        self,
        *,
        repository: CreativeIntelligenceRepository | None = None,
        analyzer: CreativeImageAnalyzer | None = None,
    ) -> None:
        self.repository = repository or CreativeIntelligenceRepository()
        self.analyzer = analyzer or CreativeImageAnalyzer()

    def record_positive(
        self,
        *,
        creator_profile_id: int,
        image_reference: str,
        event_type: str,
        source_workflow: str,
        source_image_id: str | None = None,
        source_asset_id: int | None = None,
        event_key: str | None = None,
        operational_metadata: Mapping[str, object] | None = None,
    ) -> dict:
        if event_type not in self.POSITIVE_EVENTS:
            raise ValueError(f"Unsupported positive learning event: {event_type}")
        resolved_event_key = event_key or self.event_key(
            creator_profile_id, event_type, source_image_id, image_reference
        )
        if hasattr(self.repository, "has_event") and self.repository.has_event(resolved_event_key):
            return {"already_recorded": True}
        analysis_status, analysis_error = "completed", None
        try:
            analysis = self.analyzer.analyze(image_reference)
        except Exception as exc:
            logger.warning("Creative Intelligence image analysis failed: %s", exc)
            analysis = CreativeImageAnalysis()
            analysis_status, analysis_error = "failed", str(exc)[:1000]
        return self.repository.record(
            CreativeLearningSignal(
                creator_profile_id=int(creator_profile_id),
                image_reference=str(image_reference),
                event_type=event_type,
                source_workflow=str(source_workflow),
                signal="positive",
                source_image_id=source_image_id,
                source_asset_id=source_asset_id,
                event_key=resolved_event_key,
                analysis=analysis,
                analysis_status=analysis_status,
                analysis_provider=self.analyzer.provider_name,
                analysis_error=analysis_error,
                operational_metadata=self._safe_metadata(operational_metadata),
            )
        )

    def record_negative(
        self,
        *,
        creator_profile_id: int,
        image_reference: str,
        event_type: str,
        source_workflow: str,
        source_image_id: str | None = None,
        source_asset_id: int | None = None,
        event_key: str | None = None,
        operational_metadata: Mapping[str, object] | None = None,
    ) -> dict:
        if event_type not in self.NEGATIVE_EVENTS:
            raise ValueError(f"Unsupported negative learning event: {event_type}")
        return self.repository.record(
            CreativeLearningSignal(
                creator_profile_id=int(creator_profile_id),
                image_reference=str(image_reference),
                event_type=event_type,
                source_workflow=str(source_workflow),
                signal="negative",
                source_image_id=source_image_id,
                source_asset_id=source_asset_id,
                event_key=event_key or self.event_key(
                    creator_profile_id, event_type, source_image_id, image_reference
                ),
                analysis_status="not_required",
                operational_metadata=self._safe_metadata(operational_metadata),
            )
        )

    def get_aggregated_profile(
        self,
        *,
        creator_profile_id: int,
        fanvue_account_id: int | str,
    ) -> Mapping[str, object]:
        """Return only normalized aggregate patterns, never event source text."""
        row = self.repository.get_profile(
            creator_profile_id=int(creator_profile_id),
            fanvue_account_id=str(fanvue_account_id),
        )
        row = dict(row or {})
        raw_attributes = dict(row.get("learned_attributes") or {})
        attributes: dict[str, Mapping[str, int]] = {}
        for dimension in CreativeImageAnalysis.__dataclass_fields__:
            raw_counts = raw_attributes.get(dimension)
            if not isinstance(raw_counts, Mapping):
                attributes[dimension] = MappingProxyType({})
                continue
            counts = {
                str(value): max(0, int(count))
                for value, count in raw_counts.items()
                if str(value).strip() and self._is_nonnegative_integer(count)
            }
            attributes[dimension] = MappingProxyType(
                dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))
            )
        return MappingProxyType({
            "positive_event_count": max(0, int(row.get("positive_event_count") or 0)),
            "negative_event_count": max(0, int(row.get("negative_event_count") or 0)),
            "analyzed_image_count": max(0, int(row.get("analyzed_image_count") or 0)),
            "learned_attributes": MappingProxyType(attributes),
        })

    def record_positive_safely(self, **kwargs) -> None:
        self._record_safely(self.record_positive, kwargs)

    def record_negative_safely(self, **kwargs) -> None:
        self._record_safely(self.record_negative, kwargs)

    @staticmethod
    def _record_safely(operation: Callable[..., dict], kwargs: dict) -> None:
        try:
            operation(**kwargs)
        except Exception:
            # Learning must never roll back a completed operator action.
            logger.exception("Creative Intelligence event could not be recorded")

    @staticmethod
    def event_key(
        creator_profile_id: int,
        event_type: str,
        source_image_id: str | None,
        image_reference: str,
    ) -> str:
        identity = source_image_id or hashlib.sha256(
            str(image_reference).encode("utf-8")
        ).hexdigest()
        return f"creative-intelligence:{int(creator_profile_id)}:{event_type}:{identity}"

    @staticmethod
    def _safe_metadata(metadata: Mapping[str, object] | None) -> dict[str, object]:
        # Explicit allowlist prevents prompts, captions, hashtags, or syntax from
        # accidentally becoming canonical learning data.
        return {
            key: value for key, value in dict(metadata or {}).items()
            if key in _SAFE_OPERATIONAL_KEYS
        }

    @staticmethod
    def _is_nonnegative_integer(value: object) -> bool:
        try:
            return int(value) >= 0
        except (TypeError, ValueError):
            return False
