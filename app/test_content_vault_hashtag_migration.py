from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.tools.update_existing_vault_hashtags import (
    Target, edit_target, ensure_pinned_excluded,
)


def target(message_id=16):
    return Target(
        message_id=message_id, offering_id=uuid4(), publication_id=uuid4(),
        content_type="SINGLE_IMAGE", caption="Original #personal", hashtag="#Photos",
        price_minor=1799, currency="USD", unlock_url="https://fanvue.example/existing",
    )


def test_historical_edit_preserves_identity_keyboard_url_price_and_is_idempotent():
    item = target()
    class Telegram:
        def __init__(self): self.calls=[]
        def edit_message_caption(self, **kwargs):
            self.calls.append(kwargs)
            return {"ok": True, "message_id": 16,
                    "caption": "Original #personal\n\n#Photos",
                    "caption_entities": [{"type": "hashtag"}],
                    "reply_markup": item.keyboard}
    provider = Telegram()
    status, _ = edit_target(item, provider, "-1001")
    assert status == "UPDATED"
    assert provider.calls == [{"chat_id": "-1001", "message_id": 16,
        "caption": "Original #personal\n\n#Photos", "reply_markup": item.keyboard}]
    assert item.keyboard["inline_keyboard"][0][0] == {
        "text": "🔓 Unlock · $17.99", "url": "https://fanvue.example/existing"}

    provider.edit_message_caption = lambda **_kwargs: {
        "ok": False, "error": "Bad Request: message is not modified"}
    assert edit_target(item, provider, "-1001")[0] == "ALREADY_CORRECT"


def test_pinned_return_message_is_rejected_as_a_migration_target():
    with pytest.raises(RuntimeError, match="Pinned Content Vault message"):
        ensure_pinned_excluded([target(23)], 23)
    ensure_pinned_excluded([target(16)], 23)
