from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.commercial_offering import CommercialOfferingStatus
from app.models.commercial_publication import CommercialPublicationProvider, CommercialPublicationStatus, ProviderResourceStatus
from app.services.commerce_telegram_vault_service import CommerceTelegramVaultError, CommerceTelegramVaultService


class Offerings:
    def __init__(self, value): self.value, self.repository = value, object()
    def get(self, _id, *, creator_profile_id): return self.value if creator_profile_id == 7 else None


class Publications:
    def __init__(self, url="https://fanvue.example/media-link"): self.url = url
    def list_publications(self, **_kwargs):
        if self.url is None: return ()
        return (SimpleNamespace(
            provider=CommercialPublicationProvider.FANVUE,
            status=CommercialPublicationStatus.LIVE,
            provider_resource_status=ProviderResourceStatus.PRESENT,
            publication_metadata={"media_link": {"url": self.url}},
        ),)


class Assets:
    def __init__(self, path, owner=7):
        self.value = SimpleNamespace(
            creator_profile_id=owner, local_vault_path=str(path),
            file_path=str(path), media_type="image",
        )
    def get_by_id(self, _id): return self.value


class Social:
    def __init__(self, existing=None):
        self.existing, self.created, self.published = existing, None, None
        self.telegram_provider = SimpleNamespace(load_telegram_env=lambda: {
            "bot_token": "token", "vault_chat_id": "-100123",
        })
    def find_queue_item(self, *_args, **_kwargs): return self.existing
    def create_commerce_queue_item(self, **values):
        self.created = values
        return self.existing or SimpleNamespace(queue_item_id="queue-1")
    def publish_now(self, queue_item_id, **values):
        self.published = (queue_item_id, values)
        return SimpleNamespace(queue_item_id=queue_item_id, status="posted", updated_at="2026-07-24T12:00:00Z")
    def list_history(self): return ()


def make_offering(status=CommercialOfferingStatus.READY):
    return SimpleNamespace(
        offering_id=uuid4(), creator_profile_id=7, hero_asset_id=42,
        title="Beach Set", description="A sunny collection.", status=status,
    )


def make_service(tmp_path: Path, *, current=None, publications=None, social=None, owner=7):
    preview = tmp_path / "hero.jpg"
    preview.write_bytes(b"image")
    return CommerceTelegramVaultService(
        offerings=Offerings(current or make_offering()),
        publications=publications or Publications(),
        assets=Assets(preview, owner),
        social=social or Social(),
    )


def test_success_uses_authoritative_link_preview_and_content_vault(tmp_path):
    social, current = Social(), make_offering()
    result = make_service(tmp_path, current=current, social=social).publish(
        current.offering_id, creator_profile_id=7, marketing_text="Limited release"
    )
    assert result.status == "posted"
    assert social.created["commercial_offering_id"] == str(current.offering_id)
    assert social.created["image_reference"].endswith("hero.jpg")
    values = social.published[1]
    assert values["telegram_post_to"] == "vault"
    assert values["telegram_cta_label"] == "Unlock Now"
    assert values["telegram_cta_url"] == "https://fanvue.example/media-link"
    assert "<b>Beach Set</b>" in values["caption_text"]
    assert "Limited release" in values["caption_text"]


def test_missing_media_link_missing_preview_archived_and_owner_are_rejected(tmp_path):
    current = make_offering()
    scenarios = [
        (make_service(tmp_path, current=current, publications=Publications(None)), 7, "ACTIVE_MEDIA_LINK_REQUIRED"),
        (make_service(tmp_path, current=make_offering(CommercialOfferingStatus.ARCHIVED)), 7, "OFFERING_ARCHIVED"),
        (make_service(tmp_path, current=current, owner=99), 7, "PREVIEW_NOT_FOUND"),
        (make_service(tmp_path, current=current), 8, "OFFERING_NOT_FOUND"),
    ]
    for candidate, owner, code in scenarios:
        with pytest.raises(CommerceTelegramVaultError) as error:
            candidate.publish(current.offering_id, creator_profile_id=owner)
        assert error.value.code == code

    missing = make_service(tmp_path, current=current)
    missing.assets.value.local_vault_path = str(tmp_path / "missing.jpg")
    missing.assets.value.file_path = str(tmp_path / "missing.jpg")
    with pytest.raises(CommerceTelegramVaultError) as error:
        missing.publish(current.offering_id, creator_profile_id=7)
    assert error.value.code == "PREVIEW_NOT_FOUND"


def test_duplicate_published_offering_is_protected(tmp_path):
    current = make_offering()
    with pytest.raises(CommerceTelegramVaultError) as error:
        make_service(
            tmp_path, current=current, social=Social(SimpleNamespace(status="posted"))
        ).publish(current.offering_id, creator_profile_id=7)
    assert error.value.code == "ALREADY_PUBLISHED"
