from types import SimpleNamespace
from uuid import uuid4

from app.providers.social.telegram_provider import TelegramPublishingProvider
from app.services.commerce_telegram_vault_service import CommerceTelegramVaultService
from app.services.historical_content_vault_keyboard_repair_service import HistoricalContentVaultKeyboardRepairService


class Publications:
    def __init__(self): self.updated=[]
    def update_metadata(self,publication_id,**kwargs): self.updated.append((publication_id,kwargs["metadata"])); return True


class Telegram:
    def __init__(self): self.calls=[]
    def edit_message_reply_markup(self,**kwargs):
        self.calls.append(kwargs)
        return {"ok":True,"chat_id":-1001,"message_id":16,"reply_markup":kwargs["reply_markup"]}


def row(repair=None):
    return {"publication_id":uuid4(),"publication_metadata":{"media_link":{"url":"https://fanvue.example/existing"}},
            "repair":repair or {"result":"SUCCEEDED","telegram_chat_id":"-1001","telegram_message_id":"16"},
            "price_minor":1799,"currency":"USD","url":"https://fanvue.example/existing"}


def test_keyboard_only_repair_uses_canonical_price_url_and_verifies_identity():
    publications=Publications(); telegram=Telegram()
    service=HistoricalContentVaultKeyboardRepairService(publications=publications,telegram=telegram)
    service._candidates=lambda _: (row(),)
    result=service.repair_missing(creator_profile_id=2,confirmed=True)
    assert result[0]["status"] == "SUCCEEDED"
    assert telegram.calls == [{"chat_id":"-1001","message_id":"16","reply_markup":{"inline_keyboard":[[{"text":"🔓 Unlock · $17.99","url":"https://fanvue.example/existing"}]]}}]
    metadata=publications.updated[0][1]
    assert metadata["media_link"]["url"] == "https://fanvue.example/existing"
    assert metadata["content_vault_historical_normalization"]["keyboard_result"] == "SUCCEEDED"


def test_successful_keyboard_repair_is_idempotently_skipped():
    publications=Publications(); telegram=Telegram()
    service=HistoricalContentVaultKeyboardRepairService(publications=publications,telegram=telegram)
    service._candidates=lambda _: (row({"result":"SUCCEEDED","media_result":"SUCCEEDED","telegram_chat_id":"-1001","telegram_message_id":"16","keyboard_result":"SUCCEEDED","lifecycle_result":"SUCCEEDED"}),)
    assert service.repair_missing(creator_profile_id=2,confirmed=True)[0]["status"] == "SKIPPED"
    assert telegram.calls == [] and publications.updated == []


def test_reply_markup_transport_targets_existing_message_without_media_or_caption(monkeypatch):
    calls=[]
    response=SimpleNamespace(status_code=200,text="",json=lambda:{"ok":True,"result":{"message_id":16,"chat":{"id":-1001},"reply_markup":{"inline_keyboard":[]}}})
    provider=TelegramPublishingProvider(http_client=SimpleNamespace(post=lambda url,**kwargs:(calls.append((url,kwargs)) or response)))
    monkeypatch.setattr(provider,"load_telegram_env",lambda:{"bot_token":"test"})
    result=provider.edit_message_reply_markup(chat_id="-1001",message_id=16,reply_markup={"inline_keyboard":[]})
    assert result["ok"] and result["chat_id"] == -1001 and result["message_id"] == 16
    url,request=calls[0]
    assert url.endswith("editMessageReplyMarkup")
    assert set(request["data"]) == {"chat_id","message_id","reply_markup"}
    assert "files" not in request


def test_normal_publishing_uses_same_canonical_cta_formatter():
    assert CommerceTelegramVaultService.unlock_cta_label(999,"USD") == "🔓 Unlock · $9.99"
    assert CommerceTelegramVaultService.unlock_cta_label(2499,"USD") == "🔓 Unlock · $24.99"


def test_caption_edit_transport_preserves_keyboard_without_media(monkeypatch):
    calls=[]
    keyboard={"inline_keyboard":[[{"text":"🔓 Unlock · $17.99","url":"https://fanvue.example/existing"}]]}
    response=SimpleNamespace(status_code=200,text="",json=lambda:{"ok":True,"result":{
        "message_id":16,"chat":{"id":-1001},"caption":"Original\n\n#Photos",
        "caption_entities":[{"type":"hashtag","offset":10,"length":7}],"reply_markup":keyboard}})
    provider=TelegramPublishingProvider(http_client=SimpleNamespace(post=lambda url,**kwargs:(calls.append((url,kwargs)) or response)))
    monkeypatch.setattr(provider,"load_telegram_env",lambda:{"bot_token":"test"})

    result=provider.edit_message_caption(chat_id="-1001",message_id=16,
        caption="Original\n\n#Photos",reply_markup=keyboard)

    assert result["ok"] and result["message_id"] == 16
    assert result["reply_markup"] == keyboard
    url,request=calls[0]
    assert url.endswith("editMessageCaption")
    assert set(request["data"]) == {"chat_id","message_id","caption","parse_mode","reply_markup"}
    assert "files" not in request and "media" not in request["data"]
