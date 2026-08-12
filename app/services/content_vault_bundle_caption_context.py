"""Bounded, persisted intelligence context for Photoshoot Bundle wall captions."""
from __future__ import annotations

from collections.abc import Mapping

from app.repositories.photoshoot_commerce_repository import PhotoshootCommerceRepository


class ContentVaultBundleCaptionContextBuilder:
    """Aggregate canonical paid-member evidence without invoking vision providers."""

    def __init__(self, *, photoshoots=None):
        self.photoshoots = photoshoots or PhotoshootCommerceRepository()

    def build(self, *, title: str, paid_asset_ids, price_minor: int, currency: str,
              photoshoot_session_id: str,
              photoshoot_context: Mapping | None = None,
              teaser_context: Mapping | None = None) -> dict:
        asset_ids = tuple(int(value) for value in paid_asset_ids)
        if len(asset_ids) < 2:
            raise ValueError("A Photoshoot Bundle caption requires at least two paid images.")
        member_rows = {
            int(item["asset_id"]): item
            for item in self.photoshoots.intelligence_members(str(photoshoot_session_id))
            if int(item["asset_id"]) in asset_ids
        }
        shot_rows = {
            int(item["asset_id"]): item
            for item in self.photoshoots.latest_shot_intelligence(str(photoshoot_session_id))
            if int(item["asset_id"]) in asset_ids
        }
        members = []
        for position, asset_id in enumerate(asset_ids, start=1):
            member = member_rows.get(asset_id, {})
            shot = shot_rows.get(asset_id, {})
            content = self._bounded_member_content(member.get("content_profile"))
            shot_profile = self._bounded_shot(shot.get("profile_data"))
            if not content and not shot_profile:
                raise ValueError(
                    f"Persisted Photoshoot intelligence is missing for paid Asset {asset_id}."
                )
            members.append({
                "position": position,
                "assetId": asset_id,
                "shotOrder": member.get("shot_order") or shot.get("shot_order"),
                "contentIntelligenceStatus": member.get("content_intelligence_status"),
                "contentIntelligence": content,
                "photoshootShotIntelligence": shot_profile,
            })
        return {
            "product_type": "PHOTOSHOOT_BUNDLE",
            "selling_mode": "BUNDLE",
            "destination": "CONTENT_VAULT",
            "photoshoot_title": str(title).strip(),
            "paid_image_count": len(asset_ids),
            "price_minor": int(price_minor),
            "currency": str(currency).upper(),
            "paid_members": members,
            "photoshoot": self._bounded_photoshoot(photoshoot_context),
            "promotional_teaser": self._bounded_teaser(teaser_context),
        }

    @staticmethod
    def _bounded_member_content(value: Mapping | None) -> dict:
        source = dict(value or {})
        keys = ("summary", "classification", "setting", "environment", "pose", "activity",
                "mood", "clothing", "outfit", "tags", "themes", "keywords", "technical_quality")
        result = {key: source[key] for key in keys if source.get(key) not in (None, "", {}, [])}
        ai = dict(source.get("ai_metadata") or {})
        if ai.get("gpt_vision_result") not in (None, "", {}, []):
            gpt = dict(ai["gpt_vision_result"]) if isinstance(ai["gpt_vision_result"], Mapping) else {}
            gpt_keys = ("short_safe_summary", "classification", "suggested_tags",
                        "detected_themes", "pose", "activity", "mood", "setting")
            result["gptVision"] = {
                key: gpt[key] for key in gpt_keys if gpt.get(key) not in (None, "", {}, [])
            }
        return result

    @staticmethod
    def _bounded_shot(value: Mapping | None) -> dict:
        source = dict(value or {})
        keys = ("sequence_role", "scene_environment", "pose_action", "facial_expression",
                "emotional_tone", "eye_contact", "wardrobe_state", "nudity_explicitness",
                "camera_framing_angle", "visual_focus", "quality_observations",
                "continuity_observations", "suggested_content_uses")
        return {key: source[key] for key in keys if source.get(key) not in (None, "", {}, [])}

    @staticmethod
    def _bounded_photoshoot(value: Mapping | None) -> dict:
        source = dict(value or {})
        keys = ("commercial_title", "subtitle", "commercial_summary",
                "buyer_profile", "sales_strategy", "sales_brain_brief")
        return {key: source[key] for key in keys if source.get(key) not in (None, "", {}, [])}

    @staticmethod
    def _bounded_teaser(value: Mapping | None) -> dict:
        source = dict(value or {})
        mapping = {
            "status": "status", "commercialRole": "commercial_role",
            "sourceAssetId": "source_asset_id", "teaserAssetId": "teaser_asset_id",
            "blurStrength": "blur_strength",
        }
        return {target: source[key] for key, target in mapping.items()
                if source.get(key) not in (None, "")}
