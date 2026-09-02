import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from PIL import Image

from app.api import asset_library as asset_api
from app.models.commercial_offering import CommercialOfferingStatus, CommercialOfferingType
from app.services.commerce_telegram_vault_service import CommerceTelegramVaultError, CommerceTelegramVaultService
from app.services.content_vault_bundle_caption_context import ContentVaultBundleCaptionContextBuilder
from app.services.grok_caption_service import CaptionProfile, GrokCaptionService
from app.test_commerce_telegram_vault import Assets, Offerings, Publications, Social


def bundle_options(count):
    angles = ("tonight", "privately", "behind the tease", "in my secret set", "for your eyes")
    return [{"text": f"All {count} photos 🔥 are waiting in this complete set {angle} 😈"}
            for angle in angles]


def test_bundle_context_uses_dynamic_paid_members_and_persisted_intelligence_only():
    photoshoots = SimpleNamespace(
        intelligence_members=lambda session_id: tuple({
            "asset_id": asset_id, "shot_order": position, "content_intelligence_status": "COMPLETE",
            "content_profile": {"summary": f"Image {asset_id}", "pose": "reclining",
                                "ai_metadata": {"gpt_vision_result": {"mood": "playful"}}},
        } for position, asset_id in enumerate((10, 11, 12), 1)),
        latest_shot_intelligence=lambda session_id: tuple({
            "asset_id": asset_id, "shot_order": position,
            "profile_data": {"sequence_role": "paid", "nudity_explicitness": "explicit"},
        } for position, asset_id in enumerate((10, 11, 12), 1)),
    )
    builder = ContentVaultBundleCaptionContextBuilder(photoshoots=photoshoots)
    context = builder.build(
        title="Shower Set", paid_asset_ids=(10, 11, 12), price_minor=1799, currency="usd",
        photoshoot_session_id="session-1",
        photoshoot_context={"commercial_title": "After Hours", "commercial_summary": "A complete wet-look set.",
                              "raw_provider_payload": {"must": "not leak"}},
        teaser_context={"status": "READY", "sourceAssetId": 10, "teaserAssetId": 99,
                        "previewUrl": "must-not-be-sent"},
    )
    assert context["paid_image_count"] == 3
    assert context["product_type"] == "PHOTOSHOOT_BUNDLE"
    assert context["selling_mode"] == "BUNDLE"
    assert context["destination"] == "CONTENT_VAULT"
    assert context["price_minor"] == 1799
    assert context["currency"] == "USD"
    assert [item["assetId"] for item in context["paid_members"]] == [10, 11, 12]
    assert context["paid_members"][0]["contentIntelligence"]["summary"] == "Image 10"
    assert context["paid_members"][0]["photoshootShotIntelligence"]["sequence_role"] == "paid"
    assert context["photoshoot"] == {
        "commercial_title": "After Hours", "commercial_summary": "A complete wet-look set.",
    }
    assert context["promotional_teaser"] == {
        "status": "READY", "source_asset_id": 10, "teaser_asset_id": 99,
    }
    assert "raw_provider_payload" not in json.dumps(context)
    assert "previewUrl" not in json.dumps(context)


def test_bundle_context_builds_without_a_promotional_teaser():
    builder = ContentVaultBundleCaptionContextBuilder(photoshoots=SimpleNamespace(
        intelligence_members=lambda _session: tuple({"asset_id": asset_id, "shot_order": index,
            "content_intelligence_status": "COMPLETE", "content_profile": {"summary": "Persisted"}}
            for index, asset_id in enumerate((10, 11, 12), 1)),
        latest_shot_intelligence=lambda _session: (),
    ))
    context = builder.build(
        title="Dusk Set", paid_asset_ids=(10, 11, 12),
        price_minor=1499, currency="USD", photoshoot_session_id="session-1", teaser_context=None,
    )
    assert context["paid_image_count"] == 3
    assert context["price_minor"] == 1499
    assert context["promotional_teaser"] == {}


