import json
import inspect
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api import asset_library as asset_api
from app.services.grok_caption_service import CaptionProfile, CaptionTone, GrokCaptionService
from app.services.content_vault_ppv_caption_context import ContentVaultPPVCaptionContextBuilder
from app.models.asset_intelligence import AssetIntelligenceStatus


class FakeCompletions:
    def __init__(self, payloads):
        self.payloads = payloads if isinstance(payloads, list) else [payloads]
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        payload = self.payloads[min(len(self.calls) - 1, len(self.payloads) - 1)]
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])


def service(payload):
    completions = FakeCompletions(payload)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return GrokCaptionService(client=client), completions


def options():
    return [
        {"text": f"Distinct 🔥 caption number {index} with its own angle 😈"}
        for index in range(1, 6)
    ]


def test_content_vault_profile_uses_one_text_only_canonical_grok_request(monkeypatch):
    monkeypatch.delenv("GROK_API_KEY", raising=False)
    generator, calls = service({"captions": options()})
    result = generator.generate(profile=CaptionProfile.CONTENT_VAULT_PPV, context={
        "title": "Playful Seductive Gaze", "pose": "reclining", "nudityLevel": "explicit",
    })
    assert result == {
        "profile": "CONTENT_VAULT_PPV",
        "tone": "CLASSY",
        "captions": options(),
    }
    assert len(calls.calls) == 1
    request = calls.calls[0]
    assert request["model"] == generator.model
    assert request["response_format"] == {"type": "json_object"}
    system_prompt = request["messages"][0]["content"]
    assert "make men unlock" in system_prompt.lower() or "unlock" in system_prompt.lower()
    assert "Selected tone: CLASSY" in system_prompt
    assert "seductive and elevated" in system_prompt.lower()
    assert "Avoid crude/porn-spam words" in system_prompt
    assert "DIRECT" not in system_prompt
    assert "SALES_HOOK" not in system_prompt
    assert "ALL five captions must include emojis" in system_prompt
    assert "woven through the words" in system_prompt
    assert all(isinstance(message["content"], str) for message in request["messages"])
    serialized = repr(request["messages"])
    assert "image_url" not in serialized and "Fanvue" not in request["messages"][1]["content"]


def test_content_vault_forwards_operator_guidance_to_grok(monkeypatch):
    monkeypatch.delenv("GROK_API_KEY", raising=False)
    generator, calls = service({"captions": options()})
    generator.generate(
        profile=CaptionProfile.CONTENT_VAULT_PPV,
        context={"asset": {"title": "Playful Seductive Gaze"}},
        guidance="  she's spreading her pussy with her fingers  ",
    )
    user_content = calls.calls[0]["messages"][1]["content"]
    assert "Operator guidance" in user_content
    assert "she's spreading her pussy with her fingers" in user_content
    assert "Tone selected by operator: CLASSY" in user_content


def test_content_vault_raunchy_tone_uses_direct_dirty_prompt(monkeypatch):
    monkeypatch.delenv("GROK_API_KEY", raising=False)
    generator, calls = service({"captions": options()})
    result = generator.generate(
        profile=CaptionProfile.CONTENT_VAULT_PPV,
        context={"asset": {"title": "Playful Shower Seduction"}},
        guidance="rubbing her clit until she finishes",
        tone=CaptionTone.RAUNCHY,
    )
    assert result["tone"] == "RAUNCHY"
    system_prompt = calls.calls[0]["messages"][0]["content"]
    user_content = calls.calls[0]["messages"][1]["content"]
    assert "Selected tone: RAUNCHY" in system_prompt
    assert "direct and dirty" in system_prompt.lower()
    assert "clit" in system_prompt.lower()
    assert "Tone selected by operator: RAUNCHY" in user_content
    assert "rubbing her clit until she finishes" in user_content


def test_content_vault_accepts_plain_text_caption_list(monkeypatch):
    monkeypatch.delenv("GROK_API_KEY", raising=False)
    captions = [f"Plain 🔥 unlock caption {index} for him 😈" for index in range(1, 6)]
    generator, _ = service({"captions": captions})
    result = generator.generate(profile=CaptionProfile.CONTENT_VAULT_PPV, context={"summary": "persisted"})
    assert result["captions"] == [{"text": text} for text in captions]


def test_content_vault_retries_then_accepts_single_emoji_captions(monkeypatch):
    monkeypatch.delenv("GROK_API_KEY", raising=False)
    weak = [{"text": f"End only decoration caption {index} 🔥"} for index in range(1, 6)]
    generator, calls = service({"captions": weak})
    result = generator.generate(profile=CaptionProfile.CONTENT_VAULT_PPV, context={"summary": "persisted"})
    assert len(result["captions"]) == 5
    assert len(calls.calls) == 3  # two strict attempts + soft final accept
    assert "RETRY" in calls.calls[1]["messages"][1]["content"]


@pytest.mark.parametrize("payload", [
    {"captions": options()[:4]},
    {"captions": [{"text": "same 🔥 caption 😈"}] * 5},
    {"captions": [{**item, "text": "$17.99 at https://example.test 🔥😈"} for item in options()]},
    {"captions": [{"text": f"No emoji caption number {index}"} for index in range(1, 6)]},
])
def test_content_vault_profile_rejects_malformed_unsafe_options(monkeypatch, payload):
    monkeypatch.delenv("GROK_API_KEY", raising=False)
    generator, _ = service(payload)
    with pytest.raises(ValueError):
        generator.generate(profile="CONTENT_VAULT_PPV", context={"summary": "persisted"})


