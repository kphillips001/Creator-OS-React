"""Provider-neutral Content Intelligence contracts for Creator OS."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any


@dataclass(frozen=True)
class ContentRecommendation:
    """Reusable recommendation about content presentation.

    Recommendations describe the content itself. Product Strategy, Sales
    Strategy, Publishing, and Telegram Commerce remain outside this model.
    """

    recommendation_type: str
    asset_id: int | None
    recommended: bool
    confidence: float
    rationale: tuple[str, ...] = ()
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def to_context(self) -> dict[str, Any]:
        return {
            "recommendation_type": self.recommendation_type,
            "asset_id": self.asset_id,
            "recommended": self.recommended,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class ContentIntelligence:
    """Reusable AI-generated understanding for one imported Asset.

    This contract wraps the existing AssetUnderstanding model instead of
    replacing it. Creator intent, Experience relationships, Product strategy,
    Publishing, and Telegram Commerce remain outside this model.
    """

    asset_id: int | None
    asset_understanding: Any
    summary: str | None = None
    classification: str | None = None
    confidence: float | None = None
    themes: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    mood: str | None = None
    setting: str | None = None
    outfit: str | None = None
    pose: str | None = None
    activity: str | None = None
    objects: tuple[str, ...] = ()
    environment: str | None = None
    activities: tuple[str, ...] = ()
    clothing: str | None = None
    keywords: tuple[str, ...] = ()
    technical_quality: Mapping[str, Any] = field(default_factory=dict)
    suggested_cover_image: ContentRecommendation | None = None
    recommendations: Mapping[str, ContentRecommendation] = field(
        default_factory=dict
    )
    media_metadata: Mapping[str, Any] = field(default_factory=dict)
    ai_metadata: Mapping[str, Any] = field(default_factory=dict)
    technical_metadata: Mapping[str, Any] = field(default_factory=dict)
    provenance: Mapping[str, Any] = field(default_factory=dict)
    readiness: Mapping[str, Any] = field(default_factory=dict)
    ownership: Mapping[str, Any] = field(default_factory=dict)

    def to_context(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "summary": self.summary,
            "classification": self.classification,
            "confidence": self.confidence,
            "themes": self.themes,
            "tags": self.tags,
            "mood": self.mood,
            "setting": self.setting,
            "outfit": self.outfit,
            "pose": self.pose,
            "activity": self.activity,
            "objects": self.objects,
            "environment": self.environment,
            "activities": self.activities,
            "clothing": self.clothing,
            "keywords": self.keywords,
            "technical_quality": dict(self.technical_quality),
            "suggested_cover_image": (
                self.suggested_cover_image.to_context()
                if self.suggested_cover_image is not None
                else None
            ),
            "recommendations": {
                key: recommendation.to_context()
                for key, recommendation in self.recommendations.items()
            },
            "media_metadata": dict(self.media_metadata),
            "ai_metadata": dict(self.ai_metadata),
            "technical_metadata": dict(self.technical_metadata),
            "provenance": dict(self.provenance),
            "readiness": dict(self.readiness),
            "ownership": dict(self.ownership),
        }

    def to_asset_understanding_view(self) -> Any:
        """Return a legacy-compatible view backed by Content Intelligence."""

        underlying = self.asset_understanding
        safety = getattr(underlying, "safety", None) or SimpleNamespace()
        metadata = getattr(underlying, "metadata", None) or SimpleNamespace(
            **dict(self.technical_metadata)
        )
        provenance = getattr(underlying, "provenance", None) or SimpleNamespace(
            **dict(self.provenance)
        )
        readiness = getattr(underlying, "readiness", None) or SimpleNamespace(
            **dict(self.readiness)
        )
        media_values = {
            **dict(self.media_metadata),
            **dict(self.technical_metadata),
        }
        media = getattr(underlying, "media", None) or SimpleNamespace(
            **media_values
        )
        identity = getattr(underlying, "identity", None) or SimpleNamespace()
        return SimpleNamespace(
            identity=SimpleNamespace(
                asset_id=self.asset_id,
                creator_profile_id=getattr(identity, "creator_profile_id", None),
                file_name=getattr(identity, "file_name", None),
                original_filename=getattr(
                    identity,
                    "original_filename",
                    None,
                ),
                upload_intent=getattr(identity, "upload_intent", None),
                created_at=getattr(identity, "created_at", None),
            ),
            media=media,
            visual=SimpleNamespace(
                summary=self.summary,
                detected_themes=self.themes,
                suggested_tags=self.tags,
                mood=self.mood,
                setting=self.setting or self.environment,
                outfit=self.outfit or self.clothing,
                pose=self.pose,
                activity=self.activity
                or (self.activities[0] if self.activities else None),
                objects=self.objects,
                gpt_vision_result=dict(
                    self.ai_metadata.get("gpt_vision_result", {})
                ),
            ),
            safety=safety,
            classification=SimpleNamespace(
                classification=self.classification,
                final_classification=self.classification,
                confidence=self.confidence,
                classification_result=dict(
                    self.ai_metadata.get("classification_result", {})
                ),
            ),
            metadata=metadata,
            provenance=provenance,
            readiness=readiness,
            content_intelligence=self,
        )