def test_bundle_context_uses_canonical_asset_intelligence_without_photoshoot_lineage():
    assets = (10, 11, 12)
    repository = SimpleNamespace(
        intelligence_members=lambda _source: (),
        latest_shot_intelligence=lambda _source: (),
        content_intelligence_for_assets=lambda requested: tuple({
            "asset_id": asset_id,
            "content_intelligence_status": "READY",
            "content_profile": {"summary": f"Canonical Asset {asset_id}"},
        } for asset_id in requested),
    )
    context = ContentVaultBundleCaptionContextBuilder(photoshoots=repository).build(
        title="Studio Bundle", paid_asset_ids=assets, price_minor=1499,
        currency="USD", photoshoot_session_id="bundle-studio-1",
        photoshoot_context={"source": "BUNDLE_STUDIO"},
    )
    assert context["paid_image_count"] == 3
    assert [item["assetId"] for item in context["paid_members"]] == [10, 11, 12]
    assert context["paid_members"][0]["contentIntelligence"]["summary"] == "Canonical Asset 10"


def test_bundle_context_names_the_paid_asset_when_persisted_intelligence_is_missing():
    builder = ContentVaultBundleCaptionContextBuilder(photoshoots=SimpleNamespace(
        intelligence_members=lambda _session: ({"asset_id": 10, "shot_order": 1,
            "content_intelligence_status": None, "content_profile": None},),
        latest_shot_intelligence=lambda _session: (),
    ))
    with pytest.raises(ValueError, match="paid Asset 10"):
        builder.build(title="Set", paid_asset_ids=(10, 11), price_minor=1499,
                      currency="USD", photoshoot_session_id="session-1")


def test_bundle_caption_profile_enforces_multi_image_semantics_and_canonical_quantity(monkeypatch):
    monkeypatch.delenv("GROK_API_KEY", raising=False)
    completions = SimpleNamespace(create=lambda **_kwargs: SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({"captions": bundle_options(3)})))]))
    service = GrokCaptionService(client=SimpleNamespace(chat=SimpleNamespace(completions=completions)))
    result = service.generate(profile=CaptionProfile.CONTENT_VAULT_PHOTOSHOOT_BUNDLE,
                              context={"paid_image_count": 3, "paid_members": [{}, {}, {}]})
    assert result["profile"] == "CONTENT_VAULT_PHOTOSHOOT_BUNDLE"
    GrokCaptionService.validate_bundle_caption("The complete set is waiting for you.", 3)
    GrokCaptionService.validate_bundle_caption("All three photos are waiting for you.", 3)
    with pytest.raises(ValueError, match="different quantity"):
        GrokCaptionService._validate_options({"captions": bundle_options(4)},
                                            require_woven_emojis=False, paid_image_count=3)
    with pytest.raises(ValueError, match="multi-image product"):
        GrokCaptionService.validate_bundle_caption("Come see what I saved for you.", 3)
    with pytest.raises(ValueError, match="Single Image delivery"):
        GrokCaptionService.validate_bundle_caption("Unlock this photo from my complete set.", 3)


@pytest.mark.parametrize("invalid_index,expected_style", [
    (0, "SHORT"), (1, "TEASING"), (2, "INVITATION"),
    (3, "DIRECT"), (4, "SALES_HOOK"),
])
def test_bundle_caption_repairs_only_the_invalid_named_slot(
        monkeypatch, invalid_index, expected_style):
    monkeypatch.delenv("GROK_API_KEY", raising=False)
    requests = []
    initial = bundle_options(3)
    failed = {"text": "Come closer 🔥 and see what I saved tonight 😈"}
    initial[invalid_index] = failed
    replacement = {"text": f"All 3 photos 🔥 are waiting in my {expected_style.lower()} full set 😈"}
    responses = [initial, [replacement]]

    def create(**kwargs):
        requests.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content=json.dumps({"captions": responses.pop(0)}),
        ))])

    service = GrokCaptionService(client=SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
    ))
    result = service.generate(
        profile=CaptionProfile.CONTENT_VAULT_PHOTOSHOOT_BUNDLE,
        context={"paid_image_count": 3, "paid_members": [{}, {}, {}]},
    )

    assert len(result["captions"]) == 5
    assert len(requests) == 2
    retry_prompt = requests[1]["messages"][1]["content"]
    assert "Bundle captions must clearly describe the multi-image product" in retry_prompt
    assert json.dumps(failed, ensure_ascii=False) in retry_prompt
    assert "exactly 3 photos" in retry_prompt
    assert expected_style in retry_prompt
    assert result["captions"][invalid_index] == {**replacement, "style": expected_style}
    for index, value in enumerate(result["captions"]):
        GrokCaptionService.validate_bundle_caption(value["text"], 3)
        if index != invalid_index:
            assert value["text"] == initial[index]["text"]


