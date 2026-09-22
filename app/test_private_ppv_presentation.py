from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.commercial_offering import CommercialOfferingType
from app.services.private_ppv_presentation_service import (
    PrivatePpvPresentationError,
    PrivatePpvPresentationService,
)


class Offerings:
    def __init__(self, offering): self.offering = offering
    def get(self, *_args, **_kwargs): return self.offering


class Teasers:
    def __init__(self, row): self.row = row
    def get(self, source_asset_id, distribution_use):
        assert source_asset_id == 42
        assert distribution_use == "CHAT"
        return self.row


class Assets:
    def __init__(self, asset): self.asset = asset
    def get_by_id(self, asset_id):
        return self.asset if asset_id == getattr(self.asset, "id", None) else None


def service(tmp_path, *, source=42, derived=84, row_source=42,
            path_exists=True, metadata_source=42):
    teaser_path = tmp_path / "safe-chat-teaser.png"
    if path_exists:
        teaser_path.write_bytes(b"safe teaser")
    offering = SimpleNamespace(
        offering_id=uuid4(), offering_type=CommercialOfferingType.SINGLE_IMAGE,
        hero_asset_id=source,
    )
    row = {
        "teaser_id": uuid4(), "status": "READY", "creator_profile_id": 2,
        "source_asset_id": row_source, "derived_asset_id": derived,
        "derivative_path": str(teaser_path), "distribution_use": "CHAT",
    }
    asset = SimpleNamespace(
        id=derived, creator_profile_id=2,
        media_metadata={"source_asset_id": metadata_source,
                        "distribution_use": "CHAT",
                        "commercial_role": "SINGLE_IMAGE_CHAT_TEASER"},
    )
    return PrivatePpvPresentationService(
        offerings=Offerings(offering), teasers=Teasers(row), assets=Assets(asset)), offering


def build(candidate, offering):
    return candidate.build(
        creator_profile_id=2, offering_id=offering.offering_id,
        publication_id=uuid4(), purchase_intent_id=uuid4(),
        delivery_identity="telegram:100:100", attribution_identity="provisional:100",
        message_text="A private one I think you'll love.",
        unlock_button_url="https://unlock.avablackthorne.net/u/opaque",
    )


def test_explicit_chat_teaser_builds_canonical_media_contract(tmp_path):
    candidate, offering = service(tmp_path)
    presentation = build(candidate, offering)
    payload = {"metadata": {}}
    presentation.apply_to(payload)
    assert presentation.teaser_asset_id == 84
    assert payload["asset_path"].endswith("safe-chat-teaser.png")
    assert payload["message_text"] == "A private one I think you'll love."
    assert payload["metadata"]["private_chat_unlock_button"] == {
        "label": "🔓 Unlock",
        "url": "https://unlock.avablackthorne.net/u/opaque",
    }
    assert "https://" not in payload["message_text"]


@pytest.mark.parametrize("kwargs,match", [
    ({"derived": 42}, "CHAT_TEASER_PAID_ORIGINAL_ALIAS"),
    ({"path_exists": False}, "CHAT_TEASER_FILE_MISSING"),
    ({"row_source": 43}, "CHAT_TEASER_SOURCE_MISMATCH"),
    ({"metadata_source": 43}, "CHAT_TEASER_DERIVED_SOURCE_MISMATCH"),
])
def test_invalid_or_unsafe_teaser_fails_closed(tmp_path, kwargs, match):
    candidate, offering = service(tmp_path, **kwargs)
    with pytest.raises(PrivatePpvPresentationError, match=match):
        build(candidate, offering)


@pytest.mark.parametrize("text", [
    "Unlock: https://unlock.avablackthorne.net/u/opaque",
    "Buy it at https://fanvue.com/private",
    "Open https://example.test/anything",
])
def test_customer_visible_commerce_url_is_rejected(tmp_path, text):
    candidate, offering = service(tmp_path)
    with pytest.raises(PrivatePpvPresentationError, match="commerce URL"):
        candidate.build(
            creator_profile_id=2, offering_id=offering.offering_id,
            publication_id=uuid4(), purchase_intent_id=uuid4(),
            delivery_identity="telegram:100:100", attribution_identity="provisional:100",
            message_text=text,
            unlock_button_url="https://unlock.avablackthorne.net/u/opaque",
        )
