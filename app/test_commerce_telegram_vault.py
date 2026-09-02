from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace
from uuid import uuid4

import pytest
from PIL import Image

from app.models.commercial_offering import CommercialOfferingStatus, CommercialOfferingType
from app.models.commercial_publication import CommercialPublicationProvider, CommercialPublicationStatus, ProviderResourceStatus
from app.services.commerce_telegram_vault_service import CommerceTelegramVaultError, CommerceTelegramVaultService
from app.services.social_publishing_service import SocialPublishingService


class Offerings:
    def __init__(self, value): self.value, self.repository = value, object()
    def get(self, _id, *, creator_profile_id): return self.value if creator_profile_id == 7 else None


class Publications:
    def __init__(self, url="https://fanvue.example/media-link", caption="Unlock me now"):
        self.url, self.caption, self.repository = url, caption, self
        self.publication_id = uuid4()
        self.persisted_metadata = {}
    def list_publications(self, **_kwargs):
        if self.url is None: return ()
        metadata = {"media_link": {"url": self.url}, **self.persisted_metadata,
                    "content_vault_caption_draft": {
                "text": self.caption, "source": "GROK", "updatedAt": "2026-08-08T12:00:00Z"}}
        return (SimpleNamespace(
            provider=CommercialPublicationProvider.FANVUE,
            status=CommercialPublicationStatus.LIVE,
            provider_resource_status=ProviderResourceStatus.PRESENT,
            publication_id=self.publication_id, publication_metadata=metadata,
        ),)
    def update_metadata(self, publication_id, *, creator_profile_id, metadata):
        assert publication_id == self.publication_id and creator_profile_id == 7
        self.persisted_metadata = dict(metadata)
        return SimpleNamespace(publication_metadata=metadata)