def test_bundle_caption_slot_repair_is_bounded(monkeypatch):
    monkeypatch.delenv("GROK_API_KEY", raising=False)
    invalid = {"text": "Come closer 🔥 and see what I saved tonight 😈"}
    responses = [[invalid, *bundle_options(3)[1:]], [invalid], [invalid]]
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content=json.dumps({"captions": responses.pop(0)}),
        ))])

    service = GrokCaptionService(client=SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
    ))
    with pytest.raises(ValueError, match="multi-image product"):
        service.generate(
            profile=CaptionProfile.CONTENT_VAULT_PHOTOSHOOT_BUNDLE,
            context={"paid_image_count": 3, "paid_members": [{}, {}, {}]},
        )
    assert len(calls) == 1 + service._MAX_BUNDLE_SLOT_REPAIR_ATTEMPTS


def test_bundle_caption_endpoint_uses_bundle_profile_and_authoritative_context(monkeypatch):
    captured = {}
    state = {"promotionalTeaser": {"status": "NOT_CONFIGURED", "teaserAssetId": None}}
    row = {"ai_name": "Fallback", "photoshoot_session_id": "session-1",
           "intelligence_profile": {"commercial_summary": "Complete set"}}
    members = ({"asset_id": 10}, {"asset_id": 11}, {"asset_id": 12})
    offering = SimpleNamespace(offering_id=uuid4(), title="Shower Set", price_minor=1799, currency="USD")
    publication = SimpleNamespace(publication_id=uuid4(), publication_metadata={})
    monkeypatch.setattr(asset_api, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(asset_api, "_bundle_content_vault_caption_state",
                        lambda *_args: (state, row, members, offering, publication))

    class Builder:
        def build(self, **kwargs):
            captured["context_inputs"] = kwargs
            return {"paid_image_count": 3, "product_type": "PHOTOSHOOT_BUNDLE"}

    class Captions:
        def generate(self, **kwargs):
            captured["generation"] = kwargs
            return {"profile": kwargs["profile"].value, "captions": bundle_options(3)}

    class PublicationsRepository:
        def update_metadata(self, _publication_id, *, metadata, **_kwargs):
            captured["metadata"] = metadata
            return SimpleNamespace(publication_metadata=metadata)

    monkeypatch.setattr(asset_api, "ContentVaultBundleCaptionContextBuilder", Builder)
    monkeypatch.setattr(asset_api, "GrokCaptionService", Captions)
    monkeypatch.setattr(asset_api, "CommercialPublicationRepository", PublicationsRepository)
    result = asset_api.generate_bundle_content_vault_captions(
        "deliverable-1", asset_api.ContentVaultCaptionGenerateRequest(tone="RAUNCHY"),
    )

    assert captured["context_inputs"] == {
        "title": "Shower Set", "paid_asset_ids": (10, 11, 12),
        "price_minor": 1799, "currency": "USD",
        "photoshoot_session_id": "session-1",
        "photoshoot_context": {"commercial_summary": "Complete set"},
        "teaser_context": {"status": "NOT_CONFIGURED", "teaserAssetId": None},
    }
    assert captured["generation"]["profile"] is CaptionProfile.CONTENT_VAULT_PHOTOSHOOT_BUNDLE
    assert captured["generation"]["context"]["product_type"] == "PHOTOSHOOT_BUNDLE"
    assert captured["generation"]["tone"] == "RAUNCHY"
    assert result["profile"] == "CONTENT_VAULT_PHOTOSHOOT_BUNDLE"
    persisted = captured["metadata"]["content_vault_caption_candidates"]
    assert persisted["captions"] == bundle_options(3)
    assert persisted["profile"] == "CONTENT_VAULT_PHOTOSHOOT_BUNDLE"
    assert persisted["photoshootDeliverableId"] == "deliverable-1"


def test_bundle_caption_provider_validation_failure_is_not_reported_as_readiness_conflict(monkeypatch):
    offering = SimpleNamespace(offering_id=uuid4(), title="Set", price_minor=1899, currency="USD")
    publication = SimpleNamespace(publication_id=uuid4(), publication_metadata={})
    monkeypatch.setattr(asset_api, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(asset_api, "_bundle_content_vault_caption_state", lambda *_args: (
        {"promotionalTeaser": {"status": "NOT_CONFIGURED"}},
        {"photoshoot_session_id": "session-1", "intelligence_profile": {}},
        ({"asset_id": 10}, {"asset_id": 11}, {"asset_id": 12}), offering, publication,
    ))
    monkeypatch.setattr(asset_api, "ContentVaultBundleCaptionContextBuilder", lambda: SimpleNamespace(
        build=lambda **_kwargs: {"paid_image_count": 3, "paid_members": [{}, {}, {}]},
    ))
    monkeypatch.setattr(asset_api, "GrokCaptionService", lambda: SimpleNamespace(
        generate=lambda **_kwargs: (_ for _ in ()).throw(
            ValueError("Bundle captions must clearly describe the multi-image product.")),
    ))

    with pytest.raises(asset_api.HTTPException) as error:
        asset_api.generate_bundle_content_vault_captions(
            "deliverable-1", asset_api.ContentVaultCaptionGenerateRequest(),
        )

    assert error.value.status_code == 502
    assert "Grok could not generate Bundle captions" in error.value.detail


def test_bundle_caption_state_does_not_require_a_promotional_teaser(monkeypatch):
    expected = ({"deliverable_id": "bundle-1"}, ({"asset_id": 10}, {"asset_id": 11}),
                SimpleNamespace(), SimpleNamespace())

    class Preparation:
        def inspect(self, *_args, **_kwargs):
            return {"bundleSalesChannel": "CONTENT_WALL", "status": "READY",
                    "promotionalTeaser": {"status": "NOT_CONFIGURED"}}

        def content_vault_context(self, *_args, **_kwargs):
            return expected

    monkeypatch.setattr(asset_api, "PhotoshootBundleSalePreparationService", Preparation)
    state, row, members, offering, publication = asset_api._bundle_content_vault_caption_state(
        "bundle-1", 7,
    )
    assert state["promotionalTeaser"]["status"] == "NOT_CONFIGURED"
    assert (row, members, offering, publication) == expected


def test_operator_bundle_caption_uses_canonical_persistence_without_grok_semantic_validation(monkeypatch):
    offering_id, publication_id = uuid4(), uuid4()
    publication = SimpleNamespace(publication_id=publication_id, publication_metadata={})
    offering = SimpleNamespace(offering_id=offering_id)
    saved = {}
    monkeypatch.setattr(asset_api, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(asset_api, "_bundle_content_vault_caption_state", lambda *_args: (
        {"status": "READY"}, {}, ({"asset_id": 10}, {"asset_id": 11}), offering, publication,
    ))

    class PublicationsRepository:
        def update_metadata(self, _publication_id, *, metadata, **_kwargs):
            saved.update(metadata)
            return SimpleNamespace(publication_metadata=metadata)

    class Preparation:
        def inspect(self, *_args, **_kwargs):
            return {"contentVaultPublication": {"status": "NOT_PUBLISHED", "canPublish": True}}

    monkeypatch.setattr(asset_api, "CommercialPublicationRepository", PublicationsRepository)
    monkeypatch.setattr(asset_api, "PhotoshootBundleSalePreparationService", Preparation)
    result = asset_api.save_bundle_content_vault_caption(
        "bundle-1", asset_api.ContentVaultCaptionDraftRequest(
            text="  This one is yours  ", source="MANUAL",
        ),
    )
    assert saved["content_vault_caption_draft"]["text"] == "This one is yours"
    assert saved["content_vault_caption_draft"]["source"] == "MANUAL"
    assert result["caption"]["text"] == "This one is yours"


def test_operator_bundle_caption_rejects_whitespace_only_text(monkeypatch):
    monkeypatch.setattr(asset_api, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(asset_api, "_bundle_content_vault_caption_state", lambda *_args: (
        {}, {}, ({"asset_id": 10}, {"asset_id": 11}), SimpleNamespace(),
        SimpleNamespace(publication_metadata={}),
    ))
    with pytest.raises(Exception, match="caption is required"):
        asset_api.save_bundle_content_vault_caption(
            "bundle-1", asset_api.ContentVaultCaptionDraftRequest(text="   ", source="MANUAL"),
        )


def test_operator_bundle_caption_keeps_destination_safety_without_grok_wording_rules():
    assert GrokCaptionService.validate_operator_bundle_caption("This one is yours") == "This one is yours"
    with pytest.raises(ValueError, match="URLs or invented prices"):
        GrokCaptionService.validate_operator_bundle_caption("Open https://example.test for $14.99")


class BundlePreparation:
    def __init__(self, offering, publication, teaser_asset_id=99, channel="CONTENT_WALL"):
        self.offering, self.publication, self.channel = offering, publication, channel
        self.members = tuple({"asset_id": value} for value in (10, 11, 12))
        self.teasers = SimpleNamespace(inspect=lambda *_args, **_kwargs: {
            "status": "READY", "teaserAssetId": teaser_asset_id,
        })

    def content_vault_context(self, *_args, **_kwargs):
        if self.channel != "CONTENT_WALL":
            raise ValueError("Content Vault captions are available only for WALL Bundles.")
        return ({"deliverable_id": "bundle-1"}, self.members, self.offering, self.publication)


def test_bundle_publishes_one_teaser_caption_and_fanvue_link(tmp_path: Path):
    teaser = tmp_path / "bundle-teaser.jpg"; Image.new("RGB", (832, 1248), "black").save(teaser)
    offering_id, publication_id = uuid4(), uuid4()
    offering = SimpleNamespace(
        offering_id=offering_id, offering_type=CommercialOfferingType.BUNDLE,
        source_photoshoot_deliverable_id="bundle-1", creator_profile_id=7,
        hero_asset_id=10, title="Three Photo Set", description=None,
        status=CommercialOfferingStatus.READY, price_minor=1799, currency="USD",
        assets=tuple(SimpleNamespace(asset_id=value) for value in (10, 11, 12)),
    )
    publications = Publications(caption="All 3 photos 🔥 are waiting for you 😈")
    fanvue = publications.list_publications()[0]
    assets = Assets(teaser); assets.value.id = 99
    social = Social()
    service = CommerceTelegramVaultService(
        offerings=Offerings(offering), publications=publications, assets=assets, social=social,
        bundle_preparation=BundlePreparation(offering, fanvue),
    )
    service.publish(offering_id, creator_profile_id=7)
    assert social.created["image_reference"].endswith("_telegram_presentation_v1.jpg")
    assert social.published[1]["telegram_cta_label"] == "🔓 Unlock · $17.99"
    assert social.published[1]["telegram_cta_url"] == "https://fanvue.example/media-link"
    assert social.published[1]["telegram_cta_enabled"] is True
    assert social.published[1]["caption_text"].endswith("\n\n#Photoshoots")
    assert social.published[1]["caption_text"].count("#Photoshoots") == 1
    assert social.published[1]["audit_metadata"]["paid_image_count"] == 3
    assert social.published[1]["audit_metadata"]["paid_asset_ids"] == [10, 11, 12]


def test_chat_bundle_fails_closed_before_telegram_send(tmp_path: Path):
    teaser = tmp_path / "bundle-teaser.jpg"; teaser.write_bytes(b"safe teaser")
    offering = SimpleNamespace(
        offering_id=uuid4(), offering_type=CommercialOfferingType.BUNDLE,
        source_photoshoot_deliverable_id="bundle-1", creator_profile_id=7,
        hero_asset_id=10, title="Chat Set", description=None,
        status=CommercialOfferingStatus.READY, price_minor=1799, currency="USD",
        assets=tuple(SimpleNamespace(asset_id=value) for value in (10, 11, 12)),
    )
    publications, social = Publications(), Social()
    assets = Assets(teaser); assets.value.id = 99
    service = CommerceTelegramVaultService(
        offerings=Offerings(offering), publications=publications, assets=assets, social=social,
        bundle_preparation=BundlePreparation(offering, publications.list_publications()[0], channel="CHAT"),
    )
    with pytest.raises(CommerceTelegramVaultError) as error:
        service.publish(offering.offering_id, creator_profile_id=7)
    assert error.value.code == "INVALID_DESTINATION"
    assert social.published is None
