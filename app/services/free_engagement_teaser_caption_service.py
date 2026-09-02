"""Grounded AI caption generation for autonomous Free Engagement Teasers."""
import re

from app.models.asset_intelligence import AssetIntelligenceStatus
from app.repositories.asset_intelligence_repository import AssetIntelligenceRepository
from app.services.ai_training_control_service import AiTrainingControlService


class FreeEngagementTeaserCaptionError(RuntimeError):
    pass


class FreeEngagementTeaserCaptionService:
    def __init__(self, *, asset_intelligence_repository=None,
                 ai_training_service=None, gpt_service=None):
        self.intelligence = asset_intelligence_repository or AssetIntelligenceRepository()
        self.training = ai_training_service or AiTrainingControlService()
        self.gpt = gpt_service

    def generate(self, *, asset_id, strategy, creator_profile_id,
                 fanvue_account_id, recent_conversation=(), customer_context=None):
        profile = self.intelligence.get_profile(int(asset_id))
        if profile is None or profile.analysis_status is not AssetIntelligenceStatus.READY:
            raise FreeEngagementTeaserCaptionError("ASSET_INTELLIGENCE_NOT_READY")
        grounded = {key: value for key, value in {
            "setting": profile.setting, "environment": profile.environment,
            "pose": profile.pose, "activity": profile.activity,
            "expression": profile.expression, "mood": profile.mood,
            "clothing": list(profile.clothing), "themes": list(profile.themes),
            "summary": profile.content_summary or profile.short_description,
        }.items() if value}
        rules = self.training.runtime_prompt_block(
            creator_profile_id=int(creator_profile_id), fanvue_account_id=int(fanvue_account_id))
        conversation = [
            {"direction": str(item.get("direction") or ""), "text": str(item.get("text") or "")[:300]}
            for item in list(recent_conversation)[-8:] if isinstance(item, dict)
        ]
        if self.gpt is None or not hasattr(self.gpt, "generate_free_engagement_teaser_caption"):
            raise FreeEngagementTeaserCaptionError("CAPTION_PROVIDER_UNAVAILABLE")
        caption = self.gpt.generate_free_engagement_teaser_caption(
            strategy=str(strategy), grounded_asset_context=grounded,
            customer_context=dict(customer_context or {}), recent_conversation=conversation,
            global_conversation_training=rules,
            creator_profile_id=int(creator_profile_id),
            fanvue_account_id=fanvue_account_id)
        caption = str(caption or "").strip().strip('"')
        forbidden = re.compile(r"https?://|fanvue\.com|\b(?:buy|price|pay|paid|unlock|ppv)\b", re.I)
        if not caption or len(caption) > 280 or forbidden.search(caption):
            raise FreeEngagementTeaserCaptionError("CAPTION_FAILED_NONCOMMERCIAL_VALIDATION")
        return caption
