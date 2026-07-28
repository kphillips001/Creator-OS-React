from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import creator_personality as api


FIELDS = {
    "persona_name": "Ava Blackthorne",
    "age": 29,
    "gender": "female",
    "location": "Coastal East Coast city",
    "is_active": True,
    "archetype": "Small-town sweetheart",
    "personality_description": "Warm and playful.",
    "backstory": "Ava grew up in a small town.",
    "lifestyle_context": "Coastal city life.",
    "lifestyle_vibe": "Coastal relaxation.",
    "daily_routine": "Coffee before work.",
    "hobbies": "Road trips.",
    "likes": "Meaningful conversations.",
    "dislikes": "Dishonesty.",
    "ideal_user_type": "Kind and genuine.",
    "turn_ons": "Confidence.",
    "turn_offs": "Arrogance.",
    "sexual_style": "Connection and trust.",
    "sexual_likes": "Chemistry.",
    "sexual_dislikes": "Pressure.",
    "kinks": "Playful teasing.",
    "fantasy_style": "Shared experiences.",
    "tone_style": "Warm and conversational.",
    "flirt_style": "Playful teasing.",
    "tease_intensity": 7,
    "push_pull_style": "medium",
    "mystery_level": "medium",
    "response_style": "Natural.",
    "pacing_style": "Gradual.",
    "question_frequency": "medium",
    "emotional_depth": "high",
    "affection_style": "Supportive.",
    "jealousy_style": "Secure.",
    "availability_style": "Independent.",
    "conversation_hooks": "Travel.",
    "retention_hooks": "Remember details.",
    "escalation_style": "Through trust.",
    "escalation_triggers": "Positive chemistry.",
    "self_value_style": "Confident and welcoming.",
    "persona_intensity": 7,
    "boundaries": "Mutual respect.",
    "sexual_boundaries": "Consensual adults.",
    "hard_limits": "No harmful scenarios.",
    "response_rules": "Make people feel welcome.",
}


def _profile(**overrides):
    return {
        "id": 2,
        "fanvue_account_id": "2",
        "display_name": "Ava Blackthorne",
        "created_at": "2026-06-21T10:53:03",
        "updated_at": "2026-06-21T10:53:03",
        **FIELDS,
        **overrides,
    }


def _client():
    application = FastAPI()
    application.include_router(api.router)
    return TestClient(application)


def test_loads_active_account_profile(monkeypatch):
    monkeypatch.setattr(api, "_account_id", lambda: 2)
    monkeypatch.setattr(
        api, "get_active_creator_profile",
        lambda account_id: _profile() if account_id == "2" else {},
    )

    response = _client().get("/api/v1/creator/personality")

    assert response.status_code == 200
    assert response.json()["persona_name"] == "Ava Blackthorne"
    assert response.json()["fanvue_account_id"] == "2"


def test_updates_existing_ava_row_without_touching_amanda(monkeypatch):
    calls = []
    monkeypatch.setattr(api, "_account_id", lambda: 2)
    monkeypatch.setattr(api, "get_active_creator_profile", lambda _: _profile())

    def update(profile_id, account_id, payload):
        calls.append((profile_id, account_id, payload))
        return _profile(**payload, updated_at="2026-07-27T12:00:00")

    monkeypatch.setattr(api, "update_creator_profile", update)
    payload = {**FIELDS, "tone_style": "Edited exact value"}

    response = _client().put("/api/v1/creator/personality", json=payload)

    assert response.status_code == 200
    assert calls == [(2, "2", payload)]
    assert calls[0][0] != 1
    assert response.json()["tone_style"] == "Edited exact value"


def test_does_not_create_a_profile_when_account_has_none(monkeypatch):
    monkeypatch.setattr(api, "_account_id", lambda: 2)
    monkeypatch.setattr(api, "get_active_creator_profile", lambda _: {})

    response = _client().put(
        "/api/v1/creator/personality",
        json=FIELDS,
    )

    assert response.status_code == 404
