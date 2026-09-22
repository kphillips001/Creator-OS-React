from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.commercial_offering import CommercialOfferingType
from app.services.commercial_offering_selector_service import (
    CommercialOfferingSelectorService,
)
from app.services.private_ppv_presentation_service import (
    PrivatePpvPresentationError,
    PrivatePpvPresentationService,
)
from app.services.private_ppv_readiness_service import PrivatePpvReadinessService


def ready_candidate(tmp_path, **changes):
    teaser_path = tmp_path / "canonical-chat-teaser.jpg"
    teaser_path.write_bytes(b"bounded teaser")
    value = {
        "offering_id": uuid4(),
        "creator_profile_id": 2,
        "title": "Private release",
        "offering_status": "READY",
        "primary_sales_channel": "AI_CHAT",
        "publication_id": uuid4(),
        "publication_status": "LIVE",
        "provider": "FANVUE",
        "provider_resource_status": "PRESENT",
        "delivery_url": "https://provider.invalid/private",
        "price_minor": 999,
        "destinations": ["SINGLE_PPV"],
        "asset_ids": [42],
        "hero_asset_id": 42,
        "chat_teaser_id": uuid4(),
        "chat_teaser_creator_profile_id": 2,
        "chat_teaser_source_asset_id": 42,
        "chat_teaser_derived_asset_id": 84,
        "chat_teaser_derivative_path": str(teaser_path),
        "chat_teaser_distribution_use": "CHAT",
        "chat_teaser_status": "READY",
        "chat_teaser_derived_creator_profile_id": 2,
        "chat_teaser_derived_source_asset_id": "42",
        "chat_teaser_derived_distribution_use": "CHAT",
        "chat_teaser_derived_commercial_role": "SINGLE_IMAGE_CHAT_TEASER",
    }
    value.update(changes)
    return value


@pytest.mark.parametrize("change,reason", [
    ({"chat_teaser_id": None}, "CHAT_TEASER_MISSING"),
    ({"chat_teaser_distribution_use": "X"}, "CHAT_TEASER_DISTRIBUTION_INVALID"),
    ({"chat_teaser_status": "PENDING"}, "CHAT_TEASER_NOT_READY"),
    ({"chat_teaser_creator_profile_id": 3}, "CHAT_TEASER_CREATOR_MISMATCH"),
    ({"chat_teaser_source_asset_id": 43}, "CHAT_TEASER_SOURCE_MISMATCH"),
    ({"chat_teaser_derived_asset_id": None}, "CHAT_TEASER_DERIVED_ASSET_MISSING"),
    ({"chat_teaser_derived_asset_id": 42}, "CHAT_TEASER_PAID_ORIGINAL_ALIAS"),
    ({"chat_teaser_derived_creator_profile_id": 3}, "CHAT_TEASER_DERIVED_CREATOR_MISMATCH"),
    ({"chat_teaser_derived_source_asset_id": "43"}, "CHAT_TEASER_DERIVED_SOURCE_MISMATCH"),
    ({"chat_teaser_derived_distribution_use": "X"}, "CHAT_TEASER_DERIVED_DISTRIBUTION_INVALID"),
    ({"chat_teaser_derived_commercial_role": "PAID_ORIGINAL"}, "CHAT_TEASER_DERIVED_ROLE_INVALID"),
    ({"chat_teaser_derivative_path": "missing.jpg"}, "CHAT_TEASER_FILE_MISSING"),
])
def test_readiness_fails_closed_for_each_canonical_contract_boundary(
    tmp_path, change, reason,
):
    result = PrivatePpvReadinessService().evaluate(
        ready_candidate(tmp_path, **change)
    )
    assert result.ready is False
    assert result.reason == reason


def test_readiness_accepts_only_complete_canonical_chat_teaser(tmp_path):
    value = ready_candidate(tmp_path)
    result = PrivatePpvReadinessService().evaluate(value)
    assert result.ready is True
    assert result.reason is None
    assert result.teaser_asset_id == 84
    assert result.teaser_path == value["chat_teaser_derivative_path"]


def test_readiness_is_re_evaluated_and_detects_file_drift(tmp_path):
    value = ready_candidate(tmp_path)
    authority = PrivatePpvReadinessService()
    assert authority.evaluate(value).ready is True
    (tmp_path / "canonical-chat-teaser.jpg").unlink()
    result = authority.evaluate(value)
    assert result.ready is False
    assert result.reason == "CHAT_TEASER_FILE_MISSING"


def test_selector_excludes_unready_standalone_chat_before_ranking(tmp_path):
    candidate = ready_candidate(tmp_path, chat_teaser_status="FAILED")
    candidate.update({
        "offering_type": "SINGLE_IMAGE",
        "source_photoshoot_deliverable_id": None,
        "source_bundle_studio_bundle_id": None,
        "standalone_sale_destination": "CHAT",
    })
    service = CommercialOfferingSelectorService(
        private_ppv_readiness_service=PrivatePpvReadinessService()
    )
    evaluation = service._evaluate(
        candidate, creator_profile_id=2, channel="AI_CHAT",
        purchased=frozenset(), constraints=None,
    )
    assert "PRIVATE_PPV_PRESENTATION_NOT_READY" in evaluation.exclusion_reasons


