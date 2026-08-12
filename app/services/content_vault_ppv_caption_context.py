"""Read-only, purpose-built context for adult Content Vault PPV captions."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.models.asset_intelligence import AssetIntelligenceStatus
from app.repositories.asset_intelligence_repository import AssetIntelligenceRepository


class ContentVaultPPVCaptionContextBuilder:
    PROVIDERS = ("gpt-vision", "grok-vision", "nudenet")

    def __init__(self, repository=None):
        self.repository = repository or AssetIntelligenceRepository()

    def build(self, asset_id: int) -> dict[str, Any]:
        profile = self.repository.get_profile(int(asset_id))
        if profile is None or profile.analysis_status != AssetIntelligenceStatus.READY:
            raise ValueError("Asset Intelligence must be READY before generating captions.")
        successful = {}
        for result in self.repository.list_provider_results(int(asset_id)):
            if result.status == AssetIntelligenceStatus.READY and result.provider in self.PROVIDERS:
                successful[result.provider] = result
        missing = [provider for provider in self.PROVIDERS if provider not in successful]
        if missing:
            raise ValueError("Completed persisted caption evidence is missing: " + ", ".join(missing))
        return {
            "asset": self._canonical(profile),
            "gptVision": self._gpt(successful["gpt-vision"]),
            "grokVision": self._grok(successful["grok-vision"]),
            "nudeNet": self._nudenet(successful["nudenet"]),
        }

    @classmethod
    def _canonical(cls, profile) -> dict:
        fields = (
            "title", "short_description", "detailed_description", "content_summary",
            "setting", "environment", "indoor_outdoor", "location_type", "lighting",
            "pose", "activity", "expression", "mood", "camera_framing", "camera_angle",
            "clothing", "visible_body_regions", "nudity_level", "explicit_content",
            "sexual_intensity", "safety_classification", "tags", "themes", "keywords",
        )
        return cls._compact({name: getattr(profile, name, None) for name in fields})

    @classmethod
    def _gpt(cls, result) -> dict:
        normalized, raw = dict(result.normalized_fields or {}), cls._mapping(result.raw_response)
        return cls._compact({
            "description": normalized.get("short_description") or raw.get("short_safe_summary"),
            "classification": normalized.get("classification") or raw.get("classification"),
            "safetyClassification": normalized.get("safety_classification"),
            "nudityLevel": normalized.get("nudity_level"),
            "explicitContent": normalized.get("explicit_content"),
            "sexualIntensity": normalized.get("sexual_intensity"),
            "pose": normalized.get("pose"), "activity": normalized.get("activity"),
            "visibleBodyRegions": normalized.get("visible_body_regions"),
            "tags": normalized.get("tags") or raw.get("suggested_tags"),
            "themes": normalized.get("themes") or raw.get("detected_themes"),
            "keywords": normalized.get("keywords"), "riskFlags": raw.get("risk_flags"),
            "factualReasoning": raw.get("reasoning"),
        })

    @classmethod
    def _grok(cls, result) -> dict:
        normalized, raw = dict(result.normalized_fields or {}), cls._mapping(result.raw_response)
        return cls._compact({
            "title": normalized.get("title") or raw.get("title"),
            "scene": normalized.get("content_summary") or normalized.get("short_description") or raw.get("descriptive_summary"),
            "setting": normalized.get("setting"), "environment": normalized.get("environment"),
            "pose": normalized.get("pose"), "expression": normalized.get("expression"),
            "mood": normalized.get("mood") or raw.get("mood"),
            "atmosphere": normalized.get("atmosphere") or raw.get("atmosphere"),
            "framing": normalized.get("camera_framing"), "cameraAngle": normalized.get("camera_angle"),
            "visualStyle": normalized.get("visual_style") or raw.get("visual_style"),
            "emotionalTone": normalized.get("emotional_tone") or raw.get("emotional_tone"),
            "lifestyleContext": normalized.get("lifestyle_context") or raw.get("lifestyle_context"),
            "tags": normalized.get("tags") or raw.get("tags"),
            "themes": normalized.get("themes") or raw.get("themes"),
            "keywords": normalized.get("keywords") or raw.get("search_phrases"),
        })

    @classmethod
    def _nudenet(cls, result) -> dict:
        normalized = dict(result.normalized_fields or {})
        detections: dict[str, dict[str, Any]] = {}
        if isinstance(result.raw_response, list):
            for item in result.raw_response:
                if not isinstance(item, Mapping): continue
                label = str(item.get("class") or "").strip().upper()
                if not label or label == "FACE_FEMALE": continue
                words = label.lower().replace("_", " ").split()
                state = "exposed" if "exposed" in words else "covered" if "covered" in words else "detected"
                region = " ".join(word for word in words if word not in {"exposed", "covered", "female", "male"})
                confidence = round(float(item.get("score") or 0), 3)
                current = detections.get(region)
                if current is None or confidence > current["confidence"]:
                    detections[region] = {"region": region, "state": state, "confidence": confidence}
        return cls._compact({
            "overallClassification": normalized.get("safety_classification"),
            "exposure": list(detections.values()),
            "detectorLabels": normalized.get("keywords"),
        })

    @staticmethod
    def _mapping(value) -> dict:
        return dict(value) if isinstance(value, Mapping) else {}

    @staticmethod
    def _compact(value: Mapping[str, Any]) -> dict:
        return {key: item for key, item in value.items() if item not in (None, "", [], (), {})}