class Assets:
    def __init__(self, path, owner=7):
        self.value = SimpleNamespace(
            id=42,
            creator_profile_id=owner, local_vault_path=str(path),
            file_path=str(path), media_type="image", media_metadata={
                "standalone_sale_preparation": {"destinations": ["CONTENT_VAULT"]}},
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


class Teasers:
    def __init__(self, path, *, status="READY"): self.path, self.status = path, status
    def get(self, *_args):
        return {"teaser_id": uuid4(), "source_asset_id": 42, "derived_asset_id": 43,
                "derivative_path": str(self.path), "distribution_use": "CONTENT_VAULT",
                "status": self.status}


class CapturingTelegram:
    def __init__(self, *, fail_first=False):
        self.calls = []
        self.fail_first = fail_first

    @staticmethod
    def load_telegram_env():
        return {"bot_token": "test-token", "vault_chat_id": "-100-test"}

    def publish(self, **values):
        self.calls.append(values)
        if self.fail_first and len(self.calls) == 1:
            raise RuntimeError("simulated Telegram failure")
        return SimpleNamespace(
            post_to=values["post_to"], provider_post_id="message-1",
            provider_media_id=None, provider_output_url=None,
            metadata={"reply_markup_preserved": True}, message="Posted to Telegram.",
        )


def make_offering(status=CommercialOfferingStatus.READY):
    return SimpleNamespace(
        offering_id=uuid4(), creator_profile_id=7, hero_asset_id=42,
        title="Beach Set", description="A sunny collection.", status=status,
        offering_type=CommercialOfferingType.PHOTOSET,
        price_minor=1799, currency="USD",
    )


def write_image(path, size=(832, 1248), color=(70, 40, 20)):
    Image.new("RGB", size, color).save(path)
    return path


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
    assert values["caption_text"].endswith("\n\n#Photoshoots")


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


def test_historical_published_record_is_not_normalized_or_modified(tmp_path):
    class Presentation:
        VERSION = 1
        def __init__(self): self.calls = 0
        def normalize(self, *_args, **_kwargs):
            self.calls += 1
            raise AssertionError("historical media must not be regenerated")
    current = make_offering(); current.offering_type = CommercialOfferingType.SINGLE_IMAGE
    presentation = Presentation()
    social = Social(SimpleNamespace(status="posted", queue_item_id="posted-1", updated_at="then"))
    status = CommerceTelegramVaultService(
        offerings=Offerings(current), publications=Publications(), assets=Assets(tmp_path / "paid.jpg"),
        social=social, teasers=Teasers(tmp_path / "safe.jpg"), presentation=presentation,
    ).status(current.offering_id, creator_profile_id=7)
    assert status["status"] == "PUBLISHED"
    assert status["previewUrl"] is None
    assert presentation.calls == 0


def test_standalone_single_image_uses_blurred_teaser_not_original(tmp_path):
    original = tmp_path / "original.jpg"
    blurred = tmp_path / "blurred.jpg"
    original.write_bytes(b"original")
    write_image(blurred)
    current, social = make_offering(), Social()
    current.offering_type = CommercialOfferingType.SINGLE_IMAGE
    service = CommerceTelegramVaultService(
        offerings=Offerings(current), publications=Publications(),
        assets=Assets(original), social=social,
        teasers=Teasers(blurred),
    )
    service.publish(current.offering_id, creator_profile_id=7)
    assert social.created["image_reference"].endswith("_telegram_presentation_v1.jpg")
    assert social.created["image_reference"] != str(original)
    values = social.published[1]
    assert values["caption_text"] == "Unlock me now\n\n#Photos"
    assert values["telegram_cta_label"] == "🔓 Unlock · $17.99"
    assert values["telegram_cta_url"] == "https://fanvue.example/media-link"
    assert values["telegram_cta_enabled"] is True
    assert values["audit_metadata"]["asset_id"] == 42
    assert "teaser_path" not in values["audit_metadata"]
    assert "delivery_url" not in values["audit_metadata"]


def test_runtime_publish_and_retry_append_hashtag_once_without_mutating_authored_caption(tmp_path):
    original, blurred = tmp_path / "original.jpg", tmp_path / "blurred.jpg"
    original.write_bytes(b"paid-original"); write_image(blurred)
    current = make_offering(); current.offering_type = CommercialOfferingType.SINGLE_IMAGE
    publications = Publications(caption="You caught me right when I stopped behaving")
    telegram = CapturingTelegram(fail_first=True)
    social = SocialPublishingService(storage_dir=tmp_path / "social", telegram_provider=telegram)
    service = CommerceTelegramVaultService(
        offerings=Offerings(current), publications=publications, assets=Assets(original),
        social=social, teasers=Teasers(blurred),
    )

    with pytest.raises(CommerceTelegramVaultError) as error:
        service.publish(current.offering_id, creator_profile_id=7)
    assert error.value.code == "TELEGRAM_PUBLISH_FAILED"
    result = service.publish(current.offering_id, creator_profile_id=7)

    assert result.status == "posted"
    assert len(telegram.calls) == 2
    assert all(call["caption"] == "You caught me right when I stopped behaving\n\n#Photos"
               for call in telegram.calls)
    assert all(call["caption"].count("#Photos") == 1 for call in telegram.calls)
    expected_cta = CommerceTelegramVaultService.unlock_cta_label(1799, "USD")
    assert all(call["cta_label"] == expected_cta for call in telegram.calls)
    assert all(call["cta_url"] == "https://fanvue.example/media-link" for call in telegram.calls)
    assert publications.caption == "You caught me right when I stopped behaving"


def test_content_type_hashtags_are_canonical_and_caption_normalization_is_idempotent():
    single = SimpleNamespace(offering_type=CommercialOfferingType.SINGLE_IMAGE)
    video = SimpleNamespace(offering_type=CommercialOfferingType.VIDEO)
    photoshoot = SimpleNamespace(offering_type=CommercialOfferingType.BUNDLE,
                                source_photoshoot_deliverable_id=uuid4())
    assert CommerceTelegramVaultService.content_type_hashtag(single) == "#Photos"
    assert CommerceTelegramVaultService.content_type_hashtag(video) == "#Videos"
    assert CommerceTelegramVaultService.content_type_hashtag(photoshoot) == "#Photoshoots"

    compose = CommerceTelegramVaultService.caption_with_content_type_hashtag
    assert compose("Original words", "#Photos") == "Original words\n\n#Photos"
    assert compose("Original words\n\n#Photos", "#Photos") == "Original words\n\n#Photos"
    assert compose("Original words\n\n#Videos", "#Photos") == "Original words\n\n#Photos"
    assert compose("Original words #personal\n\n#Videos", "#Photos") == "Original words #personal\n\n#Photos"


@pytest.mark.parametrize(("price_minor", "expected"), [
    (999, "🔓 Unlock · $9.99"),
    (1299, "🔓 Unlock · $12.99"),
    (1899, "🔓 Unlock · $18.99"),
    (1999, "🔓 Unlock · $19.99"),
    (2499, "🔓 Unlock · $24.99"),
])
def test_single_image_uses_canonical_priced_unlock_label(tmp_path, price_minor, expected):
    original = tmp_path / "original.jpg"
    teaser = tmp_path / "teaser.jpg"
    original.write_bytes(b"paid-original")
    write_image(teaser)
    current, social = make_offering(), Social()
    current.offering_type = CommercialOfferingType.SINGLE_IMAGE
    current.price_minor = price_minor
    service = CommerceTelegramVaultService(
        offerings=Offerings(current), publications=Publications(),
        assets=Assets(original), social=social, teasers=Teasers(teaser),
    )

    service.publish(current.offering_id, creator_profile_id=7)

    values = social.published[1]
    assert values["telegram_cta_label"] == expected
    assert values["telegram_cta_url"] == "https://fanvue.example/media-link"
    assert values["telegram_cta_enabled"] is True


@pytest.mark.parametrize(("publications", "teaser_status", "code"), [
    (Publications(caption=""), "READY", "CAPTION_REQUIRED"),
    (Publications(), "NEEDS_ATTENTION", "PREVIEW_NOT_FOUND"),
])
def test_single_image_fails_closed_without_complete_authoritative_package(
    tmp_path, publications, teaser_status, code,
):
    original, teaser = tmp_path / "original.jpg", tmp_path / "teaser.jpg"
    original.write_bytes(b"paid-original"); write_image(teaser)
    current = make_offering(); current.offering_type = CommercialOfferingType.SINGLE_IMAGE
    social = Social()
    service = CommerceTelegramVaultService(
        offerings=Offerings(current), publications=publications, assets=Assets(original),
        social=social, teasers=Teasers(teaser, status=teaser_status))
    with pytest.raises(CommerceTelegramVaultError) as error:
        service.publish(current.offering_id, creator_profile_id=7)
    assert error.value.code == code
    assert social.created is None
    assert social.published is None


@pytest.mark.parametrize("status", ["queued", "scheduled"])
def test_non_terminal_queue_item_blocks_duplicate_publish(tmp_path, status):
    current = make_offering()
    with pytest.raises(CommerceTelegramVaultError) as error:
        make_service(tmp_path, current=current, social=Social(SimpleNamespace(status=status))).publish(
            current.offering_id, creator_profile_id=7)
    assert error.value.code == "PUBLISH_IN_PROGRESS"


def test_failed_queue_item_can_be_retried(tmp_path):
    current = make_offering()
    social = Social(SimpleNamespace(status="failed", queue_item_id="queue-failed"))
    result = make_service(tmp_path, current=current, social=social).publish(
        current.offering_id, creator_profile_id=7)
    assert result.status == "posted"
    assert social.published[0] == "queue-failed"


def test_concurrent_publish_claim_allows_only_one_send(tmp_path):
    entered, release = Event(), Event()

    class BlockingSocial(Social):
        def publish_now(self, queue_item_id, **values):
            self.published = (queue_item_id, values)
            entered.set(); release.wait(timeout=2)
            return SimpleNamespace(queue_item_id=queue_item_id, status="posted", updated_at="now")

    current, social = make_offering(), BlockingSocial()
    service = make_service(tmp_path, current=current, social=social)
    first_result = []
    thread = Thread(target=lambda: first_result.append(
        service.publish(current.offering_id, creator_profile_id=7)))
    thread.start(); assert entered.wait(timeout=2)
    with pytest.raises(CommerceTelegramVaultError) as error:
        service.publish(current.offering_id, creator_profile_id=7)
    assert error.value.code == "PUBLISH_IN_PROGRESS"
    release.set(); thread.join(timeout=2)
    assert len(first_result) == 1


def test_persisted_caption_changes_authoritative_readiness_without_other_changes(tmp_path):
    original, teaser = tmp_path / "original.jpg", tmp_path / "teaser.jpg"
    original.write_bytes(b"paid-original"); write_image(teaser)
    current = make_offering(); current.offering_type = CommercialOfferingType.SINGLE_IMAGE
    publications = Publications(caption="")
    service = CommerceTelegramVaultService(
        offerings=Offerings(current), publications=publications, assets=Assets(original),
        social=Social(), teasers=Teasers(teaser))

    missing = service.status(current.offering_id, creator_profile_id=7)
    assert missing["status"] == "NOT_PUBLISHED"
    assert missing["canPublish"] is False
    assert missing["readinessError"] == "Select and save a Content Vault caption before publishing."

    publications.caption = "My persisted selected caption"
    ready = service.status(current.offering_id, creator_profile_id=7)
    assert ready["status"] == "NOT_PUBLISHED"
    assert ready["canPublish"] is True
    assert ready["readinessError"] is None
