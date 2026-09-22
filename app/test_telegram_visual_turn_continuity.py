from datetime import datetime, timezone

from app.services.customer_media_multimodal_decision_engine import (
    CustomerMediaMultimodalDecisionEngine,
)
from app.services.customer_media_processing_scope_service import (
    CustomerMediaProcessingScopeService,
)
from app.services.telegram_visual_turn_service import TelegramVisualTurnService


class Repo:
    def __init__(self):
        self.established = None
        self.saved = None
        self.turn = {"media_turn_id": "turn-1"}

    def establish(self, **values):
        self.established = values
        return self.turn

    def get(self, media_turn_id):
        return self.turn if media_turn_id == "turn-1" else None

    def save_summary(self, **values):
        self.saved = values
        return {"summary_id": "summary-1"}

    def live_summaries(self, **_values):
        return ()


def observation(attachment_id="00000000-0000-0000-0000-000000000001"):
    return {
        "attachment_id": attachment_id, "person_visible": False,
        "person_count": 0, "dog_visible": False, "animal_visible": False,
        "animals": [], "objects": ["sunset"], "activity": None,
        "broad_scene": "sunset over water", "smiling": None,
        "style_or_clothing_summary": None, "screenshot_or_meme": False,
        "visible_text_summary": None, "confidence": .93,
    }


def test_normal_production_requires_explicit_consistent_configuration(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CUSTOMER_IMAGE_SCOPE_MODE", "NORMAL_PRODUCTION")
    monkeypatch.setenv("TELEGRAM_CUSTOMER_IMAGE_SAFETY_ENABLED", "true")
    monkeypatch.setenv("TELEGRAM_CUSTOMER_IMAGE_RESPONSE_ENABLED", "true")
    monkeypatch.setenv("CONTROLLED_AUTONOMY_TEST_ENABLED", "false")
    assert CustomerMediaProcessingScopeService().decide(
        telegram_user_id=1, telegram_chat_id=1).reason == "NORMAL_PRODUCTION_AUTHORIZED"
    monkeypatch.setenv("CONTROLLED_AUTONOMY_TEST_ENABLED", "true")
    assert not CustomerMediaProcessingScopeService().decide(
        telegram_user_id=1, telegram_chat_id=1).allowed


def test_media_turn_uses_durable_members_and_watermark():
    repo = Repo(); service = TelegramVisualTurnService(repository=repo)
    service.establish(media_operation={
        "operation_id": "media-1", "creator_profile_id": 2,
        "fanvue_account_id": 2, "telegram_chat_id": 4,
        "telegram_user_id": 4, "grouped_id": "album-1",
    }, inbound_members=(
        {"inbound_id": "00000000-0000-0000-0000-000000000010",
         "telegram_message_id": 10, "has_media": True},
        {"inbound_id": "00000000-0000-0000-0000-000000000011",
         "telegram_message_id": 11, "has_media": False},
    ), burst={"conversation_burst_id": "00000000-0000-0000-0000-000000000012"},
       authoritative_operation_id="00000000-0000-0000-0000-000000000013")
    assert repo.established["member_message_ids"] == [10, 11]
    assert [x["role"] for x in repo.established["member_roles"]] == ["MEDIA", "TEXT"]


def test_one_call_visual_result_persists_only_sanitized_observation():
    repo = Repo(); turns = TelegramVisualTurnService(repository=repo)
    engine = CustomerMediaMultimodalDecisionEngine(
        visual_turn_service=turns,
        runner=lambda _request: {"response_text": "That sunset is gorgeous.",
                                 "observations": [observation()]})
    result = engine.process_message("user", "look at this", runtime_injection={
        "current_turn_visual_context": {
            "operation_id": "media-1", "media_turn_id": "turn-1",
            "response_policy": "SELFIE_COMPLIMENT_ELIGIBLE",
            "attachment_ids": [observation()["attachment_id"]],
            "attachment_paths": ["unused-by-mocked-provider.jpg"],
        }})
    assert result["visual_provider_call_count"] == 1
    assert repo.saved["observations"][0]["broad_scene"] == "sunset over water"
    assert "response_text" not in repo.saved