def test_valid_standalone_chat_ppv_remains_selectable(tmp_path):
    candidate = ready_candidate(tmp_path)
    candidate.update({
        "offering_type": "SINGLE_IMAGE",
        "source_photoshoot_deliverable_id": None,
        "source_bundle_studio_bundle_id": None,
        "standalone_sale_destination": "CHAT",
    })
    service = CommercialOfferingSelectorService(
        private_ppv_readiness_service=PrivatePpvReadinessService()
    )
    evaluation = service._evaluate(
        candidate, creator_profile_id=2, channel="AI_CHAT",
        purchased=frozenset(), constraints=None,
    )
    assert evaluation.eligible is True
    assert evaluation.exclusion_reasons == ()


def test_selector_immediately_observes_readiness_drift(tmp_path):
    candidate = ready_candidate(tmp_path)
    candidate.update({
        "offering_type": "SINGLE_IMAGE",
        "source_photoshoot_deliverable_id": None,
        "source_bundle_studio_bundle_id": None,
        "standalone_sale_destination": "CHAT",
    })
    service = CommercialOfferingSelectorService(
        private_ppv_readiness_service=PrivatePpvReadinessService()
    )
    first = service._evaluate(
        candidate, creator_profile_id=2, channel="AI_CHAT",
        purchased=frozenset(), constraints=None,
    )
    assert first.eligible is True

    (tmp_path / "canonical-chat-teaser.jpg").unlink()
    second = service._evaluate(
        candidate, creator_profile_id=2, channel="AI_CHAT",
        purchased=frozenset(), constraints=None,
    )
    assert second.eligible is False
    assert second.exclusion_reasons == (
        "PRIVATE_PPV_PRESENTATION_NOT_READY",
    )


@pytest.mark.parametrize("change", [
    {"offering_type": "BUNDLE", "source_bundle_studio_bundle_id": uuid4()},
    {"source_photoshoot_deliverable_id": uuid4()},
    {"standalone_sale_destination": "CONTENT_VAULT"},
])
def test_readiness_gate_does_not_expand_to_unrelated_inventory(tmp_path, change):
    candidate = ready_candidate(tmp_path, chat_teaser_status="FAILED")
    candidate.update({
        "offering_type": "SINGLE_IMAGE",
        "source_photoshoot_deliverable_id": None,
        "source_bundle_studio_bundle_id": None,
        "standalone_sale_destination": "CHAT",
    })
    candidate.update(change)
    service = CommercialOfferingSelectorService(
        private_ppv_readiness_service=PrivatePpvReadinessService()
    )
    evaluation = service._evaluate(
        candidate, creator_profile_id=2, channel="AI_CHAT",
        purchased=frozenset(), constraints=None,
    )
    assert (
        "PRIVATE_PPV_PRESENTATION_NOT_READY"
        not in evaluation.exclusion_reasons
    )


class Offerings:
    def __init__(self, offering):
        self.offering = offering

    def get(self, *_args, **_kwargs):
        return self.offering


class Teasers:
    def __init__(self, row):
        self.row = row

    def get(self, *_args):
        return self.row


class Assets:
    def __init__(self, asset):
        self.asset = asset

    def get_by_id(self, asset_id):
        return self.asset if asset_id == self.asset.id else None


def test_selector_and_presentation_share_same_readiness_contract(tmp_path):
    value = ready_candidate(tmp_path)
    authority = PrivatePpvReadinessService()
    assert authority.evaluate(value).ready is True

    offering_id = uuid4()
    offering = SimpleNamespace(
        offering_id=offering_id,
        offering_type=CommercialOfferingType.SINGLE_IMAGE,
        hero_asset_id=42,
    )
    teaser = {
        "teaser_id": value["chat_teaser_id"],
        "creator_profile_id": 2,
        "source_asset_id": 42,
        "derived_asset_id": 84,
        "derivative_path": value["chat_teaser_derivative_path"],
        "distribution_use": "CHAT",
        "status": "READY",
    }
    asset = SimpleNamespace(
        id=84, creator_profile_id=2,
        media_metadata={
            "source_asset_id": 42,
            "distribution_use": "CHAT",
            "commercial_role": "SINGLE_IMAGE_CHAT_TEASER",
        },
    )
    presentation = PrivatePpvPresentationService(
        offerings=Offerings(offering), teasers=Teasers(teaser),
        assets=Assets(asset), readiness=authority,
    )
    built = presentation.build(
        creator_profile_id=2, offering_id=offering_id,
        publication_id=uuid4(), purchase_intent_id=uuid4(),
        delivery_identity="telegram:1:1", attribution_identity="prospect:1",
        message_text="A private one for you.",
        unlock_button_url="https://unlock.avablackthorne.net/u/opaque",
    )
    assert built.teaser_asset_id == 84

    (tmp_path / "canonical-chat-teaser.jpg").unlink()
    with pytest.raises(PrivatePpvPresentationError, match="CHAT_TEASER_FILE_MISSING"):
        presentation.build(
            creator_profile_id=2, offering_id=offering_id,
            publication_id=uuid4(), purchase_intent_id=uuid4(),
            delivery_identity="telegram:1:1", attribution_identity="prospect:1",
            message_text="A private one for you.",
            unlock_button_url="https://unlock.avablackthorne.net/u/opaque",
        )
