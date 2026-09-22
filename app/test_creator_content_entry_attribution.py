from datetime import UTC, datetime
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from unittest.mock import Mock

import pytest

from app.models.creator_content_entry_attribution import CreatorContentEntryAttribution
from app.models.creator_content_publication import CreatorContentPublication
from app.services.creator_content_entry_attribution_service import CreatorContentEntryAttributionService
from app.services.generation_library_publishing_service import GenerationLibraryPublishingService


SECRET = "attribution-test-secret-that-is-at-least-32-bytes"


class Repository:
    def __init__(self):
        self.by_publication = {}; self.by_digest = {}; self.events = {}; self.attachments = []
    def create_or_get(self, value):
        existing = self.by_publication.setdefault(value.publication_id, value)
        self.by_digest.setdefault(existing.token_digest, existing)
        return existing
    def get_by_digest(self, digest): return self.by_digest.get(digest)
    def mark_attachment(self, attribution_id, *, succeeded, error_code=None):
        self.attachments.append((attribution_id, succeeded, error_code))
    def observe(self, value):
        key=(value.attribution_id,value.telegram_user_id,value.telegram_chat_id,value.inbound_telegram_message_id)
        return self.events.setdefault(key,value)
    def list_events(self, *, creator_profile_id, telegram_user_id):
        return tuple(value for value in self.events.values()
            if value.creator_profile_id == creator_profile_id and value.telegram_user_id == telegram_user_id)


class Telegram:
    def __init__(self, succeeds=True): self.succeeds=succeeds; self.edits=[]
    @staticmethod
    def build_inline_keyboard(*, cta_buttons):
        return {"inline_keyboard": [[{"identity": item["identity"], "url": item["url"]}
                                      for item in cta_buttons]]}
    def edit_message_reply_markup(self, *, chat_id, message_id, reply_markup):
        self.edits.append((chat_id,message_id,reply_markup))
        return {"ok":self.succeeds,"chat_id":int(chat_id),"message_id":int(message_id),
                "reply_markup":reply_markup, "error":None if self.succeeds else "failed"}


def publication(identifier="00000000-0000-4000-8000-000000000001"):
    return CreatorContentPublication(publication_id=identifier, creator_profile_id=7,
        platform="telegram", destination="main", telegram_channel_id=-1007,
        telegram_message_id=88, published_at=datetime.now(UTC), generated_image_id="image-1",
        intelligence_source="TEST", intelligence_version="v1", search_document="mirror")


def publish_item():
    return SimpleNamespace(metadata={"provider_post_id":"88","provider_metadata":{
        "response":{"result":{"message_id":88,"chat":{"id":-1007}}}}})


def issue(service):
    return service.ensure_and_attach(publication=publication(), publish_item=publish_item(),
        chat_base_url="https://t.me/AvaBlackthorne", cta_buttons=(
            {"identity":"VAULT","url":"https://t.me/vault"},
            {"identity":"CHAT","url":"https://t.me/AvaBlackthorne"},))


def test_chat_publication_gets_one_opaque_identity_and_attached_url():
    repository=Repository(); telegram=Telegram()
    service=CreatorContentEntryAttributionService(repository=repository,
        telegram_provider=telegram,signing_secret=SECRET)
    first=issue(service); second=issue(service)
    assert first["attributionId"] == second["attributionId"]
    assert len(repository.by_publication) == 1
    token=parse_qs(urlsplit(first["chatUrl"]).query)["text"][0].split("cc_",1)[1]
    assert len(token)==43 and publication().publication_id not in token
    assert repository.by_publication[publication().publication_id].token_digest != token
    assert len(telegram.edits)==2


def test_token_creation_is_not_entry_observation_then_legitimate_send_binds_customer():
    repository=Repository(); service=CreatorContentEntryAttributionService(
        repository=repository,telegram_provider=Telegram(),signing_secret=SECRET)
    result=issue(service); assert repository.events == {}
    command=parse_qs(urlsplit(result["chatUrl"]).query)["text"][0]
    observed=service.observe_message(creator_profile_id=7,message_text=command,
        telegram_user_id=101,telegram_chat_id=101,inbound_telegram_message_id=900)
    assert observed["entryObserved"] is True and observed["publicationId"]==publication().publication_id


def test_repeat_is_idempotent_customers_are_isolated_and_multiple_entries_are_preserved():
    repository=Repository(); service=CreatorContentEntryAttributionService(
        repository=repository,telegram_provider=Telegram(),signing_secret=SECRET)
    command=parse_qs(urlsplit(issue(service)["chatUrl"]).query)["text"][0]
    for user,message in ((101,900),(101,900),(202,901),(101,902)):
        service.observe_message(creator_profile_id=7,message_text=command,
            telegram_user_id=user,telegram_chat_id=user,inbound_telegram_message_id=message)
    assert len(repository.events)==3
    assert len(repository.list_events(creator_profile_id=7,telegram_user_id=101))==2
    assert len(repository.list_events(creator_profile_id=7,telegram_user_id=202))==1


@pytest.mark.parametrize("text,disposition", [
    ("/start cc_bad", "MALFORMED"),
    ("/start cc_" + "A"*43, "UNKNOWN"),
    ("hello", "NONE"),
])
def test_unknown_malformed_and_unrelated_messages_fail_closed(text,disposition):
    service=CreatorContentEntryAttributionService(repository=Repository(),signing_secret=SECRET)
    result=service.observe_message(creator_profile_id=7,message_text=text,
        telegram_user_id=1,telegram_chat_id=1,inbound_telegram_message_id=1)
    assert result["disposition"]==disposition and result["entryObserved"] is False


def test_creator_scope_mismatch_cannot_leak_attribution():
    repository=Repository(); service=CreatorContentEntryAttributionService(
        repository=repository,telegram_provider=Telegram(),signing_secret=SECRET)
    command=parse_qs(urlsplit(issue(service)["chatUrl"]).query)["text"][0]
    result=service.observe_message(creator_profile_id=8,message_text=command,
        telegram_user_id=1,telegram_chat_id=1,inbound_telegram_message_id=1)
    assert result["disposition"]=="UNKNOWN" and repository.events=={}


def test_attribution_attachment_failure_is_separate_from_memory():
    repository=Repository(); service=CreatorContentEntryAttributionService(
        repository=repository,telegram_provider=Telegram(succeeds=False),signing_secret=SECRET)
    result=issue(service)
    assert result["status"]=="CTA_ATTACHMENT_FAILED"
    assert publication().publication_id in repository.by_publication
    assert repository.attachments[-1][1] is False


def test_no_chat_cta_is_rejected_without_entry_or_publication_side_effect():
    repository=Repository(); service=CreatorContentEntryAttributionService(
        repository=repository,telegram_provider=Telegram(),signing_secret=SECRET)
    with pytest.raises(ValueError):
        service.ensure_and_attach(publication=publication(),publish_item=publish_item(),
            chat_base_url="https://t.me/AvaBlackthorne",
            cta_buttons=({"identity":"VAULT","url":"https://t.me/vault"},))
    assert repository.by_publication == {}
    assert repository.events=={}