def test_generation_endpoint_uses_persisted_context_without_commerce_fields(monkeypatch):
    captured = {}
    monkeypatch.setattr(asset_api, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(asset_api, "_content_vault_caption_state", lambda asset_id, creator_id: {
        "status": "READY", "destinations": ["CONTENT_VAULT"]})
    expected = {"asset": {"title": "Stored title"}, "gptVision": {"description": "explicit"},
                "grokVision": {"mood": "playful"}, "nudeNet": {"exposure": []}}
    monkeypatch.setattr(asset_api, "ContentVaultPPVCaptionContextBuilder", lambda: SimpleNamespace(
        build=lambda asset_id: expected))
    monkeypatch.setattr(asset_api, "GrokCaptionService", lambda: SimpleNamespace(
        generate=lambda **kwargs: captured.update(kwargs) or {"captions": options()}))
    result = asset_api.generate_content_vault_captions(
        154,
        asset_api.ContentVaultCaptionGenerateRequest(
            guidance="spread pussy",
            tone="RAUNCHY",
        ),
    )
    assert len(result["captions"]) == 5
    assert captured["profile"] == CaptionProfile.CONTENT_VAULT_PPV
    assert captured["context"] == expected
    assert captured["guidance"] == "spread pussy"
    assert captured["tone"] == "RAUNCHY"


def test_ppv_context_combines_completed_persisted_sources_without_raw_dump():
    profile = SimpleNamespace(
        analysis_status=AssetIntelligenceStatus.READY, title="Canonical title",
        content_summary="Canonical summary", pose=None, expression=None, mood="canonical mood",
        camera_framing="portrait", lighting="soft", tags=("canonical",), themes=("intimate",),
    )
    def result(provider, normalized, raw):
        return SimpleNamespace(provider=provider, status=AssetIntelligenceStatus.READY,
                               normalized_fields=normalized, raw_response=raw)
    results = (
        result("gpt-vision", {"short_description": "Full nudity and direct genital exposure.",
            "tags": ["explicit", "topless"], "safety_classification": "PREMIUM"},
            {"reasoning": "Concrete explicit evidence.", "secret": "must-not-leak",
             "image_url": "https://image.test", "short_safe_summary": "fallback"}),
        result("grok-vision", {"mood": "seductive and playful", "atmosphere": "intimate",
            "content_summary": "Direct gaze with a provocative gesture."}, {"unused_blob": "do-not-dump"}),
        result("nudenet", {"safety_classification": "EXPLICIT", "keywords": ["FEMALE_BREAST_EXPOSED"]}, [
            {"class": "FEMALE_BREAST_EXPOSED", "score": .91, "box": [1, 2, 3, 4]},
            {"class": "FEMALE_GENITALIA_COVERED", "score": .72, "box": [5, 6, 7, 8]},
        ]),
    )
    repository = SimpleNamespace(get_profile=lambda asset_id: profile, list_provider_results=lambda asset_id: results)
    context = ContentVaultPPVCaptionContextBuilder(repository=repository).build(154)
    assert context["asset"]["title"] == "Canonical title"
    assert context["gptVision"]["description"] == "Full nudity and direct genital exposure."
    assert context["gptVision"]["factualReasoning"] == "Concrete explicit evidence."
    assert context["grokVision"]["mood"] == "seductive and playful"
    assert context["nudeNet"]["exposure"] == [
        {"region": "breast", "state": "exposed", "confidence": .91},
        {"region": "genitalia", "state": "covered", "confidence": .72},
    ]
    serialized = json.dumps(context)
    for excluded in ("must-not-leak", "image.test", "do-not-dump", "box", "price", "deliveryUrl"):
        assert excluded not in serialized


def test_ppv_context_builder_is_read_only_and_has_no_analysis_or_media_dependency():
    source = inspect.getsource(ContentVaultPPVCaptionContextBuilder)
    for forbidden in ("GPTVision", "GrokVision", "NudeNetAdapter", "analyze(", "image_url", "file_path", "media_link"):
        assert forbidden not in source


def test_selected_caption_is_persisted_in_existing_publication_metadata(monkeypatch):
    publication_id = uuid4(); offering_id = uuid4(); saved = {}
    publication = SimpleNamespace(publication_id=publication_id, publication_metadata={"media_link": {"url": "kept"}})
    monkeypatch.setattr(asset_api, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(asset_api, "_content_vault_caption_state", lambda *_args: {
        "publicationId": str(publication_id), "offeringId": str(offering_id)})
    class Repo:
        def get(self, *_args, **_kwargs): return publication
        def update_metadata(self, _id, **kwargs):
            saved.update(kwargs["metadata"])
            return SimpleNamespace(publication_metadata=kwargs["metadata"])
    monkeypatch.setattr(asset_api, "CommercialPublicationRepository", Repo)
    result = asset_api.save_content_vault_caption(154, asset_api.ContentVaultCaptionDraftRequest(
        text=" My approved caption ", style="teasing", source="GROK"))
    assert saved["media_link"] == {"url": "kept"}
    assert saved["content_vault_caption_draft"]["text"] == "My approved caption"
    assert saved["content_vault_caption_draft"]["offeringId"] == str(offering_id)
    assert result["caption"]["source"] == "GROK"
