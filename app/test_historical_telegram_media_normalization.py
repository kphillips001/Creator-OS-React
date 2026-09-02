import json
from pathlib import Path

from PIL import Image

from app.services.historical_telegram_media_normalization_service import (
    HistoricalTelegramMediaNormalizationService,
)


class Telegram:
    def __init__(self): self.calls = []
    def edit_message_media(self, **kwargs):
        self.calls.append(kwargs)
        return {"ok": True, "response": {"result": {
            "message_id": kwargs["message_id"],
            "caption": kwargs["caption"],
            "caption_entities": list(kwargs["caption_entities"]),
            "reply_markup": kwargs["reply_markup"],
        }}}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def fixture(root: Path):
    source = root / "Content" / "Posted" / "Telegram" / "Main" / "image.png"
    source.parent.mkdir(parents=True)
    Image.new("RGB", (832, 1248), "blue").save(source)
    social = root / "data" / "social_publishing"
    result = {
        "message_id": 97, "chat": {"id": -1001}, "caption": "Caption",
        "caption_entities": [{"offset": 0, "length": 7, "type": "bold"}],
        "reply_markup": {"inline_keyboard": [[{"text": "Vault", "url": "https://example.test"}]]},
        "photo": [{"width": 832, "height": 1248}],
    }
    write(social / "social_publish_items.json", [{
        "publish_request_id": "publish-1", "queue_item_id": "queue-1",
        "platform": "telegram", "status": "posted", "metadata": {
            "telegram_post_to": "main", "provider_post_id": "97",
            "provider_metadata": {"response": {"result": result}},
        },
    }])
    write(social / "social_queue.json", [{
        "queue_item_id": "queue-1", "generated_image_id": "generated-1",
        "output_reference": str(root / "Content" / "Generation" / "Active" / "image.png"),
    }])
    write(social / "social_history.json", [])
    return source


def test_dry_run_builds_verified_candidate_without_telegram_mutation(tmp_path):
    source = fixture(tmp_path)
    telegram = Telegram()
    service = HistoricalTelegramMediaNormalizationService(root=tmp_path, telegram=telegram)
    candidates = service.dry_run()
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.status == "SAFE"
    assert candidate.message_id == 97
    assert candidate.source_path == str(source)
    assert (candidate.expected_width, candidate.expected_height) == (960, 1280)
    assert telegram.calls == []
    assert not service.audit_path.exists()


def test_execute_edits_in_place_preserves_metadata_persists_audit_and_is_idempotent(tmp_path):
    fixture(tmp_path)
    telegram = Telegram()
    service = HistoricalTelegramMediaNormalizationService(root=tmp_path, telegram=telegram)
    outcomes = service.execute()
    assert outcomes == ({
        "publish_request_id": "publish-1", "message_id": 97, "channel": "main",
        "repair_status": "REPAIRED", "message_id_retained": True,
        "caption_retained": True, "caption_entities_retained": True,
        "keyboard_retained": True, "error": None,
    },)
    assert telegram.calls[0]["message_id"] == 97
    assert telegram.calls[0]["caption"] == "Caption"
    assert telegram.calls[0]["reply_markup"]["inline_keyboard"][0][0]["text"] == "Vault"
    audit = json.loads(service.audit_path.read_text(encoding="utf-8"))
    assert audit[0]["event_type"] == "HISTORICAL_MEDIA_NORMALIZATION"
    assert audit[0]["replacement_width"] == 960
    assert service.dry_run()[0].status == "SKIP"
    assert "already records REPAIRED" in service.dry_run()[0].reason
